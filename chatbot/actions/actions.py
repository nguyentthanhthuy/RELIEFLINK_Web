from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from decimal import Decimal
import requests
import json
import os
import logging

logger = logging.getLogger(__name__)

try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except Exception as e:
    psycopg2 = None
    PSYCOPG2_AVAILABLE = False
    logger.warning(f"psycopg2 not available: {e}")

AI_SERVICE_URL = os.environ.get("AI_SERVICE_URL", "http://localhost:8000")


def _get_db_conn():
    """Get database connection. Returns None if unavailable."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.warning("DATABASE_URL environment variable not set")
        return None
    if not PSYCOPG2_AVAILABLE:
        logger.warning("psycopg2 is not installed")
        return None
    try:
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None


def _decimal_to_float(val):
    """Convert Decimal to float for JSON serialization."""
    if isinstance(val, Decimal):
        return float(val)
    return val


def _fetch_user_requests_from_db(user_id: str):
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT id, loai_yeu_cau, mo_ta, so_nguoi, trang_thai, created_at, dia_chi,
                   vi_do, kinh_do, do_uu_tien, trang_thai_phe_duyet
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
    except Exception as e:
        logger.error(f"Error fetching user requests: {e}")
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
    except Exception as e:
        logger.error(f"Error fetching notifications: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_centers_from_db(location_filter: Optional[str] = None):
    """Fetch relief centers, optionally filtered by location/name."""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if location_filter:
            cur.execute(
                """
                SELECT id, ten_trung_tam, dia_chi, so_lien_he, vi_do, kinh_do, nguoi_quan_ly
                FROM trung_tam_cuu_tros
                WHERE ten_trung_tam ILIKE %s OR dia_chi ILIKE %s
                LIMIT 50
                """,
                (f"%{location_filter}%", f"%{location_filter}%")
            )
        else:
            cur.execute(
                """
                SELECT id, ten_trung_tam, dia_chi, so_lien_he, vi_do, kinh_do, nguoi_quan_ly
                FROM trung_tam_cuu_tros
                LIMIT 50
                """
            )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Error fetching centers: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_center_by_name(name: str):
    """Fetch a specific center by name (partial match)."""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT id, ten_trung_tam, dia_chi, so_lien_he, vi_do, kinh_do, nguoi_quan_ly
            FROM trung_tam_cuu_tros
            WHERE ten_trung_tam ILIKE %s OR dia_chi ILIKE %s
            ORDER BY 
                CASE WHEN ten_trung_tam ILIKE %s THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (f"%{name}%", f"%{name}%", f"%{name}%")
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row
    except Exception as e:
        logger.error(f"Error fetching center by name: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_resources_from_db(center_id: Optional[int] = None, resource_type: Optional[str] = None):
    """Fetch resources, optionally filtered by center or type."""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        query = """
            SELECT nl.id, nl.ten_nguon_luc, nl.loai, nl.so_luong, nl.don_vi, 
                   nl.trang_thai, nl.so_luong_toi_thieu,
                   tt.ten_trung_tam, tt.dia_chi as trung_tam_dia_chi
            FROM nguon_lucs nl
            JOIN trung_tam_cuu_tros tt ON nl.id_trung_tam = tt.id
            WHERE 1=1
        """
        params = []
        if center_id:
            query += " AND nl.id_trung_tam = %s"
            params.append(center_id)
        if resource_type:
            query += " AND (nl.loai ILIKE %s OR nl.ten_nguon_luc ILIKE %s)"
            params.extend([f"%{resource_type}%", f"%{resource_type}%"])
        query += " ORDER BY nl.loai, nl.ten_nguon_luc LIMIT 100"
        
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Error fetching resources: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_system_stats():
    """Fetch system-wide statistics."""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        stats = {}
        
        # Count users by role
        cur.execute("""
            SELECT vai_tro, COUNT(*) as count FROM nguoi_dungs GROUP BY vai_tro
        """)
        stats['users'] = {row['vai_tro']: row['count'] for row in cur.fetchall()}
        
        # Count centers
        cur.execute("SELECT COUNT(*) as count FROM trung_tam_cuu_tros")
        stats['centers'] = cur.fetchone()['count']
        
        # Count requests by status
        cur.execute("""
            SELECT trang_thai_phe_duyet, COUNT(*) as count 
            FROM yeu_cau_cuu_tros 
            GROUP BY trang_thai_phe_duyet
        """)
        stats['requests'] = {row['trang_thai_phe_duyet']: row['count'] for row in cur.fetchall()}
        
        # Count resources by status
        cur.execute("""
            SELECT trang_thai, COUNT(*) as count, SUM(so_luong) as total
            FROM nguon_lucs 
            GROUP BY trang_thai
        """)
        stats['resources'] = {row['trang_thai']: {'count': row['count'], 'total': row['total']} for row in cur.fetchall()}
        
        # Count distributions by status
        cur.execute("""
            SELECT trang_thai, COUNT(*) as count 
            FROM phan_phois 
            GROUP BY trang_thai
        """)
        stats['distributions'] = {row['trang_thai']: row['count'] for row in cur.fetchall()}
        
        cur.close()
        conn.close()
        return stats
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_pending_requests(limit: int = 10):
    """Fetch pending relief requests."""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT y.id, y.loai_yeu_cau, y.mo_ta, y.so_nguoi, y.do_uu_tien, 
                   y.dia_chi, y.created_at, y.diem_uu_tien,
                   n.ho_va_ten as nguoi_yeu_cau
            FROM yeu_cau_cuu_tros y
            LEFT JOIN nguoi_dungs n ON y.id_nguoi_dung = n.id
            WHERE y.trang_thai_phe_duyet = 'cho_phe_duyet'
            ORDER BY y.diem_uu_tien DESC, y.created_at ASC
            LIMIT %s
            """,
            (limit,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Error fetching pending requests: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _fetch_volunteers(limit: int = 20):
    """Fetch volunteers list."""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT id, ho_va_ten, email, so_dien_thoai, vi_do, kinh_do
            FROM nguoi_dungs
            WHERE vai_tro = 'tinh_nguyen_vien'
            ORDER BY ho_va_ten
            LIMIT %s
            """,
            (limit,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Error fetching volunteers: {e}")
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


class ActionFindReliefCenters(Action):
    """Find relief centers - supports location filtering and returns coordinates."""
    
    def name(self) -> Text:
        return "action_find_relief_centers"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Get location filter from slot
        location = tracker.get_slot("location")
        
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
            # Fetch centers with optional location filter
            items = _fetch_centers_from_db(location_filter=location)
            
            if items is None:
                # Fallback to API if DB not available
                payload = {"message": "get_centers", "queryType": "centers"}
                if location:
                    payload["location"] = location
                resp = requests.post("http://localhost:3000/api/chat", json=payload, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and data.get("type") == "centers":
                        items = data.get("data", [])
                    else:
                        dispatcher.utter_message(text=str(data))
                        return []
                else:
                    dispatcher.utter_message(text="Không thể truy vấn trung tâm cứu trợ lúc này. Vui lòng kiểm tra kết nối database.")
                    return []

            if not items:
                if location:
                    dispatcher.utter_message(text=f"Không tìm thấy trung tâm cứu trợ tại {location}.")
                else:
                    dispatcher.utter_message(text="Không có trung tâm cứu trợ nào trong hệ thống.")
                return []

            # If user coordinates available, compute distance and sort
            if user_lat is not None and user_lon is not None:
                centers_with_dist = []
                for it in items:
                    c_lat = it.get("vi_do") or it.get("latitude") or it.get("lat")
                    c_lon = it.get("kinh_do") or it.get("longitude") or it.get("lon")
                    if c_lat is None or c_lon is None:
                        # Include centers without coords but mark distance as unknown
                        centers_with_dist.append((float('inf'), it))
                        continue
                    try:
                        dist = _haversine_km(float(user_lat), float(user_lon), float(c_lat), float(c_lon))
                    except Exception:
                        dist = _haversine_km(user_lat, user_lon, c_lat, c_lon)
                    if dist is None:
                        centers_with_dist.append((float('inf'), it))
                    else:
                        centers_with_dist.append((dist, it))
                
                centers_with_dist.sort(key=lambda x: x[0])
                max_n = min(5, len(centers_with_dist))
                top = centers_with_dist[:max_n]

                lines = []
                for dist, it in top:
                    vi_do = _decimal_to_float(it.get('vi_do'))
                    kinh_do = _decimal_to_float(it.get('kinh_do'))
                    coord_str = f"(Vĩ độ: {vi_do}, Kinh độ: {kinh_do})" if vi_do and kinh_do else "(Chưa có tọa độ)"
                    dist_str = f"{dist:.1f} km" if dist != float('inf') else "N/A"
                    lines.append(f"• {it.get('ten_trung_tam')}\n  📍 {it.get('dia_chi', 'N/A')}\n  📞 {it.get('so_lien_he', 'N/A')}\n  🗺️ {coord_str}\n  📏 Khoảng cách: {dist_str}")
                
                msg = "🏥 Các trung tâm cứu trợ gần bạn nhất:\n\n" + "\n\n".join(lines)
                dispatcher.utter_message(text=msg)
                return []

            # No user coords - return centers with full details including coordinates
            max_n = min(5, len(items))
            lines = []
            for it in items[:max_n]:
                vi_do = _decimal_to_float(it.get('vi_do'))
                kinh_do = _decimal_to_float(it.get('kinh_do'))
                coord_str = f"(Vĩ độ: {vi_do}, Kinh độ: {kinh_do})" if vi_do and kinh_do else "(Chưa có tọa độ)"
                lines.append(f"• {it.get('ten_trung_tam')}\n  📍 {it.get('dia_chi', 'N/A')}\n  📞 {it.get('so_lien_he', 'N/A')}\n  🗺️ {coord_str}")
            
            header = f"🏥 Trung tâm cứu trợ tại {location}:\n\n" if location else "🏥 Các trung tâm cứu trợ:\n\n"
            msg = header + "\n\n".join(lines)
            dispatcher.utter_message(text=msg)
            
        except Exception as e:
            logger.error(f"Error in ActionFindReliefCenters: {e}")
            dispatcher.utter_message(text=f"Lỗi khi kết nối tới hệ thống: {str(e)}")
        return []


class ActionGetCenterDetails(Action):
    """Get detailed information about a specific center including coordinates."""
    
    def name(self) -> Text:
        return "action_get_center_details"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        location = tracker.get_slot("location")
        if not location:
            dispatcher.utter_message(text="Bạn muốn xem thông tin trung tâm cứu trợ nào? (Ví dụ: Trung tâm cứu trợ Đà Nẵng)")
            return []

        try:
            center = _fetch_center_by_name(location)
            
            if not center:
                dispatcher.utter_message(text=f"Không tìm thấy trung tâm cứu trợ '{location}'. Thử tìm với tên khác hoặc xem danh sách các trung tâm.")
                return []
            
            vi_do = _decimal_to_float(center.get('vi_do'))
            kinh_do = _decimal_to_float(center.get('kinh_do'))
            
            msg = f"🏥 **{center.get('ten_trung_tam')}**\n\n"
            msg += f"📍 Địa chỉ: {center.get('dia_chi', 'N/A')}\n"
            msg += f"📞 Số liên hệ: {center.get('so_lien_he', 'N/A')}\n"
            msg += f"👤 Người quản lý: {center.get('nguoi_quan_ly', 'N/A')}\n"
            
            if vi_do and kinh_do:
                msg += f"\n🗺️ **Tọa độ:**\n"
                msg += f"  • Vĩ độ (Latitude): {vi_do}\n"
                msg += f"  • Kinh độ (Longitude): {kinh_do}\n"
                msg += f"\n📌 Link Google Maps: https://www.google.com/maps?q={vi_do},{kinh_do}"
            else:
                msg += f"\n⚠️ Chưa có thông tin tọa độ cho trung tâm này."
            
            dispatcher.utter_message(text=msg)
            
        except Exception as e:
            logger.error(f"Error in ActionGetCenterDetails: {e}")
            dispatcher.utter_message(text=f"Lỗi khi truy vấn thông tin: {str(e)}")
        return []


class ActionGetResources(Action):
    """Get available resources/supplies information."""
    
    def name(self) -> Text:
        return "action_get_resources"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        location = tracker.get_slot("location")
        resource_type = tracker.get_slot("resource_type")

        try:
            # If location specified, find center first
            center_id = None
            if location:
                center = _fetch_center_by_name(location)
                if center:
                    center_id = center.get('id')
            
            items = _fetch_resources_from_db(center_id=center_id, resource_type=resource_type)
            
            if items is None:
                dispatcher.utter_message(text="Không thể truy vấn nguồn lực lúc này. Vui lòng kiểm tra kết nối database.")
                return []

            if not items:
                msg = "Không tìm thấy nguồn lực"
                if location:
                    msg += f" tại {location}"
                if resource_type:
                    msg += f" loại '{resource_type}'"
                dispatcher.utter_message(text=msg + ".")
                return []

            # Group by center
            by_center = {}
            for it in items:
                center_name = it.get('ten_trung_tam', 'Không rõ')
                if center_name not in by_center:
                    by_center[center_name] = []
                by_center[center_name].append(it)
            
            lines = []
            for center_name, resources in list(by_center.items())[:3]:  # Limit to 3 centers
                lines.append(f"🏥 **{center_name}**:")
                for r in resources[:5]:  # Limit to 5 resources per center
                    status_emoji = "✅" if r.get('trang_thai') == 'san_sang' else "⚠️"
                    lines.append(f"  {status_emoji} {r.get('ten_nguon_luc')} — {r.get('so_luong')} {r.get('don_vi')} ({r.get('loai')})")
            
            header = "📦 Nguồn lực cứu trợ"
            if location:
                header += f" tại {location}"
            header += ":\n\n"
            msg = header + "\n".join(lines)
            dispatcher.utter_message(text=msg)
            
        except Exception as e:
            logger.error(f"Error in ActionGetResources: {e}")
            dispatcher.utter_message(text=f"Lỗi khi truy vấn nguồn lực: {str(e)}")
        return []


class ActionGetSystemStats(Action):
    """Get system-wide statistics."""
    
    def name(self) -> Text:
        return "action_get_system_stats"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        try:
            stats = _fetch_system_stats()
            
            if stats is None:
                dispatcher.utter_message(text="Không thể lấy thống kê hệ thống lúc này. Vui lòng kiểm tra kết nối database.")
                return []

            msg = "📊 **Thống kê Hệ thống ReliefLink**\n\n"
            
            # Users
            users = stats.get('users', {})
            total_users = sum(users.values())
            msg += f"👥 **Người dùng:** {total_users} tổng\n"
            for role, count in users.items():
                role_name = {'admin': 'Quản trị viên', 'tinh_nguyen_vien': 'Tình nguyện viên', 'nguoi_dan': 'Người dân'}.get(role, role)
                msg += f"  • {role_name}: {count}\n"
            
            # Centers
            msg += f"\n🏥 **Trung tâm cứu trợ:** {stats.get('centers', 0)}\n"
            
            # Requests
            requests = stats.get('requests', {})
            total_requests = sum(requests.values())
            msg += f"\n📋 **Yêu cầu cứu trợ:** {total_requests} tổng\n"
            status_names = {'cho_phe_duyet': 'Chờ phê duyệt', 'da_phe_duyet': 'Đã phê duyệt', 'tu_choi': 'Từ chối'}
            for status, count in requests.items():
                msg += f"  • {status_names.get(status, status)}: {count}\n"
            
            # Distributions
            distributions = stats.get('distributions', {})
            total_dist = sum(distributions.values())
            msg += f"\n🚚 **Phân phối:** {total_dist} đợt\n"
            
            dispatcher.utter_message(text=msg)
            
        except Exception as e:
            logger.error(f"Error in ActionGetSystemStats: {e}")
            dispatcher.utter_message(text=f"Lỗi khi lấy thống kê: {str(e)}")
        return []


class ActionGetPendingRequests(Action):
    """Get pending relief requests for admin/volunteers."""
    
    def name(self) -> Text:
        return "action_get_pending_requests"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        try:
            items = _fetch_pending_requests(limit=10)
            
            if items is None:
                dispatcher.utter_message(text="Không thể truy vấn yêu cầu chờ xử lý lúc này.")
                return []

            if not items:
                dispatcher.utter_message(text="🎉 Không có yêu cầu cứu trợ nào đang chờ phê duyệt!")
                return []

            lines = []
            for it in items[:5]:
                priority_emoji = {"cao": "🔴", "trung_binh": "🟡", "thap": "🟢"}.get(it.get('do_uu_tien', ''), "⚪")
                lines.append(f"{priority_emoji} #{it.get('id')} — {it.get('loai_yeu_cau')}\n  📍 {it.get('dia_chi', 'N/A')}\n  👥 {it.get('so_nguoi', 0)} người — Điểm ưu tiên: {it.get('diem_uu_tien', 0)}")
            
            msg = f"📋 **Yêu cầu cứu trợ chờ phê duyệt ({len(items)} yêu cầu):**\n\n" + "\n\n".join(lines)
            dispatcher.utter_message(text=msg)
            
        except Exception as e:
            logger.error(f"Error in ActionGetPendingRequests: {e}")
            dispatcher.utter_message(text=f"Lỗi khi truy vấn: {str(e)}")
        return []


class ActionGetVolunteers(Action):
    """Get list of volunteers."""
    
    def name(self) -> Text:
        return "action_get_volunteers"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        try:
            items = _fetch_volunteers(limit=10)
            
            if items is None:
                dispatcher.utter_message(text="Không thể truy vấn danh sách tình nguyện viên lúc này.")
                return []

            if not items:
                dispatcher.utter_message(text="Chưa có tình nguyện viên nào trong hệ thống.")
                return []

            lines = []
            for it in items[:10]:
                lines.append(f"• {it.get('ho_va_ten')} — 📞 {it.get('so_dien_thoai', 'N/A')} — ✉️ {it.get('email', 'N/A')}")
            
            msg = f"👥 **Danh sách Tình nguyện viên ({len(items)} người):**\n\n" + "\n".join(lines)
            dispatcher.utter_message(text=msg)
            
        except Exception as e:
            logger.error(f"Error in ActionGetVolunteers: {e}")
            dispatcher.utter_message(text=f"Lỗi khi truy vấn: {str(e)}")
        return []


class ActionCheckDbConnection(Action):
    """Check database connection status - useful for debugging."""
    
    def name(self) -> Text:
        return "action_check_db_connection"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        db_url = os.environ.get("DATABASE_URL")
        
        if not db_url:
            dispatcher.utter_message(text="⚠️ DATABASE_URL chưa được cấu hình trong môi trường.")
            return []
        
        if not PSYCOPG2_AVAILABLE:
            dispatcher.utter_message(text="⚠️ Thư viện psycopg2 chưa được cài đặt. Chạy: pip install psycopg2-binary")
            return []
        
        conn = _get_db_conn()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM trung_tam_cuu_tros")
                count = cur.fetchone()[0]
                cur.close()
                conn.close()
                dispatcher.utter_message(text=f"✅ Kết nối database thành công! Có {count} trung tâm cứu trợ trong hệ thống.")
            except Exception as e:
                dispatcher.utter_message(text=f"⚠️ Kết nối được DB nhưng lỗi truy vấn: {str(e)}")
        else:
            dispatcher.utter_message(text="❌ Không thể kết nối database. Kiểm tra DATABASE_URL và đảm bảo PostgreSQL đang chạy.")
        
        return []


# Keep old ActionGetCenters for backward compatibility
class ActionGetCenters(Action):
    def name(self) -> Text:
        return "action_get_centers"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Delegate to the new action
        action = ActionFindReliefCenters()
        return action.run(dispatcher, tracker, domain)
