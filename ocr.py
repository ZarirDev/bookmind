import subprocess
import shutil
import os
import sys
import ocrmypdf
from ocrmypdf.exceptions import PriorOcrFoundError

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
        return result.stdout.strip().split('\n')[1:]
    except:
        return []

def ocr_pdf_with_ocrmypdf(input_path, output_path, lang='eng', force=False):
    """OCR a PDF using ocrmypdf (CPU)."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        ocrmypdf.ocr(
            input_path,
            output_path,
            language=lang,
            force_ocr=force,
            optimize=1,
            jobs=os.cpu_count(),
            quiet=True
        )
        return output_path
    except PriorOcrFoundError:
        if not force:
            print("⚠ PDF already contains text. Retrying with --force-ocr...")
            return ocr_pdf_with_ocrmypdf(input_path, output_path, lang=lang, force=True)
        else:
            raise
    except Exception as e:
        raise

def ocr_pdf(input_pdf, output_pdf, lang='eng', force=False, backend='auto'):
    """Main OCR dispatcher."""
    if backend == 'auto':
        tess_ok, gs_ok = check_dependencies()
        if tess_ok and gs_ok:
            backend = 'ocrmypdf'
        else:
            raise RuntimeError("OCR dependencies missing.")
    if backend == 'ocrmypdf':
        return ocr_pdf_with_ocrmypdf(input_pdf, output_pdf, lang, force)
    else:
        raise ValueError(f"Unknown backend: {backend}")