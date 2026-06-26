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

# ---------- Category mapping ----------
CATEGORY_MAP = {
    "প্রাথমিক": "Primary",
    "মাধ্যমিক": "Secondary",
    "দাখিল": "Dakhil",
    "ইবতেদায়ি": "Ibtedai"
}

def _to_english_category(bangla_name):
    return CATEGORY_MAP.get(bangla_name, bangla_name)  # fallback just in case

def get_categories(force_refresh=False):
    """
    Returns list of [english_name, url] from the homepage category grid.
    """
    cache = _load_cache()
    key = 'categories'
    entry = cache.get(key, {})

    if not force_refresh and _is_fresh(entry):
        print("Using cached categories (24h valid).")
        return entry.get('data', [])

    print("Fetching fresh category links from homepage...")
    categories = []
    resp = requests.get(BASE_URL, headers=HEADERS)
    soup = BeautifulSoup(resp.text, "html.parser")

    grid = soup.select_one('.nctb-level-grid')
    if grid:
        for a in grid.find_all('a', class_='nctb-level-card'):
            name_div = a.find('div', class_='nctb-level-name')
            if name_div:
                raw_name = name_div.get_text(strip=True)
                eng_name = _to_english_category(raw_name)
                url = a.get('href')
                if url and not url.startswith('http'):
                    url = BASE_URL + url
                categories.append([eng_name, url])

    cache[key] = {'timestamp': time.time(), 'data': categories}
    _save_cache(cache)
    print(f"Cached {len(categories)} categories.")
    return categories

# ---------- Class list inside a category ----------
def _clean_class_title(raw_title):
    """
    Extract the English portion from e.g.
    "Class 9 Book 2026 PDF | ৯ম শ্রেণির বই ২০২৬"
    """
    # Split on '|' and keep the first part
    parts = raw_title.split('|')
    english_part = parts[0].strip()
    # Remove extra "PDF" duplicates, etc.
    english_part = re.sub(r'\s+', ' ', english_part)
    return english_part

def get_class_links(category_url, force_refresh=False):
    """
    Returns list of [english_title, url] from a category page (cat-grid).
    """
    cache = _load_cache()
    key = f"classes:{category_url}"
    entry = cache.get(key, {})

    if not force_refresh and _is_fresh(entry):
        print(f"Using cached class links for {category_url}")
        return entry.get('data', [])

    print(f"Fetching fresh class links from {category_url}...")
    classes = []
    resp = requests.get(category_url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, "html.parser")

    grid = soup.select_one('.cat-grid')
    if grid:
        for card in grid.find_all('a', class_='cat-card'):
            title_div = card.find('div', class_='cat-title')
            if title_div:
                raw_title = title_div.get_text(strip=True)
                eng_title = _clean_class_title(raw_title)
                url = card.get('href')
                if url and not url.startswith('http'):
                    url = BASE_URL + url
                classes.append([eng_title, url])

    # Note: pagination can be added if needed.

    cache[key] = {'timestamp': time.time(), 'data': classes}
    _save_cache(cache)
    print(f"Cached {len(classes)} classes for {category_url}")
    return classes

# ---------- Book extraction from a class page ----------
def _extract_books_from_table(table):
    """
    From a <table> element, return list of [book_name, download_url].
    """
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
    """
    Returns a dict with:
      'english_names' : list of English book names (for display & directories)
      'bangla_links'  : list of [bangla_book_name, url]
      'english_links' : list of [english_book_name, url]
    All lists are aligned by index (same order as the tables).
    """
    cache = _load_cache()
    key = f"books:{class_url}"
    entry = cache.get(key, {})

    if not force_refresh and _is_fresh(entry):
        print(f"Using cached book data for {class_url}")
        return entry.get('data', {'english_names': [], 'bangla_links': [], 'english_links': []})

    print(f"Fetching fresh book data from {class_url}...")
    resp = requests.get(class_url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, "html.parser")

    bangla_links = []
    english_links = []
    english_names = []

    # Bangla table
    bangla_header = soup.find('h2', string=re.compile(r'Bangla version', re.IGNORECASE))
    if bangla_header:
        table = bangla_header.find_next('table')
        if table:
            bangla_links = _extract_books_from_table(table)

    # English table
    english_header = soup.find('h2', string=re.compile(r'English version', re.IGNORECASE))
    if english_header:
        table = english_header.find_next('table')
        if table:
            english_links = _extract_books_from_table(table)

    # Build English names list: use English table names if available, otherwise fallback
    num_books = max(len(bangla_links), len(english_links))
    for i in range(num_books):
        if i < len(english_links):
            english_names.append(english_links[i][0])
        elif i < len(bangla_links):
            # Fallback: use Bangla name, but remove Bangla characters to keep it ASCII
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
    cache[key] = {'timestamp': time.time(), 'data': data}
    _save_cache(cache)
    print(f"Cached books: {len(bangla_links)} Bangla, {len(english_links)} English")
    return data

# ---------- Standalone CLI (kept for testing, uses English output) ----------
def main():
    categories = get_categories()
    if not categories:
        print("No categories found.")
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