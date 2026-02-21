"""
pptx_builder.py
PowerPoint generation for SKOOLED-AI lesson plans.
Color scheme: BG #0d1f2d (dark navy), accent #00bbd6 (cyan), secondary #faa32b (orange)
"""

import re
from io import BytesIO

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt


# ── Brand Colors ─────────────────────────────────────────────
NAVY   = RGBColor(0x0d, 0x1f, 0x2d)
CYAN   = RGBColor(0x00, 0xbb, 0xd6)
ORANGE = RGBColor(0xfa, 0xa3, 0x2b)
WHITE  = RGBColor(0xff, 0xff, 0xff)
LIGHT  = RGBColor(0xe8, 0xf8, 0xfb)
GREY   = RGBColor(0xaa, 0xcc, 0xd4)

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)


# ── Helpers ───────────────────────────────────────────────────

def _set_bg(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_rect(slide, left, top, width, height, color, alpha=None):
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        left, top, width, height
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape


def _add_textbox(slide, text, left, top, width, height,
                 font_size=18, bold=False, color=WHITE,
                 align=PP_ALIGN.LEFT, italic=False):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return txBox


def _add_title_bar(slide, title, subtitle=""):
    """Add a cyan top bar with title."""
    _add_rect(slide, 0, 0, SLIDE_W, Inches(1.4), CYAN)
    _add_textbox(slide, title,
                 Inches(0.5), Inches(0.12), Inches(12), Inches(0.8),
                 font_size=28, bold=True, color=NAVY, align=PP_ALIGN.LEFT)
    if subtitle:
        _add_textbox(slide, subtitle,
                     Inches(0.5), Inches(0.9), Inches(12), Inches(0.42),
                     font_size=14, bold=False, color=NAVY, align=PP_ALIGN.LEFT)


def _bullet_list(slide, items, top_start, left=Inches(0.6), width=Inches(12.2)):
    """Add bullet items starting at top_start, return final Y position."""
    y = top_start
    for item in items:
        if not item.strip():
            continue
        item = item.lstrip("•-* ").strip()
        if not item:
            continue
        tb = slide.shapes.add_textbox(left, y, width, Inches(0.38))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = "▸  " + item
        run.font.size = Pt(15)
        run.font.color.rgb = WHITE
        y += Inches(0.42)
        if y > SLIDE_H - Inches(0.3):
            break
    return y


# ── Markdown Parser ───────────────────────────────────────────

def parse_lesson_markdown(md):
    """
    Parse lesson plan markdown into structured sections.
    Returns dict with keys: title, subject, grade, quarter, objectives,
    materials, skills, phases (list of {name, content}),
    differentiation, assessment, reflection.
    """
    data = {
        "title": "",
        "subject": "",
        "grade": "",
        "quarter": "",
        "objectives": [],
        "materials": [],
        "skills": [],
        "phases": [],
        "differentiation": {"struggling": [], "advanced": [], "ell": []},
        "assessment": {"formative": [], "summative": []},
        "reflection": [],
    }

    lines = md.split('\n')

    # Extract H1 as title
    for line in lines:
        if line.startswith('# '):
            data["title"] = line[2:].strip()
            break

    # Extract header metadata
    for line in lines[:40]:
        clean = line.strip().lower()
        if 'subject' in clean or 'learning area' in clean:
            m = re.search(r'[:\|]\s*(.+)', line)
            if m:
                data["subject"] = m.group(1).strip().rstrip('*').strip()
        if 'grade' in clean:
            m = re.search(r'[:\|]\s*(.+)', line)
            if m:
                data["grade"] = m.group(1).strip().rstrip('*').strip()
        if 'quarter' in clean:
            m = re.search(r'[:\|]\s*(.+)', line)
            if m:
                data["quarter"] = m.group(1).strip().rstrip('*').strip()

    # Split into H2 sections
    sections = {}
    current_sec = None
    current_lines = []
    for line in lines:
        if line.startswith('## '):
            if current_sec is not None:
                sections[current_sec.lower()] = '\n'.join(current_lines)
            current_sec = line[3:].strip()
            current_lines = []
        elif current_sec is not None:
            current_lines.append(line)
    if current_sec:
        sections[current_sec.lower()] = '\n'.join(current_lines)

    def extract_bullets(text):
        items = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith(('- ', '* ', '• ')):
                items.append(line[2:].strip())
            elif re.match(r'^\d+\.\s', line):
                items.append(re.sub(r'^\d+\.\s', '', line).strip())
            elif line.startswith('**') and ':' in line:
                items.append(line.replace('**', '').strip())
        return [i for i in items if i]

    # Objectives
    for k in sections:
        if 'objective' in k or 'swbat' in k:
            data["objectives"] = extract_bullets(sections[k])[:8]
            break

    # Materials
    for k in sections:
        if 'material' in k or 'technolog' in k or 'resource' in k:
            data["materials"] = extract_bullets(sections[k])[:10]
            break

    # 21st Century Skills
    for k in sections:
        if '21st' in k or 'skill' in k:
            data["skills"] = extract_bullets(sections[k])[:6]
            break

    # Lesson Procedure phases (H3 within procedure section)
    for k in sections:
        if 'procedure' in k or 'lesson proper' in k or 'activities' in k:
            sec_text = sections[k]
            # Split by H3 headings
            phase_parts = re.split(r'\n###\s+', sec_text)
            if len(phase_parts) > 1:
                for pp in phase_parts[1:]:
                    ph_lines = pp.split('\n')
                    ph_name = ph_lines[0].strip()
                    ph_content = extract_bullets('\n'.join(ph_lines[1:]))
                    if not ph_content:
                        ph_content = [l.strip() for l in ph_lines[1:6] if l.strip()]
                    data["phases"].append({"name": ph_name, "content": ph_content[:6]})
            else:
                # No H3, treat whole section as one phase
                bullets = extract_bullets(sec_text)
                if bullets:
                    data["phases"].append({"name": "Lesson Procedure", "content": bullets[:8]})
            break

    # Differentiation
    for k in sections:
        if 'different' in k or 'scaffold' in k:
            sec_text = sections[k]
            for line in sec_text.split('\n'):
                ll = line.lower()
                if 'struggl' in ll or 'support' in ll:
                    data["differentiation"]["struggling"] = extract_bullets(sec_text[:300])[:4]
                if 'advanced' in ll or 'extend' in ll or 'enrich' in ll:
                    data["differentiation"]["advanced"] = extract_bullets(sec_text[300:600])[:4]
                if 'ell' in ll or 'english language' in ll or 'language learner' in ll:
                    data["differentiation"]["ell"] = extract_bullets(sec_text[600:900])[:4]
            # Fallback: grab all bullets
            if not any(data["differentiation"].values()):
                bullets = extract_bullets(sec_text)
                third = max(1, len(bullets) // 3)
                data["differentiation"]["struggling"] = bullets[:third]
                data["differentiation"]["advanced"] = bullets[third:2*third]
                data["differentiation"]["ell"] = bullets[2*third:]
            break

    # Assessment
    for k in sections:
        if 'assessment' in k and 'authentic' not in k:
            sec_text = sections[k]
            bullets = extract_bullets(sec_text)
            half = max(1, len(bullets) // 2)
            data["assessment"]["formative"] = bullets[:half]
            data["assessment"]["summative"] = bullets[half:]
            break

    # Reflection
    for k in sections:
        if 'reflect' in k:
            data["reflection"] = extract_bullets(sections[k])[:5]
            break

    return data


# ── Slide Builders ────────────────────────────────────────────

def _slide_title(prs, parsed):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    _set_bg(slide, NAVY)

    # Big cyan accent bar on left
    _add_rect(slide, 0, 0, Inches(0.18), SLIDE_H, CYAN)

    # Center content
    _add_textbox(slide, "SKOOLED-AI",
                 Inches(0.5), Inches(0.7), Inches(12), Inches(0.6),
                 font_size=16, bold=False, color=CYAN, align=PP_ALIGN.CENTER)

    title = parsed["title"] or "Lesson Plan"
    _add_textbox(slide, title,
                 Inches(0.5), Inches(1.5), Inches(12), Inches(1.8),
                 font_size=36, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

    # Meta info
    meta_parts = []
    if parsed["subject"]:
        meta_parts.append(parsed["subject"])
    if parsed["grade"]:
        meta_parts.append(parsed["grade"])
    if parsed["quarter"]:
        meta_parts.append(f"Quarter {parsed['quarter']}")
    meta = "  ·  ".join(meta_parts)

    _add_textbox(slide, meta,
                 Inches(0.5), Inches(3.4), Inches(12), Inches(0.5),
                 font_size=18, color=GREY, align=PP_ALIGN.CENTER)

    # Orange bottom accent
    _add_rect(slide, 0, SLIDE_H - Inches(0.22), SLIDE_W, Inches(0.22), ORANGE)

    # DepEd label
    _add_textbox(slide, "Philippine DepEd · MATATAG Curriculum",
                 Inches(0.5), SLIDE_H - Inches(0.68), Inches(12), Inches(0.36),
                 font_size=11, color=GREY, align=PP_ALIGN.CENTER)


def _slide_objectives(prs, parsed):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_bg(slide, NAVY)
    _add_title_bar(slide, "Learning Objectives", "Students Will Be Able To (SWBAT)")
    items = parsed["objectives"] or ["Learn key concepts from this lesson."]
    _bullet_list(slide, items, top_start=Inches(1.6))


def _slide_materials(prs, parsed):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_bg(slide, NAVY)
    _add_title_bar(slide, "Materials & Technology")
    items = parsed["materials"] or ["Textbook", "Whiteboard", "Digital projector"]
    _bullet_list(slide, items, top_start=Inches(1.6))


def _slide_skills(prs, parsed):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_bg(slide, NAVY)
    _add_title_bar(slide, "21st Century Skills")
    items = parsed["skills"] or ["Critical Thinking", "Communication", "Collaboration"]
    _bullet_list(slide, items, top_start=Inches(1.6))


def _slide_phase(prs, phase):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_bg(slide, NAVY)
    _add_title_bar(slide, phase["name"])
    items = phase["content"] or ["Teacher facilitates this phase of the lesson."]
    _bullet_list(slide, items, top_start=Inches(1.6))


def _slide_differentiation(prs, parsed):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_bg(slide, NAVY)
    _add_title_bar(slide, "Differentiation & Scaffolding")

    diff = parsed["differentiation"]
    col_w = Inches(4.0)
    col_gap = Inches(0.2)
    tops = {
        "struggling": ("Struggling Learners", ORANGE),
        "advanced": ("Advanced Learners", CYAN),
        "ell": ("ELL / Language Learners", RGBColor(0x00, 0xb8, 0x94)),
    }
    x = Inches(0.4)
    for key, (label, color) in tops.items():
        # Column header
        _add_rect(slide, x, Inches(1.55), col_w, Inches(0.4), color)
        _add_textbox(slide, label, x + Inches(0.1), Inches(1.58),
                     col_w - Inches(0.2), Inches(0.35),
                     font_size=13, bold=True, color=NAVY)
        items = diff.get(key) or ["Provide targeted support."]
        y = Inches(2.05)
        for item in items[:5]:
            if not item.strip():
                continue
            tb = slide.shapes.add_textbox(x + Inches(0.1), y, col_w - Inches(0.2), Inches(0.42))
            tf = tb.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = "• " + item.lstrip("•-* ").strip()
            run.font.size = Pt(12)
            run.font.color.rgb = WHITE
            y += Inches(0.44)
        x += col_w + col_gap


def _slide_assessment(prs, parsed):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_bg(slide, NAVY)
    _add_title_bar(slide, "Assessment")

    assess = parsed["assessment"]
    col_w = Inches(5.8)
    for i, (key, label, color) in enumerate([
        ("formative", "Formative Assessment", CYAN),
        ("summative", "Summative Assessment", ORANGE),
    ]):
        x = Inches(0.4) + i * (col_w + Inches(0.7))
        _add_rect(slide, x, Inches(1.55), col_w, Inches(0.4), color)
        _add_textbox(slide, label, x + Inches(0.1), Inches(1.58),
                     col_w - Inches(0.2), Inches(0.35),
                     font_size=14, bold=True, color=NAVY)
        items = assess.get(key) or ["Use teacher observation and questioning."]
        y = Inches(2.05)
        for item in items[:6]:
            if not item.strip():
                continue
            tb = slide.shapes.add_textbox(x + Inches(0.1), y, col_w - Inches(0.2), Inches(0.42))
            tf = tb.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = "• " + item.lstrip("•-* ").strip()
            run.font.size = Pt(13)
            run.font.color.rgb = WHITE
            y += Inches(0.44)


def _slide_reflection(prs, parsed):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_bg(slide, NAVY)
    _add_title_bar(slide, "Teacher Reflection")
    items = parsed["reflection"] or [
        "What went well in this lesson?",
        "What would I change next time?",
        "Did students meet the learning objectives?",
    ]
    _bullet_list(slide, items, top_start=Inches(1.6))


# ── Main Entry Point ──────────────────────────────────────────

def build_pptx(lesson_md):
    """
    Build a branded .pptx from lesson markdown.
    Returns BytesIO of the .pptx file.
    """
    parsed = parse_lesson_markdown(lesson_md)

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    # Slide 1: Title
    _slide_title(prs, parsed)

    # Slide 2: Objectives
    if parsed["objectives"]:
        _slide_objectives(prs, parsed)

    # Slide 3: Materials
    if parsed["materials"]:
        _slide_materials(prs, parsed)

    # Slide 4: 21st Century Skills
    if parsed["skills"]:
        _slide_skills(prs, parsed)

    # Slides 5–N: Lesson Procedure phases
    for phase in parsed["phases"]:
        _slide_phase(prs, phase)

    # If no phases were parsed, add a generic procedure slide
    if not parsed["phases"]:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _set_bg(slide, NAVY)
        _add_title_bar(slide, "Lesson Procedure")
        _add_textbox(slide, "See lesson plan for detailed procedure.",
                     Inches(0.6), Inches(1.8), Inches(12), Inches(0.5),
                     font_size=16, color=GREY)

    # Differentiation
    _slide_differentiation(prs, parsed)

    # Assessment
    _slide_assessment(prs, parsed)

    # Reflection
    _slide_reflection(prs, parsed)

    buf = BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf
