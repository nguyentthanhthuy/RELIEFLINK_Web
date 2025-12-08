import os
import json

from pprint import pprint

DATABASE_URL = os.environ.get("DATABASE_URL")
output = {"DATABASE_URL_set": bool(DATABASE_URL)}

try:
    import psycopg2
    import psycopg2.extras
    output['psycopg2_import'] = True
except Exception as e:
    output['psycopg2_import'] = False
    output['error'] = str(e)
    print(json.dumps(output, ensure_ascii=False))
    raise SystemExit(1)

if not DATABASE_URL:
    output['error'] = 'DATABASE_URL not set'
    print(json.dumps(output, ensure_ascii=False))
    raise SystemExit(2)

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute('SELECT 1')
    output['select1'] = cur.fetchone()[0]

    # center count
    try:
        cur.execute('SELECT count(*) FROM trung_tam_cuu_tros')
        output['centers_count'] = cur.fetchone()[0]
    except Exception as e:
        output['centers_count_error'] = str(e)

    # sample centers
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute('SELECT id, ten_trung_tam, dia_chi, so_lien_he FROM trung_tam_cuu_tros LIMIT 5')
        rows = cur.fetchall()
        output['centers_sample'] = rows
    except Exception as e:
        output['centers_sample_error'] = str(e)

    cur.close()
    conn.close()
except Exception as e:
    output['connect_error'] = str(e)

print(json.dumps(output, ensure_ascii=False, indent=2))
