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
    name = re.sub(r'[^\w\s\-.]', '', name, flags=re.ASCII)
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def get_book_type(book_name, language):
    name_lower = book_name.lower()
    if 'grammar' in name_lower:
        return 'bangla_grammar'
    if language == 'english' and 'bangla' in name_lower and 'bangladesh' not in name_lower:
        return 'bangla_lit'
    return 'default'

def process_existing_book():
    """Walk the books directory and let the user pick an already downloaded PDF."""
    if not os.path.isdir(BOOKS_DIR):
        print("No 'books' folder found.")
        return None
    pdf_files = []
    for root, dirs, files in os.walk(BOOKS_DIR):
        for file in files:
            if file.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(root, file))
    if not pdf_files:
        print("No PDF files found in books/ directory.")
        return None
    print("\n📂 Existing PDFs:")
    for i, path in enumerate(pdf_files, 1):
        rel = os.path.relpath(path, BOOKS_DIR)
        print(f"{i}. {rel}")
    print("0. Go back")
    while True:
        try:
            choice = int(input(f"\nPick a PDF (1-{len(pdf_files)}, or 0 to go back): "))
            if choice == 0:
                return None
            if 1 <= choice <= len(pdf_files):
                return pdf_files[choice - 1]
            print(f"Enter 1-{len(pdf_files)} or 0")
        except ValueError:
            print("Invalid input.")

def main():
    check_groq_key()

    # Fetch categories once (cached if offline)
    categories = scraper.get_categories()
    if not categories:
        print("No categories available (offline with empty cache).")
        pdf_path = process_existing_book()
        if not pdf_path:
            return
        # Proceed directly to OCR/split/summarise using the selected PDF
        book_base_dir = os.path.dirname(pdf_path)
        parts = pdf_path.split(os.sep)
        language = 'english' if 'english' in parts else 'bangla'
        safe_book = os.path.splitext(os.path.basename(pdf_path))[0]
        original_dir = os.path.join(book_base_dir, "original")
        ocr_dir = os.path.join(book_base_dir, "ocr")
        chapters_dir = os.path.join(book_base_dir, "chapters")
        os.makedirs(original_dir, exist_ok=True)
        os.makedirs(ocr_dir, exist_ok=True)
        os.makedirs(chapters_dir, exist_ok=True)
        original_pdf = os.path.join(original_dir, os.path.basename(pdf_path))
        if not os.path.exists(original_pdf):
            shutil.copy2(pdf_path, original_pdf)
            pdf_path = original_pdf
        else:
            pdf_path = original_pdf
        print(f"\n📄 Working on: {safe_book}")
        # Run OCR/split/summarise menu (same as bottom part)
        run_post_download_menu(pdf_path, ocr_dir, chapters_dir, book_base_dir, language)
        return

    # ---------- Navigation state machine ----------
    STAGE_CATEGORY = 'category'
    STAGE_CLASS = 'class'
    STAGE_BOOK_DATA = 'book_data'   # fetch data
    STAGE_LANGUAGE = 'language'
    STAGE_CHOOSE_BOOK = 'choose_book'

    stage = STAGE_CATEGORY
    cat_name = cat_url = None
    class_title = class_url = None
    book_data = None
    language = None

    while True:
        if stage == STAGE_CATEGORY:
            print("\nSelect a category (0 to exit):")
            for i, (name, _) in enumerate(categories, 1):
                print(f"{i}. {name}")

            choice = input("\nEnter number: ").strip()
            if choice == '0':
                print("Goodbye!")
                return
            if not choice.isdigit() or not (1 <= int(choice) <= len(categories)):
                print(f"Please choose 1-{len(categories)} or 0 to exit.")
                continue

            idx = int(choice) - 1
            cat_name, cat_url = categories[idx]
            print(f"\nCategory: {cat_name}")
            stage = STAGE_CLASS
            continue

        elif stage == STAGE_CLASS:
            # Fetch classes (cached)
            classes = scraper.get_class_links(cat_url)
            if not classes:
                print("No classes found. Going back to category selection.")
                stage = STAGE_CATEGORY
                continue

            print(f"\nFound {len(classes)} classes (0 to go back):")
            for i, (title, _) in enumerate(classes, 1):
                print(f"{i}. {title}")

            choice = input("\nEnter class number: ").strip()
            if choice == '0':
                stage = STAGE_CATEGORY
                continue
            if not choice.isdigit() or not (1 <= int(choice) <= len(classes)):
                print(f"Please choose 1-{len(classes)} or 0 to go back.")
                continue

            idx = int(choice) - 1
            class_title, class_url = classes[idx]
            print(f"\nSelected: {class_title}")
            stage = STAGE_BOOK_DATA
            continue

        elif stage == STAGE_BOOK_DATA:
            # Fetch book data
            book_data = scraper.scrape_download_links(class_url)
            english_names = book_data['english_names']
            bangla_links = book_data['bangla_links']
            english_links = book_data['english_links']

            # Decide next stage
            if bangla_links and english_links:
                stage = STAGE_LANGUAGE
            elif bangla_links:
                language = 'bangla'
                print("\nOnly Bangla version available.")
                stage = STAGE_CHOOSE_BOOK
            elif english_links:
                language = 'english'
                print("\nOnly English version available.")
                stage = STAGE_CHOOSE_BOOK
            else:
                print("No books found. Going back to class selection.")
                stage = STAGE_CLASS
            continue

        elif stage == STAGE_LANGUAGE:
            print("\nBoth Bangla and English available.")
            lang_choice = input("Which version? (b/e, or 0 to go back): ").strip().lower()
            if lang_choice == '0':
                stage = STAGE_CLASS
                continue
            if lang_choice.startswith('e'):
                language = 'english'
                stage = STAGE_CHOOSE_BOOK
                continue
            elif lang_choice.startswith('b'):
                language = 'bangla'
                stage = STAGE_CHOOSE_BOOK
                continue
            else:
                print("Invalid choice. Enter 'b' for Bangla, 'e' for English, or 0 to go back.")
                continue

        # After language chosen, proceed to choose book
        if stage == STAGE_LANGUAGE:
            stage = STAGE_CHOOSE_BOOK
            continue

        elif stage == STAGE_CHOOSE_BOOK:
            english_names = book_data['english_names']
            # pick appropriate link list
            if language == 'bangla':
                chosen_links = book_data['bangla_links']
            else:
                chosen_links = book_data['english_links']

            num_books = len(english_names)
            print(f"\n{num_books} textbooks ({language} version, 0 to go back):")
            for i in range(num_books):
                avail = ""
                if i < len(book_data['bangla_links']):
                    avail += " [Bangla]"
                if i < len(book_data['english_links']):
                    avail += " [English]"
                print(f"{i+1}. {english_names[i]}{avail}")

            if num_books == 1:
                print("Only one book available. Selecting it automatically...")
                # but still allow 0 to go back? We'll ask confirmation or just pick.
                # For safety, we ask with input.
                pass

            choice = input(f"\nEnter book number (1-{num_books}, or 0 to go back): ").strip()
            if choice == '0':
                # go back to language selection if it existed, else to class
                if book_data['bangla_links'] and book_data['english_links']:
                    stage = STAGE_LANGUAGE
                else:
                    stage = STAGE_CLASS
                continue
            if not choice.isdigit() or not (1 <= int(choice) <= num_books):
                print(f"Please pick 1-{num_books} or 0 to go back.")
                continue

            idx = int(choice) - 1
            english_book_name = english_names[idx]
            download_url = chosen_links[idx][1] if idx < len(chosen_links) else None
            if not download_url:
                print("Download link missing. Going back.")
                continue

            print(f"\nDownloading: {english_book_name} ({language} version)")

            # Setup directories
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

            # Download
            if not download_pdf(download_url, pdf_path):
                print("Download failed. Going back to book selection.")
                continue  # stay in STAGE_CHOOSE_BOOK

            # Run post-download pipeline (OCR, split, summarise)
            run_post_download_menu(pdf_path, ocr_dir, chapters_dir, book_base_dir, language)
            print("\nDone processing. Returning to category selection.")
            stage = STAGE_CATEGORY   # loop back to top
            continue

    # If we ever break out of the while loop, end
    print("Exiting.")

