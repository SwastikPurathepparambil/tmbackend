import base64
import io
import mimetypes
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

from dotenv import load_dotenv
from pypdf import PdfReader
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import TailoredResume
from .crew import build_crew
from .tools import build_tools

# ---------- Helpers ----------

def _pdf_bytes_to_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF, best-effort."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    texts = []
    for page in reader.pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception:
            pass
    return "\n".join(texts).strip()

# If you want to reuse this from the endpoint, you can put it here too
def b64_to_bytes(data: str) -> bytes:
    """Accept raw base64 or data URLs; returns decoded bytes."""
    if "," in data:  # handle "data:...;base64,XXXX"
        data = data.split(",", 1)[1]
    return base64.b64decode(data)

# ---------- HTML + PDF rendering ----------

# adjust path to your templates folder
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

def render_resume_html(resume: TailoredResume) -> str:
    template = env.get_template("resume.html")
    return template.render(resume=resume)

# def html_to_pdf(html: str) -> bytes:
#     # you can swap this to wkhtmltopdf/pdfkit if you prefer
#     from weasyprint import HTML
#     pdf = HTML(string=html).write_pdf()
#     return pdf


import io
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.units import inch
from reportlab.lib import colors

from .models import TailoredResume  # whatever file defines your Pydantic model

# src/tmbackend/run_tailor.py (or wherever you keep it)
from io import BytesIO
from typing import Any, Dict, List

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    ListFlowable,
    ListItem,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT


def resume_to_pdf(resume: Dict[str, Any]) -> bytes:
    """
    Render a TailoredResume-like dict to a nicely formatted one-page PDF.
    Expects the JSON shape you showed:
      { contact: {...}, headline: str, summary: str, sections: [ ... ] }
    """

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()

    # ----- Typography / styles -----
    name_style = ParagraphStyle(
        "Name",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        alignment=TA_LEFT,
        spaceAfter=4,
    )

    contact_style = ParagraphStyle(
        "Contact",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        alignment=TA_LEFT,
        spaceAfter=8,
    )

    headline_style = ParagraphStyle(
        "Headline",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        spaceAfter=6,
    )

    summary_style = ParagraphStyle(
        "Summary",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        spaceAfter=10,
    )

    section_title_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontSize=12,
        leading=14,
        spaceBefore=10,
        spaceAfter=4,
        # Slightly tighter than default Heading2
    )

    item_title_style = ParagraphStyle(
        "ItemTitle",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=13,
        spaceBefore=2,
        spaceAfter=0,
    )

    meta_line_style = ParagraphStyle(
        "MetaLine",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
        spaceAfter=2,
    )

    bullet_style = ParagraphStyle(
        "Bullet",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
    )

    story: List[Any] = []

    # ----- Header: name + contact -----
    contact = resume.get("contact", {}) or {}
    name = contact.get("name") or "Anonymous Candidate"
    story.append(Paragraph(name, name_style))

    contact_parts: List[str] = []
    if contact.get("email"):
        contact_parts.append(contact["email"])
    if contact.get("phone"):
        contact_parts.append(contact["phone"])
    if contact.get("location"):
        contact_parts.append(contact["location"])

    links = contact.get("links") or []
    contact_parts.extend(str(link) for link in links if link)

    if contact_parts:
        contact_line = " · ".join(contact_parts)
        # Paragraph will wrap as needed instead of running off the page
        story.append(Paragraph(contact_line, contact_style))

    # ----- Headline + Summary -----
    headline = resume.get("headline")
    if headline:
        story.append(Paragraph(headline, headline_style))

    # summary = resume.get("summary")
    # if summary:
    #     story.append(Paragraph(summary, summary_style))

    # Small spacer before sections
    story.append(Spacer(1, 4))

    sections = resume.get("sections", []) or []

    def find_section(title: str):
        for s in sections:
            if s.get("title", "").lower() == title.lower():
                return s
        return None

    # Enforce Education > Experience > Projects order, then any extras
    ordered_sections: List[Dict[str, Any]] = []
    for key in ("Education", "Experience", "Projects"):
        s = find_section(key)
        if s:
            ordered_sections.append(s)

    for s in sections:
        if s not in ordered_sections:
            ordered_sections.append(s)

    # ----- Render each section -----
    for section in ordered_sections:
        title = section.get("title", "")
        items = section.get("items") or []

        if not items:
            continue

        story.append(Paragraph(title.upper(), section_title_style))

        for item in items:
            if title.lower() == "education":
                institution = item.get("institution", "")
                degree = item.get("degree", "")
                loc = item.get("location") or ""
                grad = item.get("graduation") or ""

                line_main = f"<b>{institution}</b>"
                if degree:
                    line_main += f" — {degree}"

                story.append(Paragraph(line_main, item_title_style))

                meta_parts = []
                if loc:
                    meta_parts.append(loc)
                if grad:
                    meta_parts.append(grad)
                if meta_parts:
                    story.append(Paragraph(" · ".join(meta_parts), meta_line_style))

                coursework = item.get("coursework") or []
                if coursework:
                    cw_text = "Relevant coursework: " + ", ".join(coursework)
                    story.append(Paragraph(cw_text, bullet_style))

            elif title.lower() == "experience":
                role = item.get("role", "")
                company = item.get("company", "")
                loc = item.get("location") or ""
                start = item.get("start_date") or ""
                end = item.get("end_date") or ""

                main_line = f"<b>{role}</b>"
                if company:
                    main_line += f" · {company}"
                story.append(Paragraph(main_line, item_title_style))

                meta_parts = []
                if loc:
                    meta_parts.append(loc)
                if start or end:
                    date_str = f"{start} — {end}" if start or end else ""
                    if date_str.strip():
                        meta_parts.append(date_str)
                if meta_parts:
                    story.append(Paragraph(" · ".join(meta_parts), meta_line_style))

                bullets = item.get("bullets") or []
                if bullets:
                    bullet_items = [
                        ListItem(Paragraph(b, bullet_style), leftIndent=10)
                        for b in bullets
                    ]
                    story.append(
                        ListFlowable(
                            bullet_items,
                            bulletType="bullet",
                            start="•",
                            leftIndent=15,
                            bulletIndent=5,
                        )
                    )

            else:  # Projects or any other section
                name_ = item.get("name", "")
                tech_stack = item.get("tech_stack") or []
                bullets = item.get("bullets") or []

                if name_:
                    story.append(Paragraph(f"<b>{name_}</b>", item_title_style))

                if tech_stack:
                    tech_line = "Tech: " + ", ".join(str(t) for t in tech_stack)
                    story.append(Paragraph(tech_line, meta_line_style))

                if bullets:
                    bullet_items = [
                        ListItem(Paragraph(b, bullet_style), leftIndent=10)
                        for b in bullets
                    ]
                    story.append(
                        ListFlowable(
                            bullet_items,
                            bulletType="bullet",
                            start="•",
                            leftIndent=15,
                            bulletIndent=5,
                        )
                    )

            # Small space between items
            story.append(Spacer(1, 4))

    # Build PDF
    doc.build(story)
    return buffer.getvalue()





