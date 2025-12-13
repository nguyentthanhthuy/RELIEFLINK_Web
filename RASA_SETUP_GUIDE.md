# 🤖 Hướng Dẫn Hoàn Chỉnh: Tạo, Train và Tích Hợp Rasa Chatbot

> **Dự án:** ReliefLink - Hệ thống Quản lý Cứu trợ Thiên tai  
> **Phiên bản:** 1.0  
> **Cập nhật:** Tháng 12/2025

---

## 📋 Mục Lục

1. [Tổng Quan](#1-tổng-quan)
2. [Yêu Cầu Hệ Thống](#2-yêu-cầu-hệ-thống)
3. [Cài Đặt Môi Trường](#3-cài-đặt-môi-trường)
4. [Cấu Trúc Thư Mục](#4-cấu-trúc-thư-mục)
5. [Cấu Hình Chatbot](#5-cấu-hình-chatbot)
6. [Kết Nối Database](#6-kết-nối-database)
7. [Training Model](#7-training-model)
8. [Chạy Dự Án](#8-chạy-dự-án)
9. [Tích Hợp với Next.js](#9-tích-hợp-với-nextjs)
10. [Các Lệnh Chatbot Hỗ Trợ](#10-các-lệnh-chatbot-hỗ-trợ)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Tổng Quan

### 1.1 Chatbot làm gì?
Rasa Chatbot trong ReliefLink có thể:
- 🏥 Tra cứu thông tin trung tâm cứu trợ (địa chỉ, tọa độ GPS, số liên hệ)
- 📦 Xem nguồn lực/vật tư cứu trợ còn trong kho
- 📊 Xem thống kê hệ thống (người dùng, yêu cầu, phân phối)
- 🌤️ Kiểm tra thời tiết và cảnh báo thiên tai
- 📋 Tra cứu yêu cầu cứu trợ đang chờ xử lý
- 👥 Xem danh sách tình nguyện viên

### 1.2 Kiến trúc

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Next.js Web   │────▶│   Rasa Server   │────▶│  Action Server  │
│   (Port 3000)   │     │   (Port 5005)   │     │   (Port 5055)   │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │   PostgreSQL    │
                                                │   (Port 5432)   │
                                                └─────────────────┘
```

---

## 2. Yêu Cầu Hệ Thống

### ⚠️ QUAN TRỌNG: Phiên bản Python

| Python Version | Hỗ trợ |
|----------------|--------|
| 3.7, 3.8, 3.9 | ✅ Có |
| **3.10** | ✅ **Khuyên dùng** |
| 3.11, 3.12+ | ❌ Không hỗ trợ |

### Phần mềm cần thiết:
- **Python 3.10** (tải từ https://www.python.org/downloads/release/python-31011/)
- **PostgreSQL** (đang chạy với database `relieflink`)
- **Node.js** (cho Next.js frontend)
- **Visual Studio C++ Build Tools** (Windows - nếu gặp lỗi biên dịch)

---

## 3. Cài Đặt Môi Trường

### Bước 1: Tạo thư mục và môi trường ảo

**Windows PowerShell:**
```powershell
# Di chuyển vào thư mục dự án
cd C:\xampp\htdocs\RELIEFLINK_Web_Groq

# Tạo thư mục chatbot (nếu chưa có)
mkdir chatbot
cd chatbot

# Tạo môi trường ảo với Python 3.10
py -3.10 -m venv venv

# Kích hoạt môi trường ảo
.\venv\Scripts\activate
```

**macOS/Linux:**
```bash
cd /path/to/RELIEFLINK_Web_Groq
mkdir chatbot && cd chatbot
python3.10 -m venv venv
source venv/bin/activate
```

### Bước 2: Cài đặt Rasa và dependencies

```powershell
# Nâng cấp pip
python -m pip install --upgrade pip

# Cài đặt Rasa
pip install rasa

# Cài đặt thư viện kết nối PostgreSQL
pip install psycopg2-binary

# Cài đặt requests cho API calls
pip install requests
```

### Bước 3: Khởi tạo dự án Rasa (nếu chưa có)

```powershell
rasa init
```
- Chọn `.` khi được hỏi thư mục
- Chọn `Y` để train model mẫu

---

## 4. Cấu Trúc Thư Mục

```
chatbot/
├── venv/                    # Môi trường ảo Python
├── actions/
│   ├── __init__.py
│   └── actions.py           # 🔥 Code xử lý logic, kết nối DB
├── data/
│   ├── nlu.yml              # 🔥 Dữ liệu training (intents + examples)
│   ├── rules.yml            # Rules mapping intent → action
│   └── stories.yml          # Kịch bản hội thoại
├── models/                  # Model đã train (tự động tạo)
├── scripts/
│   └── test_db_connection.py  # Script test kết nối DB
├── config.yml               # Cấu hình NLU pipeline
├── credentials.yml          # Cấu hình channels (REST API, Socket...)
├── domain.yml               # 🔥 Định nghĩa intents, actions, slots, responses
├── endpoints.yml            # Cấu hình action server endpoint
└── requirements.txt         # Dependencies
```

---

## 5. Cấu Hình Chatbot

### 5.1 File `domain.yml` - Định nghĩa "Vũ trụ" của bot

```yaml
version: "3.1"

intents:
  - greet
  - goodbye
  - ask_relief_centers          # Hỏi về trung tâm cứu trợ
  - ask_center_details          # Hỏi chi tiết (tọa độ) trung tâm
  - ask_resources               # Hỏi nguồn lực trong kho
  - ask_system_stats            # Hỏi thống kê hệ thống
  - ask_pending_requests        # Hỏi yêu cầu chờ xử lý
  - ask_volunteers              # Hỏi danh sách tình nguyện viên
  - ask_weather                 # Hỏi thời tiết
  - ask_db_status               # Kiểm tra kết nối DB

actions:
  - action_find_relief_centers
  - action_get_center_details
  - action_get_resources
  - action_get_system_stats
  - action_get_pending_requests
  - action_get_volunteers
  - action_check_weather
  - action_check_db_connection

slots:
  location:
    type: text
    mappings:
    - type: from_entity
      entity: location
  resource_type:
    type: text
    mappings:
    - type: from_entity
      entity: resource_type

entities:
  - location
  - resource_type

responses:
  utter_greet:
  - text: "Xin chào! Tôi là trợ lý ReliefLink. Bạn cần hỗ trợ gì?"
  
  utter_goodbye:
  - text: "Tạm biệt! Chúc bạn một ngày tốt lành."
```

### 5.2 File `data/nlu.yml` - Dữ liệu training

```yaml
version: "3.1"

nlu:
- intent: greet
  examples: |
    - xin chào
    - hello
    - hi
    - chào bạn

- intent: ask_center_details
  examples: |
    - kinh độ và vĩ độ của trung tâm cứu trợ [Đà Nẵng](location)
    - tọa độ trung tâm cứu trợ [Hà Nội](location)
    - thông tin chi tiết trung tâm [Hồ Chí Minh](location)
    - cho tôi biết tọa độ trung tâm [Đà Nẵng](location)

- intent: ask_resources
  examples: |
    - nguồn lực cứu trợ hiện có
    - còn bao nhiêu [gạo](resource_type)?
    - kiểm tra [thuốc](resource_type) còn bao nhiêu
    - xem nguồn lực tại [Đà Nẵng](location)

- intent: ask_system_stats
  examples: |
    - thống kê hệ thống
    - có bao nhiêu người dùng
    - tổng quan hệ thống
```

### 5.3 File `data/rules.yml` - Mapping Intent → Action

```yaml
version: "3.1"

rules:
- rule: Greet user
  steps:
  - intent: greet
  - action: utter_greet

- rule: Get center details when asked
  steps:
  - intent: ask_center_details
  - action: action_get_center_details

- rule: Get resources when asked
  steps:
  - intent: ask_resources
  - action: action_get_resources

- rule: Get system stats when asked
  steps:
  - intent: ask_system_stats
  - action: action_get_system_stats
```

### 5.4 File `endpoints.yml` - Cấu hình Action Server

```yaml
action_endpoint:
  url: "http://localhost:5055/webhook"
```

---

## 6. Kết Nối Database

### 6.1 Cấu hình DATABASE_URL

Rasa Action Server cần biến môi trường `DATABASE_URL` để kết nối PostgreSQL.

**Lấy từ file `.env` của dự án:**
```
DATABASE_URL="postgresql://postgres:123456@localhost:5432/relieflink"
```

### 6.2 File `actions/actions.py` - Kết nối DB

```python
import os
import psycopg2
import psycopg2.extras
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

def _get_db_conn():
    """Tạo kết nối database."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return None
    try:
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        print(f"DB connection error: {e}")
        return None


class ActionGetCenterDetails(Action):
    def name(self):
        return "action_get_center_details"

    def run(self, dispatcher, tracker, domain):
        location = tracker.get_slot("location")
        
        conn = _get_db_conn()
        if not conn:
            dispatcher.utter_message(text="Không thể kết nối database.")
            return []
        
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT ten_trung_tam, dia_chi, so_lien_he, vi_do, kinh_do
            FROM trung_tam_cuu_tros
            WHERE ten_trung_tam ILIKE %s OR dia_chi ILIKE %s
            LIMIT 1
        """, (f"%{location}%", f"%{location}%"))
        
        center = cur.fetchone()
        cur.close()
        conn.close()
        
        if center:
            msg = f"🏥 {center['ten_trung_tam']}\n"
            msg += f"📍 Địa chỉ: {center['dia_chi']}\n"
            msg += f"📞 Số liên hệ: {center['so_lien_he']}\n"
            if center['vi_do'] and center['kinh_do']:
                msg += f"🗺️ Vĩ độ: {center['vi_do']}\n"
                msg += f"🗺️ Kinh độ: {center['kinh_do']}"
            dispatcher.utter_message(text=msg)
        else:
            dispatcher.utter_message(text=f"Không tìm thấy trung tâm '{location}'")
        
        return []
```

### 6.3 Test kết nối Database

```powershell
cd C:\xampp\htdocs\RELIEFLINK_Web_Groq\chatbot

# Đặt biến môi trường
$env:DATABASE_URL = "postgresql://postgres:123456@localhost:5432/relieflink"

# Chạy script test
python scripts/test_db_connection.py
```

**Kết quả mong đợi:**
```
✅ DATABASE_URL: postgresql://postgres:****@localhost:5432/relieflink
✅ psycopg2 đã được cài đặt
✅ Kết nối database thành công!
   🏥 Trung tâm cứu trợ: 15
   👥 Người dùng: 71
   📦 Nguồn lực: 200
```

---

## 7. Training Model

### 7.1 Train model mới

Mỗi khi thay đổi các file `nlu.yml`, `domain.yml`, `stories.yml`, hoặc `rules.yml`, bạn cần train lại model:

```powershell
cd C:\xampp\htdocs\RELIEFLINK_Web_Groq\chatbot
.\venv\Scripts\activate

rasa train
```

**Thời gian training:** 2-10 phút tùy thuộc vào lượng data và cấu hình máy.

### 7.2 Validate cấu hình trước khi train

```powershell
rasa data validate
```

### 7.3 Test model trong terminal

```powershell
rasa shell
```

Sau đó nhập tin nhắn để test:
```
Your input -> kinh độ vĩ độ trung tâm cứu trợ Đà Nẵng
```

---

## 8. Chạy Dự Án

### 8.1 Chạy đầy đủ (3 terminal)

**Terminal 1: Action Server** (xử lý logic, kết nối DB)
```powershell
cd C:\xampp\htdocs\RELIEFLINK_Web_Groq\chatbot
.\venv\Scripts\activate
$env:DATABASE_URL = "postgresql://postgres:123456@localhost:5432/relieflink"
rasa run actions
```

**Terminal 2: Rasa Server** (NLU + API endpoint)
```powershell
cd C:\xampp\htdocs\RELIEFLINK_Web_Groq\chatbot
.\venv\Scripts\activate
rasa run --enable-api --cors "*"
```

**Terminal 3: Next.js Frontend**
```powershell
cd C:\xampp\htdocs\RELIEFLINK_Web_Groq
yarn dev
```


### 8.2 Chạy bằng batch file (tự động)

Tạo file `RUN_CHATBOT.bat`:
```batch
@echo off
echo Starting Rasa Chatbot...

:: Start Action Server
start cmd /k "cd /d C:\xampp\htdocs\RELIEFLINK_Web_Groq\chatbot && venv\Scripts\activate && set DATABASE_URL=postgresql://postgres:123456@localhost:5432/relieflink && rasa run actions"

:: Wait 5 seconds
timeout /t 5

:: Start Rasa Server
start cmd /k "cd /d C:\xampp\htdocs\RELIEFLINK_Web_Groq\chatbot && venv\Scripts\activate && rasa run --enable-api --cors *"

echo Rasa is starting...
echo Action Server: http://localhost:5055
echo Rasa API: http://localhost:5005
```

### 8.3 Kiểm tra services

| Service | URL | Kiểm tra |
|---------|-----|----------|
| Rasa API | http://localhost:5005 | `GET /` |
| Action Server | http://localhost:5055 | `GET /health` |
| Next.js | http://localhost:3000 | Mở trình duyệt |

---

## 9. Tích Hợp với Next.js

### 9.1 Gọi Rasa API từ Frontend

**File: `src/app/api/chat/route.ts`**
```typescript
import { NextRequest, NextResponse } from 'next/server';

const RASA_URL = process.env.RASA_URL || 'http://localhost:5005';

export async function POST(request: NextRequest) {
  try {
    const { message, sender } = await request.json();
    
    const response = await fetch(`${RASA_URL}/webhooks/rest/webhook`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sender: sender || 'user',
        message: message
      })
    });
    
    const data = await response.json();
    return NextResponse.json(data);
    
  } catch (error) {
    return NextResponse.json(
      { error: 'Không thể kết nối chatbot' },
      { status: 500 }
    );
  }
}
```

### 9.2 Component Chatbox

**File: `src/components/Chatbox.tsx`**
```tsx
'use client';
import { useState } from 'react';

export default function Chatbox() {
  const [messages, setMessages] = useState<{text: string, isBot: boolean}[]>([]);
  const [input, setInput] = useState('');

  const sendMessage = async () => {
    if (!input.trim()) return;
    
    // Add user message
    setMessages(prev => [...prev, { text: input, isBot: false }]);
    
    // Call Rasa API
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: input, sender: 'user123' })
    });
    
    const data = await res.json();
    
    // Add bot responses
    data.forEach((msg: any) => {
      setMessages(prev => [...prev, { text: msg.text, isBot: true }]);
    });
    
    setInput('');
  };

  return (
    <div className="chatbox">
      <div className="messages">
        {messages.map((msg, i) => (
          <div key={i} className={msg.isBot ? 'bot' : 'user'}>
            {msg.text}
          </div>
        ))}
      </div>
      <input 
        value={input} 
        onChange={e => setInput(e.target.value)}
        onKeyPress={e => e.key === 'Enter' && sendMessage()}
        placeholder="Nhập tin nhắn..."
      />
      <button onClick={sendMessage}>Gửi</button>
    </div>
  );
}
```

---

## 10. Các Lệnh Chatbot Hỗ Trợ

| Câu hỏi mẫu | Chức năng |
|-------------|-----------|
| "kinh độ vĩ độ trung tâm cứu trợ Đà Nẵng" | Xem tọa độ GPS của trung tâm |
| "các trung tâm cứu trợ" | Liệt kê danh sách trung tâm |
| "nguồn lực cứu trợ hiện có" | Xem vật tư trong kho |
| "còn bao nhiêu gạo" | Kiểm tra số lượng gạo |
| "thống kê hệ thống" | Xem tổng quan (users, requests...) |
| "yêu cầu chờ phê duyệt" | Xem yêu cầu đang chờ xử lý |
| "danh sách tình nguyện viên" | Xem volunteers |
| "thời tiết Hà Nội" | Kiểm tra thời tiết |
| "kiểm tra kết nối database" | Debug DB connection |

---

## 11. Troubleshooting

### ❌ Lỗi: "Python version 2.7 or 3.4+ required"
**Nguyên nhân:** Đang dùng Python 3.11+
**Giải pháp:** Cài Python 3.10 và tạo lại venv

### ❌ Lỗi: "Command 'rasa' not found"
**Nguyên nhân:** Chưa activate môi trường ảo
**Giải pháp:** Chạy `.\venv\Scripts\activate`

### ❌ Lỗi: "No module named 'psycopg2'"
**Nguyên nhân:** Chưa cài psycopg2
**Giải pháp:** `pip install psycopg2-binary`

### ❌ Lỗi: "Connection refused" khi gọi Action Server
**Nguyên nhân:** Action Server chưa chạy hoặc sai port
**Giải pháp:** Đảm bảo `rasa run actions` đang chạy ở terminal khác

### ❌ Lỗi: "CORS error" từ frontend
**Nguyên nhân:** Chưa bật CORS
**Giải pháp:** Thêm `--cors "*"` khi chạy rasa server

### ❌ Bot không trả về tọa độ
**Nguyên nhân:** DATABASE_URL chưa được set cho Action Server
**Giải pháp:** 
```powershell
$env:DATABASE_URL = "postgresql://postgres:123456@localhost:5432/relieflink"
rasa run actions
```

### ❌ Model cũ, không nhận intent mới
**Nguyên nhân:** Chưa train lại sau khi sửa NLU
**Giải pháp:** `rasa train`

---

