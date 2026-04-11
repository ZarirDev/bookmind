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

def find_table(soup, language):
    """Helper to find Bangla or English table (copy of scraper's internal)."""
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        header_text = " ".join(headers)
        if language == 'bangla':
            if re.search(r"ক্রমিক|বাংলা", header_text):
                return table
        else:
            if re.search(r"(sl|no\.?|sl no|english)", header_text):
                return table
    return None

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

    # 3. Detect available languages
    resp = requests.get(class_url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, "html.parser")
    has_bangla = bool(find_table(soup, 'bangla'))
    has_english = bool(find_table(soup, 'english'))

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

    # 6. Prepare directories
    lang_dir = "bangla" if language == 'bangla' else "english"
    base_dir = os.path.join(BOOKS_DIR, class_folder, lang_dir)
    non_ocr_dir = os.path.join(base_dir, "non_ocr")
    ocr_dir = os.path.join(base_dir, "ocr")

    safe_name = sanitize_filename(book_name) + ".pdf"
    pdf_path = os.path.join(non_ocr_dir, safe_name)
    ocr_path = os.path.join(ocr_dir, safe_name)

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
                print(f"OCR failed: {e}")

    # 9. Chapter splitting (optional)
    split_choice = input("\nSplit into chapters using advanced detection? (y/n): ").strip().lower()
    if split_choice.startswith('y'):
        try:
            from splitter import detect_chapter_pages_advanced, split_pdf_by_pages
        except ImportError:
            print("❌ PyMuPDF not installed. Run: pip install PyMuPDF")
            return

        # Use OCR'd PDF if available, else original
        source_pdf = ocr_path if os.path.exists(ocr_path) else pdf_path
        print("Analyzing PDF for chapter boundaries...")
        pages = detect_chapter_pages_advanced(source_pdf, language)

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
            # Book-specific chapters folder
            chapters_dir = os.path.join(base_dir, f"{safe_name.replace('.pdf', '')}_chapters")
            split_pdf_by_pages(source_pdf, chapters_dir, pages)
            print(f"✓ Split into {len(pages)} chapters in: {chapters_dir}")
        else:
            print("No chapters to split.")

    print("\nDone.")

if __name__ == "__main__":
    main()