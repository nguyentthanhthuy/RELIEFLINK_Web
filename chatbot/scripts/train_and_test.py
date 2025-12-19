#!/usr/bin/env python
"""
Script để train và test chatbot Rasa với các câu hỏi database
Chạy: python -m scripts.train_and_test
"""

import subprocess
import sys
import os
import json
import requests
from pathlib import Path

# Thêm thư mục cha vào path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Test messages cho database queries
TEST_MESSAGES = [
    # Thống kê
    ("Thống kê hệ thống", "ask_statistics"),
    ("Số liệu tổng quan", "ask_statistics"),
    
    # Trung tâm
    ("Danh sách trung tâm cứu trợ", "ask_relief_centers"),
    ("Trung tâm gần Hà Nội", "ask_relief_centers"),
    
    # Nguồn lực
    ("Kiểm tra kho hàng", "ask_resources"),
    ("Nguồn lực sắp hết", "ask_low_stock_resources"),
    ("Nguồn lực loại thực phẩm", "search_resources_by_type"),
    
    # Yêu cầu
    ("Yêu cầu đang chờ duyệt", "ask_pending_requests"),
    ("Yêu cầu khẩn cấp", "ask_urgent_requests"),
    ("Yêu cầu loại thực phẩm", "search_requests_by_type"),
    
    # Phân phối
    ("Lịch sử phân phối", "ask_distributions"),
    
    # AI
    ("Dự báo AI", "ask_ai_predictions"),
    ("Thời tiết Hà Nội", "ask_weather"),
    
    # Tình nguyện viên
    ("Danh sách tình nguyện viên", "ask_volunteers"),
    
    # So sánh
    ("So sánh nguồn lực giữa các trung tâm", "compare_resources"),
    
    # Tổng người cứu trợ
    ("Tổng số người được cứu trợ", "ask_total_affected_people"),
    
    # Help
    ("Tôi có thể hỏi gì?", "ask_help_chatbot"),
    
    # Hoạt động gần đây
    ("Hoạt động gần đây", "ask_recent_activities"),
]


def test_nlu_model():
    """Test NLU model với các câu hỏi mẫu"""
    print("\n" + "="*60)
    print("🧪 TESTING NLU MODEL")
    print("="*60 + "\n")
    
    try:
        # Chạy rasa shell nlu với pipe
        for message, expected_intent in TEST_MESSAGES:
            result = subprocess.run(
                ["rasa", "nlu", "parse", "-m", "models"],
                input=message,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                try:
                    output = result.stdout
                    # Parse JSON output
                    # Rasa outputs JSON after some text
                    json_start = output.find('{')
                    if json_start != -1:
                        json_str = output[json_start:]
                        parsed = json.loads(json_str)
                        detected_intent = parsed.get('intent', {}).get('name', 'unknown')
                        confidence = parsed.get('intent', {}).get('confidence', 0)
                        
                        status = "✅" if detected_intent == expected_intent else "❌"
                        print(f"{status} \"{message}\"")
                        print(f"   Expected: {expected_intent}")
                        print(f"   Detected: {detected_intent} (confidence: {confidence:.2f})")
                        print()
                except json.JSONDecodeError:
                    print(f"⚠️  Could not parse response for: {message}")
            else:
                print(f"❌ Error testing: {message}")
                print(f"   {result.stderr}")
    except FileNotFoundError:
        print("❌ Rasa command not found. Make sure rasa is installed and venv is activated.")
    except Exception as e:
        print(f"❌ Error during testing: {e}")


def test_rasa_server(rasa_url="http://localhost:5005"):
    """Test chatbot qua REST API"""
    print("\n" + "="*60)
    print("🌐 TESTING RASA SERVER")
    print("="*60 + "\n")
    
    webhook_url = f"{rasa_url}/webhooks/rest/webhook"
    
    # Test một số câu hỏi
    test_queries = [
        "Xin chào",
        "Thống kê hệ thống",
        "Yêu cầu khẩn cấp",
        "Nguồn lực sắp hết",
        "Tôi có thể hỏi gì?",
    ]
    
    for query in test_queries:
        try:
            response = requests.post(
                webhook_url,
                json={"sender": "test_user", "message": query},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"📤 User: {query}")
                for msg in data:
                    text = msg.get('text', '')
                    # Truncate long messages
                    if len(text) > 200:
                        text = text[:200] + "..."
                    print(f"🤖 Bot: {text}")
                print()
            else:
                print(f"❌ Error for '{query}': HTTP {response.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"❌ Cannot connect to Rasa server at {rasa_url}")
            print("   Make sure Rasa server is running: rasa run --enable-api")
            break
        except Exception as e:
            print(f"❌ Error: {e}")


def train_model():
    """Train Rasa model"""
    print("\n" + "="*60)
    print("🏋️ TRAINING RASA MODEL")
    print("="*60 + "\n")
    
    try:
        result = subprocess.run(
            ["rasa", "train"],
            capture_output=False,
            timeout=600  # 10 minutes max
        )
        
        if result.returncode == 0:
            print("\n✅ Model trained successfully!")
            return True
        else:
            print("\n❌ Training failed!")
            return False
    except FileNotFoundError:
        print("❌ Rasa command not found. Make sure rasa is installed.")
        return False
    except subprocess.TimeoutExpired:
        print("❌ Training timeout (>10 minutes)")
        return False


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Train and test Rasa chatbot")
    parser.add_argument("--train", action="store_true", help="Train the model")
    parser.add_argument("--test-nlu", action="store_true", help="Test NLU model")
    parser.add_argument("--test-server", action="store_true", help="Test Rasa server")
    parser.add_argument("--rasa-url", default="http://localhost:5005", help="Rasa server URL")
    parser.add_argument("--all", action="store_true", help="Run all steps")
    
    args = parser.parse_args()
    
    # Change to chatbot directory
    chatbot_dir = Path(__file__).parent.parent
    os.chdir(chatbot_dir)
    print(f"📁 Working directory: {chatbot_dir}")
    
    if args.all or args.train:
        train_model()
    
    if args.all or args.test_nlu:
        test_nlu_model()
    
    if args.all or args.test_server:
        test_rasa_server(args.rasa_url)
    
    if not any([args.train, args.test_nlu, args.test_server, args.all]):
        print("ℹ️  Usage examples:")
        print("   python -m scripts.train_and_test --train      # Train model")
        print("   python -m scripts.train_and_test --test-nlu   # Test NLU")
        print("   python -m scripts.train_and_test --test-server # Test server")
        print("   python -m scripts.train_and_test --all        # All steps")


if __name__ == "__main__":
    main()
