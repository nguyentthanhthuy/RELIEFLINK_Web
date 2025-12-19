# 🤖 Rasa Chatbot Setup Guide cho ReliefLink

Hướng dẫn này mô tả **cách cài đặt và chạy Rasa Chatbot** đang nằm trong thư mục `chatbot/` của project ReliefLink, cũng như cách nó kết nối với Next.js và Python AI Service.

---

## 1. Yêu cầu hệ thống

Rasa kén phiên bản Python, nên hãy tuân thủ:

- **Python**: 3.8, 3.9 hoặc **3.10** (khuyến nghị 3.10).
- **Không nên dùng**: 3.11+ (dễ lỗi dependency).
- Hệ điều hành: Windows / macOS / Linux (trên Windows, nếu gặp lỗi build có thể cần C++ Build Tools).

---

## 2. Vị trí project Rasa trong repo

Trong repo hiện tại, chatbot Rasa đã được tạo sẵn ở:

```text
RELIEFLINK_Web/
    chatbot/
        actions/
        config.yml
        credentials.yml
        data/
        domain.yml
        endpoints.yml
        models/
        requirements.txt
        scripts/
```

Bạn **không cần chạy `rasa init` lại**, chỉ cần cài môi trường và train/running.

---

## 3. Thiết lập môi trường Rasa (làm 1 lần)

### 3.1. Tạo virtualenv trong thư mục `chatbot/`

Từ thư mục gốc project (`RELIEFLINK_Web`):

```cmd
cd chatbot

:: Tạo môi trường ảo bằng Python 3.10
py -3.10 -m venv venv

:: Kích hoạt venv (Windows)
venv\Scripts\activate
```

> Lần sau chỉ cần: `cd chatbot` rồi `venv\Scripts\activate`.

### 3.2. Cài đặt dependencies

Trong khi venv đang được kích hoạt:

```cmd
:: Nâng cấp pip
python -m pip install --upgrade pip

:: Cài Rasa core + SDK cho custom actions
pip install rasa rasa-sdk

:: Cài thêm các thư viện liên quan tới database & AI service
pip install -r requirements.txt
```

File `chatbot/requirements.txt` hiện hỗ trợ:

- `psycopg2-binary` (kết nối PostgreSQL)
- `python-dotenv` (load biến môi trường từ file .env)
- `requests` (gọi API nội bộ)

---

## 4. Cấu hình biến môi trường

Các action trong [chatbot/actions/actions.py](chatbot/actions/actions.py) dùng biến môi trường từ **file `.env` ở thư mục gốc** project.

Tại thư mục `RELIEFLINK_Web/` tạo (hoặc bổ sung) file `.env` với các biến tối thiểu:

```env
DATABASE_URL=postgresql://username:password@localhost:5432/relieflink
AI_SERVICE_URL=http://localhost:8000
RASA_URL=http://localhost:5005
```

Giải thích nhanh:

- `DATABASE_URL`: trỏ tới cùng database mà Next.js/Prisma đang dùng.
- `AI_SERVICE_URL`: URL của Python AI Service (xem chi tiết trong [PYTHON_AI_SERVICE_SETUP.md](PYTHON_AI_SERVICE_SETUP.md)).
- `RASA_URL`: URL Rasa dùng để Next.js proxy qua route `/api/rasa`.

Có thể kiểm tra kết nối DB và action bằng các script có sẵn:

```cmd
cd chatbot
venv\Scripts\activate

:: Kiểm tra kết nối database
python -m scripts.check_db

:: Test nhanh custom action lấy trung tâm cứu trợ
python -m scripts.invoke_action
```

---

## 5. Train/Retrain model Rasa

Sau khi sửa các file trong thư mục `chatbot/data/` hoặc `chatbot/domain.yml`, bạn cần train lại model:

```cmd
cd chatbot
venv\Scripts\activate

rasa train
```

Model mới sẽ được lưu vào thư mục `chatbot/models/` và dùng khi chạy server.

### 5.1. Train với tùy chọn nâng cao

```cmd
:: Train chỉ NLU (nhanh hơn khi chỉ sửa data/nlu.yml)
rasa train nlu

:: Train với augmentation để tăng độ chính xác
rasa train --augmentation 50

:: Train và chạy thử ngay với shell
rasa train && rasa shell
```

### 5.2. Test chatbot sau khi train

```cmd
:: Chat trực tiếp qua terminal
rasa shell

:: Hoặc test với verbose mode để xem intent/entities được nhận diện
rasa shell --debug
```

---

## 5.3. Các tính năng chatbot hỗ trợ

Sau khi train, chatbot có thể trả lời các câu hỏi liên quan đến database:

