"""
🚀 CORE AGENT APP (Dành cho Role 4: Core Agent Developer)
Mốc 3: Ghép Baseline + ReAct Agent Loop + Tools + Guardrails.
"""

import argparse
import ast
import concurrent.futures
import inspect
import json
import os
import re
import sys
from dotenv import load_dotenv

# Đảm bảo import các module cùng thư mục src/ hoạt động mượt mà
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Import các thành phần của Role 2, Role 3 và Multi-Provider Adapter.
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    MAX_ITERATIONS,
    REACT_SYSTEM_PROMPT,
    TIMEOUT_SECONDS,
)
from providers import get_llm_provider
from tools import AVAILABLE_TOOLS

load_dotenv()

# 5 test case đại diện: lý thuyết, 1 tool, 2 tools, 3 tools và edge case.
BASELINE_TEST_IDS = (2, 5, 8, 10, 11)

# Câu demo có đủ dữ liệu xác minh để Agent chạy trọn chuỗi 3 tools.
DEFAULT_REACT_QUERY = (
    "Tôi muốn hoàn tiền đơn ORD-002 cho sản phẩm ITM-B vì tai nghe "
    "bị hỏng. Số điện thoại xác minh của tôi là 0912345678. "
    "Hãy kiểm tra điều kiện và tạo yêu cầu đổi trả."
)

SAFE_FALLBACK = (
    "Xin lỗi, mình chưa xử lý được yêu cầu này một cách an toàn. "
    "Mình sẽ chuyển yêu cầu cho nhân viên hỗ trợ."
)

