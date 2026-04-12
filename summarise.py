import re
import os
import sys
import fitz  # PyMuPDF
from groq import Groq



def extract_text_from_pdf(pdf_path, max_chars=1000000):
    """Extract text from a PDF file, limiting to max_chars."""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        page_text = page.get_text("text")
        text += page_text
        if len(text) >= max_chars:
            break
    doc.close()
    return text[:max_chars]

def summarise_chapter(pdf_path, output_dir, chapter_name, api_key=None):
    """
    Summarise a chapter PDF using Groq API with Llama 4 Scout.
    Generates a Markdown study guide with corrected OCR and exam focus.
    """
    if api_key is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            print("❌ GROQ_API_KEY environment variable not set.")
            return None

    try:
        client = Groq(api_key=api_key)
    except Exception as e:
        print(f"❌ Failed to initialize Groq client: {e}")
        return None

    print(f"  Extracting text from {os.path.basename(pdf_path)}...")
    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        print("  ❌ No text extracted from PDF.")
        return None

    prompt = f"""
You are an expert educator and curriculum designer. Your task is to transform a raw textbook chapter into a **high-quality, exam-ready study guide** capable of preparing a student for definitions, conceptual questions, mathematical problems, and graph analysis.

---

## Step 1 – OCR Correction (Silent)
- Fix OCR errors (broken words, spacing, encoding issues).
- Preserve all technical terms and original meaning.
- Do NOT mention corrections.

---

## Step 2 – Structure Detection
- Detect the chapter’s **true lesson/section structure** (e.g., 2.1, 2.2, Lesson 5, subheadings).
- If the structure is unclear, infer logical sections based on clear topic shifts.
- Preserve the pedagogical flow and sequence of the original text.

---

## Step 3 – Study Guide Generation (Markdown)

Output must begin exactly with:
## Study Guide: {chapter_name}

For **EACH** detected lesson/section, you must generate the following **top-level** blocks:

### [section-title]

#### 1. Key Concepts
- 5–10 high-value bullet points capturing the core ideas.
- Avoid redundancy and fluff. These are the "big picture" takeaways.

#### 2. Definitions / Key Terms
- Markdown table with columns: Term | Definition
- Include **all** bolded, italicized, or technically significant terms.
- Definitions must be precise, clear, and context-aware.

#### 3. Core Content (Adaptive Section)

**CRITICAL RULE – Conditional Sub-Sections Only:**
- You **MUST ONLY** include a sub-heading (e.g., `- **Formulas / Equations**`) **if the source text actually contains that specific type of content.**
- **If the text has NO formulas, DO NOT write "Formulas / Equations" and DO NOT write "No formulas are provided."** Simply skip that sub-section entirely.
- **If the text has NO worked examples, DO NOT write "Worked Examples" and DO NOT write "No worked examples are provided."** Skip it.
- **If the text has NO graph analysis, DO NOT write "Graphical Analysis" and DO NOT write "No graphical analysis."** Skip it.

This applies to ALL adaptive sub-sections listed below. **Silence is better than placeholder text.**

When the content **IS** present, use the following format:

- **Formulas / Equations**
  - Use LaTeX formatting (e.g., $v = u + at$).
  - Define every variable immediately after the formula.
  - Provide a 1-sentence explanation of when the formula is used.

- **Worked Examples / Sample Problems**
  - Transcribe the problem statement **verbatim**.
  - Show the **step-by-step mathematical solution** with unit conversions.
  - Present the final answer clearly.

- **Graphical Analysis / "Motion and Graph" Sections**
  - Explain **how** to extract data from the graph (slope, area).
  - Explain **what** the slope and area represent physically.
  - Describe the shape of the graph for key scenarios (uniform velocity, constant acceleration).

- **Processes / Mechanisms**
  - Step-by-step explanation of natural phenomena (e.g., free fall, relative motion).
  - Use clear, sequential language.

- **Theories / Laws / Principles**
  - State the law/principle clearly.
  - Explain its meaning and implications.
  - Include any associated mathematical expression.

- **Investigations / Experiments / "Do Yourself" Activities**
  - Extract the **Objective**, **Apparatus**, and **Procedure**.
  - Include the formula used for calculation.
  - Summarize the data table structure if provided.

#### 4. Conceptual Understanding
- A dense, structured explanation of **why** the topic works.
- Focus on relationships (e.g., "If acceleration is constant, velocity changes linearly").
- Explain underlying logic without storytelling.
- **If the section is purely descriptive (e.g., listing types of motion), this section should still contain meaningful insight, not just a rephrasing of the definitions.**

#### 5. Connections & Insights
- Link to other topics within the chapter.
- Real-world applications.
- Significance of the concepts.
- **This section should always contain at least one concrete connection. Avoid vague statements like "Relating to real-world examples." Instead, give a specific example: "The relative nature of motion explains why passengers in a moving train perceive stationary objects outside as moving backward."**

#### 6. Fundamental Questions
- 3–5 conceptual questions that test understanding.
- Use stems like: **Explain why...**, **Compare X and Y...**, **How would you determine...**, **What happens if...**.
- These should probe the limits of the student's understanding.

---

## Step 4 – Quality Constraints for Mathematics & Graphs

- **Anti-Summarization Rule for Math:** You are forbidden from saying "the text discusses equations of motion." You **MUST** list the explicit equations if they appear.
- **Graph Extraction Rule:** If a section mentions graphs or includes the word "Graph" in the title, you **MUST** include the Graphical Analysis sub-section.
- **Worked Example Rule:** If the text uses numbers in a problem context (e.g., "60 km/hour" or "10 cm"), those numbers **MUST** appear in a solved example format.

---

## Step 5 – Output Rules

- No introduction or conclusion outside the study guide structure.
- No meta commentary (e.g., "The text goes on to say...").
- No references to OCR errors.
- Only output the final structured guide.
- Use clean, academic Markdown.

---

## Completion Requirement (CRITICAL)

- You **MUST** process the **ENTIRE** provided text.
- You **MUST** generate every **top-level** section block for every lesson.
- Do **NOT** stop early.
- The answer is considered **incomplete** if any equation, worked example, or graph interpretation present in the source text is missing from the guide.
- **Token Efficiency:** Omit any sub-section that lacks substantive content. Do not waste tokens on empty placeholders. i.e  if a lesson doesn't have any formulae, do not even bother writing that section.
- You must **NOT** answer the sample questions (if attached) at the end of the chapter. 

{text}

Continue writing until the entire chapter is fully exhausted.
"""

    try:
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=8096,
        )
        summary = completion.choices[0].message.content
    except Exception as e:
        print(f"  ❌ Groq API error: {e}")
        return None

    # Save as Markdown file
    os.makedirs(output_dir, exist_ok=True)
    safe_name = re.sub(r'[\\/*?:"<>|]', "", chapter_name)
    out_path = os.path.join(output_dir, f"{safe_name}.md")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(summary)

    print(f"  ✓ Study guide saved to {out_path}")
    return out_path

if __name__ == "__main__":
    import re
    if len(sys.argv) < 3:
        print("Usage: python summarise.py <pdf_path> <output_dir> [chapter_name]")
        sys.exit(1)
    pdf_path = sys.argv[1]
    output_dir = sys.argv[2]
    chapter_name = sys.argv[3] if len(sys.argv) > 3 else "Chapter"
    summarise_chapter(pdf_path, output_dir, chapter_name)