def extract_json(text: str) -> str:
    """Extracts and returns raw JSON even if wrapped in ```json fences."""
    text = text.strip()

    if text.startswith("```"):
        # split on triple backticks
        parts = text.split("```")
        # parts: ["", "json\n{...}", ""]
        for p in parts:
            p = p.strip()
            if p.startswith("{") and p.endswith("}"):
                return p
            if p.startswith("json"):
                j = p[len("json"):].strip()
                if j.startswith("{") and j.endswith("}"):
                    return j

    # otherwise assume it's raw JSON
    return text




# ---------- Main pipeline ----------

def run_tailor_pipeline(
    topic: str,
    work_experience: Optional[str] = None,
    resume_bytes: Optional[bytes] = None,
    resume_mime: Optional[str] = None,
) -> dict:
    """
    - Prepares temp files for resume text + work_experience
    - Builds Crew tools and crew
    - Runs crew to get TailoredResume JSON
    - Renders HTML and converts to PDF
    - Returns pdf bytes + a suggested filename
    """
    load_dotenv()

    github_url = os.getenv("GITHUB_URL", "https://github.com/joaomdmoura")
    personal_writeup = work_experience or os.getenv("PERSONAL_WRITEUP", "")

    with TemporaryDirectory() as td:
        tmpdir = Path(td)

        resume_text_path: Optional[Path] = None
        work_exp_path: Optional[Path] = None

        # ---- Decode resume (if any) and extract text into a temp MDX ----
        if resume_bytes:
            ext = mimetypes.guess_extension(resume_mime or "") or ".pdf"
            (tmpdir / f"resume{ext}").write_bytes(resume_bytes)

            if (resume_mime or "").lower() == "application/pdf" or ext == ".pdf":
                text = _pdf_bytes_to_text(resume_bytes)
            else:
                text = (
                    f"[Resume uploaded as {resume_mime or ext}; text extraction not supported]"
                )

            resume_text_path = tmpdir / "resume_text.mdx"
            resume_text_path.write_text(text or "", encoding="utf-8")

        # ---- Save work_experience as temp MDX ----
        if personal_writeup:
            work_exp_path = tmpdir / "work_experience.mdx"
            work_exp_path.write_text(personal_writeup, encoding="utf-8")

        # ---- Build tools bound to these ephemeral files ----
        tools = build_tools(
            resume_text_path=resume_text_path,
            work_experience_path=work_exp_path,
        )

        # ---- Build the crew in resume-only mode ----
        crew = build_crew(
            tool_instances=tools,
            task_names=["research_task", "profile_task", "resume_strategy_task"],
        )

        # ---- Provide inputs referenced in tasks.yaml ----
        inputs = {
            "job_posting_url": topic,
            "github_url": github_url,
            "personal_writeup": personal_writeup,
        }

        raw = crew.kickoff(inputs=inputs)
        raw_str = str(raw)

        # Parse the final JSON into TailoredResume
        clean = extract_json(raw_str)
        tailored = TailoredResume.model_validate_json(clean)


        pdf_bytes = resume_to_pdf(tailored.model_dump())

        safe_headline = (tailored.headline or "tailored_resume").replace(" ", "_").lower()
        filename = f"{safe_headline}.pdf"

        return {
            "pdf_bytes": pdf_bytes,
            "filename": filename,
            # "tailored": tailored,  # optional but handy for debugging/front-end preview
        }
