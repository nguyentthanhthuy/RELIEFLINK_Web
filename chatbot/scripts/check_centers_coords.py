import os
import sys
try:
    import psycopg2
    import psycopg2.extras
except Exception as e:
    print("psycopg2 not installed or import failed:", e)
    sys.exit(2)

from math import radians, sin, cos, sqrt, atan2


def haversine_km(lat1, lon1, lat2, lon2):
    try:
        lat1 = float(lat1)
        lon1 = float(lon1)
        lat2 = float(lat2)
        lon2 = float(lon2)
    except Exception:
        return None
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set. Set $env:DATABASE_URL before running.")
        sys.exit(1)

    try:
        conn = psycopg2.connect(db_url)
    except Exception as e:
        print("Failed to connect to DB:", e)
        sys.exit(3)

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT COUNT(*) AS total FROM trung_tam_cuu_tros")
    total = cur.fetchone().get("total")
    cur.execute("SELECT COUNT(*) AS missing FROM trung_tam_cuu_tros WHERE vi_do IS NULL OR kinh_do IS NULL")
    missing = cur.fetchone().get("missing")
    cur.execute("SELECT COUNT(*) AS with_coords FROM trung_tam_cuu_tros WHERE vi_do IS NOT NULL AND kinh_do IS NOT NULL")
    with_coords = cur.fetchone().get("with_coords")

    print(f"Total centers: {total}")
    print(f"Centers with coords: {with_coords}")
    print(f"Centers missing coords: {missing}\n")

    print("Sample centers missing coords (up to 20):")
    cur.execute("SELECT id, ten_trung_tam, dia_chi, vi_do, kinh_do FROM trung_tam_cuu_tros WHERE vi_do IS NULL OR kinh_do IS NULL LIMIT 20")
    rows = cur.fetchall()
    for r in rows:
        print(r)

    print("\nSample centers WITH coords (up to 50):")
    cur.execute("SELECT id, ten_trung_tam, dia_chi, vi_do, kinh_do FROM trung_tam_cuu_tros WHERE vi_do IS NOT NULL AND kinh_do IS NOT NULL LIMIT 50")
    rows = cur.fetchall()
    for r in rows[:10]:
        print(r)

    # If there are coords, compute nearest to given user coords (example coords provided)
    user_lat = os.environ.get("TEST_USER_LAT") or "21.022977"
    user_lon = os.environ.get("TEST_USER_LON") or "107.248401"
    print(f"\nComputing distances to user at ({user_lat}, {user_lon}) for centers with coords...")
    cur.execute("SELECT id, ten_trung_tam, dia_chi, vi_do, kinh_do, so_lien_he FROM trung_tam_cuu_tros WHERE vi_do IS NOT NULL AND kinh_do IS NOT NULL")
    rows = cur.fetchall()
    centers = []
    for r in rows:
        dist = haversine_km(user_lat, user_lon, r.get("vi_do"), r.get("kinh_do"))
        if dist is None:
            continue
        centers.append((dist, r))
    centers.sort(key=lambda x: x[0])
    for dist, r in centers[:10]:
        print(f"{dist:.2f} km — {r.get('ten_trung_tam')} — {r.get('dia_chi')} — {r.get('so_lien_he')}")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
