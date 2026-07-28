# 📊 BÁO CÁO GIÁM SÁT & ĐÁNH GIÁ (OBSERVABILITY TRACE LOGS)
*Dành cho Role 5: Observability & Reviewer*

> **Đề tài đã chọn:** Đề tài 5 — **Trợ Lý Tra Cứu Đơn Hàng & Xử Lý Đổi Trả**

---

## 🎯 1. BẢNG CHẤM ĐIỂM AGENTIC FIT (SCORING MATRIX)

| Tiêu chí | Điểm (1-5) | Lý do đánh giá |
| :--- | :---: | :--- |
| 🧠 **Multi-step Reasoning** | `5/5` | Yêu cầu nhiều bước suy luận: tra mã đơn → kiểm tra trạng thái giao hàng → xác minh điều kiện đổi trả (thời hạn, tình trạng sản phẩm) → tạo yêu cầu đổi trả → xác nhận kết quả. Mỗi bước phụ thuộc kết quả bước trước. |
| 🛠️ **Tool Interaction** | `5/5` | Cần gọi nhiều tool thực tế: `lookup_order` (tra cứu đơn hàng), `check_return_policy` (kiểm tra chính sách đổi trả), `create_return_request` (tạo yêu cầu đổi trả), `get_shipping_status` (kiểm tra vận chuyển). Chatbot thuần không thể truy xuất dữ liệu đơn hàng thực. |
| 🔀 **Dynamic Decision** | `5/5` | Rẽ nhánh phong phú: Đơn hàng có tồn tại không? → Đã giao chưa? → Còn trong hạn đổi trả không? → Lý do có hợp lệ không? → Hoàn tiền hay đổi sản phẩm? Mỗi nhánh dẫn đến hành động hoàn toàn khác nhau. |
| ⏳ **Long Horizon** | `4/5` | Quy trình xử lý đổi trả gồm 3-5 bước: xác minh đơn hàng → kiểm tra điều kiện → tạo yêu cầu → xác nhận phương thức hoàn trả. Có thể kéo dài thêm nếu cần hỏi bổ sung thông tin từ khách hàng. |
| **TỔNG ĐIỂM FIT** | **19/20** | **KẾT LUẬN: BÀI TOÁN RẤT PHÙ HỢP ĐỂ DÙNG REACT AGENT!** |

---

## 🔍 2. SO SÁNH PHẢN HỒI (TEST CASE #2)

**Câu hỏi**: *"Tôi muốn đổi trả đơn hàng ORD-002, sản phẩm bị lỗi"*

### 🤖 Chatbot Baseline:
* **Phản hồi**: *"Tôi không có quyền truy cập hệ thống đơn hàng nên không thể kiểm tra đơn ORD-002. Vui lòng liên hệ bộ phận CSKH qua hotline 1900xxxx."*
* **Nhận xét**: An toàn nhưng không giải quyết được nhu cầu thực tế — khách hàng vẫn phải tự liên hệ nơi khác.

### 🧠 ReAct Agent:
* **Thought 1**: Khách muốn đổi trả đơn ORD-002 vì sản phẩm lỗi. Cần tra cứu thông tin đơn hàng trước.
* **Action 1**: `lookup_order['ORD-002']`
* **Observation 1**: `Đơn ORD-002: Tai nghe Bluetooth XYZ, giá 450.000đ, ngày mua 25/07/2026, trạng thái: Đã giao (26/07/2026).`
* **Thought 2**: Đơn đã giao ngày 26/07, hôm nay 28/07 → mới 2 ngày, cần kiểm tra chính sách đổi trả.
* **Action 2**: `check_return_policy['electronics', 2]`
* **Observation 2**: `Danh mục "electronics": cho phép đổi trả trong 7 ngày. Đơn hàng ĐỦ ĐIỀU KIỆN đổi trả.`
* **Thought 3**: Sản phẩm còn trong hạn đổi trả, lý do "sản phẩm lỗi" hợp lệ. Tạo yêu cầu đổi trả.
* **Action 3**: `create_return_request['ORD-002', 'Sản phẩm bị lỗi', 'refund']`
* **Observation 3**: `Yêu cầu đổi trả RET-0058 đã được tạo. Vui lòng gửi sản phẩm về kho trong 5 ngày.`
* **Final Answer**: *"Đơn ORD-002 (Tai nghe Bluetooth XYZ) đủ điều kiện đổi trả! Mã đổi trả của bạn là RET-0058. Vui lòng gửi sản phẩm về kho trong 5 ngày, sau khi nhận được hàng chúng tôi sẽ hoàn tiền 450.000đ cho bạn."*
* **Nhận xét**: Hoàn thành xuất sắc quy trình đổi trả 3 bước nhờ vòng lặp Thought → Action → Observation.
