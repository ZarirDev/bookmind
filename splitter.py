import re
import os
import fitz  # PyMuPDF

def detect_chapter_pages_advanced(pdf_path, language='english'):
    """
    Advanced chapter/unit detection using heading + previous exercise check.
    Supports 'Chapter' and 'Unit' headings.
    Returns list of 0-indexed page numbers where chapters/units begin.
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    # Patterns for English and Bangla
    if language == 'english':
        heading_pattern = re.compile(
            r'\b(chapter|unit)\s*(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|'
            r'eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|'
            r'twenty|twenty[\s-]one|twenty[\s-]two|twenty[\s-]three|twenty[\s-]four|'
            r'twenty[\s-]five|twenty[\s-]six|twenty[\s-]seven|twenty[\s-]eight|'
            r'twenty[\s-]nine|thirty)\b',
            re.IGNORECASE
        )
        exercise_pattern = re.compile(r'\bexercise\b', re.IGNORECASE)
        mcq_pattern = re.compile(r'\b(multiple\s+choice\s+questions?|mcq)\b', re.IGNORECASE)
    else:  # bangla
        heading_pattern = re.compile(
            r'(অধ্যায়|ইউনিট)\s*([০-৯\d]{1,2}|প্রথম|দ্বিতীয়|তৃতীয়|চতুর্থ|পঞ্চম|ষষ্ঠ|সপ্তম|অষ্টম|নবম|দশম|'
            r'এগারো|বারো|তেরো|চৌদ্দ|পনেরো|ষোল|সতেরো|আঠারো|উনিশ|বিশ|একুশ|বাইশ|তেইশ|চব্বিশ|পঁচিশ|'
            r'ছাব্বিশ|সাতাশ|আঠাশ|উনত্রিশ|ত্রিশ)',
            re.IGNORECASE
        )
        exercise_pattern = re.compile(r'অনুশীলনী|অনুশীলন', re.IGNORECASE)
        mcq_pattern = re.compile(r'বহুনির্বাচনী|এমসিকিউ|mcq', re.IGNORECASE)

    chapter_starts = []
    found_first_heading = False

    for page_num in range(total_pages):
        page = doc[page_num]
        text = page.get_text("text")

        if len(text.strip()) < 50:
            continue

        if heading_pattern.search(text):
            if not found_first_heading:
                if page_num > 2:  # Skip TOC/preface
                    chapter_starts.append(page_num)
                    found_first_heading = True
                continue

            # Check previous up to 4 pages for exercise + MCQ
            exercise_found = False
            mcq_found = False
            start_lookback = max(0, page_num - 4)
            for lookback_page in range(start_lookback, page_num):
                lookback_text = doc[lookback_page].get_text("text")
                if exercise_pattern.search(lookback_text):
                    exercise_found = True
                if mcq_pattern.search(lookback_text):
                    mcq_found = True
                if exercise_found and mcq_found:
                    break

            if exercise_found and mcq_found:
                chapter_starts.append(page_num)

    doc.close()

    # Fallback if advanced detection finds too few sections
    if len(chapter_starts) <= 1:
        print("⚠ Advanced detection found few sections; using simple heading detection.")
        chapter_starts = _detect_headings_simple(pdf_path, language)

    return chapter_starts

def _detect_headings_simple(pdf_path, language='english'):
    """Simple heading detection for Chapter/Unit."""
    doc = fitz.open(pdf_path)
    starts = []
    patterns = {
        'english': re.compile(r'\b(chapter|unit)\s+\d+\b', re.IGNORECASE),
        'bangla': re.compile(r'(অধ্যায়|ইউনিট)\s*[০-৯\d]+|প্রথম|দ্বিতীয়|তৃতীয়|চতুর্থ|পঞ্চম|ষষ্ঠ|সপ্তম|অষ্টম|নবম|দশম')
    }
    pattern = patterns.get(language, patterns['english'])

    for page_num in range(len(doc)):
        text = doc[page_num].get_text("text")[:500]
        if pattern.search(text):
            starts.append(page_num)
    doc.close()
    return starts

def split_pdf_by_pages(input_pdf, output_dir, split_pages, base_name="Chapter"):
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