"""
Standalone script to (re)initialize the SQLite database from camps_structured.json.
Run: python init_db.py
"""
import os
import json
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), 'camps.db')
JSON_PATH = os.path.join(os.path.dirname(__file__), 'camps_structured.json')


def main():
    if not os.path.exists(JSON_PATH):
        print(f'ERROR: {JSON_PATH} not found')
        return

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print('Old database removed.')

    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        camps = json.load(f)

    conn = sqlite3.connect(DB_PATH)
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

    cur = conn.cursor()
    count = 0
    for c in camps:
        content = c.get('content', {})
        cur.execute('''
            INSERT OR REPLACE INTO camps VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
        count += 1

    conn.commit()
    conn.close()
    print(f'Done! {count} camps written to {DB_PATH}')


if __name__ == '__main__':
    main()
