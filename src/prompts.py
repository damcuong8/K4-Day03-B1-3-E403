"""
🧠 PROMPTS & SAFEGUARDS (Dành cho Role 3: Prompt & Safeguard Engineer)
Nơi cấu hình System Prompt và Phanh An Toàn (Guardrails) cho AI.
"""
"""
====================================================================
FAILURE MODES ANALYSIS — Role 3 (Guardrails)
Đề tài #5: Trợ Lý Tra Cứu Đơn Hàng & Xử Lý Đổi Trả
====================================================================

Mục đích: liệt kê các cách mỗi Tool có thể "gãy" trong thực tế, để
Agent biết cách nhận diện lỗi qua Observation và phản ứng đúng,
thay vì tự suy diễn (hallucinate) hoặc lặp vô hạn.
"""

# --------------------------------------------------------------
# TOOL 1: get_order(order_id, phone_number)
# --------------------------------------------------------------
# FM-1.1  Order ID không tồn tại trong hệ thống.
#         -> Observation: "ORDER_NOT_FOUND". Agent phải hỏi lại
#            khách xác nhận mã đơn, KHÔNG được tự bịa thông tin đơn.
# FM-1.2  Order ID đúng nhưng phone_number không khớp chủ đơn.
#         -> Observation: "IDENTITY_MISMATCH". Đây là guardrail bảo
#            mật — Agent buộc phải từ chối trả thông tin đơn, không
#            được "linh động" bỏ qua bước xác minh.
# FM-1.3  order_id sai định dạng (rỗng, chứa ký tự lạ, thiếu tham số).
#         -> Observation: "INVALID_INPUT". Agent hỏi lại thay vì gọi
#            tool nhiều lần với tham số rác.
# FM-1.4  Hệ thống backend timeout / lỗi giả lập 500.
#         -> Observation: "SYSTEM_ERROR". Agent thử lại tối đa 1 lần,
#            sau đó báo khách "hệ thống đang lỗi" thay vì lặp vô hạn.

# --------------------------------------------------------------
# TOOL 2: check_return_eligibility(order_id, item_id)
# --------------------------------------------------------------
# FM-2.1  Sản phẩm đã quá hạn đổi trả (vượt X ngày kể từ ngày giao).
#         -> Observation: "RETURN_WINDOW_EXPIRED". Agent từ chối và
#            gợi ý phương án khác (bảo hành, liên hệ CSKH), KHÔNG
#            tự ý gọi process_return().
# FM-2.2  item_id không thuộc order_id đã tra cứu (chọn nhầm món).
#         -> Observation: "ITEM_NOT_IN_ORDER". Agent phải đối chiếu
#            lại danh sách item hợp lệ trước khi hỏi tiếp.
# FM-2.3  Sản phẩm thuộc danh mục không được đổi trả (vd: hàng sale,
#         đồ dùng cá nhân đã bóc seal).
#         -> Observation: "ITEM_NOT_ELIGIBLE_CATEGORY".
# FM-2.4  item_id đã có yêu cầu đổi trả trước đó (duplicate request).
#         -> Observation: "RETURN_ALREADY_REQUESTED". Agent báo lại
#            trạng thái yêu cầu cũ, không tạo yêu cầu mới.
# FM-2.5  Đơn hàng chưa ở trạng thái "delivered" (chưa nhận hàng).
#         -> Observation: "ORDER_NOT_DELIVERED_YET".

# --------------------------------------------------------------
# TOOL 3: process_return(order_id, item_id, reason)
# --------------------------------------------------------------
# FM-3.1  Agent gọi process_return() TRƯỚC khi gọi
#         check_return_eligibility() (bỏ bước bắt buộc).
#         -> Guardrail: process_return phải tự kiểm tra lại điều
#            kiện lần cuối và trả "PRECONDITION_FAILED" nếu chưa
#            qua bước check — không tin tưởng hoàn toàn vào việc
#            Agent đã làm đúng trình tự.
# FM-3.2  Gọi process_return() 2 lần cho cùng 1 item (do agent lặp
#         bước vì hiểu nhầm Observation trước đó thất bại).
#         -> Observation: "DUPLICATE_ACTION_BLOCKED" (tool không
#            idempotent nên phải tự chặn, không dựa vào Agent nhớ).
# FM-3.3  reason rỗng hoặc không thuộc danh sách lý do hợp lệ.
#         -> Observation: "INVALID_REASON".
# FM-3.4  Case mơ hồ cần con người xử lý (sản phẩm vỡ/lỗi, tranh
#         chấp trách nhiệm vận chuyển).
#         -> Guardrail QUAN TRỌNG NHẤT: Agent KHÔNG được tự quyết
#            hoàn tiền/đổi trả trong case này. Phải trả lời dạng
#            "ESCALATE_TO_HUMAN" + tạo ticket, không hoàn tất tool.

# --------------------------------------------------------------
# FAILURE MODES CẤP ĐỘ VÒNG LẶP REACT (áp dụng chung mọi tool)
# --------------------------------------------------------------
# FM-LOOP-1  Agent gọi lại đúng 1 tool với đúng tham số nhiều lần
#            liên tiếp (infinite loop do không hiểu Observation lỗi).
#            -> Guardrail: max_iterations = 5-6, quá số này thì dừng
#               và trả lời "Xin lỗi, mình chưa xử lý được yêu cầu này,
#               để mình chuyển cho nhân viên hỗ trợ."
# FM-LOOP-2  Agent "ảo giác" tự bịa dữ liệu đơn hàng/kết quả tool khi
#            Observation trả về rỗng hoặc lỗi, thay vì báo lỗi thật.
#            -> Guardrail: prompt cấm rõ "KHÔNG được tự suy đoán dữ
#               liệu đơn hàng nếu Tool không trả về dữ liệu đó."
# FM-LOOP-3  Agent bỏ qua bước Observation, hành động dựa trên Thought
#            trước khi Tool thực sự trả kết quả (race condition trong
#            thiết kế loop, không phải lỗi nghiệp vụ).

# Baseline Chatbot Prompt (Chỉ dùng LLM thông thường, không có Tool)
CHATBOT_BASELINE_PROMPT = """"""

# ReAct Agent Prompt (Ép LLM suy luận theo chuỗi Thought -> Action)
REACT_SYSTEM_PROMPT = """
"""

# 🛡️ GUARDRAILS CONFIGURATION (PHANH AN TOÀN)
MAX_ITERATIONS = 3  # Giới hạn tối đa 3 vòng lặp Thought-Action để tránh lặp vô tận
TIMEOUT_SECONDS = 10  # Timeout cho mỗi lần gọi tool