| Loại câu hỏi | Ví dụ |
|--------------|-------|
| **Thống kê tổng quan** | "Thống kê hệ thống", "Số liệu tổng quan" |
| **Trung tâm cứu trợ** | "Danh sách trung tâm", "Trung tâm gần Hà Nội" |
| **Nguồn lực** | "Kiểm tra kho hàng", "Nguồn lực sắp hết", "Nguồn lực loại thực phẩm" |
| **Yêu cầu cứu trợ** | "Yêu cầu đang chờ duyệt", "Yêu cầu khẩn cấp", "Yêu cầu của tôi" |
| **Phân phối** | "Lịch sử phân phối", "Các đợt cứu trợ" |
| **Thời tiết & AI** | "Thời tiết Hà Nội", "Dự báo cứu trợ Đà Nẵng", "Dự báo AI" |
| **Tình nguyện viên** | "Danh sách tình nguyện viên" |
| **Tìm kiếm** | "Yêu cầu loại thực phẩm", "Nguồn lực y tế" |
| **So sánh** | "So sánh nguồn lực giữa các trung tâm" |
| **Hỗ trợ** | "Tôi có thể hỏi gì?", "Help" |

---

## 6. Chạy chatbot trong môi trường phát triển

Trong dev, nên dùng **nhiều terminal** riêng:

### 6.1. Terminal 1 – Action Server (custom actions)

```cmd
cd chatbot
venv\Scripts\activate

rasa run actions --port 5055
```

Endpoint action server đã được khai báo trong [chatbot/endpoints.yml](chatbot/endpoints.yml):

```yaml
action_endpoint:
    url: "http://localhost:5055/webhook"
```

### 6.2. Terminal 2 – Rasa Server (REST API cho chatbot)

```cmd
cd chatbot
venv\Scripts\activate

rasa run ^
    --enable-api ^
    --cors "*" ^
    --endpoints endpoints.yml
```

- Port mặc định: `5005`.
- REST webhook mặc định: `POST http://localhost:5005/webhooks/rest/webhook`.

Bạn có thể test nhanh trực tiếp (không qua Next.js):

```bash
curl -X POST http://localhost:5005/webhooks/rest/webhook \
    -H "Content-Type: application/json" \
    -d '{"sender": "test-user", "message": "Xin chào"}'
```

### 6.3. Terminal 3 – Next.js app (frontend + API proxy)

Từ thư mục gốc `RELIEFLINK_Web/`:

```bash
npm install        # lần đầu
npm run dev        # hoặc: yarn dev / pnpm dev
```

Next.js sẽ chạy tại `http://localhost:3000` và gửi message tới Rasa qua route
[src/app/api/rasa/route.ts](src/app/api/rasa/route.ts).

Route này sẽ:

- Nhận request `POST /api/rasa` với body dạng:
    ```json
    { "message": "Xin chào" }
    ```
- Proxy sang `RASA_URL/webhooks/rest/webhook` (mặc định `http://localhost:5005`).

---

## 7. Kiểm tra sức khỏe & debug nhanh

### 7.1. Health check qua Next.js

Route GET `/api/rasa` sẽ gọi tới `RASA_URL` và trả về:

- `{ status: "ok", rasa: ... }` nếu Rasa đang sống.
- `{ status: "error", message: "Rasa not responding" }` nếu không kết nối được.

### 7.2. Một số lỗi thường gặp

- **`rasa: command not found`**  
    → Quên kích hoạt venv. Chạy lại `venv\Scripts\activate`.

- **Lỗi kết nối DB trong actions**  
    → Kiểm tra `DATABASE_URL` trong `.env`, đảm bảo Postgres đang chạy. Có thể dùng `python -m scripts.check_db` để xem chi tiết.

- **Frontend không nhận được trả lời từ bot**  
    → Kiểm tra lần lượt:
    - Rasa action server có chạy ở port 5055 không?
    - Rasa server có chạy ở port 5005 không?
    - Biến `RASA_URL` trong `.env` có đúng (`http://localhost:5005`) không?

---

## 8. Ghi chú khi deploy

- Trong môi trường production, nên:
    - Dùng domain riêng cho Rasa (ví dụ: `https://chatbot.relieflink.vn`).
    - Cấu hình lại `RASA_URL` trong `.env` cho phù hợp.
    - Hạn chế CORS thay vì dùng `--cors "*"`.
    - Chạy Rasa và action server bằng process manager (systemd, supervisor, Docker, v.v.).

Các phần còn lại (Next.js app, Python AI Service) tham khảo thêm trong
[PYTHON_AI_SERVICE_SETUP.md](PYTHON_AI_SERVICE_SETUP.md) và tài liệu trong thư mục `src/docs/`.
