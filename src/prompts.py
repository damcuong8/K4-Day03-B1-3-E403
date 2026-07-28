"""
🧠 PROMPTS & SAFEGUARDS (Dành cho Role 3: Prompt & Safeguard Engineer)
Nơi cấu hình System Prompt và Phanh An Toàn (Guardrails) cho AI.
"""
"""
====================================================================
FAILURE MODES ANALYSIS — Role 3 (Guardrails)
Đề tài #5: Trợ Lý Tra Cứu Đơn Hàng & Xử Lý Đổi Trả
Tools: lookup_order · check_return_policy · create_return_request ·
       get_shipping_status
====================================================================
"""

# --------------------------------------------------------------
# TOOL 1: lookup_order(order_id, phone_number)
# --------------------------------------------------------------
# FM-1.1  order_id không tồn tại trong hệ thống.
#         -> Observation: "ORDER_NOT_FOUND". Agent hỏi lại khách xác
#            nhận mã đơn, KHÔNG tự bịa thông tin đơn hàng.
# FM-1.2  phone_number không khớp chủ đơn (guardrail bảo mật).
#         -> Observation: "IDENTITY_MISMATCH". Agent bắt buộc từ
#            chối trả thông tin đơn, không được bỏ qua bước xác minh.

# --------------------------------------------------------------
# TOOL 2: check_return_policy(order_id, item_id)
# --------------------------------------------------------------
# FM-2.1  Đã quá hạn đổi trả (vượt X ngày từ ngày giao).
#         -> Observation: "RETURN_WINDOW_EXPIRED". Agent từ chối,
#            KHÔNG tự ý gọi create_return_request().
# FM-2.2  Sản phẩm thuộc danh mục không cho đổi trả (hàng sale, đã
#         bóc seal...).
#         -> Observation: "ITEM_NOT_ELIGIBLE".

# --------------------------------------------------------------
# TOOL 3: create_return_request(order_id, item_id, reason)
# --------------------------------------------------------------
# FM-3.1  Agent gọi tool này TRƯỚC khi gọi check_return_policy()
#         (bỏ bước bắt buộc, chưa xác nhận đủ điều kiện).
#         -> Guardrail: tool tự kiểm tra lại lần cuối, trả về
#            "PRECONDITION_FAILED" nếu chưa qua check — không tin
#            tưởng hoàn toàn rằng Agent đã làm đúng thứ tự.
# FM-3.2  Item đã có yêu cầu đổi trả trước đó (gọi trùng do Agent
#         hiểu nhầm Observation cũ là thất bại).
#         -> Observation: "DUPLICATE_REQUEST_BLOCKED".

# --------------------------------------------------------------
# TOOL 4: get_shipping_status(return_id)
# --------------------------------------------------------------
# FM-4.1  return_id chưa tồn tại (gọi tool này trước khi
#         create_return_request() thành công).
#         -> Observation: "RETURN_ID_NOT_FOUND". Agent phải đảm bảo
#            đã có return_id hợp lệ trước khi tra cứu vận chuyển.
# FM-4.2  Trạng thái vận chuyển bị lỗi/thiếu (đơn vị ship chưa cập
#         nhật) -> Agent KHÔNG tự suy đoán ("chắc đang trên đường"),
#         phải báo "đang chờ cập nhật" đúng với dữ liệu thật.

# --------------------------------------------------------------
# GUARDRAIL VÒNG LẶP (áp dụng chung)
# --------------------------------------------------------------
# FM-LOOP-1  Lặp gọi cùng 1 tool nhiều lần liên tiếp không tiến triển.
#            -> max_iterations = 5-6, vượt quá thì dừng và chuyển
#               nhân viên hỗ trợ.
# FM-LOOP-2  Agent "ảo giác" tự bịa dữ liệu khi Observation rỗng/lỗi.
#            -> Prompt cấm rõ: không tự suy đoán dữ liệu nếu Tool
#               không trả về.

# Baseline Chatbot Prompt (Chỉ dùng LLM thông thường, không có Tool)
CHATBOT_BASELINE_PROMPT = """
Bạn là trợ lý chăm sóc khách hàng của một sàn thương mại điện tử,
hỗ trợ khách hàng về tra cứu đơn hàng và xử lý đổi trả.

Bạn chỉ được trả lời dựa trên kiến thức và ngữ cảnh cuộc trò chuyện.
Bạn KHÔNG có quyền truy cập vào bất kỳ hệ thống, cơ sở dữ liệu, hay
công cụ tra cứu thực tế nào. Bạn không biết thông tin đơn hàng cụ thể
của bất kỳ khách hàng nào.

Khi khách hàng hỏi về:
- Tình trạng đơn hàng cụ thể (mã đơn, ngày giao, sản phẩm...)
- Đơn hàng có đủ điều kiện đổi trả hay không
- Trạng thái vận chuyển của một đơn hàng
- Yêu cầu tạo/xử lý đổi trả cho một đơn hàng thật

Bạn hãy trả lời tự nhiên theo hiểu biết chung của mình, dùng giọng
điệu thân thiện, chuyên nghiệp như một tổng đài viên thực thụ.
Hãy cố gắng giúp đỡ khách hàng hết mức có thể trong khả năng của bạn.
"""

# ReAct Agent Prompt (Ép LLM suy luận theo chuỗi Thought -> Action)
REACT_SYSTEM_PROMPT = """
"""

# 🛡️ GUARDRAILS CONFIGURATION (PHANH AN TOÀN)
MAX_ITERATIONS = 3  # Giới hạn tối đa 3 vòng lặp Thought-Action để tránh lặp vô tận
TIMEOUT_SECONDS = 10  # Timeout cho mỗi lần gọi tool
