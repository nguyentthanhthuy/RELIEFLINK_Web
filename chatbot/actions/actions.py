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


# ============================================
# NEW ACTIONS FOR DATABASE QUERIES
# ============================================

def _fetch_requests_by_status_from_db(status: str = None, priority: str = None, limit: int = 20):
    """Lấy yêu cầu theo trạng thái hoặc độ ưu tiên"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        query = """
            SELECT yc.id, yc.loai_yeu_cau, yc.mo_ta, yc.so_nguoi, yc.dia_chi, 
                   yc.do_uu_tien, yc.trang_thai, yc.trang_thai_phe_duyet, yc.created_at,
                   nd.ho_va_ten as ten_nguoi_yeu_cau
            FROM yeu_cau_cuu_tros yc
            LEFT JOIN nguoi_dungs nd ON yc.id_nguoi_dung = nd.id
            WHERE 1=1
        """
        params = []
        
        if status:
            # Map common status names to database values
            status_map = {
                'cho_phe_duyet': 'cho_phe_duyet',
                'chờ duyệt': 'cho_phe_duyet',
                'pending': 'cho_phe_duyet',
                'da_phe_duyet': 'da_phe_duyet',
                'đã duyệt': 'da_phe_duyet',
                'approved': 'da_phe_duyet',
                'tu_choi': 'tu_choi',
                'từ chối': 'tu_choi',
                'rejected': 'tu_choi',
                'đang xử lý': 'dang_xu_ly',
                'hoàn thành': 'hoan_thanh',
                'completed': 'hoan_thanh'
            }
            mapped_status = status_map.get(status.lower(), status)
            query += " AND (yc.trang_thai_phe_duyet = %s OR yc.trang_thai = %s)"
            params.extend([mapped_status, mapped_status])
        
        if priority:
            # Map priority names
            priority_map = {
                'khan_cap': 'khan_cap',
                'khẩn cấp': 'khan_cap',
                'urgent': 'khan_cap',
                'emergency': 'khan_cap',
                'cao': 'cao',
                'high': 'cao',
                'trung_binh': 'trung_binh',
                'medium': 'trung_binh',
                'thap': 'thap',
                'low': 'thap'
            }
            mapped_priority = priority_map.get(priority.lower(), priority)
            query += " AND yc.do_uu_tien = %s"
            params.append(mapped_priority)
        
        query += """
            ORDER BY 
                CASE yc.do_uu_tien 
                    WHEN 'khan_cap' THEN 1 
                    WHEN 'cao' THEN 2 
                    WHEN 'trung_binh' THEN 3 
                    ELSE 4 
                END,
                yc.created_at DESC
            LIMIT %s
        """
        params.append(limit)
        
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"DEBUG: Error fetching requests by status: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_requests_by_type_from_db(request_type: str = None, limit: int = 20):
    """Lấy yêu cầu theo loại"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        query = """
            SELECT yc.id, yc.loai_yeu_cau, yc.mo_ta, yc.so_nguoi, yc.dia_chi, 
                   yc.do_uu_tien, yc.trang_thai, yc.trang_thai_phe_duyet, yc.created_at,
                   nd.ho_va_ten as ten_nguoi_yeu_cau
            FROM yeu_cau_cuu_tros yc
            LEFT JOIN nguoi_dungs nd ON yc.id_nguoi_dung = nd.id
            WHERE 1=1
        """
        params = []
        
        if request_type:
            query += " AND LOWER(yc.loai_yeu_cau) LIKE %s"
            params.append(f"%{request_type.lower()}%")
        
        query += " ORDER BY yc.created_at DESC LIMIT %s"
        params.append(limit)
        
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"DEBUG: Error fetching requests by type: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_resources_by_type_from_db(resource_type: str = None, limit: int = 30):
    """Lấy nguồn lực theo loại"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        query = """
            SELECT nl.id, nl.ten_nguon_luc, nl.loai, nl.so_luong, nl.don_vi, 
                   nl.trang_thai, nl.so_luong_toi_thieu,
                   tt.ten_trung_tam, tt.dia_chi
            FROM nguon_lucs nl
            JOIN trung_tam_cuu_tros tt ON nl.id_trung_tam = tt.id
            WHERE 1=1
        """
        params = []
        
        if resource_type:
            query += " AND (LOWER(nl.loai) LIKE %s OR LOWER(nl.ten_nguon_luc) LIKE %s)"
            params.extend([f"%{resource_type.lower()}%", f"%{resource_type.lower()}%"])
        
        query += " ORDER BY nl.loai, nl.ten_nguon_luc LIMIT %s"
        params.append(limit)
        
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"DEBUG: Error fetching resources by type: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_low_stock_resources_from_db(limit: int = 20):
    """Lấy danh sách nguồn lực sắp hết"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT nl.id, nl.ten_nguon_luc, nl.loai, nl.so_luong, nl.don_vi, 
                   nl.trang_thai, nl.so_luong_toi_thieu,
                   tt.ten_trung_tam, tt.dia_chi,
                   (nl.so_luong * 100.0 / NULLIF(nl.so_luong_toi_thieu, 0)) as percent_remaining
            FROM nguon_lucs nl
            JOIN trung_tam_cuu_tros tt ON nl.id_trung_tam = tt.id
            WHERE nl.so_luong <= nl.so_luong_toi_thieu * 1.5
            ORDER BY percent_remaining ASC, nl.so_luong ASC
            LIMIT %s
        """, (limit,))
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"DEBUG: Error fetching low stock resources: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_recent_activities_from_db(limit: int = 15):
    """Lấy hoạt động gần đây"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get recent requests
        cur.execute("""
            SELECT 'request' as activity_type, id, loai_yeu_cau as description, 
                   trang_thai_phe_duyet as status, created_at
            FROM yeu_cau_cuu_tros
            ORDER BY created_at DESC
            LIMIT %s
        """, (limit,))
        requests = cur.fetchall()
        
        # Get recent distributions
        cur.execute("""
            SELECT 'distribution' as activity_type, pp.id, nl.ten_nguon_luc as description,
                   pp.trang_thai as status, COALESCE(pp.thoi_gian_xuat, pp.thoi_gian_giao) as created_at
            FROM phan_phois pp
            JOIN nguon_lucs nl ON pp.id_nguon_luc = nl.id
            WHERE pp.thoi_gian_xuat IS NOT NULL OR pp.thoi_gian_giao IS NOT NULL
            ORDER BY COALESCE(pp.thoi_gian_xuat, pp.thoi_gian_giao) DESC
            LIMIT %s
        """, (limit,))
        distributions = cur.fetchall()
        
        cur.close()
        conn.close()
        
        # Combine and sort by time
        activities = list(requests) + list(distributions)
        activities.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
        
        return activities[:limit]
    except Exception as e:
        print(f"DEBUG: Error fetching recent activities: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_urgent_requests_from_db(limit: int = 20):
    """Lấy các yêu cầu khẩn cấp"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT yc.id, yc.loai_yeu_cau, yc.mo_ta, yc.so_nguoi, yc.dia_chi, 
                   yc.do_uu_tien, yc.trang_thai, yc.trang_thai_phe_duyet, yc.created_at,
                   nd.ho_va_ten as ten_nguoi_yeu_cau, nd.so_dien_thoai
            FROM yeu_cau_cuu_tros yc
            LEFT JOIN nguoi_dungs nd ON yc.id_nguoi_dung = nd.id
            WHERE yc.do_uu_tien IN ('khan_cap', 'cao')
            AND yc.trang_thai_phe_duyet != 'tu_choi'
            ORDER BY 
                CASE yc.do_uu_tien WHEN 'khan_cap' THEN 1 ELSE 2 END,
                yc.created_at DESC
            LIMIT %s
        """, (limit,))
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"DEBUG: Error fetching urgent requests: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _compare_resources_between_centers():
    """So sánh nguồn lực giữa các trung tâm"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT tt.id, tt.ten_trung_tam, tt.dia_chi,
                   COUNT(nl.id) as so_loai_nguon_luc,
                   SUM(nl.so_luong) as tong_so_luong,
                   SUM(CASE WHEN nl.trang_thai = 'san_sang' THEN nl.so_luong ELSE 0 END) as so_luong_san_sang
            FROM trung_tam_cuu_tros tt
            LEFT JOIN nguon_lucs nl ON tt.id = nl.id_trung_tam
            GROUP BY tt.id, tt.ten_trung_tam, tt.dia_chi
            ORDER BY tong_so_luong DESC NULLS LAST
        """)
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"DEBUG: Error comparing resources: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_total_affected_people():
    """Thống kê tổng số người được cứu trợ"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        stats = {}
        
        # Tổng người được hỗ trợ từ các yêu cầu đã hoàn thành
        cur.execute("""
            SELECT 
                SUM(so_nguoi) as tong_nguoi,
                COUNT(*) as so_yeu_cau
            FROM yeu_cau_cuu_tros
            WHERE trang_thai_phe_duyet = 'da_phe_duyet'
        """)
        row = cur.fetchone()
        stats['approved_total'] = row['tong_nguoi'] or 0
        stats['approved_requests'] = row['so_yeu_cau'] or 0
        
        # Phân tích theo loại yêu cầu
        cur.execute("""
            SELECT loai_yeu_cau, SUM(so_nguoi) as so_nguoi, COUNT(*) as so_yeu_cau
            FROM yeu_cau_cuu_tros
            WHERE trang_thai_phe_duyet = 'da_phe_duyet'
            GROUP BY loai_yeu_cau
            ORDER BY so_nguoi DESC
        """)
        stats['by_type'] = cur.fetchall()
        
        # Phân phối đã hoàn thành
        cur.execute("""
            SELECT COUNT(*) as so_dot_phan_phoi
            FROM phan_phois
            WHERE trang_thai = 'da_giao' OR trang_thai = 'hoan_thanh'
        """)
        row = cur.fetchone()
        stats['completed_distributions'] = row['so_dot_phan_phoi'] or 0
        
        cur.close()
        conn.close()
        return stats
    except Exception as e:
        print(f"DEBUG: Error fetching affected people: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


class ActionSearchRequestsByStatus(Action):
    """Action tìm kiếm yêu cầu theo trạng thái"""
    
    def name(self) -> Text:
        return "action_search_requests_by_status"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        status = tracker.get_slot("status")
        priority = tracker.get_slot("priority")
        
        if not status and not priority:
            dispatcher.utter_message(text="Vui lòng cung cấp trạng thái hoặc độ ưu tiên để tìm kiếm. Ví dụ: 'yêu cầu đang chờ duyệt' hoặc 'yêu cầu khẩn cấp'")
            return []
        
        try:
            items = _fetch_requests_by_status_from_db(status, priority)
            
            if items is None:
                dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
                return []
            
            if not items:
                filter_text = f"trạng thái '{status}'" if status else f"độ ưu tiên '{priority}'"
                dispatcher.utter_message(text=f"Không tìm thấy yêu cầu nào với {filter_text}.")
                return []
            
            priority_icons = {
                'khan_cap': '🔴',
                'cao': '🟠',
                'trung_binh': '🟡',
                'thap': '🟢'
            }
            
            filter_text = []
            if status:
                filter_text.append(f"trạng thái: {status}")
            if priority:
                filter_text.append(f"độ ưu tiên: {priority}")
            
            msg = f"📋 **KẾT QUẢ TÌM KIẾM** ({', '.join(filter_text)})\n"
            msg += f"Tìm thấy {len(items)} yêu cầu:\n\n"
            
            for item in items[:10]:
                icon = priority_icons.get(item.get('do_uu_tien'), '⚪')
                created = item.get('created_at')
                time_str = created.strftime("%d/%m/%Y") if created else "N/A"
                
                msg += f"{icon} **{item.get('loai_yeu_cau')}** (ID: {item.get('id')})\n"
                msg += f"   👤 {item.get('ten_nguoi_yeu_cau', 'Ẩn danh')} | 👥 {item.get('so_nguoi')} người\n"
                msg += f"   📊 Trạng thái: {item.get('trang_thai_phe_duyet')}\n"
                if item.get('dia_chi'):
                    msg += f"   📍 {item.get('dia_chi')}\n"
                msg += f"   🕐 {time_str}\n\n"
            
            if len(items) > 10:
                msg += f"... và {len(items) - 10} yêu cầu khác\n"
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi tìm kiếm: {str(e)}")
        return []


class ActionSearchRequestsByType(Action):
    """Action tìm kiếm yêu cầu theo loại"""
    
    def name(self) -> Text:
        return "action_search_requests_by_type"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        request_type = tracker.get_slot("request_type")
        
        if not request_type:
            dispatcher.utter_message(text="Vui lòng cho biết loại yêu cầu bạn muốn tìm. Ví dụ: 'yêu cầu loại thực phẩm' hoặc 'yêu cầu thuốc men'")
            return []
        
        try:
            items = _fetch_requests_by_type_from_db(request_type)
            
            if items is None:
                dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
                return []
            
            if not items:
                dispatcher.utter_message(text=f"Không tìm thấy yêu cầu nào loại '{request_type}'.")
                return []
            
            msg = f"📋 **YÊU CẦU LOẠI '{request_type.upper()}'**\n"
            msg += f"Tìm thấy {len(items)} yêu cầu:\n\n"
            
            for item in items[:10]:
                created = item.get('created_at')
                time_str = created.strftime("%d/%m/%Y") if created else "N/A"
                
                msg += f"• **{item.get('loai_yeu_cau')}** (ID: {item.get('id')})\n"
                msg += f"   👤 {item.get('ten_nguoi_yeu_cau', 'Ẩn danh')} | 👥 {item.get('so_nguoi')} người\n"
                msg += f"   📊 {item.get('trang_thai_phe_duyet')} | 🕐 {time_str}\n"
                if item.get('dia_chi'):
                    msg += f"   📍 {item.get('dia_chi')}\n"
                msg += "\n"
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi tìm kiếm: {str(e)}")
        return []


class ActionSearchResourcesByType(Action):
    """Action tìm kiếm nguồn lực theo loại"""
    
    def name(self) -> Text:
        return "action_search_resources_by_type"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        resource_type = tracker.get_slot("resource_type")
        location = tracker.get_slot("location")
        
        if not resource_type:
            dispatcher.utter_message(text="Vui lòng cho biết loại nguồn lực bạn muốn tìm. Ví dụ: 'nguồn lực thực phẩm' hoặc 'kiểm tra kho thuốc'")
            return []
        
        try:
            items = _fetch_resources_by_type_from_db(resource_type)
            
            if items is None:
                dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
                return []
            
            # Filter by location if provided
            if location and items:
                loc_lower = location.lower()
                items = [it for it in items if loc_lower in (it.get('dia_chi') or '').lower() 
                        or loc_lower in (it.get('ten_trung_tam') or '').lower()]
            
            if not items:
                location_text = f" tại {location}" if location else ""
                dispatcher.utter_message(text=f"Không tìm thấy nguồn lực loại '{resource_type}'{location_text}.")
                return []
            
            total_quantity = sum(it.get('so_luong', 0) for it in items)
            location_text = f" tại {location}" if location else ""
            
            msg = f"📦 **NGUỒN LỰC '{resource_type.upper()}'{location_text.upper()}**\n"
            msg += f"Tìm thấy {len(items)} loại, tổng: {total_quantity:,} đơn vị\n\n"
            
            for item in items[:10]:
                status_icon = "✅" if item.get('trang_thai') == 'san_sang' else "⚠️"
                low_stock = item.get('so_luong', 0) <= (item.get('so_luong_toi_thieu', 10) or 10)
                warning = " 🔴 SẮP HẾT" if low_stock else ""
                
                msg += f"{status_icon} **{item.get('ten_nguon_luc')}**{warning}\n"
                msg += f"   Số lượng: {item.get('so_luong', 0):,} {item.get('don_vi')}\n"
                msg += f"   📍 {item.get('ten_trung_tam')} - {item.get('dia_chi')}\n\n"
            
            if len(items) > 10:
                msg += f"... và {len(items) - 10} loại khác\n"
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi tìm kiếm: {str(e)}")
        return []


class ActionGetLowStockResources(Action):
    """Action lấy danh sách nguồn lực sắp hết"""
    
    def name(self) -> Text:
        return "action_get_low_stock_resources"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        try:
            items = _fetch_low_stock_resources_from_db()
            
            if items is None:
                dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
                return []
            
            if not items:
                dispatcher.utter_message(text="✅ Tuyệt vời! Không có nguồn lực nào ở mức thấp.")
                return []
            
            msg = f"⚠️ **CẢNH BÁO: NGUỒN LỰC SẮP HẾT** ({len(items)} loại)\n\n"
            
            for item in items:
                percent = item.get('percent_remaining', 0)
                if percent and percent < 50:
                    icon = "🔴"
                elif percent and percent < 100:
                    icon = "🟠"
                else:
                    icon = "🟡"
                
                msg += f"{icon} **{item.get('ten_nguon_luc')}** ({item.get('loai')})\n"
                msg += f"   Còn: {item.get('so_luong', 0):,} / {item.get('so_luong_toi_thieu', 0):,} {item.get('don_vi')}"
                if percent:
                    msg += f" ({percent:.0f}%)"
                msg += f"\n   📍 {item.get('ten_trung_tam')}\n\n"
            
            msg += "\n💡 Đề xuất: Cần bổ sung các nguồn lực trên càng sớm càng tốt."
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi kiểm tra: {str(e)}")
        return []


class ActionGetRecentActivities(Action):
    """Action lấy hoạt động gần đây"""
    
    def name(self) -> Text:
        return "action_get_recent_activities"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        try:
            items = _fetch_recent_activities_from_db()
            
            if items is None:
                dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
                return []
            
            if not items:
                dispatcher.utter_message(text="Chưa có hoạt động nào được ghi nhận.")
                return []
            
            msg = "🔔 **HOẠT ĐỘNG GẦN ĐÂY**\n\n"
            
            for item in items[:15]:
                activity_type = item.get('activity_type')
                created = item.get('created_at')
                time_str = created.strftime("%d/%m %H:%M") if created else "N/A"
                
                if activity_type == 'request':
                    icon = "📋"
                    type_name = "Yêu cầu mới"
                else:
                    icon = "🚚"
                    type_name = "Phân phối"
                
                msg += f"{icon} [{time_str}] {type_name}: {item.get('description')}\n"
                msg += f"   Trạng thái: {item.get('status')}\n\n"
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi lấy hoạt động: {str(e)}")
        return []


class ActionGetUrgentRequests(Action):
    """Action lấy các yêu cầu khẩn cấp"""
    
    def name(self) -> Text:
        return "action_get_urgent_requests"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        try:
            items = _fetch_urgent_requests_from_db()
            
            if items is None:
                dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
                return []
            
            if not items:
                dispatcher.utter_message(text="✅ Hiện không có yêu cầu khẩn cấp nào.")
                return []
            
            msg = f"🚨 **YÊU CẦU KHẨN CẤP** ({len(items)} yêu cầu)\n\n"
            
            for item in items:
                priority = item.get('do_uu_tien')
                icon = "🔴" if priority == 'khan_cap' else "🟠"
                created = item.get('created_at')
                time_str = created.strftime("%d/%m/%Y %H:%M") if created else "N/A"
                
                msg += f"{icon} **{item.get('loai_yeu_cau')}** (ID: {item.get('id')})\n"
                msg += f"   👤 {item.get('ten_nguoi_yeu_cau', 'Ẩn danh')}"
                if item.get('so_dien_thoai'):
                    msg += f" | 📱 {item.get('so_dien_thoai')}"
                msg += f"\n   👥 {item.get('so_nguoi')} người | 🕐 {time_str}\n"
                if item.get('dia_chi'):
                    msg += f"   📍 {item.get('dia_chi')}\n"
                if item.get('mo_ta'):
                    msg += f"   📝 {item.get('mo_ta')[:100]}...\n" if len(item.get('mo_ta', '')) > 100 else f"   📝 {item.get('mo_ta')}\n"
                msg += "\n"
            
            msg += "⚠️ Các yêu cầu này cần được xử lý ngay!"
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi lấy yêu cầu khẩn cấp: {str(e)}")
        return []


class ActionChatbotHelp(Action):
    """Action hiển thị hướng dẫn sử dụng chatbot"""
    
    def name(self) -> Text:
        return "action_chatbot_help"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        msg = """🤖 **HƯỚNG DẪN SỬ DỤNG CHATBOT RELIEFLINK**

