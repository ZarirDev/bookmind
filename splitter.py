import re
import os
import fitz  # PyMuPDF

def normalize_text(text):
    """Replace newlines and multiple spaces with a single space."""
    return re.sub(r'\s+', ' ', text)

# Mapping word numbers (cardinal + ordinal) to integers (up to thirty)
WORD_TO_NUM = {
    # cardinal numbers
    'one':1, 'two':2, 'three':3, 'four':4, 'five':5, 'six':6, 'seven':7, 'eight':8, 'nine':9, 'ten':10,
    'eleven':11, 'twelve':12, 'thirteen':13, 'fourteen':14, 'fifteen':15, 'sixteen':16, 'seventeen':17,
    'eighteen':18, 'nineteen':19, 'twenty':20, 'twentyone':21, 'twentytwo':22, 'twentythree':23,
    'twentyfour':24, 'twentyfive':25, 'twentysix':26, 'twentyseven':27, 'twentyeight':28, 'twentynine':29,
    'thirty':30, 'twenty-one':21, 'twenty-two':22, 'twenty-three':23, 'twenty-four':24,
    'twenty-five':25, 'twenty-six':26, 'twenty-seven':27, 'twenty-eight':28, 'twenty-nine':29,
    # ordinal numbers
    'first':1, 'second':2, 'third':3, 'fourth':4, 'fifth':5, 'sixth':6, 'seventh':7, 'eighth':8,
    'ninth':9, 'tenth':10, 'eleventh':11, 'twelfth':12, 'thirteenth':13, 'fourteenth':14,
    'fifteenth':15, 'sixteenth':16, 'seventeenth':17, 'eighteenth':18, 'nineteenth':19,
    'twentieth':20, 'twenty-first':21, 'twenty-second':22, 'twenty-third':23, 'twenty-fourth':24,
    'twenty-fifth':25, 'twenty-sixth':26, 'twenty-seventh':27, 'twenty-eighth':28, 'twenty-ninth':29,
    'thirtieth':30
}

def chapter_number_to_int(num_str):
    """Convert chapter number string (digit or word) to integer, or None."""
    num_str = num_str.lower().strip()
    if num_str.isdigit():
        return int(num_str)
    cleaned = re.sub(r'[\s\-]', '', num_str)
    return WORD_TO_NUM.get(cleaned, None)

def extract_chapter_info(match_text, language='english'):
    """
    Return (type, number_str, number_int).
    Handles both 'Chapter First' and 'First Chapter' order.
    """
    # Pattern A: Unit/Chapter + number
    m1 = re.search(r'\b(Unit|Chapter)\s+([^\s\.]+)', match_text, re.IGNORECASE)
    if m1:
        typ = m1.group(1).lower()
        num_str = m1.group(2).lower()
        num_int = chapter_number_to_int(num_str)
        return ('unit' if 'unit' in typ else 'chapter', num_str, num_int)

    # Pattern B: number + (Chapter/Unit) – handles "First Chapter" and broken "Chap ter"
    m2 = re.search(r'\b([^\s\.]+)\s+(C\s*h\s*a\s*p\s*t\s*e\s*r|U\s*n\s*i\s*t)\b', match_text, re.IGNORECASE)
    if m2:
        num_str = m2.group(1).lower()
        num_int = chapter_number_to_int(num_str)
        if num_int is not None:
            typ_word = re.sub(r'\s+', '', m2.group(2)).lower()
            typ = 'unit' if 'unit' in typ_word else 'chapter'
            return (typ, num_str, num_int)

    return (None, None, None)

def find_answer_key_page(pdf_path, language='english'):
    """Return the first page number (0-indexed) that contains answer key content."""
    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    if language == 'english':
        patterns = [
            re.compile(r'Answers?\s+to\s+Exercises?', re.IGNORECASE),
            re.compile(r'Answer\s+Key', re.IGNORECASE),
            re.compile(r'Solutions?\s+to\s+Exercises?', re.IGNORECASE),
            re.compile(r'Appendix.*Answers', re.IGNORECASE),
        ]
    else:
        patterns = [
            re.compile(r'উত্তর\s*মালা', re.IGNORECASE),
            re.compile(r'উত্তর\s*পত্র', re.IGNORECASE),
        ]

    for page_num in range(total_pages):
        text = normalize_text(doc[page_num].get_text("text"))
        for pat in patterns:
            if pat.search(text):
                doc.close()
                return page_num
    doc.close()
    return None

