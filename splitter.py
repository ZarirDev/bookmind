import re
import os
import fitz  # PyMuPDF

def normalize_text(text):
    """Replace newlines and multiple spaces with a single space."""
    return re.sub(r'\s+', ' ', text)

def extract_chapter_info(match_text, language='english'):
    """Return (type, number) where type is 'chapter' or 'unit'."""
    if language == 'english':
        m = re.search(r'\b(Unit|Chapter)[\s:\-–—]+([^\s\.]+)', match_text, re.IGNORECASE)
    else:
        m = re.search(r'(অধ্যায়|ইউনিট)[\s:\-–—]*([^\s\.]+)', match_text, re.IGNORECASE)
    if m:
        typ = m.group(1).lower()
        num = m.group(2).lower()
        # Normalize type to 'unit' or 'chapter'
        if 'unit' in typ or 'ইউনিট' in typ:
            return ('unit', num)
        else:
            return ('chapter', num)
    return (None, None)

def detect_chapter_pages_advanced(pdf_path, language='english', debug=True):
    """
    Chapter/unit detection with type-aware acceptance.
    - Unit headings: accepted without requiring 'question' in previous pages.
    - Chapter headings: require 'question' in previous 5 pages.
    - First heading always accepted.
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    if language == 'english':
        heading_plain = re.compile(
            r'\b(Unit|Chapter)[\s:\-–—]+(\d{1,2}|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|'
            r'Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|Nineteen|'
            r'Twenty|Twenty[- ]One|Twenty[- ]Two|Twenty[- ]Three|Twenty[- ]Four|'
            r'Twenty[- ]Five|Twenty[- ]Six|Twenty[- ]Seven|Twenty[- ]Eight|'
            r'Twenty[- ]Nine|Thirty)\b(?!\.)',
            re.IGNORECASE
        )
        heading_period_ok = re.compile(
            r'\b(Unit|Chapter)[\s:\-–—]+(\d{1,2}|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|'
            r'Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|Nineteen|'
            r'Twenty|Twenty[- ]One|Twenty[- ]Two|Twenty[- ]Three|Twenty[- ]Four|'
            r'Twenty[- ]Five|Twenty[- ]Six|Twenty[- ]Seven|Twenty[- ]Eight|'
            r'Twenty[- ]Nine|Thirty)\b',
            re.IGNORECASE
        )
        question_pattern = re.compile(r'\bquestion\b', re.IGNORECASE)
        contents_pattern = re.compile(r'\bContents\b', re.IGNORECASE)
    else:
        heading_plain = re.compile(
            r'(অধ্যায়|ইউনিট)[\s:\-–—]*([০-৯\d]{1,2}|প্রথম|দ্বিতীয়|তৃতীয়|চতুর্থ|পঞ্চম|ষষ্ঠ|সপ্তম|অষ্টম|নবম|দশম|'
            r'এগারো|বারো|তেরো|চৌদ্দ|পনেরো|ষোল|সতেরো|আঠারো|উনিশ|বিশ|একুশ|বাইশ|তেইশ|চব্বিশ|পঁচিশ|'
            r'ছাব্বিশ|সাতাশ|আঠাশ|উনত্রিশ|ত্রিশ)(?!\.)',
            re.IGNORECASE
        )
        heading_period_ok = re.compile(
            r'(অধ্যায়|ইউনিট)[\s:\-–—]*([০-৯\d]{1,2}|প্রথম|দ্বিতীয়|তৃতীয়|চতুর্থ|পঞ্চম|ষষ্ঠ|সপ্তম|অষ্টম|নবম|দশম|'
            r'এগারো|বারো|তেরো|চৌদ্দ|পনেরো|ষোল|সতেরো|আঠারো|উনিশ|বিশ|একুশ|বাইশ|তেইশ|চব্বিশ|পঁচিশ|'
            r'ছাব্বিশ|সাতাশ|আঠাশ|উনত্রিশ|ত্রিশ)',
            re.IGNORECASE
        )
        question_pattern = re.compile(r'প্রশ্ন', re.IGNORECASE)
        contents_pattern = re.compile(r'সূচিপত্র|Contents', re.IGNORECASE)

    chapter_starts = []
    found_first_heading = False
    seen_numbers = set()
    header_occurrences = {}  # key: (type, number) -> list of page numbers

    # First pass: collect all heading occurrences
    for page_num in range(total_pages):
        text = normalize_text(doc[page_num].get_text("text"))
        if len(text) < 50:
            continue
        first_part = text[:200].lower()
        if contents_pattern.search(first_part):
            continue

        matches = list(heading_plain.finditer(text))
        if not matches:
            matches = list(heading_period_ok.finditer(text))

        for match in matches:
            typ, num = extract_chapter_info(match.group(0), language)
            if typ and num:
                key = (typ, num)
                if key not in header_occurrences:
                    header_occurrences[key] = []
                header_occurrences[key].append(page_num)

    # Second pass: decide which pages to accept
    for (typ, num), pages in header_occurrences.items():
        if not pages:
            continue
        candidate_page = pages[0]

        if not found_first_heading:
            chapter_starts.append(candidate_page)
            found_first_heading = True
            seen_numbers.add((typ, num))
            if debug:
                print(f"Page {candidate_page+1}: ACCEPTED as first {typ} ({num})")
            continue

        # For chapters, require 'question' proximity; for units, accept immediately
        if typ == 'unit':
            accept = True
            reason = f"unit ({num})"
        else:
            # Check for 'question' in previous 5 pages (including current)
            question_found = False
            start_lookback = max(0, candidate_page - 5)
            for lookback in range(start_lookback, candidate_page + 1):
                if question_pattern.search(normalize_text(doc[lookback].get_text("text"))):
                    question_found = True
                    break
            accept = question_found
            reason = f"chapter ({num}) - {'question found' if accept else 'no question'}"

        if accept:
            chapter_starts.append(candidate_page)
            seen_numbers.add((typ, num))
            if debug:
                print(f"Page {candidate_page+1}: ACCEPTED {reason}")
        else:
            if debug:
                print(f"Page {candidate_page+1}: REJECTED {reason}")

    doc.close()
    chapter_starts = sorted(set(chapter_starts))

    if len(chapter_starts) <= 2:
        print("⚠ Advanced detection found few sections; using simple heading detection.")
        chapter_starts = _detect_headings_simple(pdf_path, language, debug)

    if debug:
        print(f"\nFinal detected starts (1-indexed): {[p+1 for p in chapter_starts]}")

    return chapter_starts

def _detect_headings_simple(pdf_path, language='english', debug=True):
    """Simple fallback: first occurrence of each heading number."""
    doc = fitz.open(pdf_path)
    starts = []
    seen = set()

    if language == 'english':
        pattern = re.compile(
            r'\b(Unit|Chapter)[\s:\-–—]+(\d{1,2}|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|'
            r'Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|Nineteen|'
            r'Twenty|Twenty[- ]One|Twenty[- ]Two|Twenty[- ]Three|Twenty[- ]Four|'
            r'Twenty[- ]Five|Twenty[- ]Six|Twenty[- ]Seven|Twenty[- ]Eight|'
            r'Twenty[- ]Nine|Thirty)\b',
            re.IGNORECASE
        )
        contents_pattern = re.compile(r'\bContents\b', re.IGNORECASE)
    else:
        pattern = re.compile(
            r'(অধ্যায়|ইউনিট)[\s:\-–—]*([০-৯\d]{1,2}|প্রথম|দ্বিতীয়|তৃতীয়|চতুর্থ|পঞ্চম|ষষ্ঠ|সপ্তম|অষ্টম|নবম|দশম|'
            r'এগারো|বারো|তেরো|চৌদ্দ|পনেরো|ষোল|সতেরো|আঠারো|উনিশ|বিশ|একুশ|বাইশ|তেইশ|চব্বিশ|পঁচিশ|'
            r'ছাব্বিশ|সাতাশ|আঠাশ|উনত্রিশ|ত্রিশ)',
            re.IGNORECASE
        )
        contents_pattern = re.compile(r'সূচিপত্র|Contents', re.IGNORECASE)

    header_occurrences = {}
    for page_num in range(len(doc)):
        text = normalize_text(doc[page_num].get_text("text"))
        first_part = text[:200].lower()
        if contents_pattern.search(first_part):
            continue
        for match in pattern.finditer(text):
            typ, num = extract_chapter_info(match.group(0), language)
            if typ and num:
                key = (typ, num)
                if key not in header_occurrences:
                    header_occurrences[key] = []
                header_occurrences[key].append(page_num)

    for key, pages in header_occurrences.items():
        if pages and key not in seen:
            starts.append(pages[0])
            seen.add(key)

    starts.sort()
    doc.close()
    return starts

def detect_bangla_grammar_chapters(pdf_path, debug=False):
    """
    Special detection for Bangla grammar books.
    Looks for 'পরিচ্ছেদ' followed by digits, tolerating OCR noise/symbols.
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    # Pattern: "প" + anything + "রি" + anything + "চ্ছে" + anything + "দ" + optional punctuation + digits
    pattern = re.compile(
        r'প.*?রি.*?চ্ছে.*?দ\s*[ঃ\-\.]?\s*([০-৯\d]+)',
        re.IGNORECASE
    )
    chapter_starts = []
    found_first = False

    for page_num in range(total_pages):
        text = normalize_text(doc[page_num].get_text("text"))
        if debug and page_num < 10:
            snippet = text[:150].replace('\n', ' ')
            print(f"Page {page_num+1}: {snippet}...")

        match = pattern.search(text)
        if match:
            if debug:
                print(f"  -> Found heading on page {page_num+1}: {match.group(0)}")
            if not found_first:
                chapter_starts.append(page_num)
                found_first = True
            else:
                chapter_starts.append(page_num)

    doc.close()

    if not chapter_starts:
        print("⚠ No 'পরিচ্ছেদ' headings found.")
    elif debug:
        print(f"Bangla grammar chapters at pages (1-indexed): {[p+1 for p in chapter_starts]}")

    return chapter_starts

