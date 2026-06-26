import os
import re
import requests
import shutil
from bs4 import BeautifulSoup
import scraper
from ocr import ocr_pdf, check_dependencies, get_tesseract_langs, pdf_has_text
from dotenv import load_dotenv

load_dotenv()

BOOKS_DIR = "books"
HEADERS = scraper.HEADERS

def check_groq_key():
    if not os.environ.get("GROQ_API_KEY"):
        print("⚠ GROQ_API_KEY not set. Summarisation will fail.")
        print("  Set it with: export GROQ_API_KEY='your-key'")

def is_pdf_content(response):
    content_type = response.headers.get('Content-Type', '').lower()
    if 'application/pdf' in content_type:
        return True
    content_start = response.content[:8]
    if content_start.startswith(b'%PDF'):
        return True
    return False

def extract_direct_pdf_url(html_content, base_url=None):
    soup = BeautifulSoup(html_content, 'html.parser')
    download_input = soup.find('input', {'id': 'downloadURL'})
    if download_input and download_input.get('value'):
        return download_input['value']
    download_link = soup.find('a', {'id': 'downloadFile'})
    if download_link and download_link.get('href'):
        href = download_link['href']
        if href.startswith('http'):
            return href
        elif base_url:
            from urllib.parse import urljoin
            return urljoin(base_url, href)
    for a in soup.find_all('a', href=True):
        if '/download' in a['href']:
            href = a['href']
            if href.startswith('http'):
                return href
            elif base_url:
                from urllib.parse import urljoin
                return urljoin(base_url, href)
    return None

def download_pdf(url, save_path):
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    if os.path.exists(save_path):
        print(f"  Already downloaded: {os.path.basename(save_path)}")
        return True
    try:
        resp = requests.get(url, headers=HEADERS, stream=True, timeout=30)
        resp.raise_for_status()
        if is_pdf_content(resp):
            with open(save_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"  Downloaded: {os.path.basename(save_path)}")
            return True
        content_type = resp.headers.get('Content-Type', '').lower()
        if 'text/html' in content_type or resp.text.strip().startswith('<!DOCTYPE'):
            print("  Detected HTML landing page, extracting direct PDF link...")
            direct_url = extract_direct_pdf_url(resp.text, base_url=url)
            if not direct_url:
                print("  Failed to extract direct PDF link.")
                return False
            print(f"  Found direct link: {direct_url}")
            pdf_resp = requests.get(direct_url, headers=HEADERS, stream=True, timeout=60)
            pdf_resp.raise_for_status()
            if is_pdf_content(pdf_resp):
                with open(save_path, 'wb') as f:
                    for chunk in pdf_resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"  Downloaded: {os.path.basename(save_path)}")
                return True
            else:
                print("  Direct link did not return a PDF.")
                return False
        else:
            print(f"  Unexpected content type: {content_type}")
            return False
    except Exception as e:
        print(f"  Failed: {e}")
        return False

def sanitize_filename(name):
    # Allow only ASCII letters, digits, spaces, hyphens, underscores, dots
    name = re.sub(r'[^\w\s\-.]', '', name, flags=re.ASCII)
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def get_book_type(book_name, language):
    """Determine special book type for splitting/OCR."""
    name_lower = book_name.lower()
    if 'grammar' in name_lower:
        return 'bangla_grammar'
    if language == 'english' and 'bangla' in name_lower and 'bangladesh' not in name_lower:
        return 'bangla_lit'
    return 'default'

