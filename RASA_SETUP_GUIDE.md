# 🤖 Hướng dẫn Tích hợp & Vận hành Rasa Chatbot

Hướng dẫn này chi tiết cách cài đặt, cấu hình và chạy Rasa Chatbot trong dự án Python/Next.js.

## 1. Yêu cầu Hệ thống (Quan trọng ⚠️)
Rasa rất kén phiên bản Python. Bạn **BẮT BUỘC** phải tuân thủ:

*   **Python Version**: `3.7`, `3.8`, `3.9`, hoặc **`3.10`** (Khuyên dùng **3.10**).
*   **KHÔNG HỖ TRỢ**: Python 3.11, 3.12 (sẽ lỗi cài đặt `absl-py` hoặc `tensorflow`).
*   **Hệ điều hành**: Windows, macOS, Linux (Windows cần cài thêm `C++ Build Tools` nếu gặp lỗi biên dịch).

---

## 2. Cài đặt Môi trường (Làm một lần duy nhất)

Nên cài đặt trong thư mục riêng `chatbot/` để không xung đột với các service khác.

### Bước 1: Chuẩn bị thư mục & Môi trường ảo (Windows CMD)
```cmd
mkdir chatbot
cd chatbot

# Tạo venv bằng Python 3.10 (nếu máy có nhiều bản python)
py -3.10 -m venv venv

# Kích hoạt venv
venv\Scripts\activate
```

### Bước 2: Cài đặt thư viện Rasa
```cmd
# Nâng cấp pip (bắt buộc để tránh lỗi build)
python -m pip install --upgrade pip

# Cài đặt Rasa (phiên bản ổn định)
pip install rasa
```

### Bước 3: Khởi tạo dự án
```cmd
rasa init
```
*   Chọn `.` khi được hỏi thư mục cài đặt.
*   Chọn `Y` để train model mẫu.

---

## 3. Cách Vận hành (Hàng ngày)

Luôn đảm bảo đã kích hoạt môi trường ảo trước khi chạy lệnh:
`cd chatbot` -> `venv\Scripts\activate`

### 3.1. Chế độ Phát triển (Dev Mode)
Dùng để test chat trực tiếp trên terminal.

```cmd
rasa shell
```

### 3.2. Chế độ API Server (Cho Web/App kết nối)
Dùng để Next.js hoặc Mobile App gọi qua API.

```cmd
rasa run --enable-api --cors "*"
```
*   **Port mặc định**: `5005`
*   **API Endpoint cho tin nhắn**: `POST http://localhost:5005/webhooks/rest/webhook`
    *   Body: `{"sender": "user123", "message": "Xin chào"}`

### 3.3. Huấn luyện lại bot (Retrain)
Chạy lệnh này sau mỗi lần sửa file `nlu.yml`, `domain.yml` hoặc `stories.yml`.

```cmd
rasa train
```

---

## 4. Cấu trúc Thư mục Quan trọng

*   **`data/nlu.yml`**: Dữ liệu huấn luyện (Câu nói của người dùng & Intent tương ứng).
*   **`data/stories.yml`**: Kịch bản hội thoại mẫu (Flow: User nói A -> Bot làm B).
*   **`domain.yml`**: Định nghĩa "Vũ trụ" của bot (Intents, Responses, Slots).
*   **`actions/actions.py`**: Code Python xử lý logic phức tạp (Gọi API thời tiết, Database...)
*   **`config.yml`**: Cấu hình Pipeline (Nên dùng `DIETClassifier` cho đa ngôn ngữ).

---

## 5. Các Lỗi Thường Gặp & Cách Fix

### ❌ Lỗi "Python version 2.7 or 3.4+ required" khi cài đặt
*   **Nguyên nhân**: Đang dùng Python 3.11+.
*   **Fix**: Cài Python 3.10 và tạo lại venv như Bước 1.

### ❌ Lỗi "Command 'rasa' not found"
*   **Nguyên nhân**: Chưa activate venv.
*   **Fix**: Chạy `venv\Scripts\activate`.

### ❌ Lỗi kết nối API (CORS Error trên Web)
*   **Nguyên nhân**: Chưa bật cờ CORS khi chạy server.
*   **Fix**: Thêm `--cors "*"` vào lệnh run.

### ❌ Lỗi Port in use
*   **Nguyên nhân**: Rasa hoặc service khác đang chạy.
*   **Fix**: Tắt terminal cũ hoặc chạy `rasa run -p 5006` để đổi port.

---

## 6. Mẹo Đa Ngôn Ngữ (Việt/Anh)
Để bot hiểu tiếng Việt tốt hơn:
1.  Trong `config.yml`: Đảm bảo dùng `DIETClassifier`.
2.  Trong `nlu.yml`: Thêm nhiều ví dụ tiếng Việt có dấu.
3.  Trong `domain.yml`: Viết câu trả lời song ngữ hoặc tách riêng response theo slot ngôn ngữ.
