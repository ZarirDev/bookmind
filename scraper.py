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

# ---------- Cache ----------
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

# ---------- Class list ----------
def clean_title(raw_title):
    """Remove Bengali text and extra separators."""
    bengali_pattern = re.compile(r'[\u0980-\u09FF]+')
    cleaned = bengali_pattern.sub('', raw_title)
    cleaned = re.sub(r'[|–]', '', cleaned)
    cleaned = cleaned.replace(" - NCTB Books", "").strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned

def is_class_page(title):
    """True if title contains 'class' and 'book' or 'dakhil' and 'book' (excluding syllabus)."""
    title_lower = title.lower()
    if "syllabus" in title_lower:
        return False
    return ("class" in title_lower and "book" in title_lower) or \
           ("dakhil" in title_lower and "book" in title_lower)

def get_class_links(force_refresh=False):
    """Return list of [cleaned_title, url] for all class textbook pages."""
    cache = _load_cache()
    class_cache = cache.get('class_links', {})

    if not force_refresh and _is_fresh(class_cache):
        print("Using cached class links (24h valid).")
        return class_cache.get('data', [])

    print("Fetching fresh class links from website...")
    class_links = []
    url = BASE_URL

    while True:
        resp = requests.get(url, headers=HEADERS)
        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.select("h2.wp-block-post-title a")
        if not links:
            break

        for a in links:
            raw_title = a.get_text(strip=True)
            if is_class_page(raw_title):
                class_links.append([clean_title(raw_title), a["href"]])

        next_link = soup.find("link", rel="next")
        if next_link and next_link.get("href"):
            url = next_link["href"]
            time.sleep(1)
        else:
            break

    cache['class_links'] = {'timestamp': time.time(), 'data': class_links}
    _save_cache(cache)
    print(f"Cached {len(class_links)} class links.")
    return class_links

# ---------- Language availability ----------
def _find_table(soup, language):
    """Return the table element for the given language (bangla/english)."""
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        header_text = " ".join(headers)
        if language == 'bangla':
            if re.search(r"ক্রমিক|বাংলা", header_text):
                return table
        else:  # english
            if re.search(r"(sl|no\.?|sl no|english)", header_text):
                return table
    return None

def get_language_availability(class_url, force_refresh=False):
    """
    Return dict like {'bangla': True/False, 'english': True/False} for a class page.
    Cached per URL for 24h.
    """
    cache = _load_cache()
    cache_key = f"langs:{class_url}"
    entry = cache.get(cache_key, {})

    if not force_refresh and _is_fresh(entry):
        return entry.get('data', {'bangla': False, 'english': False})

    print(f"Fetching language availability for {class_url}...")
    resp = requests.get(class_url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, "html.parser")

    has_bangla = bool(_find_table(soup, 'bangla'))
    has_english = bool(_find_table(soup, 'english'))

    data = {'bangla': has_bangla, 'english': has_english}
    cache[cache_key] = {'timestamp': time.time(), 'data': data}
    _save_cache(cache)
    return data

# ---------- Download links ----------
def scrape_download_links(class_url, language='bangla', force_refresh=False):
    """
    Return list of [textbook_name, download_url] for the given class URL and language.
    Cached per (URL, language) for 24h.
    """
    cache = _load_cache()
    cache_key = f"downloads:{class_url}:{language}"
    entry = cache.get(cache_key, {})

    if not force_refresh and _is_fresh(entry):
        print(f"Using cached download links for {class_url} ({language})")
        return entry.get('data', [])

    print(f"Fetching fresh download links from {class_url} ({language})...")
    resp = requests.get(class_url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, "html.parser")

    table = _find_table(soup, language)
    if not table:
        print(f"No {language} table found on {class_url}")
        return []

    rows = table.find_all("tr")
    if len(rows) < 2:
        return []

    # Determine column indices
    header_cells = rows[0].find_all(["th", "td"])
    headers = [cell.get_text(strip=True).lower() for cell in header_cells]
    num_cols = len(headers)

    # Name column is usually the second (index 1)
    name_col = 1 if num_cols > 1 else 0

    # Find download column based on language
    if language == 'bangla':
        download_col = 2 if num_cols > 2 else name_col + 1
        for i, h in enumerate(headers):
            if 'বাংলা' in h:
                download_col = i
                break
    else:  # english
        download_col = 2 if num_cols > 2 else name_col + 1
        for i, h in enumerate(headers):
            if 'english' in h or 'ইংরেজি' in h:
                download_col = i
                break
        # For combined 4‑col tables, English download is often column 3
        if num_cols == 4 and download_col == 2:
            if len(headers) > 3 and ('english' in headers[3] or 'ইংরেজি' in headers[3]):
                download_col = 3

    books = []
    for row in rows[1:]:
        cols = row.find_all("td")
        if len(cols) > max(name_col, download_col):
            textbook_name = cols[name_col].get_text(strip=True)
            link_tag = cols[download_col].find("a")
            if link_tag and link_tag.get("href"):
                books.append([textbook_name, link_tag["href"]])

    # Cache and return
    cache[cache_key] = {'timestamp': time.time(), 'data': books}
    _save_cache(cache)
    print(f"Cached {len(books)} books for {class_url} ({language})")
    return books

# ---------- Interactive CLI ----------
def main():
    classes = get_class_links()
    if not classes:
        print("No class pages found.")
        return

    print(f"\nFound {len(classes)} class pages:")
    for i, (title, _) in enumerate(classes, 1):
        print(f"{i}. {title}")

    while True:
        try:
            choice = int(input("\nEnter the number of the class page to scrape: "))
            if 1 <= choice <= len(classes):
                break
            print(f"Please enter a number between 1 and {len(classes)}")
        except ValueError:
            print("Invalid input. Enter a number.")

    selected_title, selected_url = classes[choice - 1]
    print(f"\nSelected: {selected_title}\nURL: {selected_url}")

    # Detect languages (using cache)
    lang_info = get_language_availability(selected_url)
    has_bangla = lang_info.get('bangla', False)
    has_english = lang_info.get('english', False)

    if has_bangla and has_english:
        lang_choice = input("\nBoth Bangla and English available. Which version? (b/e): ").strip().lower()
        language = 'english' if lang_choice.startswith('e') else 'bangla'
    elif has_bangla:
        language = 'bangla'
        print("\nOnly Bangla version available.")
    elif has_english:
        language = 'english'
        print("\nOnly English version available.")
    else:
        print("No book tables found.")
        return

    books = scrape_download_links(selected_url, language)
    if not books:
        print("No books found.")
        return

    print(f"\n--- {language.capitalize()} version textbooks ---")
    for name, url in books:
        print(f"{name} -> {url}")

if __name__ == "__main__":
    main()