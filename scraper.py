import requests
from bs4 import BeautifulSoup
import time
import re
import json
import os

BASE_URL = "https://nctbbook.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}
# Cache file stored next to this script (not in current working directory)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(SCRIPT_DIR, ".cache")
CACHE_TTL = 86400  # 24 hours in seconds

# ---------- Cache functions ----------
def _load_cache():
    """Load entire cache from .cache file (if exists)."""
    if not os.path.exists(CACHE_FILE):
        print(f"[DEBUG] Cache file not found: {CACHE_FILE}")
        return {}
    try:
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
        print(f"[DEBUG] Cache loaded from {CACHE_FILE}")
        return cache
    except (json.JSONDecodeError, IOError) as e:
        print(f"[DEBUG] Failed to load cache: {e}")
        return {}

def _save_cache(cache):
    """Save entire cache to .cache file (pretty printed)."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        print(f"[DEBUG] Cache saved to {CACHE_FILE}")
    except Exception as e:
        print(f"[DEBUG] Failed to save cache: {e}")

def _is_fresh(entry):
    """Check if a cache entry (with timestamp) is still valid."""
    if not isinstance(entry, dict) or 'timestamp' not in entry:
        return False
    age = time.time() - entry['timestamp']
    return age < CACHE_TTL

# ---------- Class links (cached) ----------
def clean_title(raw_title):
    """Remove Bengali text and extra separators from title."""
    bengali_pattern = re.compile(r'[\u0980-\u09FF]+')
    cleaned = bengali_pattern.sub('', raw_title)
    cleaned = re.sub(r'[|–]', '', cleaned)
    cleaned = cleaned.replace(" - NCTB Books", "").strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned

def is_class_page(title):
    """Return True if the title looks like a class textbook page (not a syllabus or notice)."""
    title_lower = title.lower()
    if "syllabus" in title_lower:
        return False
    if "class" in title_lower and "book" in title_lower:
        return True
    if "dakhil" in title_lower and "book" in title_lower:
        return True
    return False

def get_class_links(force_refresh=False):
    """
    Scrape all class textbook pages across pagination.
    Uses cache unless force_refresh=True.
    Returns list of (cleaned_title, url).
    """
    cache = _load_cache()
    class_cache = cache.get('class_links', {})

    if not force_refresh and _is_fresh(class_cache):
        print("Using cached class links (24h valid).")
        return class_cache.get('data', [])

    print("Fetching fresh class links from website...")
    class_links = []
    url = BASE_URL
    page_num = 1

    while True:
        resp = requests.get(url, headers=HEADERS)
        soup = BeautifulSoup(resp.text, "html.parser")

        links = soup.select("h2.wp-block-post-title a")
        if not links:
            break

        for a in links:
            raw_title = a.get_text(strip=True)
            if is_class_page(raw_title):
                clean = clean_title(raw_title)
                href = a["href"]
                class_links.append([clean, href])  # store as list for consistency

        next_link = soup.find("link", rel="next")
        if next_link and next_link.get("href"):
            url = next_link["href"]
            page_num += 1
            time.sleep(1)
        else:
            break

    # Save to cache
    cache['class_links'] = {
        'timestamp': time.time(),
        'data': class_links
    }
    _save_cache(cache)
    print(f"Cached {len(class_links)} class links.")
    return class_links

# ---------- Download links (cached per URL + language) ----------
def scrape_download_links(class_url, language='bangla', force_refresh=False):
    """
    Scrape textbook names and download links from a class page.
    language: 'bangla' or 'english'
    Returns list of (textbook_name, download_url)
    Uses cache unless force_refresh=True.
    Handles both separate tables (3 columns) and combined tables (4 columns).
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

    # Find the correct table
    target_table = None
    if language == 'bangla':
        # Look for table with "ক্রমিক" header OR a column header containing "বাংলা"
        for table in soup.find_all("table"):
            headers = table.find_all("th")
            for th in headers:
                if re.search(r"ক্রমিক", th.get_text(strip=True)):
                    target_table = table
                    break
                if re.search(r"বাংলা", th.get_text(strip=True), re.IGNORECASE):
                    target_table = table
                    break
            if target_table:
                break
    else:  # english
        for table in soup.find_all("table"):
            headers = table.find_all("th")
            for th in headers:
                if re.search(r"(SL|No\.?|SL No)", th.get_text(strip=True), re.IGNORECASE):
                    target_table = table
                    break
                if re.search(r"English", th.get_text(strip=True), re.IGNORECASE):
                    target_table = table
                    break
            if target_table:
                break

    if not target_table:
        print(f"No {language} table found on {class_url}")
        return []

    # Determine column indices
    rows = target_table.find_all("tr")
    if len(rows) < 2:
        return []

    # Get header row
    header_row = rows[0]
    headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]
    num_cols = len(headers)

    # Column for textbook name: usually second column (index 1)
    name_col = 1
    # Column for download link depends on language and table structure
    if language == 'bangla':
        # In 3‑col table: download is col 2; in 4‑col table: Bangla download is also col 2
        download_col = 2
        # But if the header says "বাংলা সংস্করণ" or similar, we can use that
        for i, h in enumerate(headers):
            if 'বাংলা' in h:
                download_col = i
                break
    else:  # english
        # In 3‑col table (separate English table): download is col 2
        # In 4‑col combined table: English download is col 3
        download_col = 2
        for i, h in enumerate(headers):
            if 'english' in h or 'ইংরেজি' in h:
                download_col = i
                break
        # If the table has exactly 4 columns, English download is usually column 3 (index 3)
        if num_cols == 4 and download_col == 2:
            # Check if column 3 header contains 'english'
            if len(headers) > 3 and ('english' in headers[3] or 'ইংরেজি' in headers[3]):
                download_col = 3

    books = []
    for row in rows[1:]:  # skip header
        cols = row.find_all("td")
        if len(cols) > max(name_col, download_col):
            textbook_name = cols[name_col].get_text(strip=True)
            download_link_tag = cols[download_col].find("a")
            if download_link_tag and download_link_tag.get("href"):
                download_url = download_link_tag["href"]
                books.append([textbook_name, download_url])

    # Save to cache
    cache[cache_key] = {
        'timestamp': time.time(),
        'data': books
    }
    _save_cache(cache)
    print(f"Cached {len(books)} books for {class_url} ({language})")
    return books

