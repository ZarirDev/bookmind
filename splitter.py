import re
import os
import fitz  # PyMuPDF

def normalize_text(text):
    """Replace newlines and multiple spaces with a single space."""
    return re.sub(r'\s+', ' ', text)

def detect_chapter_pages_advanced(pdf_path, language='english'):
    """
    Relaxed chapter/unit detection.
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    if language == 'english':
        heading_pattern = re.compile(
            r'\b(Unit|Chapter)\s+(\d{1,2}|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|'
            r'Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|Nineteen|'
            r'Twenty|Twenty[- ]One|Twenty[- ]Two|Twenty[- ]Three|Twenty[- ]Four|'
            r'Twenty[- ]Five|Twenty[- ]Six|Twenty[- ]Seven|Twenty[- ]Eight|'
            r'Twenty[- ]Nine|Thirty)\b(?!\.)',
            re.IGNORECASE
        )
        question_pattern = re.compile(r'\bquestion\b', re.IGNORECASE)
        contents_pattern = re.compile(r'\bContents\b', re.IGNORECASE)
    else:
        heading_pattern = re.compile(
            r'(অধ্যায়|ইউনিট)\s*([০-৯\d]{1,2}|প্রথম|দ্বিতীয়|তৃতীয়|চতুর্থ|পঞ্চম|ষষ্ঠ|সপ্তম|অষ্টম|নবম|দশম|'
            r'এগারো|বারো|তেরো|চৌদ্দ|পনেরো|ষোল|সতেরো|আঠারো|উনিশ|বিশ|একুশ|বাইশ|তেইশ|চব্বিশ|পঁচিশ|'
            r'ছাব্বিশ|সাতাশ|আঠাশ|উনত্রিশ|ত্রিশ)(?!\.)',
            re.IGNORECASE
        )
        question_pattern = re.compile(r'প্রশ্ন', re.IGNORECASE)
        contents_pattern = re.compile(r'সূচিপত্র|Contents', re.IGNORECASE)

    chapter_starts = []
    found_first_heading = False

    for page_num in range(total_pages):
        page = doc[page_num]
        raw_text = page.get_text("text")
        text = normalize_text(raw_text)

        if len(text.strip()) < 50:
            continue

        if contents_pattern.search(text):
            continue

        heading_matches = list(heading_pattern.finditer(text))
        if len(heading_matches) > 1:
            continue

        if heading_matches:
            if not found_first_heading:
                chapter_starts.append(page_num)
                found_first_heading = True
                continue

            question_found = False
            start_lookback = max(0, page_num - 4)
            for lookback_page in range(start_lookback, page_num):
                lookback_text = normalize_text(doc[lookback_page].get_text("text"))
                if question_pattern.search(lookback_text):
                    question_found = True
                    break

            if question_found:
                chapter_starts.append(page_num)

    doc.close()

    # If we got too few chapters, fall back to simple heading detection
    if len(chapter_starts) <= 2:
        print("⚠ Advanced detection found few sections; using simple heading detection.")
        chapter_starts = _detect_headings_simple(pdf_path, language)

    return chapter_starts

def _detect_headings_simple(pdf_path, language='english'):
    """
    Simple heading detection: takes all heading occurrences
    (skipping TOC and multi‑heading pages).
    """
    doc = fitz.open(pdf_path)
    starts = []

    if language == 'english':
        pattern = re.compile(
            r'\b(Unit|Chapter)\s+(\d{1,2}|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|'
            r'Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|Nineteen|'
            r'Twenty|Twenty[- ]One|Twenty[- ]Two|Twenty[- ]Three|Twenty[- ]Four|'
            r'Twenty[- ]Five|Twenty[- ]Six|Twenty[- ]Seven|Twenty[- ]Eight|'
            r'Twenty[- ]Nine|Thirty)\b',
            re.IGNORECASE
        )
        contents_pattern = re.compile(r'\bContents\b', re.IGNORECASE)
    else:
        pattern = re.compile(
            r'(অধ্যায়|ইউনিট)\s*([০-৯\d]{1,2}|প্রথম|দ্বিতীয়|তৃতীয়|চতুর্থ|পঞ্চম|ষষ্ঠ|সপ্তম|অষ্টম|নবম|দশম|'
            r'এগারো|বারো|তেরো|চৌদ্দ|পনেরো|ষোল|সতেরো|আঠারো|উনিশ|বিশ|একুশ|বাইশ|তেইশ|চব্বিশ|পঁচিশ|'
            r'ছাব্বিশ|সাতাশ|আঠাশ|উনত্রিশ|ত্রিশ)',
            re.IGNORECASE
        )
        contents_pattern = re.compile(r'সূচিপত্র|Contents', re.IGNORECASE)

    for page_num in range(len(doc)):
        text = normalize_text(doc[page_num].get_text("text"))

        if contents_pattern.search(text):
            continue

        matches = list(pattern.finditer(text))
        if len(matches) > 1:
            continue

        if matches:
            starts.append(page_num)

    doc.close()
    return starts

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