📊 **Thống kê & Báo cáo:**
• "Thống kê hệ thống" - Xem tổng quan
• "Số liệu tổng quan" - Dashboard stats
• "Tổng số người được cứu trợ" - Thống kê người nhận hỗ trợ

🏥 **Trung tâm cứu trợ:**
• "Danh sách trung tâm" - Xem tất cả trung tâm
• "Trung tâm gần Hà Nội" - Tìm theo địa điểm

📦 **Nguồn lực:**
• "Kiểm tra kho hàng" - Xem nguồn lực
• "Nguồn lực sắp hết" - Cảnh báo thiếu hàng
• "Nguồn lực loại thực phẩm" - Tìm theo loại
• "So sánh nguồn lực giữa các trung tâm"

📋 **Yêu cầu cứu trợ:**
• "Yêu cầu đang chờ duyệt" - Yêu cầu chờ xử lý
• "Yêu cầu khẩn cấp" - Các trường hợp gấp
• "Yêu cầu của tôi" - Yêu cầu cá nhân
• "Yêu cầu loại thực phẩm" - Tìm theo loại

🚚 **Phân phối:**
• "Lịch sử phân phối" - Các đợt đã thực hiện

🌤️ **Thời tiết & Dự báo:**
• "Thời tiết Hà Nội" - Xem thời tiết
• "Dự báo cứu trợ Đà Nẵng" - Dự báo nhu cầu
• "Dự báo AI" - Xem các dự báo AI

