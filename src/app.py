"""
🚀 CORE AGENT APP (Dành cho Role 4: Core Agent Developer)
Mốc 2: Ghép Baseline Prompt + Test Cases + Multi-Provider.
"""

import json
import os
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

# Mốc 2 chỉ dùng Prompt + Provider; Baseline tuyệt đối không gọi Tool.
from prompts import CHATBOT_BASELINE_PROMPT
from providers import get_llm_provider

load_dotenv()

# 5 test case đại diện: lý thuyết, 1 tool, 2 tools, 3 tools và edge case.
BASELINE_TEST_IDS = (2, 5, 8, 10, 11)


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


if __name__ == "__main__":
    print("==================================================")
    print("🏫 BÀI LAB 3 - MỐC 2: CHATBOT BASELINE")
    print("==================================================")

    # Khởi tạo Multi-Provider LLM Adapter (Đọc từ biến môi trường LLM_PROVIDER)
    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print(f"🔌 LLM Provider đang hoạt động: {provider.__class__.__name__} (Model: {model_name})")

    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases từ config/test_cases.json\n")

    run_baseline_suite(tests, provider)