def debug_print(msg, debug, fh=None):
    if debug:
        print(msg)
    if fh:
        fh.write(msg + '\n')

def detect_chapter_pages_advanced(pdf_path, language='english', debug=False):
    """
    Chapter/unit detection – now supports both 'Chapter First' and 'First Chapter' orders,
    with tolerance for broken OCR words like 'Third Chap ter'.
    """
    fh = None
    if debug:
        fh = open('debug.txt', 'w', encoding='utf-8')

    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    # Number group for English (used only for the "Chapter + number" direction)
    num_group = (
        r'(\d{1,2}|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|'
        r'Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|Nineteen|'
        r'Twenty|Twenty[- ]One|Twenty[- ]Two|Twenty[- ]Three|Twenty[- ]Four|'
        r'Twenty[- ]Five|Twenty[- ]Six|Twenty[- ]Seven|Twenty[- ]Eight|'
        r'Twenty[- ]Nine|Thirty|'
        r'First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|'
        r'Eleventh|Twelfth|Thirteenth|Fourteenth|Fifteenth|Sixteenth|Seventeenth|Eighteenth|Nineteenth|'
        r'Twentieth|Twenty[- ]First|Twenty[- ]Second|Twenty[- ]Third|Twenty[- ]Fourth|'
        r'Twenty[- ]Fifth|Twenty[- ]Sixth|Twenty[- ]Seventh|Twenty[- ]Eighth|Twenty[- ]Ninth|'
        r'Thirtieth)'
    )

    if language == 'english':
        # Direction A: Chapter/Unit + number
        pattern_chapter_first = re.compile(
            r'\b(Unit|Chapter)[\s:\-–—]+' + num_group + r'\b',
            re.IGNORECASE
        )
        # Direction B: number + Chapter/Unit (allowing spaces inside "Chapter"/"Unit")
        pattern_number_first = re.compile(
            r'\b' + num_group + r'\s+(C\s*h\s*a\s*p\s*t\s*e\s*r|U\s*n\s*i\s*t)\b',
            re.IGNORECASE
        )
        exercise_pattern = re.compile(r'\b(?:question|choice|exercise|problem|ultiple)\b', re.IGNORECASE)
        contents_pattern = re.compile(r'\bContents\b', re.IGNORECASE)
    else:
        # Bangla variants – unchanged
        pattern_chapter_first = re.compile(
            r'(অধ্যায়|ইউনিট)[\s:\-–—]*([০-৯\d]{1,2}|প্রথম|দ্বিতীয়|তৃতীয়|চতুর্থ|পঞ্চম|ষষ্ঠ|সপ্তম|অষ্টম|নবম|দশম|'
            r'এগারো|বারো|তেরো|চৌদ্দ|পনেরো|ষোল|সতেরো|আঠারো|উনিশ|বিশ|একুশ|বাইশ|তেইশ|চব্বিশ|পঁচিশ|'
            r'ছাব্বিশ|সাতাশ|আঠাশ|উনত্রিশ|ত্রিশ)',
            re.IGNORECASE
        )
        pattern_number_first = None   # Bangla books typically use the standard order
        exercise_pattern = re.compile(r'প্রশ্ন|অনুশীলনী|বহুনির্বাচনী', re.IGNORECASE)
        contents_pattern = re.compile(r'সূচিপত্র|Contents', re.IGNORECASE)

    chapter_starts = []
    found_first = False
    seen_numbers = set()
    last_accepted_num = -1
    header_occurrences = {}

    debug_print(f"=== Advanced detection for {pdf_path} ===", debug, fh)

    for page_num in range(total_pages):
        text = normalize_text(doc[page_num].get_text("text"))
        if len(text) < 50:
            continue
        first_part = text[:200].lower()
        if contents_pattern.search(first_part):
            if debug:
                debug_print(f"Page {page_num+1}: skipped (Contents at top)", debug, fh)
            continue

        matches = []
        # Try both patterns
        if pattern_chapter_first:
            matches.extend(pattern_chapter_first.finditer(text))
        if pattern_number_first:
            matches.extend(pattern_number_first.finditer(text))

        if debug:
            snippet = text[:300].replace('\n', ' ')
            debug_print(f"--- Page {page_num+1} ---", debug, fh)
            debug_print(f"Text start: {snippet}...", debug, fh)
            if matches:
                for m in matches:
                    debug_print(f"  Match: '{m.group(0)}'", debug, fh)
            else:
                debug_print("  No heading match on this page.", debug, fh)

        for match in matches:
            typ, num_str, num_int = extract_chapter_info(match.group(0), language)
            if typ and num_str:
                key = (typ, num_str)
                if key not in header_occurrences:
                    header_occurrences[key] = []
                header_occurrences[key].append(page_num)

    debug_print("\n=== Decision phase ===", debug, fh)
    for (typ, num_str), pages in header_occurrences.items():
        if not pages:
            continue
        candidate_page = pages[0]
        _, _, num_int = extract_chapter_info(f"{typ} {num_str}", language)

        if not found_first:
            chapter_starts.append(candidate_page)
            found_first = True
            seen_numbers.add((typ, num_str))
            if num_int is not None:
                last_accepted_num = num_int
            debug_print(f"Page {candidate_page+1}: ACCEPTED as first {typ} ({num_str})", debug, fh)
            continue

        if typ == 'chapter' and num_int is not None:
            if num_int <= last_accepted_num:
                debug_print(f"Page {candidate_page+1}: REJECTED {typ} ({num_str}) - out of order (last={last_accepted_num})", debug, fh)
                continue

        if typ == 'unit':
            accept = True
            reason = f"unit ({num_str})"
        else:
            exercise_found = False
            start_lookback = max(0, candidate_page - 5)
            for lookback in range(start_lookback, candidate_page + 1):
                if exercise_pattern.search(normalize_text(doc[lookback].get_text("text"))):
                    exercise_found = True
                    break
            accept = exercise_found
            reason = f"chapter ({num_str}) - {'exercise found' if accept else 'no exercise'}"

        if accept:
            chapter_starts.append(candidate_page)
            seen_numbers.add((typ, num_str))
            if num_int is not None:
                last_accepted_num = num_int
            debug_print(f"Page {candidate_page+1}: ACCEPTED {reason}", debug, fh)
        else:
            debug_print(f"Page {candidate_page+1}: REJECTED {reason}", debug, fh)

    doc.close()
    chapter_starts = sorted(set(chapter_starts))

    if language == 'english':
        answer_page = find_answer_key_page(pdf_path, language)
        if answer_page is not None:
            original_count = len(chapter_starts)
            chapter_starts = [p for p in chapter_starts if p < answer_page]
            if debug and len(chapter_starts) < original_count:
                debug_print(f"⚠ Answer key detected at page {answer_page+1}; truncated last chapters.", debug, fh)

    if len(chapter_starts) <= 2:
        debug_print("⚠ Advanced detection found few sections; using simple heading detection.", debug, fh)
        chapter_starts = _detect_headings_simple(pdf_path, language, debug, fh)

    debug_print(f"\nFinal detected starts (1-indexed): {[p+1 for p in chapter_starts]}", debug, fh)
    if fh:
        fh.close()
    return chapter_starts

