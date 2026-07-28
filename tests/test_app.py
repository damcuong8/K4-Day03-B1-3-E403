"""Kiểm thử offline cho ReAct runtime Mốc 3."""

import contextlib
import io
import os
import sys
import unittest
from unittest import mock

import requests


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
sys.path.insert(0, SRC_DIR)

from app import (  # noqa: E402
    MAX_ITERATIONS,
    build_react_system_prompt,
    execute_tool_safely,
    parse_action,
    run_react_agent,
)
from tools import (  # noqa: E402
    AVAILABLE_TOOLS,
    MOCK_RETURNS,
    RETURN_REQUESTS_LOG,
)
from providers import NvidiaProvider  # noqa: E402


class ScriptedProvider:
    """Provider giả lập trả lần lượt các bước ReAct đã định trước."""

    def __init__(self, outputs):
        self.outputs = iter(outputs)

    def generate(self, prompt, system_prompt=""):
        return next(self.outputs)


class ReactRuntimeTests(unittest.TestCase):
    def setUp(self):
        MOCK_RETURNS.clear()
        RETURN_REQUESTS_LOG.clear()

    def run_silently(self, query, outputs):
        with contextlib.redirect_stdout(io.StringIO()):
            return run_react_agent(query, ScriptedProvider(outputs))

    def test_parse_action_maps_positional_arguments(self):
        tool_name, args = parse_action(
            'Thought: Tra cứu đơn.\n'
            'Action: lookup_order["ORD-002", "0912345678"]'
        )
        self.assertEqual(tool_name, "lookup_order")
        self.assertEqual(
            args,
            {
                "order_id": "ORD-002",
                "phone_number": "0912345678",
            },
        )

    def test_system_prompt_contains_runtime_tool_signatures(self):
        system_prompt = build_react_system_prompt()

        self.assertNotIn("{TOOL_SIGNATURES}", system_prompt)
        self.assertNotIn("{MAX_ITERATIONS}", system_prompt)
        for tool_name in AVAILABLE_TOOLS:
            self.assertIn(f"- {tool_name}", system_prompt)

    def test_full_three_tool_trace(self):
        outputs = [
            (
                "Thought: Cần xác minh đơn hàng.\n"
                'Action: lookup_order["ORD-002", "0912345678"]'
            ),
            (
                "Thought: Cần kiểm tra chính sách.\n"
                'Action: check_return_policy["ORD-002", "ITM-B"]'
            ),
            (
                "Thought: Đơn đủ điều kiện, tạo yêu cầu.\n"
                'Action: create_return_request['
                '"ORD-002", "ITM-B", "Sản phẩm bị hỏng"]'
            ),
            (
                "Thought: Đã tạo yêu cầu thành công.\n"
                "Final Answer: Yêu cầu đổi trả đã được tạo an toàn."
            ),
        ]

        result = self.run_silently("Tạo yêu cầu đổi trả.", outputs)

        self.assertEqual(result["tool_calls"], 3)
        self.assertEqual(result["llm_calls"], 4)
        self.assertIsNone(result["guardrail"])
        self.assertIn("đã được tạo", result["answer"])
        self.assertIn("RET-0058", MOCK_RETURNS)

    def test_duplicate_action_is_blocked(self):
        repeated_action = (
            "Thought: Tra cứu đơn.\n"
            'Action: lookup_order["ORD-002", "0912345678"]'
        )
        result = self.run_silently(
            "Tra cứu đơn.",
            [repeated_action, repeated_action],
        )

        self.assertEqual(result["guardrail"], "DUPLICATE_ACTION")
        self.assertEqual(result["tool_calls"], 1)

    def test_max_iterations_is_enforced(self):
        result = self.run_silently(
            "Yêu cầu không rõ.",
            ["Phản hồi sai định dạng"] * MAX_ITERATIONS,
        )

        self.assertEqual(result["guardrail"], "MAX_ITERATIONS")
        self.assertEqual(result["llm_calls"], MAX_ITERATIONS)
        self.assertEqual(result["tool_calls"], 0)

    def test_invalid_tool_arguments_do_not_crash(self):
        observation = execute_tool_safely(
            "lookup_order",
            {"order_id": "ORD-002"},
        )
        self.assertTrue(observation.startswith("INVALID_TOOL_ARGUMENTS:"))

    @mock.patch("providers.time.sleep")
    @mock.patch("providers.requests.post")
    def test_nvidia_retries_transient_connection_error(
        self,
        mock_post,
        mock_sleep,
    ):
        successful_response = mock.Mock(status_code=200)
        successful_response.json.return_value = {
            "choices": [
                {"message": {"content": "Final Answer: Thành công."}}
            ]
        }
        mock_post.side_effect = [
            requests.RequestException("temporary failure"),
            successful_response,
        ]

        provider = NvidiaProvider(
            api_key="test-key",
            model="google/gemma-4-31b-it",
        )
        response = provider.generate("Xin chào")

        self.assertEqual(response, "Final Answer: Thành công.")
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