# ---------- Main (when run directly) ----------
def main():
    classes = get_class_links()
    if not classes:
        print("No class pages found.")
        return

    print(f"\nFound {len(classes)} class pages:")
    for i, (title, url) in enumerate(classes, 1):
        print(f"{i}. {title}")

    while True:
        try:
            choice = int(input("\nEnter the number of the class page to scrape: "))
            if 1 <= choice <= len(classes):
                break
            else:
                print(f"Please enter a number between 1 and {len(classes)}")
        except ValueError:
            print("Invalid input. Enter a number.")

    selected_title, selected_url = classes[choice-1]
    print(f"\nSelected: {selected_title}\nURL: {selected_url}")

    # Detect available languages
    resp = requests.get(selected_url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, "html.parser")
    has_bangla = False
    has_english = False

    for table in soup.find_all("table"):
        headers = table.find_all("th")
        header_texts = " ".join([th.get_text(strip=True).lower() for th in headers])
        if re.search(r"ক্রমিক", header_texts) or re.search(r"বাংলা", header_texts):
            has_bangla = True
        if re.search(r"(sl|no\.?|sl no)", header_texts) or re.search(r"english", header_texts):
            has_english = True

    if has_bangla and has_english:
        print("\nThis page has both Bangla and English versions.")
        lang_choice = input("Which version? (b for Bangla / e for English): ").strip().lower()
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