import os
import re
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


def _clean_field(text):
    """Remove scraping artifacts and legal boilerplate from text fields."""
    import re
    if not text:
        return text

    meta_labels = {'Год основания', 'Взрослых на группу', 'Детей в группе', 'Детей на программе'}
    junk_lines = {'Запросить больше информации о программе', 'Запросить больше информации о лагере'}
    junk_starts = (
        'Информация с официального сайта',
        'Смотрите также другие программы',
        'Услуги предоставляет',
    )

    lines = text.split('\n')
    result = []
    skip_legal = False
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped in meta_labels:
            # Skip label + its value line
            j = i + 1
            while j < len(lines) and lines[j].strip() == '':
                j += 1
            i = j + 1
            continue
        if stripped in junk_lines:
            i += 1
            continue
        if any(stripped.startswith(p) for p in junk_starts):
            if stripped.startswith('Услуги предоставляет'):
                skip_legal = True
            i += 1
            continue
        if skip_legal:
            if (re.match(r'^КПП\b', stripped) or
                    re.match(r'^ОГРН\b', stripped) or
                    re.match(r'^\d{3,6},', stripped) or
                    re.search(r'ИНН\s+\d', stripped) or
                    re.search(r'ОГРН\s+\d', stripped)):
                i += 1
                continue
            else:
                skip_legal = False
        result.append(lines[i])
        i += 1

    cleaned = '\n'.join(result)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return cleaned


def row_to_dict(row):
    d = dict(row)
    for field in ('categories', 'photos', 'sessions'):
        try:
            d[field] = json.loads(d[field] or '[]')
        except Exception:
            d[field] = []
    for field in ('about_org', 'description', 'program', 'accommodation', 'safety'):
        if d.get(field):
            d[field] = _clean_field(d[field])
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
        # Support multi-term OR matching: comma separates selected filters,
        # pipe separates synonym patterns within one filter
        all_terms = []
        for group in category.split(','):
            all_terms.extend([t.strip() for t in group.split('|') if t.strip()])
        if all_terms:
            subclauses = ' OR '.join(['categories LIKE ?' for _ in all_terms])
            query += f' AND ({subclauses})'
            params.extend([f'%{t}%' for t in all_terms])
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


@app.route('/api/lead', methods=['POST'])
def api_lead():
    data = request.json or {}
    parent_name = data.get('parent_name', '').strip()
    phone = data.get('phone', '').strip()
    child_age = data.get('child_age', '')
    wishes = data.get('wishes', '').strip()

    if not parent_name or not phone:
        return jsonify({'ok': False, 'error': 'Укажите имя и телефон'}), 400

    text = (
        f'🎯 Новая заявка с главной страницы!\n'
        f'Родитель: {parent_name}\n'
        f'Телефон: {phone}\n'
        f'Возраст ребёнка: {child_age or "—"}\n'
        f'Пожелания: {wishes or "—"}'
    )

    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(
                f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
                json={'chat_id': TELEGRAM_CHAT_ID, 'text': text},
                timeout=5
            )
        except Exception as e:
            print('Telegram send failed:', e)

    return jsonify({'ok': True})


# ─── ORGS DB ─────────────────────────────────────────────────────────────────

ORGS_DB   = os.path.join(os.path.dirname(__file__), 'orgs.db')
ORGS_JSON = os.path.join(os.path.dirname(__file__), 'top250_cards.json')