👥 **Người dùng:**
• "Danh sách tình nguyện viên"
• "Thông báo của tôi"

🔔 **Hoạt động:**
• "Hoạt động gần đây" - Cập nhật mới nhất

💡 Tip: Bạn có thể kết hợp với tên địa điểm để tìm kiếm cụ thể hơn!"""
        
        dispatcher.utter_message(text=msg)
        return []


class ActionCompareResources(Action):
    """Action so sánh nguồn lực giữa các trung tâm"""
    
    def name(self) -> Text:
        return "action_compare_resources"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        try:
            items = _compare_resources_between_centers()
            
            if items is None:
                dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
                return []
            
            if not items:
                dispatcher.utter_message(text="Chưa có trung tâm nào trong hệ thống.")
                return []
            
            msg = "📊 **SO SÁNH NGUỒN LỰC GIỮA CÁC TRUNG TÂM**\n\n"
            
            # Find max for percentage calculation
            max_total = max((it.get('tong_so_luong', 0) or 0) for it in items) if items else 1
            
            for i, item in enumerate(items, 1):
                total = item.get('tong_so_luong', 0) or 0
                ready = item.get('so_luong_san_sang', 0) or 0
                types_count = item.get('so_loai_nguon_luc', 0) or 0
                
                # Progress bar
                if max_total > 0:
                    bar_length = int((total / max_total) * 10)
                    bar = "█" * bar_length + "░" * (10 - bar_length)
                else:
                    bar = "░" * 10
                
                medal = ""
                if i == 1:
                    medal = "🥇 "
                elif i == 2:
                    medal = "🥈 "
                elif i == 3:
                    medal = "🥉 "
                
                msg += f"{medal}**{item.get('ten_trung_tam')}**\n"
                msg += f"   📍 {item.get('dia_chi')}\n"
                msg += f"   [{bar}] {total:,} đơn vị ({types_count} loại)\n"
                msg += f"   ✅ Sẵn sàng: {ready:,} đơn vị\n\n"
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi so sánh: {str(e)}")
        return []


class ActionGetTotalAffectedPeople(Action):
    """Action thống kê tổng số người được cứu trợ"""
    
    def name(self) -> Text:
        return "action_get_total_affected_people"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        try:
            stats = _fetch_total_affected_people()
            
            if stats is None:
                dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
                return []
            
            msg = "👥 **THỐNG KÊ NGƯỜI ĐƯỢC CỨU TRỢ**\n\n"
            
            msg += f"✅ **Tổng số người được phê duyệt hỗ trợ:** {stats.get('approved_total', 0):,} người\n"
            msg += f"📋 **Số yêu cầu đã được duyệt:** {stats.get('approved_requests', 0):,} yêu cầu\n"
            msg += f"🚚 **Số đợt phân phối hoàn thành:** {stats.get('completed_distributions', 0):,} đợt\n\n"
            
            by_type = stats.get('by_type', [])
            if by_type:
                msg += "📊 **Phân loại theo nhu cầu:**\n"
                for item in by_type[:5]:
                    msg += f"   • {item.get('loai_yeu_cau')}: {(item.get('so_nguoi') or 0):,} người ({item.get('so_yeu_cau')} yêu cầu)\n"
            
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi lấy thống kê: {str(e)}")
        return []
