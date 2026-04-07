import requests
from bs4 import BeautifulSoup
import time
import re

BASE_URL = "https://nctbbook.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}

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
    # Exclude syllabus pages
    if "syllabus" in title_lower:
        return False
    # Include class textbook pages
    if "class" in title_lower and "book" in title_lower:
        return True
    # Include Dakhil (madrasah) pages
    if "dakhil" in title_lower and "book" in title_lower:
        return True
    return False

def get_class_links():
    """Scrape all class textbook pages across pagination. Returns list of (cleaned_title, url)."""
    class_links = []
    url = BASE_URL
    page_num = 1

    while True:
        # print(f"Scanning page {page_num}...")
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
                class_links.append((clean, href))
                # print(f"  Found: {clean}")

        # Pagination: look for <link rel="next">
        next_link = soup.find("link", rel="next")
        if next_link and next_link.get("href"):
            url = next_link["href"]
            page_num += 1
            time.sleep(1)
        else:
            break

    # print(f"\nTotal class pages found: {len(class_links)}")
    return class_links

# Example usage (you can comment this out later)
# if __name__ == "__main__":
#     classes = get_class_links()
#     for title, url in classes:
#         print(f"{title} -> {url}")