def main():
    # 1. Select category
    categories = scraper.get_categories()
    if not categories:
        print("No categories found on homepage.")
        return
    print("\nSelect a category:")
    for i, (name, _) in enumerate(categories, 1):
        print(f"{i}. {name}")

    while True:
        try:
            choice = int(input("\nEnter number: "))
            if 1 <= choice <= len(categories):
                break
            print(f"Choose between 1 and {len(categories)}")
        except ValueError:
            print("Invalid input.")
    cat_name, cat_url = categories[choice - 1]
    print(f"\nCategory: {cat_name}")

    # 2. Select class
    classes = scraper.get_class_links(cat_url)
    if not classes:
        print("No classes found in this category.")
        return
    print(f"\nFound {len(classes)} classes:")
    for i, (title, _) in enumerate(classes, 1):
        print(f"{i}. {title}")

    while True:
        try:
            choice = int(input("\nEnter class number: "))
            if 1 <= choice <= len(classes):
                break
            print(f"Choose between 1 and {len(classes)}")
        except ValueError:
            print("Invalid input.")
    class_title, class_url = classes[choice - 1]
    print(f"\nSelected: {class_title}")

    # 3. Get book data (both tables)
    book_data = scraper.scrape_download_links(class_url)
    english_names = book_data['english_names']
    bangla_links = book_data['bangla_links']
    english_links = book_data['english_links']

    # 4. Language selection
    if bangla_links and english_links:
        lang_choice = input("\nBoth Bangla and English available. Which version? (b/e): ").strip().lower()
        if lang_choice.startswith('e'):
            chosen_links = english_links
            language = 'english'
        else:
            chosen_links = bangla_links
            language = 'bangla'
    elif bangla_links:
        chosen_links = bangla_links
        language = 'bangla'
        print("\nOnly Bangla version available.")
    elif english_links:
        chosen_links = english_links
        language = 'english'
        print("\nOnly English version available.")
    else:
        print("No books found for this class.")
        return

    # 5. Show books using English names
    num_books = len(english_names)
    print(f"\n{num_books} textbooks (English names):")
    for i in range(num_books):
        # Show both English name and source language availability
        avail = ""
        if i < len(bangla_links):
            avail += " [Bangla]"
        if i < len(english_links):
            avail += " [English]"
        print(f"{i+1}. {english_names[i]}")

    # Choose book
    if num_books == 1:
        idx = 0
    else:
        while True:
            try:
                choice = int(input(f"\nEnter book number (1-{num_books}): "))
                if 1 <= choice <= num_books:
                    idx = choice - 1
                    break
                print(f"Pick 1 to {num_books}")
            except ValueError:
                print("Invalid input.")
    english_book_name = english_names[idx]
    download_url = chosen_links[idx][1] if idx < len(chosen_links) else None
    if not download_url:
        print("Download link missing for this book in the chosen language.")
        return
    print(f"\nDownloading: {english_book_name} ({language} version)")

    # 6. Setup directories using English names only
    safe_cat = sanitize_filename(cat_name)
    safe_class = sanitize_filename(class_title)
    safe_book = sanitize_filename(english_book_name)
    lang_dir = "bangla" if language == 'bangla' else "english"
    book_base_dir = os.path.join(BOOKS_DIR, safe_cat, safe_class, lang_dir, safe_book)

    original_dir = os.path.join(book_base_dir, "original")
    ocr_dir = os.path.join(book_base_dir, "ocr")
    chapters_dir = os.path.join(book_base_dir, "chapters")

    pdf_filename = safe_book + ".pdf"
    pdf_path = os.path.join(original_dir, pdf_filename)
    ocr_path = os.path.join(ocr_dir, pdf_filename)

    # 7. Download PDF
    if not download_pdf(download_url, pdf_path):
        print("Download failed, exiting.")
        return

    # 8. OCR (optional)
    book_type = get_book_type(english_book_name, language)
    ocr_enabled = input("\nGenerate searchable (OCR) PDF? (y/n): ").strip().lower().startswith('y')
    if ocr_enabled:
        tess_ok, gs_ok = check_dependencies()
        if not (tess_ok and gs_ok):
            print("⚠ OCR dependencies missing.")
        elif os.path.exists(ocr_path):
            print(f"✓ Searchable PDF already exists: {ocr_path}")
        else:
            if pdf_has_text(pdf_path):
                print("ℹ PDF already contains selectable text. Skipping OCR.")
                os.makedirs(os.path.dirname(ocr_path), exist_ok=True)
                shutil.copy2(pdf_path, ocr_path)
                print(f"✓ Copied to OCR folder: {ocr_path}")
            else:
                ocr_lang = 'eng' if language == 'english' else 'ben'
                if book_type in ('bangla_lit', 'bangla_grammar'):
                    ocr_lang = 'ben'
                    print(f"  Using Bengali OCR for {book_type} book.")
                installed = get_tesseract_langs()
                if ocr_lang not in installed and ocr_lang != 'eng':
                    print(f"⚠ Tesseract language '{ocr_lang}' not installed. Falling back to English.")
                    ocr_lang = 'eng'
                try:
                    ocr_pdf(pdf_path, ocr_path, lang=ocr_lang, force=False)
                    print(f"✓ Searchable PDF created: {ocr_path}")
                except Exception as e:
                    error_msg = str(e)
                    if "already has text" in error_msg or "PriorOcrFoundError" in error_msg:
                        force_choice = input("PDF may contain hidden text. Force OCR anyway? (y/n): ").strip().lower()
                        if force_choice.startswith('y'):
                            try:
                                ocr_pdf(pdf_path, ocr_path, lang=ocr_lang, force=True)
                                print(f"✓ Searchable PDF created (forced): {ocr_path}")
                            except Exception as e2:
                                print(f"OCR failed even with force: {e2}")
                        else:
                            print("OCR skipped.")
                    else:
                        print(f"OCR failed: {e}")

    # 9. Split into chapters/units (optional)
    split_choice = input("\nSplit into chapters/units? (y/n): ").strip().lower()
    if split_choice.startswith('y'):
        try:
            from splitter import (
                detect_chapter_pages_advanced,
                detect_bangla_literature_chapters,
                detect_bangla_grammar_chapters,
                split_pdf_by_pages
            )
        except ImportError:
            print("❌ PyMuPDF not installed. Run: pip install PyMuPDF")
            return

        source_pdf = ocr_path if os.path.exists(ocr_path) else pdf_path
        print("Analyzing PDF for chapter boundaries...")
        if book_type == 'bangla_lit':
            pages = detect_bangla_literature_chapters(source_pdf, debug=False)
        elif book_type == 'bangla_grammar':
            pages = detect_bangla_grammar_chapters(source_pdf, debug=False)
        else:
            pages = detect_chapter_pages_advanced(source_pdf, language, debug=False)

        if not pages:
            print("❌ No chapter starts detected automatically.")
            manual = input("Enter page numbers manually (1-indexed, comma-separated): ").strip()
            if manual:
                try:
                    pages = [int(p.strip()) - 1 for p in manual.split(',')]
                except ValueError:
                    print("Invalid input. Skipping split.")
                    pages = []

        if pages:
            split_pdf_by_pages(source_pdf, chapters_dir, pages)
            print(f"✓ Split into {len(pages)} sections in: {chapters_dir}")
        else:
            print("No sections to split.")

    # 10. Summarise (optional)
    summarise_choice = input("\nSummarise a chapter using Groq AI? (y/n): ").strip().lower()
    if summarise_choice.startswith('y'):
        if not os.environ.get("GROQ_API_KEY"):
            print("⚠ GROQ_API_KEY environment variable not set.")
            print("  Set it with: export GROQ_API_KEY='your-key'")
        else:
            try:
                from summarise import summarise_chapter
            except ImportError:
                print("❌ summarise.py not found or missing 'groq' package.")
            else:
                if os.path.exists(chapters_dir):
                    chapter_files = sorted([f for f in os.listdir(chapters_dir) if f.endswith('.pdf')])
                    if not chapter_files:
                        print("No chapter PDFs found. Split the book first.")
                    else:
                        print("\nAvailable chapters:")
                        for i, f in enumerate(chapter_files, 1):
                            print(f"{i}. {f}")
                        while True:
                            try:
                                ch_choice = int(input(f"Enter chapter number to summarise (1-{len(chapter_files)}): "))
                                if 1 <= ch_choice <= len(chapter_files):
                                    break
                                print(f"Enter a number between 1 and {len(chapter_files)}")
                            except ValueError:
                                print("Invalid input.")
                        selected_chapter = chapter_files[ch_choice - 1]
                        chapter_path = os.path.join(chapters_dir, selected_chapter)
                        chapter_name = os.path.splitext(selected_chapter)[0]
                        summary_dir = os.path.join(book_base_dir, "summarised")
                        summarise_chapter(chapter_path, summary_dir, chapter_name)
                else:
                    print("No chapters directory found. Split the book first.")

    print("\nDone.")

if __name__ == "__main__":
    main()