def split_pdf_by_pages(input_pdf, output_dir, split_pages, base_name="Section"):
    """Split PDF at the given 0-indexed start pages."""
    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(input_pdf)
    total_pages = len(doc)

    ranges = []
    for i, start in enumerate(split_pages):
        end = split_pages[i+1] - 1 if i+1 < len(split_pages) else total_pages - 1
        ranges.append((start, end))

    output_paths = []
    for idx, (start, end) in enumerate(ranges, 1):
        new_doc = fitz.open()
        for page_num in range(start, end+1):
            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
        out_path = os.path.join(output_dir, f"{base_name}_{idx:02d}.pdf")
        new_doc.save(out_path)
        new_doc.close()
        output_paths.append(out_path)

    doc.close()
    return output_paths

def detect_bangla_literature_chapters(pdf_path, debug=True):
    """
    Special detection for Bangla literature books.
    Splits at pages containing 'সৃজনশীল প্রশ্ন' (creative questions).
    The next page after such a marker becomes a new chapter start.
    Chapter 1 always starts at page 0.
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    creative_pattern = re.compile(r'সৃজনশীল প্রশ্ন', re.IGNORECASE)

    chapter_starts = [0]
    for page_num in range(total_pages):
        text = normalize_text(doc[page_num].get_text("text"))
        if creative_pattern.search(text):
            if page_num + 1 < total_pages:
                chapter_starts.append(page_num + 1)
    doc.close()
    chapter_starts = sorted(set(chapter_starts))
    if debug:
        print(f"Bangla literature chapters at pages (1-indexed): {[p+1 for p in chapter_starts]}")
    return chapter_starts