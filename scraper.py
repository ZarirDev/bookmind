import requests
from bs4 import BeautifulSoup
import time
import re
import json
import os

BASE_URL = "https://nctbbook.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(SCRIPT_DIR, ".cache")
CACHE_TTL = 86400  # 24 hours

# ---------- Cache helpers ----------
def _load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def _save_cache(cache):
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def _is_fresh(entry):
    if not isinstance(entry, dict) or 'timestamp' not in entry:
        return False
    return (time.time() - entry['timestamp']) < CACHE_TTL

# ---------- Safe request + cache fallback ----------
def _fetch_with_fallback(url, cache_key, force_refresh=False):
    """
    Try a live GET. On failure, return cached data (even expired).
    Returns (data, source) where source is 'live', 'fresh_cache', 'stale_cache', or 'none'.
    """
    cache = _load_cache()
    entry = cache.get(cache_key, {})
    cached_data = entry.get('data') if isinstance(entry, dict) else None

    if not force_refresh and _is_fresh(entry) and cached_data is not None:
        return cached_data, 'fresh_cache'

    # Try live request
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text, 'live'
    except Exception as e:
        print(f"⚠ Live request failed ({e}). Trying cached data...")
        if cached_data is not None:
            return cached_data, 'stale_cache'
        return None, 'none'

# ---------- Category mapping ----------
CATEGORY_MAP = {
    "প্রাথমিক": "Primary",
    "মাধ্যমিক": "Secondary",
    "দাখিল": "Dakhil",
    "ইবতেদায়ি": "Ibtedai"
}

def _to_english_category(bangla_name):
    return CATEGORY_MAP.get(bangla_name, bangla_name)

def get_categories(force_refresh=False):
    """Returns list of [english_name, url] – live or from cache."""
    cache = _load_cache()
    key = 'categories'

    # Try live first (or fresh cache)
    html, source = _fetch_with_fallback(BASE_URL, key, force_refresh)

    if html is None:
        return []

    # If we got live HTML, parse it
    if source == 'live':
        soup = BeautifulSoup(html, "html.parser")
        categories = []
        grid = soup.select_one('.nctb-levels')
        if grid:
            for a in grid.find_all('a', class_='nctb-level'):
                name_span = a.find('span', class_='nctb-level__name')
                if name_span:
                    raw_name = name_span.get_text(strip=True)
                    eng_name = _to_english_category(raw_name)
                    url = a.get('href')
                    if url and not url.startswith('http'):
                        url = BASE_URL + url
                    categories.append([eng_name, url])
        cache[key] = {'timestamp': time.time(), 'data': categories}
        _save_cache(cache)
        print(f"✅ Cached {len(categories)} categories (live).")
        return categories

    # Fallback to cached data (source is 'fresh_cache' or 'stale_cache')
    entry = cache.get(key, {})
    data = entry.get('data', [])
    print(f"📦 Using cached categories ({len(data)} items).")
    return data

# ---------- Class list ----------
def _clean_class_title(raw_title):
    parts = raw_title.split('|')
    english_part = parts[0].strip()
    return re.sub(r'\s+', ' ', english_part)

def get_class_links(category_url, force_refresh=False):
    key = f"classes:{category_url}"
    html, source = _fetch_with_fallback(category_url, key, force_refresh)

    if html is None:
        return []

    if source == 'live':
        soup = BeautifulSoup(html, "html.parser")
        classes = []
        grid = soup.select_one('.nctb-grid')
        if grid:
            for card in grid.find_all('a', class_='nctb-card'):
                title_h3 = card.find('h3', class_='nctb-card__title')
                if title_h3:
                    raw_title = title_h3.get_text(strip=True)
                    eng_title = _clean_class_title(raw_title)
                    url = card.get('href')
                    if url and not url.startswith('http'):
                        url = BASE_URL + url
                    classes.append([eng_title, url])
        cache = _load_cache()
        cache[key] = {'timestamp': time.time(), 'data': classes}
        _save_cache(cache)
        print(f"✅ Cached {len(classes)} classes (live).")
        return classes

    # Fallback
    cache = _load_cache()
    entry = cache.get(key, {})
    data = entry.get('data', [])
    print(f"📦 Using cached classes ({len(data)} items).")
    return data

