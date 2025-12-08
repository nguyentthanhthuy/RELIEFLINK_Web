from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
import requests
import json
import os

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
        conn = psycopg2.connect(db_url)
        return conn
    except Exception:
        return None


def _fetch_user_requests_from_db(user_id: str):
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT id, loai_yeu_cau, mo_ta, so_nguoi, trang_thai, created_at, dia_chi
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
            SELECT tieu_de, noi_dung, loai_thong_bao, created_at
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
                    dispatcher.utter_message(text="Không tìm thấy trung tâm có tọa độ để tính khoảng cách.")
                    return []

                lines = []
                for dist, it in top:
                    lines.append(f"• {it.get('ten_trung_tam')} — {it.get('dia_chi', '')} — {it.get('so_lien_he', '')} — {dist:.1f} km")
                msg = "Các trung tâm cứu trợ gần bạn nhất:\n" + "\n".join(lines)
                dispatcher.utter_message(text=msg)
                return []

            # Fallback: no user coords — return first 5 centers (existing behaviour)
            # fallback count
            try:
                slot_val = tracker.get_slot("max_centers") or tracker.get_slot("max_results")
                max_n = int(slot_val) if slot_val is not None else 5
            except Exception:
                max_n = 5
            if max_n <= 0:
                max_n = 5
            max_n = min(max_n, 20)

            lines = []
            for it in items[:max_n]:
                lines.append(f"• {it.get('ten_trung_tam')} — {it.get('dia_chi')} — {it.get('so_lien_he')}")
            msg = "Một vài trung tâm cứu trợ:\n" + "\n".join(lines)
            dispatcher.utter_message(text=msg)
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi khi kết nối tới hệ thống: {str(e)}")
        return []
