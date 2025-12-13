#!/usr/bin/env python
"""
Test database connection for Rasa chatbot.
Run this script from the chatbot directory with DATABASE_URL environment variable set.

Usage:
    # Windows PowerShell
    $env:DATABASE_URL = "postgresql://user:password@localhost:5432/relieflink"
    python scripts/test_db_connection.py

    # Windows CMD
    set DATABASE_URL=postgresql://user:password@localhost:5432/relieflink
    python scripts/test_db_connection.py

    # Linux/macOS
    DATABASE_URL="postgresql://user:password@localhost:5432/relieflink" python scripts/test_db_connection.py
"""

import os
import sys

def test_connection():
    print("=" * 60)
    print("🔍 Kiểm tra kết nối Database cho Rasa Chatbot")
    print("=" * 60)
    
    # Check DATABASE_URL
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL chưa được cấu hình!")
        print("   Hãy đặt biến môi trường DATABASE_URL trước khi chạy script này.")
        print("\n   Ví dụ (PowerShell):")
        print('   $env:DATABASE_URL = "postgresql://user:password@localhost:5432/relieflink"')
        return False
    
    # Mask password for display
    masked_url = db_url
    if "@" in db_url and ":" in db_url:
        try:
            parts = db_url.split("@")
            prefix = parts[0]
            if ":" in prefix:
                user_pass = prefix.split("//")[1]
                user = user_pass.split(":")[0]
                masked_url = db_url.replace(user_pass, f"{user}:****")
        except:
            pass
    
    print(f"✅ DATABASE_URL: {masked_url}")
    
    # Check psycopg2
    try:
        import psycopg2
        import psycopg2.extras
        print("✅ psycopg2 đã được cài đặt")
    except ImportError as e:
        print(f"❌ psycopg2 chưa được cài đặt: {e}")
        print("   Chạy: pip install psycopg2-binary")
        return False
    
    # Test connection
    print("\n🔌 Đang kết nối database...")
    try:
        conn = psycopg2.connect(db_url)
        print("✅ Kết nối database thành công!")
    except Exception as e:
        print(f"❌ Lỗi kết nối database: {e}")
        return False
    
    # Test queries
    print("\n📊 Kiểm tra dữ liệu...")
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Count centers
        cur.execute("SELECT COUNT(*) as count FROM trung_tam_cuu_tros")
        centers_count = cur.fetchone()['count']
        print(f"   🏥 Trung tâm cứu trợ: {centers_count}")
        
        # Count users
        cur.execute("SELECT COUNT(*) as count FROM nguoi_dungs")
        users_count = cur.fetchone()['count']
        print(f"   👥 Người dùng: {users_count}")
        
        # Count resources
        cur.execute("SELECT COUNT(*) as count FROM nguon_lucs")
        resources_count = cur.fetchone()['count']
        print(f"   📦 Nguồn lực: {resources_count}")
        
        # Count requests
        cur.execute("SELECT COUNT(*) as count FROM yeu_cau_cuu_tros")
        requests_count = cur.fetchone()['count']
        print(f"   📋 Yêu cầu cứu trợ: {requests_count}")
        
        # Test center with coordinates
        print("\n🗺️ Kiểm tra trung tâm có tọa độ...")
        cur.execute("""
            SELECT ten_trung_tam, dia_chi, vi_do, kinh_do 
            FROM trung_tam_cuu_tros 
            WHERE vi_do IS NOT NULL AND kinh_do IS NOT NULL
            LIMIT 3
        """)
        centers = cur.fetchall()
        
        if centers:
            print(f"   ✅ Có {len(centers)} trung tâm có tọa độ:")
            for c in centers:
                print(f"      • {c['ten_trung_tam']}")
                print(f"        Địa chỉ: {c['dia_chi']}")
                print(f"        Vĩ độ: {c['vi_do']}, Kinh độ: {c['kinh_do']}")
        else:
            print("   ⚠️ Không có trung tâm nào có tọa độ!")
            print("   Hãy chạy seed để tạo dữ liệu mẫu: npx ts-node prisma/seed.ts")
        
        # Check for specific center (Đà Nẵng)
        print("\n🔍 Tìm kiếm 'Trung tâm Cứu trợ Đà Nẵng'...")
        cur.execute("""
            SELECT ten_trung_tam, dia_chi, vi_do, kinh_do, so_lien_he
            FROM trung_tam_cuu_tros 
            WHERE ten_trung_tam ILIKE '%Đà Nẵng%' OR dia_chi ILIKE '%Đà Nẵng%'
        """)
        danang = cur.fetchone()
        
        if danang:
            print(f"   ✅ Tìm thấy: {danang['ten_trung_tam']}")
            print(f"      📍 Địa chỉ: {danang['dia_chi']}")
            print(f"      📞 Số liên hệ: {danang['so_lien_he']}")
            if danang['vi_do'] and danang['kinh_do']:
                print(f"      🗺️ Vĩ độ: {danang['vi_do']}")
                print(f"      🗺️ Kinh độ: {danang['kinh_do']}")
            else:
                print("      ⚠️ Chưa có tọa độ!")
        else:
            print("   ⚠️ Không tìm thấy trung tâm Đà Nẵng trong database.")
            print("   Có thể cần chạy seed: npx ts-node prisma/seed.ts")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Lỗi truy vấn: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ Kiểm tra hoàn tất! Database sẵn sàng cho Rasa chatbot.")
    print("=" * 60)
    
    print("\n📝 Hướng dẫn chạy Rasa action server với DATABASE_URL:")
    print("\n   # Windows PowerShell:")
    print('   $env:DATABASE_URL = "postgresql://user:password@localhost:5432/relieflink"')
    print("   rasa run actions")
    print("\n   # Windows CMD:")
    print("   set DATABASE_URL=postgresql://user:password@localhost:5432/relieflink")
    print("   rasa run actions")
    
    return True


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
