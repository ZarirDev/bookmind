def ocr_pdf_to_pdf(input_pdf, output_pdf, lang='eng', force_ocr=False):
    import shutil, sys, subprocess, os
    
    if not force_ocr and os.path.exists(output_pdf):
        print(f"OCR output already exists: {output_pdf}")
        return output_pdf

    os.makedirs(os.path.dirname(output_pdf), exist_ok=True)
    
    # Check dependencies first
    if not shutil.which("gs") and not shutil.which("tesseract"):
        raise RuntimeError("Missing dependencies: Install Ghostscript and Tesseract")
    
    # Check language pack
    try:
        result = subprocess.run(["tesseract", "--list-langs"], 
                              capture_output=True, text=True, check=True)
        if lang not in result.stdout and lang.split('+')[0] not in result.stdout:
            print(f"⚠ Warning: Language '{lang}' may not be installed in Tesseract")
    except:
        pass  # Don't block execution, just warn

    cmd = [
        sys.executable, "-m", "ocrmypdf",
        "--language", lang,
        "--output-type", "pdf",
        "--optimize", "0",
        "--fast-web-view", "999999", 
        "--jobs", "1",
        "--tesseract-timeout", "0",
        "--skip-text" if not force_ocr else "--force-ocr",
        "--color-conversion-strategy", "RGB",
        input_pdf, output_pdf
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✓ OCR completed: {output_pdf}")
        return output_pdf
    except subprocess.CalledProcessError as e:
        print(f"\n❌ OCR failed for: {os.path.basename(input_pdf)}")
        print(f"   Command: {' '.join(cmd)}")
        if e.stderr:
            print(f"   Error output:\n{e.stderr[:500]}")  # First 500 chars
        # Suggest fixes based on error content
        err = e.stderr.lower()
        if "ben" in err or "language" in err:
            print("   💡 Try: sudo apt install tesseract-ocr-ben")
        elif "ghostscript" in err:
            print("   💡 Try: sudo apt install ghostscript")
        elif "already has text" in err:
            print("   💡 Try: Add force_ocr=True or use --redo-ocr")
        elif "not a valid pdf" in err:
            print("   💡 PDF may be corrupted - try re-downloading")
        raise