def load_test_cases():
    """Đọc bộ test cases từ config/test_cases.json của Role 1"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")

    with open(config_path, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    if not isinstance(test_cases, list):
        raise ValueError("config/test_cases.json phải chứa một JSON array.")

    for test_case in test_cases:
        if not isinstance(test_case, dict) or "id" not in test_case or "question" not in test_case:
            raise ValueError("Mỗi test case phải có ít nhất hai trường 'id' và 'question'.")

    return test_cases


def run_baseline_chatbot(user_query: str, provider):
    """
    Gọi Chatbot Baseline đúng một lần và không sử dụng bất kỳ Tool nào.
    """
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    return response


def build_react_system_prompt():
    """Điền cấu hình và chữ ký Tool thật từ registry vào System Prompt."""
    tool_signatures = "\n".join(
        f"- {tool_name}{inspect.signature(tool)}"
        for tool_name, tool in AVAILABLE_TOOLS.items()
    )
    prompt = REACT_SYSTEM_PROMPT.replace(
        "{MAX_ITERATIONS}",
        str(MAX_ITERATIONS),
    )
    return prompt.replace("{TOOL_SIGNATURES}", tool_signatures)


def extract_final_answer(model_output: str):
    """Lấy Final Answer nếu model đã kết thúc nhiệm vụ."""
    match = re.search(
        r"(?is)^\s*Final\s+Answer\s*:\s*(.+?)\s*$",
        model_output,
        re.MULTILINE,
    )
    if not match:
        return None
    return match.group(1).strip()


def parse_action(model_output: str):
    """
    Parse Action an toàn, không dùng eval.

    Hỗ trợ:
      Action: lookup_order["ORD-002", "0912345678"]
      Action: lookup_order("ORD-002", "0912345678")
      Action: {"tool": "lookup_order", "args": {"order_id": "..."}}
    """
    action_match = re.search(
        r"(?im)^\s*Action\s*:\s*(.+?)\s*$",
        model_output,
    )
    if not action_match:
        return None

    action_text = action_match.group(1).strip()

    if action_text.startswith("{"):
        try:
            action_data = json.loads(action_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Action JSON không hợp lệ: {exc.msg}") from exc

        tool_name = action_data.get("tool")
        tool_args = action_data.get("args", {})
        if not isinstance(tool_name, str) or not isinstance(tool_args, dict):
            raise ValueError("Action JSON phải có 'tool' dạng chuỗi và 'args' dạng object.")
        return tool_name, tool_args

    function_match = re.fullmatch(
        r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[(.*)\]|\((.*)\))",
        action_text,
    )
    if not function_match:
        raise ValueError(
            "Action phải có dạng tool_name[\"arg1\", \"arg2\"]."
        )

    tool_name = function_match.group(1)
    raw_args = (
        function_match.group(2)
        if function_match.group(2) is not None
        else function_match.group(3)
    )

    try:
        positional_args = ast.literal_eval(f"[{raw_args}]")
    except (SyntaxError, ValueError) as exc:
        raise ValueError("Các tham số Action phải là chuỗi có dấu nháy.") from exc

    if not isinstance(positional_args, list):
        raise ValueError("Danh sách tham số Action không hợp lệ.")

    tool = AVAILABLE_TOOLS.get(tool_name)
    if tool is None:
        return tool_name, {"_positional": positional_args}

    parameter_names = list(inspect.signature(tool).parameters)
    if len(positional_args) != len(parameter_names):
        raise ValueError(
            f"Tool '{tool_name}' cần {len(parameter_names)} tham số, "
            f"nhưng Agent gửi {len(positional_args)}."
        )

    return tool_name, dict(zip(parameter_names, positional_args))


def execute_tool_safely(tool_name: str, tool_args: dict):
    """Validate và chạy một tool với timeout; luôn trả về Observation dạng chuỗi."""
    tool = AVAILABLE_TOOLS.get(tool_name)
    if tool is None:
        return f"UNKNOWN_TOOL: '{tool_name}' không nằm trong AVAILABLE_TOOLS."

    if "_positional" in tool_args:
        return f"UNKNOWN_TOOL: Không thể ánh xạ tham số cho '{tool_name}'."

    try:
        signature = inspect.signature(tool)
        bound_args = signature.bind(**tool_args)
    except TypeError as exc:
        return f"INVALID_TOOL_ARGUMENTS: {str(exc)}"

    for parameter_name, value in bound_args.arguments.items():
        annotation = signature.parameters[parameter_name].annotation
        if annotation is str and not isinstance(value, str):
            return (
                "INVALID_TOOL_ARGUMENTS: "
                f"'{parameter_name}' phải là chuỗi."
            )

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(tool, **bound_args.arguments)
    try:
        result = future.result(timeout=TIMEOUT_SECONDS)
        return str(result)
    except concurrent.futures.TimeoutError:
        future.cancel()
        return f"TOOL_TIMEOUT: Tool vượt quá {TIMEOUT_SECONDS} giây."
    except Exception as exc:
        return f"TOOL_ERROR: {type(exc).__name__}: {str(exc)}"
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def run_react_agent(user_query: str, provider):
    """
    Chạy vòng lặp ReAct và trả về answer, trace, số lần gọi LLM/tool.
    """
    system_prompt = build_react_system_prompt()
    scratchpad = f"Yêu cầu ban đầu của khách hàng:\n{user_query}\n"
    trace = []
    seen_actions = set()
    llm_calls = 0
    tool_calls = 0

    print("\n" + "=" * 70)
    print("🧠 REACT AGENT")
    print(f"👤 Câu hỏi: {user_query}")

    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- Vòng {iteration}/{MAX_ITERATIONS} ---")
        turn_prompt = (
            f"{scratchpad}\n"
            "Hãy đưa ra đúng MỘT bước tiếp theo theo định dạng bắt buộc."
        )

        try:
            model_output = provider.generate(
                turn_prompt,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            answer = f"{SAFE_FALLBACK} Lỗi provider: {type(exc).__name__}."
            print(f"🛡️ {answer}")
            return {
                "answer": answer,
                "trace": trace,
                "llm_calls": llm_calls,
                "tool_calls": tool_calls,
                "guardrail": "PROVIDER_EXCEPTION",
            }

        llm_calls += 1
        model_output = str(model_output).strip()
        print(model_output)

        if re.match(
            r"^\[[^\]]*(?:Error|Exception)[^\]]*\]",
            model_output,
            re.IGNORECASE,
        ):
            answer = f"{SAFE_FALLBACK} Provider trả về lỗi."
            print(f"🛡️ Final Answer: {answer}")
            return {
                "answer": answer,
                "trace": trace,
                "llm_calls": llm_calls,
                "tool_calls": tool_calls,
                "guardrail": "PROVIDER_ERROR",
            }

        try:
            action = parse_action(model_output)
        except ValueError as exc:
            observation = f"FORMAT_ERROR: {str(exc)}"
            print(f"👁️ Observation: {observation}")
            trace.append({
                "iteration": iteration,
                "model_output": model_output,
                "observation": observation,
            })
            scratchpad += (
                f"\nAgent lượt {iteration}:\n{model_output}\n"
                f"Observation: {observation}\n"
            )
            continue

        # Nếu model vừa sinh Action vừa sinh Final Answer, runtime ưu tiên Action
        # để không cho phép tuyên bố kết quả trước khi có Observation thật.
        if action is not None:
            tool_name, tool_args = action
            action_key = (
                tool_name,
                json.dumps(tool_args, ensure_ascii=False, sort_keys=True),
            )
            print(
                "🛠️ Action đã parse: "
                f"{tool_name}({json.dumps(tool_args, ensure_ascii=False)})"
            )

            if action_key in seen_actions:
                answer = (
                    f"{SAFE_FALLBACK} Guardrail đã chặn việc gọi lặp "
                    f"tool '{tool_name}' với cùng tham số."
                )
                print(f"🛡️ Final Answer: {answer}")
                return {
                    "answer": answer,
                    "trace": trace,
                    "llm_calls": llm_calls,
                    "tool_calls": tool_calls,
                    "guardrail": "DUPLICATE_ACTION",
                }

            seen_actions.add(action_key)
            observation = execute_tool_safely(tool_name, tool_args)
            tool_calls += 1
            print(f"👁️ Observation: {observation}")

            trace.append({
                "iteration": iteration,
                "thought_action": model_output,
                "tool": tool_name,
                "args": tool_args,
                "observation": observation,
            })
            scratchpad += (
                f"\nAgent lượt {iteration}:\n{model_output}\n"
                f"Observation: {observation}\n"
            )
            continue

        final_answer = extract_final_answer(model_output)
        if final_answer:
            print(f"🏁 Final Answer: {final_answer}")
            trace.append({
                "iteration": iteration,
                "model_output": model_output,
                "final_answer": final_answer,
            })
            return {
                "answer": final_answer,
                "trace": trace,
                "llm_calls": llm_calls,
                "tool_calls": tool_calls,
                "guardrail": None,
            }

        observation = (
            "FORMAT_ERROR: Phải trả về Action hoặc Final Answer đúng định dạng."
        )
        print(f"👁️ Observation: {observation}")
        trace.append({
            "iteration": iteration,
            "model_output": model_output,
            "observation": observation,
        })
        scratchpad += (
            f"\nAgent lượt {iteration}:\n{model_output}\n"
            f"Observation: {observation}\n"
        )

    answer = (
        f"{SAFE_FALLBACK} Đã đạt giới hạn {MAX_ITERATIONS} vòng xử lý."
    )
    print(f"\n🛡️ MAX_ITERATIONS TRIGGERED")
    print(f"🏁 Final Answer: {answer}")
    return {
        "answer": answer,
        "trace": trace,
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
        "guardrail": "MAX_ITERATIONS",
    }


def select_baseline_test_cases(test_cases):
    """Chọn đúng 5 test case đại diện theo ID đã thống nhất."""
    test_cases_by_id = {test_case["id"]: test_case for test_case in test_cases}
    missing_ids = [
        test_id for test_id in BASELINE_TEST_IDS
        if test_id not in test_cases_by_id
    ]
    if missing_ids:
        raise ValueError(
            f"Không tìm thấy test case ID: {missing_ids} trong config/test_cases.json."
        )

    return [test_cases_by_id[test_id] for test_id in BASELINE_TEST_IDS]


def run_baseline_suite(test_cases, provider):
    """Chạy 5 test case để Role 5 ghi nhận và phân loại phản hồi."""
    selected_tests = select_baseline_test_cases(test_cases)
    results = []

    for index, test_case in enumerate(selected_tests, start=1):
        print("\n" + "=" * 70)
        print(
            f"TEST {index}/{len(selected_tests)}"
            f" | ID {test_case['id']}"
            f" | {test_case.get('category', 'Chưa phân loại')}"
        )
        print(f"👤 Câu hỏi: {test_case['question']}")

        response = run_baseline_chatbot(test_case["question"], provider)
        print(f"🤖 Baseline trả lời:\n{response}")

        results.append({
            "id": test_case["id"],
            "question": test_case["question"],
            "response": response,
        })

    print("\n" + "=" * 70)
    print(
        f"✅ Đã chạy {len(results)} test case"
        f" | LLM calls: {len(results)}"
        " | Tool calls: 0"
    )
    return results


def find_test_case(test_cases, test_id: int):
    """Tìm test case theo ID hoặc báo lỗi rõ ràng."""
    for test_case in test_cases:
        if test_case["id"] == test_id:
            return test_case
    raise ValueError(f"Không tìm thấy test case ID {test_id}.")


def parse_cli_args():
    parser = argparse.ArgumentParser(
        description="Chạy Chatbot Baseline hoặc ReAct Agent."
    )
    parser.add_argument(
        "--mode",
        choices=("baseline", "react", "both"),
        default="react",
        help="Mặc định: react.",
    )
    parser.add_argument(
        "--test-id",
        type=int,
        help="Chạy câu hỏi từ config/test_cases.json theo ID.",
    )
    parser.add_argument(
        "--query",
        help="Câu hỏi tùy chỉnh; được ưu tiên hơn --test-id.",
    )
    return parser.parse_args()


def main():
    args = parse_cli_args()

    print("==================================================")
    print("🏫 BÀI LAB 3 - MỐC 3: REACT AGENT & SAFEGUARDS")
    print("==================================================")

    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print(f"🔌 LLM Provider đang hoạt động: {provider.__class__.__name__} (Model: {model_name})")

    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases từ config/test_cases.json\n")

    # Giữ nguyên hành vi Mốc 2: không chỉ định query/test thì chạy bộ 5 case.
    if args.mode == "baseline" and not args.query and args.test_id is None:
        run_baseline_suite(tests, provider)
        return

    if args.query:
        user_query = args.query
    elif args.test_id is not None:
        user_query = find_test_case(tests, args.test_id)["question"]
    else:
        user_query = DEFAULT_REACT_QUERY

    if args.mode in ("baseline", "both"):
        print("\n" + "=" * 70)
        print("💬 CHATBOT BASELINE")
        print(f"👤 Câu hỏi: {user_query}")
        baseline_response = run_baseline_chatbot(user_query, provider)
        print(f"🤖 Baseline trả lời:\n{baseline_response}")

    if args.mode in ("react", "both"):
        result = run_react_agent(user_query, provider)
        print("\n" + "=" * 70)
        print(
            f"📊 Tổng kết | LLM calls: {result['llm_calls']}"
            f" | Tool calls: {result['tool_calls']}"
            f" | Guardrail: {result['guardrail'] or 'Không kích hoạt'}"
        )


if __name__ == "__main__":
    main()