def _detect_headings_simple(pdf_path, language='english', debug=False, fh=None):
    """Simple fallback with ordering – also supports both heading directions."""
    doc = fitz.open(pdf_path)
    starts = []
    seen = set()
    last_num = -1

    if language == 'english':
        num_group = (
            r'(\d{1,2}|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|'
            r'Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|Nineteen|'
            r'Twenty|Twenty[- ]One|Twenty[- ]Two|Twenty[- ]Three|Twenty[- ]Four|'
            r'Twenty[- ]Five|Twenty[- ]Six|Twenty[- ]Seven|Twenty[- ]Eight|'
            r'Twenty[- ]Nine|Thirty|'
            r'First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|'
            r'Eleventh|Twelfth|Thirteenth|Fourteenth|Fifteenth|Sixteenth|Seventeenth|Eighteenth|Nineteenth|'
            r'Twentieth|Twenty[- ]First|Twenty[- ]Second|Twenty[- ]Third|Twenty[- ]Fourth|'
            r'Twenty[- ]Fifth|Twenty[- ]Sixth|Twenty[- ]Seventh|Twenty[- ]Eighth|Twenty[- ]Ninth|'
            r'Thirtieth)'
        )
        pattern_chapter_first = re.compile(r'\b(Unit|Chapter)[\s:\-–—]+' + num_group + r'\b', re.IGNORECASE)
        pattern_number_first = re.compile(r'\b' + num_group + r'\s+(C\s*h\s*a\s*p\s*t\s*e\s*r|U\s*n\s*i\s*t)\b', re.IGNORECASE)
        contents_pattern = re.compile(r'\bContents\b', re.IGNORECASE)
    else:
        pattern_chapter_first = re.compile(
            r'(অধ্যায়|ইউনিট)[\s:\-–—]*([০-৯\d]{1,2}|প্রথম|দ্বিতীয়|তৃতীয়|চতুর্থ|পঞ্চম|ষষ্ঠ|সপ্তম|অষ্টম|নবম|দশম|'
            r'এগারো|বারো|তেরো|চৌদ্দ|পনেরো|ষোল|সতেরো|আঠারো|উনিশ|বিশ|একুশ|বাইশ|তেইশ|চব্বিশ|পঁচিশ|'
            r'ছাব্বিশ|সাতাশ|আঠাশ|উনত্রিশ|ত্রিশ)',
            re.IGNORECASE
        )
        pattern_number_first = None
        contents_pattern = re.compile(r'সূচিপত্র|Contents', re.IGNORECASE)

    debug_print("\n=== Simple heading detection ===", debug, fh)
    header_occurrences = {}
    for page_num in range(len(doc)):
        text = normalize_text(doc[page_num].get_text("text"))
        first_part = text[:200].lower()
        if contents_pattern.search(first_part):
            continue
        matches = []
        if pattern_chapter_first:
            matches.extend(pattern_chapter_first.finditer(text))
        if pattern_number_first:
            matches.extend(pattern_number_first.finditer(text))
        for match in matches:
            typ, num_str, num_int = extract_chapter_info(match.group(0), language)
            if typ and num_str:
                key = (typ, num_str)
                if key not in header_occurrences:
                    header_occurrences[key] = []
                header_occurrences[key].append(page_num)
                if debug:
                    debug_print(f"Page {page_num+1}: found '{match.group(0)}' → ({typ}, {num_str})", debug, fh)

    for (typ, num_str), pages in header_occurrences.items():
        if not pages:
            continue
        _, _, num_int = extract_chapter_info(f"{typ} {num_str}", language)
        if typ == 'chapter' and num_int is not None:
            if num_int <= last_num:
                if debug:
                    debug_print(f"  Skipping {typ} {num_str} (out of order)", debug, fh)
                continue
        candidate = pages[0]
        starts.append(candidate)
        seen.add((typ, num_str))
        if num_int is not None:
            last_num = num_int
        if debug:
            debug_print(f"  -> Accepted page {candidate+1} as {typ} {num_str}", debug, fh)

    starts.sort()
    doc.close()

    if language == 'english':
        answer_page = find_answer_key_page(pdf_path, language)
        if answer_page is not None:
            starts = [p for p in starts if p < answer_page]

    return starts

def detect_bangla_grammar_chapters(pdf_path, debug=False):
    """Special detection for Bangla grammar books."""
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    pattern = re.compile(r'প.*?রি.*?চ্ছে.*?দ\s*[ঃ\-\.]?\s*([০-৯\d]+)', re.IGNORECASE)
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

def detect_bangla_literature_chapters(pdf_path, debug=False):
    """Special detection for Bangla literature books."""
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