# ---------- Book extraction ----------
def _extract_books_from_table(table):
    books = []
    rows = table.find_all("tr")
    if len(rows) < 2:
        return books
    for row in rows[1:]:
        cols = row.find_all("td")
        if len(cols) < 3:
            continue
        name_td = cols[1]
        link_td = cols[2]
        book_name = name_td.get_text(strip=True)
        a_tag = link_td.find("a")
        if a_tag and a_tag.get("href"):
            books.append([book_name, a_tag["href"]])
    return books

def scrape_download_links(class_url, force_refresh=False):
    key = f"books:{class_url}"
    html, source = _fetch_with_fallback(class_url, key, force_refresh)

    if html is None:
        return {'english_names': [], 'bangla_links': [], 'english_links': []}

    if source == 'live':
        soup = BeautifulSoup(html, "html.parser")
        bangla_links = []
        english_links = []

        post_content = soup.select_one('.post-content')
        if post_content:
            bangla_header = post_content.find('h2', string=re.compile(r'Bangla version', re.IGNORECASE))
            if bangla_header:
                table = bangla_header.find_next('table')
                if table:
                    bangla_links = _extract_books_from_table(table)

            english_header = post_content.find('h2', string=re.compile(r'English version', re.IGNORECASE))
            if english_header:
                table = english_header.find_next('table')
                if table:
                    english_links = _extract_books_from_table(table)
        else:
            # fallback search whole page
            bangla_header = soup.find('h2', string=re.compile(r'Bangla version', re.IGNORECASE))
            if bangla_header:
                table = bangla_header.find_next('table')
                if table:
                    bangla_links = _extract_books_from_table(table)
            english_header = soup.find('h2', string=re.compile(r'English version', re.IGNORECASE))
            if english_header:
                table = english_header.find_next('table')
                if table:
                    english_links = _extract_books_from_table(table)

        # Build English names list
        english_names = []
        num_books = max(len(bangla_links), len(english_links))
        for i in range(num_books):
            if i < len(english_links):
                english_names.append(english_links[i][0])
            elif i < len(bangla_links):
                fallback = re.sub(r'[^\x00-\x7F]+', '', bangla_links[i][0]).strip()
                if not fallback:
                    fallback = f"Book_{i+1}"
                english_names.append(fallback)
            else:
                english_names.append(f"Book_{i+1}")

        data = {
            'english_names': english_names,
            'bangla_links': bangla_links,
            'english_links': english_links
        }
        cache = _load_cache()
        cache[key] = {'timestamp': time.time(), 'data': data}
        _save_cache(cache)
        print(f"✅ Cached books: {len(bangla_links)} Bangla, {len(english_links)} English (live).")
        return data

    # Fallback
    cache = _load_cache()
    entry = cache.get(key, {})
    data = entry.get('data', {'english_names': [], 'bangla_links': [], 'english_links': []})
    print(f"📦 Using cached books ({len(data.get('english_names', []))} items).")
    return data

# ---------- Standalone CLI ----------
def main():
    categories = get_categories()
    if not categories:
        print("No categories found (offline with empty cache).")
        return

    print("\nAvailable categories:")
    for i, (name, _) in enumerate(categories, 1):
        print(f"{i}. {name}")

    choice = int(input("\nSelect category: "))
    if not (1 <= choice <= len(categories)):
        print("Invalid choice.")
        return
    cat_name, cat_url = categories[choice - 1]
    print(f"\nCategory: {cat_name}")

    classes = get_class_links(cat_url)
    if not classes:
        print("No classes found.")
        return

    print(f"\nFound {len(classes)} classes:")
    for i, (title, _) in enumerate(classes, 1):
        print(f"{i}. {title}")

    choice = int(input("\nSelect class: "))
    if not (1 <= choice <= len(classes)):
        print("Invalid.")
        return
    class_title, class_url = classes[choice - 1]

    data = scrape_download_links(class_url)
    english_names = data['english_names']
    bangla_links = data['bangla_links']
    english_links = data['english_links']

    if bangla_links and english_links:
        lang = input("Both Bangla and English available. Which? (b/e): ").strip().lower()
        if lang.startswith('e'):
            links = english_links
            lang_name = 'English'
        else:
            links = bangla_links
            lang_name = 'Bangla'
    elif bangla_links:
        links = bangla_links
        lang_name = 'Bangla'
    elif english_links:
        links = english_links
        lang_name = 'English'
    else:
        print("No books found.")
        return

    print(f"\n{len(links)} {lang_name} books (English names displayed):")
    for i in range(len(links)):
        print(f"{i+1}. {english_names[i]}")

if __name__ == "__main__":
    main()