def run_post_download_menu(pdf_path, ocr_dir, chapters_dir, book_base_dir, language):
    """Common OCR / Split / Summarise flow after a PDF is available."""
    ocr_path = os.path.join(ocr_dir, os.path.basename(pdf_path))
    book_type = get_book_type(os.path.basename(pdf_path), language)

    ocr_enabled = input("\nGenerate searchable (OCR) PDF? (y/n, 0 to skip): ").strip().lower()
    if ocr_enabled == '0':
        pass
    elif ocr_enabled.startswith('y'):
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

    split_choice = input("\nSplit into chapters/units? (y/n, 0 to skip): ").strip().lower()
    if split_choice == '0' or not split_choice.startswith('y'):
        pass
    else:
        try:
            from splitter import (
                detect_chapter_pages_advanced,
                detect_bangla_literature_chapters,
                detect_bangla_grammar_chapters,
                split_pdf_by_pages
            )
        except ImportError:
            print("❌ PyMuPDF not installed. Run: pip install PyMuPDF")
        else:
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
                manual = input("Enter page numbers manually (1-indexed, comma-separated, or 0 to skip): ").strip()
                if manual == '0':
                    pages = []
                elif manual:
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

    summarise_choice = input("\nSummarise a chapter using Groq AI? (y/n, 0 to skip): ").strip().lower()
    if summarise_choice == '0' or not summarise_choice.startswith('y'):
        pass
    else:
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
                            choice = input(f"Enter chapter number to summarise (1-{len(chapter_files)}, or 0 to skip): ").strip()
                            if choice == '0':
                                break
                            if choice.isdigit() and 1 <= int(choice) <= len(chapter_files):
                                ch_choice = int(choice)
                                selected_chapter = chapter_files[ch_choice - 1]
                                chapter_path = os.path.join(chapters_dir, selected_chapter)
                                chapter_name = os.path.splitext(selected_chapter)[0]
                                summary_dir = os.path.join(book_base_dir, "summarised")
                                summarise_chapter(chapter_path, summary_dir, chapter_name)
                                break
                            else:
                                print(f"Enter a number between 1 and {len(chapter_files)} or 0.")
                else:
                    print("No chapters directory found. Split the book first.")

if __name__ == "__main__":
    main()