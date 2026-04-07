import os
import subprocess
import sys

def ocr_pdf_to_pdf(input_pdf, output_pdf, lang='eng', force_ocr=False):
    """
    Create a searchable PDF using ocrmypdf with fastest settings.
    Avoids PDF/A conversion to prevent color space errors.
    """
    if not force_ocr and os.path.exists(output_pdf):
        print(f"OCR output already exists: {output_pdf}")
        return output_pdf

    os.makedirs(os.path.dirname(output_pdf), exist_ok=True)

    # Fastest parameters:
    # --output-type pdf          → no PDF/A conversion (avoids color space issues)
    # --optimize 1               → basic optimization (2 is slower)
    # --jobs 1                   → single thread
    # --tesseract-timeout 0      → no timeout for large files
    # --skip-text                → don’t re‑OCR pages that already have text
    # --color-conversion-strategy RGB → convert weird color spaces
    # --quiet                    → suppress most warnings
    cmd = [
        sys.executable, "-m", "ocrmypdf",
        "--language", lang,
        "--output-type", "pdf",
        "--optimize", "0",
        "--fast-web-view", "999999",
        "--jobs", "1",
        "--tesseract-timeout", "0",
        "--skip-text",
        "--color-conversion-strategy", "RGB",
        # "--skip-big",
        input_pdf, output_pdf
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"OCR completed: {output_pdf}")
    except subprocess.CalledProcessError as e:
        print(f"OCR failed for {input_pdf}: {e.stderr}")
        raise
    return output_pdf

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Input PDF file")
    parser.add_argument("output", help="Output PDF file")
    parser.add_argument("--lang", default="eng", help="OCR language (eng, ben, eng+ben)")
    args = parser.parse_args()
    ocr_pdf_to_pdf(args.input, args.output, args.lang)