# ocr.py
import subprocess
import shutil
import os
import sys
from pathlib import Path

def check_dependencies():
    """Return (tesseract_ok, ghostscript_ok)."""
    tess = shutil.which("tesseract") is not None
    gs = shutil.which("gs") is not None
    return tess, gs

def get_tesseract_langs():
    """Return list of installed Tesseract languages."""
    try:
        result = subprocess.run(["tesseract", "--list-langs"],
                                capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n')[1:]  # first line is header
    except:
        return []

def ocr_pdf_with_ocrmypdf(input_path, output_path, lang='eng', force=False):
    """
    OCR a PDF using ocrmypdf (CPU).
    Returns output path or raises exception.
    """
    import ocrmypdf
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # ocrmypdf will skip text pages automatically
    ocrmypdf.ocr(
        input_path,
        output_path,
        language=lang,
        force_ocr=force,
        optimize=1,          # mild compression
        jobs=os.cpu_count(), # use all cores
        quiet=True
    )
    return output_path

def ocr_pdf_with_paddleocr(input_path, output_path, lang='en', use_gpu=False):
    """
    Alternative: extract text with PaddleOCR and embed into PDF.
    (Placeholder – you can implement later)
    """
    raise NotImplementedError("PaddleOCR integration coming soon")

# Main dispatcher
def ocr_pdf(input_pdf, output_pdf, lang='eng', force=False, backend='auto'):
    """
    OCR a PDF with automatic backend selection.
    backend: 'auto', 'ocrmypdf', 'paddle'
    """
    if backend == 'auto':
        # Prefer ocrmypdf for reliability
        tess_ok, gs_ok = check_dependencies()
        if tess_ok and gs_ok:
            backend = 'ocrmypdf'
        else:
            raise RuntimeError(
                "OCR dependencies missing.\n"
                "Install Tesseract and Ghostscript:\n"
                "  Ubuntu/Debian: sudo apt install tesseract-ocr tesseract-ocr-{lang} ghostscript\n"
                "  macOS: brew install tesseract ghostscript\n"
                "  Windows: download installers from GitHub"
            )
    
    if backend == 'ocrmypdf':
        return ocr_pdf_with_ocrmypdf(input_pdf, output_pdf, lang, force)
    elif backend == 'paddle':
        return ocr_pdf_with_paddleocr(input_pdf, output_pdf, lang, use_gpu=True)
    else:
        raise ValueError(f"Unknown backend: {backend}")