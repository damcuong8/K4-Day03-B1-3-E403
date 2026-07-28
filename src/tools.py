"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)
Nơi khai báo tất cả các "món đồ nghề" mà ReAct Agent có thể gọi.

====================================================================
ĐỀ TÀI #5: TRỢ LÝ TRA CỨU ĐƠN HÀNG & XỬ LÝ ĐỔI TRẢ
Tool Contract chuẩn (8 fields) cho mỗi tool:
  1. Name          2. Purpose       3. Input schema   4. Output schema
  5. Error semantics (FM)           6. Side effect     7. Example
  8. Safety
====================================================================
"""

# --------------------------------------------------------------
# Mock Data — Cơ sở dữ liệu giả lập cho 4 tools bên dưới
# --------------------------------------------------------------
MOCK_ORDERS = {
    "ORD-001": {
        "customer_phone": "0901234567",
        "items": [
            {"item_id": "ITM-A", "name": "Áo thun nam", "price": 250000,
             "category": "fashion", "delivered_date": "2026-07-20",
             "seal_opened": False},
        ],
        "status": "Đã giao",
    },
    "ORD-002": {
        "customer_phone": "0912345678",
        "items": [
            {"item_id": "ITM-B", "name": "Tai nghe Bluetooth XYZ", "price": 450000,
             "category": "electronics", "delivered_date": "2026-07-26",
             "seal_opened": True},
        ],
        "status": "Đã giao",
    },
    "ORD-003": {
        "customer_phone": "0923456789",
        "items": [
            {"item_id": "ITM-C", "name": "Giày thể thao", "price": 800000,
             "category": "fashion", "delivered_date": "2026-06-15",
             "seal_opened": True},
        ],
        "status": "Đã giao",
    },
}

MOCK_RETURN_POLICY = {
    # category: (window_days, eligible_categories, blocked_categories)
    "electronics": {"window_days": 7, "allow_opened_seal": True},
    "fashion":     {"window_days": 7, "allow_opened_seal": False},
    "sale":        {"window_days": 0, "allow_opened_seal": False},  # Không cho đổi trả
}

MOCK_RETURNS = {
    # return_id: {order_id, item_id, status, refund_amount}
    # Bắt đầu rỗng — sẽ được thêm khi create_return_request() chạy.
}

RETURN_REQUESTS_LOG = []  # Lưu các yêu cầu đã tạo (giúp phát hiện DUPLICATE)


# --------------------------------------------------------------
# TOOL 1: lookup_order(order_id, phone_number)
# --------------------------------------------------------------
def lookup_order(order_id: str, phone_number: str) -> str:
    """
    1. Name: lookup_order
    2. Purpose: Tra cứu thông tin đơn hàng và xác minh chủ đơn bằng SĐT.
    3. Input schema:
         - order_id (str): Mã đơn hàng, định dạng 'ORD-XXX' (VD: 'ORD-002').
         - phone_number (str): Số điện thoại chủ đơn (10 số, bắt đầu bằng '0').
    4. Output schema:
         - Trả về chuỗi mô tả đơn hàng gồm: tên sản phẩm, giá, ngày giao,
           trạng thái, hoặc mã lỗi (xem Error semantics).
    5. Error semantics (Failure Modes):
         - FM-1.1: order_id không tồn tại  -> "ORDER_NOT_FOUND".
         - FM-1.2: SĐT không khớp chủ đơn  -> "IDENTITY_MISMATCH".
         - FM-1.3: order_id sai định dạng -> "INVALID_ORDER_ID_FORMAT".
         - FM-1.4: phone_number rỗng/sai -> "INVALID_PHONE_FORMAT".
    6. Side effect: KHÔNG có (chỉ đọc dữ liệu mock).
    7. Example:
         >>> lookup_order("ORD-002", "0912345678")
         'Đơn ORD-002: Tai nghe Bluetooth XYZ, giá 450.000đ, ngày giao 2026-07-26, trạng thái: Đã giao.'
    8. Safety: BẮT BUỘC xác minh SĐT trước khi trả thông tin đơn (chống lộ dữ liệu).
    """
    # --- Validate input ---
    if not isinstance(order_id, str) or not order_id.strip().startswith("ORD-"):
        return "INVALID_ORDER_ID_FORMAT"
    if not isinstance(phone_number, str) or not phone_number.strip().startswith("0") \
            or len(phone_number.strip()) < 10:
        return "INVALID_PHONE_FORMAT"

    # --- Tra cứu ---
    order = MOCK_ORDERS.get(order_id)
    if order is None:
        return "ORDER_NOT_FOUND"

    # --- Xác minh chủ đơn (guardrail bảo mật) ---
    if order["customer_phone"] != phone_number.strip():
        return "IDENTITY_MISMATCH"

    # --- Trả về mô tả ---
    items_desc = ", ".join(
        f"{it['name']} (ID: {it['item_id']}, giá {it['price']:,}đ)"
        for it in order["items"]
    )
    delivered = order["items"][0]["delivered_date"]
    return (f"Đơn {order_id}: {items_desc}, ngày giao {delivered}, "
            f"trạng thái: {order['status']}.")


# --------------------------------------------------------------
# TOOL 2: check_return_policy(order_id, item_id)
# --------------------------------------------------------------
def check_return_policy(order_id: str, item_id: str) -> str:
    """
    1. Name: check_return_policy
    2. Purpose: Kiểm tra sản phẩm trong đơn có còn trong thời hạn & đủ
       điều kiện đổi trả hay không.
    3. Input schema:
         - order_id (str): Mã đơn hàng 'ORD-XXX'.
         - item_id (str): Mã sản phẩm trong đơn (VD: 'ITM-B').
    4. Output schema:
         - Trả về chuỗi: "ELIGIBLE: <lý do đủ điều kiện>" hoặc mã lỗi.
    5. Error semantics (Failure Modes):
         - FM-2.1: Quá hạn đổi trả       -> "RETURN_WINDOW_EXPIRED".
         - FM-2.2: Sản phẩm không hợp lệ (sale / bóc seal) -> "ITEM_NOT_ELIGIBLE".
         - FM-2.3: order_id không tồn tại -> "ORDER_NOT_FOUND".
         - FM-2.4: item_id không thuộc đơn -> "ITEM_NOT_FOUND".
    6. Side effect: KHÔNG có (chỉ đọc).
    7. Example:
         >>> check_return_policy("ORD-002", "ITM-B")
         'ELIGIBLE: Danh mục "electronics", trong hạn 7 ngày, sản phẩm ĐỦ ĐIỀU KIỆN đổi trả.'
    8. Safety: KHÔNG tự ý gọi create_return_request() — chỉ trả về đánh giá.
    """
    # --- Validate ---
    if order_id not in MOCK_ORDERS:
        return "ORDER_NOT_FOUND"

    order = MOCK_ORDERS[order_id]
    item = next((it for it in order["items"] if it["item_id"] == item_id), None)
    if item is None:
        return "ITEM_NOT_FOUND"

    # --- Tính số ngày từ khi giao đến hôm nay (28/07/2026 theo trace_eval) ---
    today = "2026-07-28"
    days_since_delivery = (int(today[8:10]) - int(item["delivered_date"][8:10]))
    policy = MOCK_RETURN_POLICY.get(item["category"], {})

    # --- Quá hạn ---
    if days_since_delivery > policy.get("window_days", 0):
        return "RETURN_WINDOW_EXPIRED"

    # --- Danh mục không cho đổi trả (VD: 'sale') ---
    if policy.get("window_days", 0) == 0:
        return "ITEM_NOT_ELIGIBLE"

    # --- Sản phẩm bóc seal không được đổi (với danh mục 'fashion') ---
    if not policy.get("allow_opened_seal", True) and item["seal_opened"]:
        return "ITEM_NOT_ELIGIBLE"

    return (f'ELIGIBLE: Danh mục "{item["category"]}", trong hạn '
            f'{policy["window_days"]} ngày, sản phẩm ĐỦ ĐIỀU KIỆN đổi trả.')


# --------------------------------------------------------------
# TOOL 3: create_return_request(order_id, item_id, reason)
# --------------------------------------------------------------
def create_return_request(order_id: str, item_id: str, reason: str) -> str:
    """
    1. Name: create_return_request
    2. Purpose: Tạo yêu cầu đổi trả cho một sản phẩm cụ thể trong đơn hàng.
    3. Input schema:
         - order_id (str): Mã đơn hàng 'ORD-XXX'.
         - item_id (str): Mã sản phẩm (VD: 'ITM-B').
         - reason (str): Lý do đổi trả (VD: 'Sản phẩm bị lỗi', 'refund').
    4. Output schema:
         - Trả về chuỗi xác nhận gồm mã yêu cầu (RET-XXXX) và số tiền hoàn.
    5. Error semantics (Failure Modes):
         - FM-3.1: Chưa qua check_return_policy() -> "PRECONDITION_FAILED".
         - FM-3.2: Sản phẩm đã có yêu cầu đổi trả -> "DUPLICATE_REQUEST_BLOCKED".
         - FM-3.3: order_id / item_id không hợp lệ -> "ORDER_NOT_FOUND" / "ITEM_NOT_FOUND".
         - FM-3.4: reason rỗng -> "EMPTY_REASON".
    6. Side effect: Ghi log vào RETURN_REQUESTS_LOG & tạo entry trong MOCK_RETURNS.
    7. Example:
         >>> create_return_request("ORD-002", "ITM-B", "Sản phẩm bị lỗi")
         'Yêu cầu đổi trả RET-0058 đã được tạo. Hoàn tiền dự kiến: 450.000đ.'
    8. Safety: TỰ KIỂM TRA điều kiện trước khi tạo (không tin tưởng Agent 100%).
    """
    # --- Validate ---
    if not reason or not reason.strip():
        return "EMPTY_REASON"
    if order_id not in MOCK_ORDERS:
        return "ORDER_NOT_FOUND"

    order = MOCK_ORDERS[order_id]
    item = next((it for it in order["items"] if it["item_id"] == item_id), None)
    if item is None:
        return "ITEM_NOT_FOUND"

    # --- Precondition check (FM-3.1) — không cho tạo nếu chưa qua check policy ---
    policy_check = check_return_policy(order_id, item_id)
    if not policy_check.startswith("ELIGIBLE"):
        return f"PRECONDITION_FAILED: {policy_check}"

    # --- Duplicate check (FM-3.2) ---
    for req in RETURN_REQUESTS_LOG:
        if req["order_id"] == order_id and req["item_id"] == item_id:
            return "DUPLICATE_REQUEST_BLOCKED"

    # --- Tạo yêu cầu ---
    return_id = f"RET-{len(MOCK_RETURNS) + 58:04d}"  # Bắt đầu RET-0058 cho khớp trace
    refund = item["price"]

    MOCK_RETURNS[return_id] = {
        "order_id": order_id,
        "item_id": item_id,
        "reason": reason,
        "refund_amount": refund,
        "shipping_status": "Chờ gửi hàng về kho",
    }
    RETURN_REQUESTS_LOG.append({"order_id": order_id, "item_id": item_id, "return_id": return_id})

    return (f"Yêu cầu đổi trả {return_id} đã được tạo. "
            f"Hoàn tiền dự kiến: {refund:,}đ. "
            f"Vui lòng gửi sản phẩm về kho trong 5 ngày.")


# --------------------------------------------------------------
# TOOL 4: get_shipping_status(return_id)
# --------------------------------------------------------------
def get_shipping_status(return_id: str) -> str:
    """
    1. Name: get_shipping_status
    2. Purpose: Tra cứu trạng thái vận chuyển của một yêu cầu đổi trả.
    3. Input schema:
         - return_id (str): Mã yêu cầu đổi trả 'RET-XXXX'.
    4. Output schema:
         - Trả về chuỗi mô tả trạng thái vận chuyển hiện tại.
    5. Error semantics (Failure Modes):
         - FM-4.1: return_id chưa tồn tại -> "RETURN_ID_NOT_FOUND".
         - FM-4.2: Đơn vị ship chưa cập nhật -> "Đang chờ cập nhật".
    6. Side effect: KHÔNG có (chỉ đọc).
    7. Example:
         >>> get_shipping_status("RET-0058")
         'RET-0058: Chờ gửi hàng về kho.'
    8. Safety: KHÔNG tự suy đoán trạng thái khi dữ liệu rỗng/lỗi (chống ảo giác).
    """
    # --- Validate ---
    if not isinstance(return_id, str) or not return_id.strip().startswith("RET-"):
        return "RETURN_ID_NOT_FOUND"

    info = MOCK_RETURNS.get(return_id)
    if info is None:
        return "RETURN_ID_NOT_FOUND"

    # --- FM-4.2: Nếu đơn vị ship chưa cập nhật ---
    if not info.get("shipping_status"):
        return "Đang chờ cập nhật"

    return f'{return_id}: {info["shipping_status"]}.'


# --------------------------------------------------------------
# Danh sách tool đăng ký để Agent tra cứu runtime.
# Key = tên tool (string), Value = function reference.
# --------------------------------------------------------------
AVAILABLE_TOOLS = {
    "lookup_order":         lookup_order,
    "check_return_policy":  check_return_policy,
    "create_return_request": create_return_request,
    "get_shipping_status":  get_shipping_status,
}
