import subprocess
import shutil
import os
import sys
import tempfile
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

def downsample_pdf(input_path, output_path, dpi=200):
    """
    Use Ghostscript to downsample images in a PDF to the given DPI.
    Returns True on success, False on failure.
    """
    try:
        subprocess.run([
            "gs", "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/printer",   # 300 dpi printer setting; we override below
            f"-dDownsampleColorImages=true",
            f"-dColorImageResolution={dpi}",
            f"-dDownsampleGrayImages=true",
            f"-dGrayImageResolution={dpi}",
            f"-dDownsampleMonoImages=true",
            f"-dMonoImageResolution={dpi}",
            "-dNOPAUSE", "-dQUIET", "-dBATCH",
            f"-sOutputFile={output_path}",
            input_path
        ], check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠ Ghostscript downsampling failed: {e.stderr[:200]}")
        return False

def ocr_pdf_with_ocrmypdf(input_path, output_path, lang='eng', force=False):
    """OCR a PDF using ocrmypdf, with automatic image optimization."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # First, create an optimized version to avoid decompression bombs
    optimized_path = None
    try:
        # Create a temporary file for the optimized PDF
        fd, optimized_path = tempfile.mkstemp(suffix=".pdf", prefix="ocr_optimized_")
        os.close(fd)

        if not downsample_pdf(input_path, optimized_path, dpi=200):
            # If downsampling fails, proceed with original file
            print("  Downsampling failed, using original file (may be slow or fail).")
            os.remove(optimized_path)
            optimized_path = input_path
        else:
            print("  PDF optimized (200 DPI) for OCR processing.")

        try:
            ocrmypdf.ocr(
                optimized_path,
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
                ocrmypdf.ocr(
                    optimized_path,
                    output_path,
                    language=lang,
                    force_ocr=True,
                    optimize=1,
                    jobs=os.cpu_count(),
                    quiet=True
                )
                return output_path
            else:
                raise
    finally:
        # Clean up temporary optimized file if created
        if optimized_path and optimized_path != input_path and os.path.exists(optimized_path):
            os.remove(optimized_path)

def ocr_pdf(input_pdf, output_pdf, lang='eng', force=False, backend='auto'):
    """Main OCR dispatcher."""
    if backend == 'auto':
        tess_ok, gs_ok = check_dependencies()
        if tess_ok and gs_ok:
            backend = 'ocrmypdf'
        else:
            raise RuntimeError("OCR dependencies missing. Install Tesseract and Ghostscript.")
    if backend == 'ocrmypdf':
        return ocr_pdf_with_ocrmypdf(input_pdf, output_pdf, lang, force)
    else:
        raise ValueError(f"Unknown backend: {backend}")

def pdf_has_text(pdf_path, min_text_length=50):
    """Check if a PDF already contains extractable text."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        for page_num in range(min(5, len(doc))):
            text = doc[page_num].get_text("text")
            if len(text.strip()) > min_text_length:
                doc.close()
                return True
        doc.close()
        return False
    except ImportError:
        return False