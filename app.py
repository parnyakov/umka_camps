import os
import json
import sqlite3
import requests
from flask import Flask, jsonify, request, send_from_directory, abort

app = Flask(__name__, static_folder='static')

DB_PATH = os.path.join(os.path.dirname(__file__), 'camps.db')
JSON_PATH = os.path.join(os.path.dirname(__file__), 'camps_structured.json')

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')


# ─── DB INIT ────────────────────────────────────────────────────────────────

def init_db():
    if os.path.exists(DB_PATH):
        return
    if not os.path.exists(JSON_PATH):
        print('WARNING: camps_structured.json not found, starting with empty DB')
        conn = sqlite3.connect(DB_PATH)
        _create_table(conn)
        conn.close()
        return

    print('Initializing database from JSON...')
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        camps = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    _create_table(conn)
    cur = conn.cursor()

    for c in camps:
        content = c.get('content', {})
        cur.execute('''
            INSERT OR IGNORE INTO camps VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
        ''', (
            c.get('id', ''),
            c.get('name', ''),
            c.get('type', ''),
            c.get('location', ''),
            c.get('age_min') or 0,
            c.get('age_max') or 18,
            c.get('price_min') or 0,
            c.get('price_max') or 0,
            c.get('rating') or 0.0,
            c.get('reviews_count') or 0,
            json.dumps(c.get('categories', []), ensure_ascii=False),
            1 if c.get('has_pool') else 0,
            c.get('food_times') or 0,
            c.get('tagline', ''),
            c.get('description', ''),
            content.get('program', ''),
            content.get('accommodation', ''),
            content.get('safety', ''),
            content.get('about_org', ''),
            content.get('reviews', ''),
            c.get('main_photo', ''),
            json.dumps(c.get('photos', []), ensure_ascii=False),
            c.get('url', ''),
            json.dumps(c.get('sessions', []), ensure_ascii=False),
        ))

    conn.commit()
    conn.close()
    print(f'Database initialized with {len(camps)} camps.')


def _create_table(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS camps (
            id TEXT PRIMARY KEY,
            name TEXT,
            type TEXT,
            location TEXT,
            age_min INTEGER,
            age_max INTEGER,
            price_min INTEGER,
            price_max INTEGER,
            rating REAL,
            reviews_count INTEGER,
            categories TEXT,
            has_pool INTEGER,
            food_times INTEGER,
            tagline TEXT,
            description TEXT,
            program TEXT,
            accommodation TEXT,
            safety TEXT,
            about_org TEXT,
            reviews TEXT,
            main_photo TEXT,
            photos TEXT,
            url TEXT,
            sessions TEXT
        )
    ''')
    conn.commit()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row):
    d = dict(row)
    for field in ('categories', 'photos', 'sessions'):
        try:
            d[field] = json.loads(d[field] or '[]')
        except Exception:
            d[field] = []
    return d


# ─── API ────────────────────────────────────────────────────────────────────

@app.route('/api/camps')
def api_camps():
    age_min = request.args.get('age_min', type=int)
    age_max = request.args.get('age_max', type=int)
    price_min = request.args.get('price_min', type=int)
    price_max = request.args.get('price_max', type=int)
    location = request.args.get('location', '').strip()
    category = request.args.get('category', '').strip()
    camp_type = request.args.get('type', '').strip()
    has_pool = request.args.get('has_pool', '').strip()
    rating_min = request.args.get('rating_min', type=float)
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 24, type=int)
    offset = (page - 1) * limit

    query = 'SELECT * FROM camps WHERE 1=1'
    params = []

    if age_min is not None:
        query += ' AND age_max >= ?'
        params.append(age_min)
    if age_max is not None:
        query += ' AND age_min <= ?'
        params.append(age_max)
    if price_min is not None:
        query += ' AND price_max >= ?'
        params.append(price_min)
    if price_max is not None:
        query += ' AND (price_min <= ? OR price_min = 0)'
        params.append(price_max)
    if location:
        query += ' AND location LIKE ?'
        params.append(f'%{location}%')
    if category:
        query += ' AND categories LIKE ?'
        params.append(f'%{category}%')
    if camp_type:
        query += ' AND type LIKE ?'
        params.append(f'%{camp_type}%')
    if has_pool == '1':
        query += ' AND has_pool = 1'
    if rating_min is not None:
        query += ' AND rating >= ?'
        params.append(rating_min)
    if search:
        query += ' AND (name LIKE ? OR tagline LIKE ? OR description LIKE ?)'
        s = f'%{search}%'
        params.extend([s, s, s])

    count_query = query.replace('SELECT *', 'SELECT COUNT(*)')
    conn = get_db()
    total = conn.execute(count_query, params).fetchone()[0]

    query += ' ORDER BY rating DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()

    camps = []
    for row in rows:
        d = row_to_dict(row)
        # Return only card-level fields for the list
        camps.append({
            'id': d['id'],
            'name': d['name'],
            'type': d['type'],
            'location': d['location'],
            'age_min': d['age_min'],
            'age_max': d['age_max'],
            'price_min': d['price_min'],
            'price_max': d['price_max'],
            'rating': d['rating'],
            'reviews_count': d['reviews_count'],
            'categories': d['categories'],
            'has_pool': bool(d['has_pool']),
            'tagline': d['tagline'],
            'main_photo': d['main_photo'],
        })

    return jsonify({'camps': camps, 'total': total, 'page': page, 'pages': -(-total // limit)})


@app.route('/api/camps/<camp_id>')
def api_camp(camp_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM camps WHERE id = ?', (camp_id,)).fetchone()
    conn.close()
    if not row:
        abort(404)
    return jsonify(row_to_dict(row))


@app.route('/api/booking', methods=['POST'])
def api_booking():
    data = request.json or {}
    camp_name = data.get('camp_name', 'Не указан')
    parent_name = data.get('parent_name', '')
    phone = data.get('phone', '')
    telegram = data.get('telegram', '')
    child_age = data.get('child_age', '')
    comment = data.get('comment', '')
    session_start = data.get('session_start', '')
    session_end = data.get('session_end', '')
    session_price = data.get('session_price', '')

    if not parent_name or not phone:
        return jsonify({'ok': False, 'error': 'Укажите имя и телефон'}), 400

    session_line = ''
    if session_start or session_end:
        session_line = f'\nСмена: {session_start} — {session_end}'
        if session_price:
            session_line += f' ({int(float(session_price)):,} ₽)'.replace(',', ' ')

    text = (
        f'🏕️ Новая заявка!\n'
        f'Лагерь: {camp_name}'
        f'{session_line}\n'
        f'Родитель: {parent_name}\n'
        f'Телефон: {phone}\n'
        f'Telegram: {telegram or "—"}\n'
        f'Возраст ребёнка: {child_age or "—"}\n'
        f'Комментарий: {comment or "—"}'
    )

    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            resp = requests.post(
                f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
                json={'chat_id': TELEGRAM_CHAT_ID, 'text': text},
                timeout=5
            )
            if not resp.ok:
                print('Telegram error:', resp.text)
        except Exception as e:
            print('Telegram send failed:', e)

    return jsonify({'ok': True})


# ─── STATIC FILES ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/camp/<camp_id>')
def camp_page(camp_id):
    return send_from_directory('static', 'camp.html')


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