def init_orgs_db():
    if os.path.exists(ORGS_DB):
        return
    if not os.path.exists(ORGS_JSON):
        print('WARNING: top250_cards.json not found, orgs DB skipped')
        return
    print('Initializing orgs database...')
    with open(ORGS_JSON, encoding='utf-8') as f:
        cards = json.load(f)
    conn = sqlite3.connect(ORGS_DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS organizations (
        id INTEGER PRIMARY KEY, name TEXT, category TEXT, subcategory TEXT,
        address TEXT, metro TEXT, district TEXT,
        photos TEXT, photo_count INTEGER, programs TEXT, skills TEXT,
        age_range TEXT, price TEXT, price_type TEXT, description TEXT,
        schedule TEXT, group_size TEXT, duration TEXT,
        phone TEXT, website TEXT, vk TEXT,
        rating REAL, reviews_count INTEGER, has_trial INTEGER, data_quality INTEGER,
        extra_photos TEXT
    )''')
    for c in cards:
        conn.execute('INSERT OR REPLACE INTO organizations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
            c.get('id'), c.get('name',''), c.get('category',''), c.get('subcategory',''),
            c.get('address',''), c.get('metro',''), c.get('district',''),
            json.dumps(c.get('photos',[]), ensure_ascii=False), c.get('photo_count',0),
            json.dumps(c.get('programs',[]), ensure_ascii=False),
            json.dumps(c.get('skills',[]), ensure_ascii=False),
            c.get('age_range',''), c.get('price',''), c.get('price_type',''),
            c.get('description',''), c.get('schedule',''), c.get('group_size',''),
            c.get('duration',''), c.get('phone',''), c.get('website',''), c.get('vk',''),
            c.get('rating',0) or 0, c.get('reviews_count',0) or 0,
            1 if c.get('has_trial') else 0, c.get('data_quality',0) or 0,
            json.dumps(c.get('extra_photos',[]), ensure_ascii=False),
        ))
    conn.commit()
    conn.close()
    print(f'Orgs DB ready: {len(cards)} organizations')

def _migrate_orgs_db():
    """Add extra_photos column if missing (safe to call on existing DB)."""
    if not os.path.exists(ORGS_DB):
        return
    conn = _orgs_conn()
    try:
        conn.execute("ALTER TABLE organizations ADD COLUMN extra_photos TEXT DEFAULT '[]'")
        conn.commit()
        print("Migration: added extra_photos column")
        # Backfill from JSON
        if os.path.exists(ORGS_JSON):
            with open(ORGS_JSON, encoding='utf-8') as f:
                cards = json.load(f)
            for c in cards:
                eps = c.get('extra_photos', [])
                if eps:
                    conn.execute("UPDATE organizations SET extra_photos=? WHERE id=?",
                                 (json.dumps(eps, ensure_ascii=False), c['id']))
            conn.commit()
    except Exception:
        pass  # Column already exists — OK
    finally:
        conn.close()

def _price_lte(price_str, max_val):
    """Return True if first number in price_str <= max_val (or no number found)."""
    if not price_str: return True
    m = re.search(r'(\d[\d\s]*)', price_str)
    if not m: return True
    return int(m.group(1).replace(' ', '')) <= max_val

def _age_includes(age_str, target):
    """Return True if target age falls within age_str range."""
    if not age_str: return True
    m = re.search(r'(\d+)\s*[-–]\s*(\d+)', age_str)
    if m: return int(m.group(1)) <= target <= int(m.group(2))
    m = re.search(r'(\d+)\s*\+', age_str)
    if m: return target >= int(m.group(1))
    m = re.search(r'от\s*(\d+)', age_str)
    if m: return target >= int(m.group(1))
    m = re.search(r'(\d+)', age_str)
    if m: return int(m.group(1)) <= target
    return True

def _orgs_conn():
    conn = sqlite3.connect(ORGS_DB)
    conn.row_factory = sqlite3.Row
    return conn

def _parse_list(val):
    try: return json.loads(val) if val else []
    except: return []

def _org_dict(row):
    d = dict(row)
    d['photos']       = _parse_list(d.get('photos'))
    d['programs']     = _parse_list(d.get('programs'))
    d['skills']       = _parse_list(d.get('skills'))
    d['extra_photos'] = _parse_list(d.get('extra_photos'))
    d['has_trial']    = bool(d.get('has_trial'))
    return d

# ─── ORGS API ─────────────────────────────────────────────────────────────────

@app.route('/api/orgs')
def api_orgs():
    if not os.path.exists(ORGS_DB): return jsonify({'total':0,'items':[]})
    conn = _orgs_conn()
    category    = request.args.get('category','')
    subcategory = request.args.get('subcategory','')
    metro       = request.args.get('metro','')
    has_trial   = request.args.get('has_trial','')
    q           = request.args.get('q','')
    age         = request.args.get('age', type=int)
    price_max   = request.args.get('price_max', type=int)
    limit       = min(int(request.args.get('limit',50)), 200)
    offset      = int(request.args.get('offset',0))

    conds, params = [], []
    if category:       conds.append('category=?');     params.append(category)
    if subcategory:    conds.append('subcategory=?');  params.append(subcategory)
    if metro:          conds.append('metro=?');        params.append(metro)
    if has_trial=='1': conds.append('has_trial=1')
    if q:
        conds.append('(name LIKE ? OR description LIKE ? OR programs LIKE ?)')
        params += [f'%{q}%']*3
    where = ('WHERE ' + ' AND '.join(conds)) if conds else ''

    # Age and price need Python-side filtering (stored as text)
    if age or price_max:
        rows  = conn.execute(f'SELECT * FROM organizations {where} ORDER BY data_quality DESC, rating DESC', params).fetchall()
        conn.close()
        items = [_org_dict(r) for r in rows]
        if age:       items = [o for o in items if _age_includes(o.get('age_range',''), age)]
        if price_max: items = [o for o in items if _price_lte(o.get('price',''), price_max)]
        total = len(items)
        items = items[offset:offset+limit]
    else:
        total = conn.execute(f'SELECT COUNT(*) FROM organizations {where}', params).fetchone()[0]
        rows  = conn.execute(f'SELECT * FROM organizations {where} ORDER BY data_quality DESC, rating DESC LIMIT ? OFFSET ?', params+[limit,offset]).fetchall()
        conn.close()
        items = [_org_dict(r) for r in rows]

    return jsonify({'total': total, 'items': items})

@app.route('/api/orgs/<int:org_id>')
def api_org(org_id):
    if not os.path.exists(ORGS_DB): return jsonify({'error':'not found'}), 404
    conn = _orgs_conn()
    row = conn.execute('SELECT * FROM organizations WHERE id=?', (org_id,)).fetchone()
    conn.close()
    if not row: return jsonify({'error':'not found'}), 404
    return jsonify(_org_dict(row))

@app.route('/api/orgs-meta')
def api_orgs_meta():
    if not os.path.exists(ORGS_DB): return jsonify({'categories':[],'metros':[]})
    conn = _orgs_conn()
    cats   = [r[0] for r in conn.execute("SELECT DISTINCT category FROM organizations WHERE category!='' ORDER BY category").fetchall()]
    metros = [r[0] for r in conn.execute("SELECT DISTINCT metro FROM organizations WHERE metro!='' ORDER BY metro").fetchall()]
    conn.close()
    return jsonify({'categories': cats, 'metros': metros})

# ─── STATIC FILES ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/camps')
def camps_page():
    return send_from_directory('static', 'camps.html')


@app.route('/camp/<camp_id>')
def camp_page(camp_id):
    return send_from_directory('static', 'camp.html')


@app.route('/orgs')
def orgs_page():
    return send_from_directory('static', 'orgs.html')


@app.route('/org/<int:org_id>')
def org_page(org_id):
    return send_from_directory('static', 'org.html')


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


# ─── STARTUP (runs for both gunicorn and direct) ──────────────────────────────
init_db()
init_orgs_db()
_migrate_orgs_db()   # safe no-op if extra_photos column already exists

# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
