import os
import re
import requests
from bs4 import BeautifulSoup
import scraper
from ocr import ocr_pdf, check_dependencies, get_tesseract_langs

BOOKS_DIR = "books"
HEADERS = scraper.HEADERS

def download_pdf(url, save_path):
    """Download a PDF if not already present."""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    if os.path.exists(save_path):
        print(f"  Already downloaded: {os.path.basename(save_path)}")
        return True
    try:
        resp = requests.get(url, stream=True, timeout=30)
        resp.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  Downloaded: {os.path.basename(save_path)}")
        return True
    except Exception as e:
        print(f"  Failed: {e}")
        return False

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def main():
    # 1. Get class list
    classes = scraper.get_class_links()
    if not classes:
        print("No class pages found.")
        return

    print(f"\nFound {len(classes)} class pages:")
    for i, (title, _) in enumerate(classes, 1):
        print(f"{i}. {title}")

    # 2. Select class
    while True:
        try:
            choice = int(input("\nEnter the number of the class page: "))
            if 1 <= choice <= len(classes):
                break
            print(f"Enter a number between 1 and {len(classes)}")
        except ValueError:
            print("Invalid input.")

    class_title, class_url = classes[choice - 1]
    class_folder = sanitize_filename(class_title)
    print(f"\nSelected: {class_title}\nURL: {class_url}")

    # 3. Detect available languages (cached)
    lang_info = scraper.get_language_availability(class_url)
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

    # 4. Get all books for that language
    books = scraper.scrape_download_links(class_url, language)
    if not books:
        print("No books found.")
        return

    # Ensure each book is a list/tuple of (name, url)
    valid_books = []
    for b in books:
        if isinstance(b, (list, tuple)) and len(b) >= 2:
            valid_books.append((b[0], b[1]))
        else:
            print(f"Skipping invalid book entry: {b}")
    books = valid_books
    if not books:
        print("No valid books after filtering.")
        return

    print(f"\nFound {len(books)} textbooks in {language.capitalize()} version:")
    for i, (name, _) in enumerate(books, 1):
        print(f"{i}. {name}")

    # 5. Select a single book
    if len(books) == 1:
        idx = 0
    else:
        while True:
            try:
                choice = int(input(f"\nEnter the number of the book to download/OCR (1-{len(books)}): "))
                if 1 <= choice <= len(books):
                    idx = choice - 1
                    break
                print(f"Please enter a number between 1 and {len(books)}")
            except ValueError:
                print("Invalid input. Enter a number.")

    book_name, pdf_url = books[idx]
    print(f"\nProcessing: {book_name}")

    # 6. Prepare directories: books/class/language/book-name/
    lang_dir = "bangla" if language == 'bangla' else "english"
    safe_book_name = sanitize_filename(book_name)
    book_base_dir = os.path.join(BOOKS_DIR, class_folder, lang_dir, safe_book_name)
    
    original_dir = os.path.join(book_base_dir, "original")
    ocr_dir = os.path.join(book_base_dir, "ocr")
    chapters_dir = os.path.join(book_base_dir, "chapters")

    pdf_filename = safe_book_name + ".pdf"
    pdf_path = os.path.join(original_dir, pdf_filename)
    ocr_path = os.path.join(ocr_dir, pdf_filename)

    # 7. Download if needed
    if not download_pdf(pdf_url, pdf_path):
        print("Download failed, exiting.")
        return

    # 8. OCR (optional, skip if exists)
    ocr_enabled = input("\nGenerate searchable (OCR) PDF? (y/n): ").strip().lower().startswith('y')
    if ocr_enabled:
        tess_ok, gs_ok = check_dependencies()
        if not (tess_ok and gs_ok):
            print("⚠ OCR dependencies missing. Install Tesseract and Ghostscript.")
        elif os.path.exists(ocr_path):
            print(f"✓ Searchable PDF already exists: {ocr_path}")
        else:
            ocr_lang = 'eng' if language == 'english' else 'ben'
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

    # 9. Chapter splitting (optional)
    split_choice = input("\nSplit into chapters/units using advanced detection? (y/n): ").strip().lower()
    if split_choice.startswith('y'):
        try:
            from splitter import detect_chapter_pages_advanced, split_pdf_by_pages
        except ImportError:
            print("❌ PyMuPDF not installed. Run: pip install PyMuPDF")
            return

        # Use OCR'd PDF if available, else original
        source_pdf = ocr_path if os.path.exists(ocr_path) else pdf_path
        print("Analyzing PDF for chapter/unit boundaries...")
        pages = detect_chapter_pages_advanced(source_pdf, language)

        if not pages:
            print("❌ No chapter/unit starts detected automatically.")
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

    print("\nDone.")

if __name__ == "__main__":
    main()