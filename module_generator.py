"""
Module & Submodule Generator
Parses uploaded course guides (PDF/DOCX/XLSX/TXT) and generates LMS-ready content.
"""
import io
import json
import re
from typing import Optional, Tuple


def extract_text_from_file(file_content: bytes, filename: str) -> Tuple[str, str]:
    """Extract plain text from PDF, DOCX, XLSX, or TXT. Returns (text, error)."""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'txt'
    try:
        if ext == 'pdf':
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                return '\n'.join(p.extract_text() or '' for p in pdf.pages), None
        elif ext == 'docx':
            import docx
            doc = docx.Document(io.BytesIO(file_content))
            return '\n'.join(p.text for p in doc.paragraphs if p.text.strip()), None
        elif ext in ('xlsx', 'xls'):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
            lines = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    row_text = '\t'.join(str(c) if c is not None else '' for c in row)
                    if row_text.strip():
                        lines.append(row_text)
            return '\n'.join(lines), None
        else:
            return file_content.decode('utf-8', errors='replace'), None
    except Exception as e:
        return '', f'Could not read file: {e}'


def parse_course_guide(text: str, api_key: str) -> Tuple[Optional[dict], str]:
    """
    Use Claude to extract a module/submodule structure from course guide text.
    Returns (structure_dict, error).
    """
    if not api_key:
        return None, 'API key is required.'

    prompt = f"""You are an instructional designer. Analyze this course guide and extract a structured course outline.

COURSE GUIDE:
{text[:12000]}

Return ONLY a JSON object in this exact format (no markdown, no extra text):
{{
  "course_title": "...",
  "course_description": "1-2 sentence course summary",
  "modules": [
    {{
      "id": "M1",
      "title": "Module 1: Module Title",
      "description": "Brief module description",
      "submodules": [
        {{
          "id": "M1.1",
          "title": "Submodule 1.1: Topic Name",
          "description": "What this submodule covers",
          "topics": ["key topic 1", "key topic 2", "key topic 3"]
        }}
      ]
    }}
  ]
}}

Requirements:
- 3-8 modules total
- 2-5 submodules per module
- Derive structure directly from the course content
- If structure is implicit, infer logical groupings from the subject matter
- Use the terminology from the course guide"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=5000,
            messages=[{'role': 'user', 'content': prompt}]
        )
        raw = msg.content[0].text.strip()
        m = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', raw)
        if m:
            raw = m.group(1)
        return json.loads(raw), None
    except json.JSONDecodeError as e:
        return None, f'AI returned invalid JSON: {e}'
    except Exception as e:
        return None, str(e)


def generate_submodule_content(
    course_title: str,
    module_title: str,
    submodule: dict,
    course_context: str,
    api_key: str,
) -> Tuple[Optional[str], str]:
    """Generate full HTML content for a single submodule. Returns (html, error)."""
    if not api_key:
        return None, 'API key is required.'

    topics_list = '\n'.join(f'- {t}' for t in submodule.get('topics', []))

    prompt = f"""You are an expert curriculum developer. Generate comprehensive, educational content for this course submodule.

Course: {course_title}
Module: {module_title}
Submodule: {submodule['title']}
Description: {submodule.get('description', '')}
Key Topics:
{topics_list}

Course Context (first 2000 chars of the guide):
{course_context[:2000]}

Generate rich HTML content (no <html>/<body>/<head> tags — inner content only). Structure it as follows:

<h2>Overview</h2>
2-3 paragraphs providing context and introducing the submodule. Make it engaging and relevant.

<h2>Learning Objectives</h2>
An unordered list of 4-5 specific, measurable objectives. Start each with an action verb (Identify, Explain, Apply, Analyze, etc.).

<h2>Key Concepts</h2>
For each key topic: <h3>Concept Title</h3> followed by a clear explanation with examples. Use <blockquote> for important definitions and <strong> for key terms.

<h2>Activities & Practice</h2>
2-3 practical learning activities students can do to apply the concepts. Number them.

<h2>Check Your Understanding</h2>
3-5 formative questions (questions only, no answers). Use <ol>.

Write substantive content — this goes directly into the LMS as course material. Use <ul>, <ol>, <table> where appropriate."""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=3500,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return msg.content[0].text.strip(), None
    except Exception as e:
        return None, str(e)
