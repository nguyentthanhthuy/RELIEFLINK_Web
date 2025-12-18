from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
import requests
import json
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables from the root .env file (2 levels up)
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env'))


try:
    import psycopg2
    import psycopg2.extras
except Exception:
    psycopg2 = None

AI_SERVICE_URL = os.environ.get("AI_SERVICE_URL", "http://localhost:8000")


def _get_db_conn():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url or psycopg2 is None:
        return None
    try:
        if not db_url:
            print("DEBUG: DATABASE_URL is not set.")
            return None
        # Mask password for logging
        safe_url = db_url.split("@")[-1] if "@" in db_url else "..."
        print(f"DEBUG: Connecting to DB at ...{safe_url}")
        
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        print(f"DEBUG: DB Connection Error: {e}")
        return None


def _fetch_user_requests_from_db(user_id: str):
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT id, loai_yeu_cau, mo_ta, so_nguoi, trang_thai, created_at, dia_chi, trang_thai_phe_duyet
            FROM yeu_cau_cuu_tros
            WHERE id_nguoi_dung = %s
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (user_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_notifications_from_db(user_id: str):
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT tieu_de, noi_dung, loai_thong_bao, created_at, da_doc
            FROM thong_baos
            WHERE id_nguoi_nhan = %s
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (user_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_centers_from_db():
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT id, ten_trung_tam, dia_chi, so_lien_he, vi_do, kinh_do
            FROM trung_tam_cuu_tros
            LIMIT 50
            """
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_statistics_from_db():
    """Lấy thống kê tổng quan từ database"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        stats = {}
        
        # Tổng số người dùng
        cur.execute("SELECT COUNT(*) as total FROM nguoi_dungs")
        stats['total_users'] = cur.fetchone()['total']
        
        # Số người dùng theo vai trò
        cur.execute("""
            SELECT vai_tro, COUNT(*) as count 
            FROM nguoi_dungs 
            GROUP BY vai_tro
        """)
        stats['users_by_role'] = {row['vai_tro']: row['count'] for row in cur.fetchall()}
        
        # Tổng số yêu cầu cứu trợ
        cur.execute("SELECT COUNT(*) as total FROM yeu_cau_cuu_tros")
        stats['total_requests'] = cur.fetchone()['total']
        
        # Yêu cầu theo trạng thái
        cur.execute("""
            SELECT trang_thai, COUNT(*) as count 
            FROM yeu_cau_cuu_tros 
            GROUP BY trang_thai
        """)
        stats['requests_by_status'] = {row['trang_thai']: row['count'] for row in cur.fetchall()}
        
        # Yêu cầu theo trạng thái phê duyệt
        cur.execute("""
            SELECT trang_thai_phe_duyet, COUNT(*) as count 
            FROM yeu_cau_cuu_tros 
            GROUP BY trang_thai_phe_duyet
        """)
        stats['requests_by_approval'] = {row['trang_thai_phe_duyet']: row['count'] for row in cur.fetchall()}
        
        # Tổng số trung tâm cứu trợ
        cur.execute("SELECT COUNT(*) as total FROM trung_tam_cuu_tros")
        stats['total_centers'] = cur.fetchone()['total']
        
        # Tổng số nguồn lực
        cur.execute("SELECT COUNT(*) as total, SUM(so_luong) as total_quantity FROM nguon_lucs")
        row = cur.fetchone()
        stats['total_resources'] = row['total']
        stats['total_resource_quantity'] = row['total_quantity'] or 0
        
        # Tổng số đợt phân phối
        cur.execute("SELECT COUNT(*) as total FROM phan_phois")
        stats['total_distributions'] = cur.fetchone()['total']
        
        cur.close()
        conn.close()
        return stats
    except Exception as e:
        print(f"DEBUG: Error fetching statistics: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_resources_from_db(location_filter: str = None):
    """Lấy danh sách nguồn lực từ database"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        if location_filter:
            cur.execute("""
                SELECT nl.id, nl.ten_nguon_luc, nl.loai, nl.so_luong, nl.don_vi, nl.trang_thai,
                       tt.ten_trung_tam, tt.dia_chi
                FROM nguon_lucs nl
                JOIN trung_tam_cuu_tros tt ON nl.id_trung_tam = tt.id
                WHERE LOWER(tt.dia_chi) LIKE %s OR LOWER(tt.ten_trung_tam) LIKE %s
                ORDER BY nl.loai, nl.ten_nguon_luc
                LIMIT 30
            """, (f"%{location_filter.lower()}%", f"%{location_filter.lower()}%"))
        else:
            cur.execute("""
                SELECT nl.id, nl.ten_nguon_luc, nl.loai, nl.so_luong, nl.don_vi, nl.trang_thai,
                       tt.ten_trung_tam, tt.dia_chi
                FROM nguon_lucs nl
                JOIN trung_tam_cuu_tros tt ON nl.id_trung_tam = tt.id
                ORDER BY nl.loai, nl.ten_nguon_luc
                LIMIT 30
            """)
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"DEBUG: Error fetching resources: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_distributions_from_db(limit: int = 10):
    """Lấy danh sách phân phối gần đây"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT pp.id, pp.trang_thai, pp.ma_giao_dich, pp.thoi_gian_xuat, pp.thoi_gian_giao,
                   yc.loai_yeu_cau, yc.dia_chi as dia_chi_yeu_cau, yc.so_nguoi,
                   nl.ten_nguon_luc, nl.so_luong, nl.don_vi,
                   nd.ho_va_ten as ten_tinh_nguyen_vien
            FROM phan_phois pp
            JOIN yeu_cau_cuu_tros yc ON pp.id_yeu_cau = yc.id
            JOIN nguon_lucs nl ON pp.id_nguon_luc = nl.id
            JOIN nguoi_dungs nd ON pp.id_tinh_nguyen_vien = nd.id
            ORDER BY pp.thoi_gian_xuat DESC NULLS LAST, pp.id DESC
            LIMIT %s
        """, (limit,))
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"DEBUG: Error fetching distributions: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_pending_requests_from_db():
    """Lấy các yêu cầu đang chờ duyệt"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT yc.id, yc.loai_yeu_cau, yc.mo_ta, yc.so_nguoi, yc.dia_chi, 
                   yc.do_uu_tien, yc.created_at, yc.trang_thai_phe_duyet,
                   nd.ho_va_ten as ten_nguoi_yeu_cau
            FROM yeu_cau_cuu_tros yc
            LEFT JOIN nguoi_dungs nd ON yc.id_nguoi_dung = nd.id
            WHERE yc.trang_thai_phe_duyet = 'cho_phe_duyet'
            ORDER BY 
                CASE yc.do_uu_tien 
                    WHEN 'khan_cap' THEN 1 
                    WHEN 'cao' THEN 2 
                    WHEN 'trung_binh' THEN 3 
                    ELSE 4 
                END,
                yc.created_at DESC
            LIMIT 20
        """)
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"DEBUG: Error fetching pending requests: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_volunteers_from_db():
    """Lấy danh sách tình nguyện viên"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT nd.id, nd.ho_va_ten, nd.email, nd.so_dien_thoai, nd.created_at,
                   COUNT(pp.id) as so_dot_phan_phoi
            FROM nguoi_dungs nd
            LEFT JOIN phan_phois pp ON nd.id = pp.id_tinh_nguyen_vien
            WHERE nd.vai_tro = 'tinh_nguyen_vien'
            GROUP BY nd.id, nd.ho_va_ten, nd.email, nd.so_dien_thoai, nd.created_at
            ORDER BY so_dot_phan_phoi DESC, nd.created_at DESC
            LIMIT 20
        """)
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"DEBUG: Error fetching volunteers: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_ai_predictions_from_db():
    """Lấy dự báo AI gần đây"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT tinh_thanh, loai_thien_tai, 
                   du_doan_nhu_cau_thuc_pham, du_doan_nhu_cau_nuoc, 
                   du_doan_nhu_cau_thuoc, du_doan_nhu_cau_cho_o,
                   ngay_du_bao, created_at
            FROM du_bao_ais
            ORDER BY ngay_du_bao DESC, created_at DESC
            LIMIT 10
        """)
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"DEBUG: Error fetching AI predictions: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _haversine_km(lat1, lon1, lat2, lon2):
    # Haversine formula to compute distance between two lat/lon points in kilometers
    from math import radians, sin, cos, sqrt, atan2

    try:
        lat1 = float(lat1)
        lon1 = float(lon1)
        lat2 = float(lat2)
        lon2 = float(lon2)
    except Exception:
        return None

    R = 6371.0  # Earth radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


class ActionCheckWeather(Action):
    def name(self) -> Text:
        return "action_check_weather"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        location = tracker.get_slot("location")
        if not location:
            dispatcher.utter_message(text="Bạn muốn xem thời tiết ở đâu? (Ví dụ: Thời tiết Hà Nội)")
            return []

        try:
            response = requests.get(f"{AI_SERVICE_URL}/weather/check/{location}")
            if response.status_code == 200:
                data = response.json()
                weather = data.get("weather", {})
                risk = data.get("disaster_risk", {})
                temp = weather.get("temp", "N/A")
                desc = weather.get("description", "")
                risk_level = risk.get("risk_level", "low")
                msg = f"🌤️ Thời tiết tại {location}:\n- Nhiệt độ: {temp}°C\n- Tình trạng: {desc}\n"
                if risk_level in ["high", "critical"]:
                    types = ", ".join(risk.get("disaster_types", []))
                    msg += f"\n⚠️ CẢNH BÁO: Có nguy cơ {types} (Mức độ: {risk_level})!"
                else:
                    msg += "\n✅ Chưa phát hiện nguy cơ thiên tai lớn."
                dispatcher.utter_message(text=msg)
            else:
                dispatcher.utter_message(text=f"Xin lỗi, tôi không lấy được thông tin thời tiết cho {location} lúc này.")
        except Exception as e:
            dispatcher.utter_message(text=f"Có lỗi xảy ra khi kết nối tới dịch vụ thời tiết: {str(e)}")
        return []


class ActionPredictRelief(Action):
    def name(self) -> Text:
        return "action_predict_relief"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        location = tracker.get_slot("location")
        if not location:
            dispatcher.utter_message(text="Bạn cần dự báo cứu trợ cho tỉnh nào? (Ví dụ: Dự báo cứu trợ Huế)")
            return []

        try:
            payload = {"tinh_thanh": location, "so_nguoi": 1000}
            response = requests.post(f"{AI_SERVICE_URL}/predict", json=payload)
            if response.status_code == 200:
                data = response.json()
                food = data.get("du_doan_nhu_cau_thuc_pham", 0)
                water = data.get("du_doan_nhu_cau_nuoc", 0)
                medicine = data.get("du_doan_nhu_cau_thuoc", 0)
                msg = f"📊 Dự báo nhu cầu cứu trợ cho {location} (giả định 1000 người trong 7 ngày):\n"
                msg += f"- 🍚 Thực phẩm: {food} kg\n"
                msg += f"- 💧 Nước uống: {water} lít\n"
                msg += f"- 💊 Thuốc men: {medicine} đơn vị\n"
                msg += f"\n(Dự báo dựa trên phương pháp: {data.get('method', 'heuristic')})"
                dispatcher.utter_message(text=msg)
            else:
                dispatcher.utter_message(text=f"Xin lỗi, tôi không thể dự báo ngay lúc này cho {location}.")
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi kết nối AI Service: {str(e)}")
        return []


class ActionGetUserRequests(Action):
    def name(self) -> Text:
        return "action_get_user_requests"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        user_id = tracker.get_slot("user_id")
        if not user_id:
            dispatcher.utter_message(text="Vui lòng đăng nhập hoặc cung cấp `user_id` để xem các yêu cầu của bạn.")
            return []

        try:
            items = _fetch_user_requests_from_db(user_id)
            if items is None:
                payload = {"message": "get_user_requests", "userId": user_id, "queryType": "user_requests"}
                resp = requests.post("http://localhost:3000/api/chat", json=payload, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and data.get("type") == "user_requests":
                        items = data.get("data", [])
                    else:
                        dispatcher.utter_message(text=str(data))
                        return []
                else:
                    dispatcher.utter_message(text="Không thể lấy yêu cầu cứu trợ lúc này. Vui lòng thử lại sau.")
                    return []

            if not items:
                dispatcher.utter_message(text="Bạn hiện chưa có yêu cầu cứu trợ nào.")
                return []

            lines = []
            for it in items[:5]:
                lines.append(f"• {it.get('loai_yeu_cau')} — {it.get('trang_thai')} — {it.get('created_at', '')}")
            msg = "Yêu cầu cứu trợ của bạn:\n" + "\n".join(lines)
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi kết nối tới hệ thống: {str(e)}")
        return []


class ActionGetNotifications(Action):
    def name(self) -> Text:
        return "action_get_notifications"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        user_id = tracker.get_slot("user_id")
        if not user_id:
            dispatcher.utter_message(text="Vui lòng đăng nhập hoặc cung cấp `user_id` để xem thông báo.")
            return []

        try:
            items = _fetch_notifications_from_db(user_id)
            if items is None:
                payload = {"message": "get_notifications", "userId": user_id, "queryType": "notifications"}
                resp = requests.post("http://localhost:3000/api/chat", json=payload, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and data.get("type") == "notifications":
                        items = data.get("data", [])
                    else:
                        dispatcher.utter_message(text=str(data))
                        return []
                else:
                    dispatcher.utter_message(text="Không thể lấy thông báo lúc này. Vui lòng thử lại sau.")
                    return []

            if not items:
                dispatcher.utter_message(text="Hiện tại bạn không có thông báo mới.")
                return []

            lines = []
            for it in items[:5]:
                lines.append(f"• {it.get('tieu_de')} — {it.get('created_at', '')}")
            msg = "Thông báo mới:\n" + "\n".join(lines)
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi kết nối tới hệ thống: {str(e)}")
        return []


class ActionGetCenters(Action):
    def name(self) -> Text:
        return "action_get_centers"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Try to get user coordinates from common slot names
        slot_names = [
            ("user_lat", "user_lon"),
            ("vi_do", "kinh_do"),
            ("latitude", "longitude"),
            ("lat", "lon"),
        ]

        user_lat = None
        user_lon = None
        for lat_slot, lon_slot in slot_names:
            lat = tracker.get_slot(lat_slot)
            lon = tracker.get_slot(lon_slot)
            if lat is not None and lon is not None:
                user_lat = lat
                user_lon = lon
                break

        try:
            items = _fetch_centers_from_db()
            if items is None:
                payload = {"message": "get_centers", "queryType": "centers"}
                # gửi kèm userId nếu có, để backend có thể log hoặc mở rộng logic sau này
                if user_id:
                    payload["userId"] = user_id
                resp = requests.post("http://localhost:3000/api/chat", json=payload, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and data.get("type") == "centers":
                        items = data.get("data", [])
                    else:
                        dispatcher.utter_message(text=str(data))
                        return []
                else:
                    dispatcher.utter_message(text="Không thể truy vấn trung tâm cứu trợ lúc này.")
                    return []

            if not items:
                dispatcher.utter_message(text="Không có trung tâm cứu trợ nào trong hệ thống.")
                return []

            # Try to get requested location filter (e.g. "Hà Nội")
            location_filter = tracker.get_slot("location")

            # If user coordinates available, compute distance and sort
            if user_lat is not None and user_lon is not None:
                centers_with_dist = []
                for it in items:
                    c_lat = it.get("vi_do") or it.get("latitude") or it.get("lat")
                    c_lon = it.get("kinh_do") or it.get("longitude") or it.get("lon")
                    if c_lat is None or c_lon is None:
                        # skip centers without coords
                        continue
                    dist = _haversine_km(user_lat, user_lon, c_lat, c_lon)
                    if dist is None:
                        continue
                    centers_with_dist.append((dist, it))
                
                centers_with_dist.sort(key=lambda x: x[0])
                
                # Apply text filter if exists
                if location_filter:
                    loc_lower = location_filter.lower()
                    centers_with_dist = [
                        (d, it) for (d, it) in centers_with_dist
                        if loc_lower in (it.get('dia_chi') or '').lower() or loc_lower in (it.get('ten_trung_tam') or '').lower()
                    ]

                # number of results to return; allow override from slot `max_centers` or `max_results`
                try:
                    slot_val = tracker.get_slot("max_centers") or tracker.get_slot("max_results")
                    max_n = int(slot_val) if slot_val is not None else 5
                except Exception:
                    max_n = 5
                if max_n <= 0:
                    max_n = 5
                max_n = min(max_n, 20)
                top = centers_with_dist[:max_n]
                
                if not top:
                    if location_filter:
                         dispatcher.utter_message(text=f"Không tìm thấy trung tâm cứu trợ nào ở {location_filter} gần bạn.")
                    else:
                         dispatcher.utter_message(text="Không tìm thấy trung tâm có tọa độ để tính khoảng cách.")
                    return []

                lines = []
                for dist, it in top:
                    lines.append(f"• {it.get('ten_trung_tam')} — {it.get('dia_chi')} — {it.get('so_lien_he')} — {dist:.1f} km")
                msg = f"Các trung tâm cứu trợ gần bạn nhất{' tại ' + location_filter if location_filter else ''}:\n" + "\n".join(lines)
                dispatcher.utter_message(text=msg)
                return []

            # Fallback: no user coords — create list from unfiltered items
            filtered_items = items
            
            # Apply text filter if exists (Crucial step added)
            if location_filter:
                loc_lower = location_filter.lower()
                filtered_items = [
                    it for it in items
                    if loc_lower in (it.get('dia_chi') or '').lower() or loc_lower in (it.get('ten_trung_tam') or '').lower()
                ]

            try:
                slot_val = tracker.get_slot("max_centers") or tracker.get_slot("max_results")
                max_n = int(slot_val) if slot_val is not None else 5
            except Exception:
                max_n = 5
            if max_n <= 0:
                max_n = 5
            max_n = min(max_n, 20)

            results = filtered_items[:max_n]
            
            if not results:
                if location_filter:
                    dispatcher.utter_message(text=f"Không tìm thấy trung tâm cứu trợ nào khớp với '{location_filter}' trong hệ thống.")
                else:
                    dispatcher.utter_message(text="Không có trung tâm cứu trợ nào trong hệ thống.")
                return []

            lines = []
            for it in results:
                lines.append(f"• {it.get('ten_trung_tam')} — {it.get('dia_chi')} — {it.get('so_lien_he')}")
            
            if location_filter:
                msg = f"Các trung tâm cứu trợ tại {location_filter}:\n" + "\n".join(lines)
            else:
                msg = "Một vài trung tâm cứu trợ:\n" + "\n".join(lines)
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi kết nối tới hệ thống: {str(e)}")
        return []


class ActionGetStatistics(Action):
    """Action lấy thống kê tổng quan hệ thống từ database"""
    
    def name(self) -> Text:
        return "action_get_statistics"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        try:
            stats = _fetch_statistics_from_db()
            
            if stats is None:
                dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
                return []
            
            # Định dạng vai trò
            role_names = {
                'admin': 'Quản trị viên',
                'tinh_nguyen_vien': 'Tình nguyện viên',
                'nguoi_dan': 'Người dân'
            }
            
            # Định dạng trạng thái phê duyệt
            approval_names = {
                'cho_phe_duyet': 'Chờ duyệt',
                'da_phe_duyet': 'Đã duyệt',
                'tu_choi': 'Từ chối'
            }
            
            msg = "📊 **THỐNG KÊ HỆ THỐNG RELIEFLINK**\n\n"
            
            msg += f"👥 **Người dùng**: {stats['total_users']} người\n"
            for role, count in stats.get('users_by_role', {}).items():
                role_vn = role_names.get(role, role)
                msg += f"   • {role_vn}: {count}\n"
            
            msg += f"\n📋 **Yêu cầu cứu trợ**: {stats['total_requests']} yêu cầu\n"
            for status, count in stats.get('requests_by_approval', {}).items():
                status_vn = approval_names.get(status, status)
                msg += f"   • {status_vn}: {count}\n"
            
            msg += f"\n🏥 **Trung tâm cứu trợ**: {stats['total_centers']} trung tâm\n"
            msg += f"📦 **Nguồn lực**: {stats['total_resources']} loại ({stats['total_resource_quantity']:,.0f} đơn vị)\n"
            msg += f"🚚 **Đợt phân phối**: {stats['total_distributions']} đợt\n"
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi lấy thống kê: {str(e)}")
        return []


class ActionGetResources(Action):
    """Action lấy danh sách nguồn lực cứu trợ từ database"""
    
    def name(self) -> Text:
        return "action_get_resources"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        location_filter = tracker.get_slot("location")
        
        try:
            items = _fetch_resources_from_db(location_filter)
            
            if items is None:
                dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
                return []
            
            if not items:
                if location_filter:
                    dispatcher.utter_message(text=f"Không tìm thấy nguồn lực nào tại {location_filter}.")
                else:
                    dispatcher.utter_message(text="Hiện không có nguồn lực nào trong hệ thống.")
                return []
            
            # Nhóm theo loại
            by_type = {}
            for item in items:
                loai = item.get('loai', 'Khác')
                if loai not in by_type:
                    by_type[loai] = []
                by_type[loai].append(item)
            
            location_text = f" tại {location_filter}" if location_filter else ""
            msg = f"📦 **NGUỒN LỰC CỨU TRỢ{location_text.upper()}**\n\n"
            
            for loai, resources in by_type.items():
                msg += f"**{loai}:**\n"
                for r in resources[:5]:  # Giới hạn 5 item mỗi loại
                    status_icon = "✅" if r.get('trang_thai') == 'san_sang' else "⚠️"
                    msg += f"   {status_icon} {r.get('ten_nguon_luc')}: {r.get('so_luong'):,} {r.get('don_vi')}\n"
                    msg += f"      📍 {r.get('ten_trung_tam')}\n"
                if len(resources) > 5:
                    msg += f"   ... và {len(resources) - 5} loại khác\n"
                msg += "\n"
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi lấy nguồn lực: {str(e)}")
        return []


class ActionGetDistributions(Action):
    """Action lấy lịch sử phân phối từ database"""
    
    def name(self) -> Text:
        return "action_get_distributions"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        try:
            items = _fetch_distributions_from_db(10)
            
            if items is None:
                dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
                return []
            
            if not items:
                dispatcher.utter_message(text="Chưa có đợt phân phối nào được ghi nhận.")
                return []
            
            status_names = {
                'dang_van_chuyen': '🚚 Đang vận chuyển',
                'da_giao': '✅ Đã giao',
                'cho_xu_ly': '⏳ Chờ xử lý',
                'huy': '❌ Đã hủy'
            }
            
            msg = "🚚 **LỊCH SỬ PHÂN PHỐI CỨU TRỢ**\n\n"
            
            for item in items:
                status = status_names.get(item.get('trang_thai'), item.get('trang_thai', 'N/A'))
                time_str = ""
                if item.get('thoi_gian_giao'):
                    time_str = item['thoi_gian_giao'].strftime("%d/%m/%Y %H:%M")
                elif item.get('thoi_gian_xuat'):
                    time_str = item['thoi_gian_xuat'].strftime("%d/%m/%Y %H:%M")
                
                msg += f"• **{item.get('ten_nguon_luc')}** ({item.get('so_luong'):,} {item.get('don_vi')})\n"
                msg += f"  {status}\n"
                msg += f"  📍 {item.get('dia_chi_yeu_cau', 'N/A')} | 👤 {item.get('ten_tinh_nguyen_vien')}\n"
                if time_str:
                    msg += f"  🕐 {time_str}\n"
                msg += "\n"
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi lấy lịch sử phân phối: {str(e)}")
        return []


class ActionGetPendingRequests(Action):
    """Action lấy các yêu cầu đang chờ duyệt từ database"""
    
    def name(self) -> Text:
        return "action_get_pending_requests"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        try:
            items = _fetch_pending_requests_from_db()
            
            if items is None:
                dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
                return []
            
            if not items:
                dispatcher.utter_message(text="✅ Không có yêu cầu nào đang chờ duyệt.")
                return []
            
            priority_icons = {
                'khan_cap': '🔴',
                'cao': '🟠',
                'trung_binh': '🟡',
                'thap': '🟢'
            }
            
            msg = f"⏳ **YÊU CẦU CHỜ PHÊ DUYỆT** ({len(items)} yêu cầu)\n\n"
            
            for item in items[:10]:
                priority = priority_icons.get(item.get('do_uu_tien'), '⚪')
                created = item.get('created_at')
                time_str = created.strftime("%d/%m/%Y %H:%M") if created else "N/A"
                
                msg += f"{priority} **{item.get('loai_yeu_cau')}** (ID: {item.get('id')})\n"
                msg += f"   👤 {item.get('ten_nguoi_yeu_cau', 'Ẩn danh')} | 👥 {item.get('so_nguoi')} người\n"
                if item.get('dia_chi'):
                    msg += f"   📍 {item.get('dia_chi')}\n"
                msg += f"   🕐 {time_str}\n\n"
            
            if len(items) > 10:
                msg += f"... và {len(items) - 10} yêu cầu khác\n"
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi lấy yêu cầu chờ duyệt: {str(e)}")
        return []


class ActionGetVolunteers(Action):
    """Action lấy danh sách tình nguyện viên từ database"""
    
    def name(self) -> Text:
        return "action_get_volunteers"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        try:
            items = _fetch_volunteers_from_db()
            
            if items is None:
                dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
                return []
            
            if not items:
                dispatcher.utter_message(text="Chưa có tình nguyện viên nào đăng ký.")
                return []
            
            msg = f"👥 **DANH SÁCH TÌNH NGUYỆN VIÊN** ({len(items)} người)\n\n"
            
            for item in items[:10]:
                distributions = item.get('so_dot_phan_phoi', 0)
                badge = ""
                if distributions >= 10:
                    badge = "🏆 "
                elif distributions >= 5:
                    badge = "⭐ "
                
                msg += f"{badge}**{item.get('ho_va_ten')}**\n"
                msg += f"   📧 {item.get('email')}\n"
                if item.get('so_dien_thoai'):
                    msg += f"   📱 {item.get('so_dien_thoai')}\n"
                msg += f"   🚚 {distributions} đợt phân phối\n\n"
            
            if len(items) > 10:
                msg += f"... và {len(items) - 10} tình nguyện viên khác\n"
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi lấy danh sách tình nguyện viên: {str(e)}")
        return []


class ActionGetAIPredictions(Action):
    """Action lấy dự báo AI từ database"""
    
    def name(self) -> Text:
        return "action_get_ai_predictions"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        try:
            items = _fetch_ai_predictions_from_db()
            
            if items is None:
                dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
                return []
            
            if not items:
                dispatcher.utter_message(text="Chưa có dự báo AI nào được lưu trữ.")
                return []
            
            disaster_icons = {
                'lu_lut': '🌊',
                'bao': '🌀',
                'dong_dat': '🏚️',
                'han_han': '☀️',
                'chay_rung': '🔥'
            }
            
            msg = "🤖 **DỰ BÁO AI GẦN ĐÂY**\n\n"
            
            for item in items:
                icon = disaster_icons.get(item.get('loai_thien_tai'), '⚠️')
                forecast_date = item.get('ngay_du_bao')
                date_str = forecast_date.strftime("%d/%m/%Y") if forecast_date else "N/A"
                
                msg += f"{icon} **{item.get('tinh_thanh')}** - {item.get('loai_thien_tai')}\n"
                msg += f"   📅 Dự báo cho: {date_str}\n"
                msg += f"   🍚 Thực phẩm: {item.get('du_doan_nhu_cau_thuc_pham', 0):,} kg\n"
                msg += f"   💧 Nước: {item.get('du_doan_nhu_cau_nuoc', 0):,} lít\n"
                msg += f"   💊 Thuốc: {item.get('du_doan_nhu_cau_thuoc', 0):,} đơn vị\n"
                msg += f"   🏠 Chỗ ở: {item.get('du_doan_nhu_cau_cho_o', 0):,} người\n\n"
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi lấy dự báo AI: {str(e)}")
        return []
