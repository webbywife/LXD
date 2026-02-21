"""
Syllabus Generator for SKOOLED-AI.
Generates complete OBE-aligned course syllabi for SHS and College level.
Uses AI (Claude/OpenAI) or returns a structured template when no API key is set.
"""

import json
import re


# ── Public entry point ──────────────────────────────────────────────────────

def generate_syllabus(config, api_key="", ai_provider="anthropic"):
    """
    Generate a complete course syllabus.

    config keys (all strings unless noted):
        institution_type  : "college" | "shs"
        school_name       : str
        college_dept      : str
        program           : str
        course_code       : str
        course_title      : str
        credits           : str  (e.g. "3 units (2 lec + 1 lab)")
        prerequisites     : str
        course_type       : str  (e.g. "Core / Major / Elective")
        semester          : str  (e.g. "2nd Semester, AY 2025-2026")
        course_description: str
        num_weeks         : int  (12–18)
        program_outcomes  : str  (one outcome per line)
        course_outcomes   : str  (one outcome per line)
        grading           : dict {component: weight_int}

    Returns (syllabus_dict, error_string | None).
    """
    if not api_key:
        return _build_template_syllabus(config), None

    try:
        ai_data = _generate_with_ai(config, api_key, ai_provider)
        return _merge_config_with_ai(config, ai_data), None
    except Exception as e:
        # Graceful fallback — never crash the user-facing request
        return _build_template_syllabus(config), f"AI generation failed ({e}); template used instead."


# ── AI Generation ───────────────────────────────────────────────────────────

def _generate_with_ai(config, api_key, ai_provider):
    """Call AI and return the raw parsed dict."""
    prompt = _build_prompt(config)
    if ai_provider == "openai":
        return _call_openai(prompt, api_key)
    return _call_anthropic(prompt, api_key)


def _build_prompt(config):
    num_weeks = int(config.get("num_weeks", 14))
    course_title = config.get("course_title", "Course")
    po_text = config.get("program_outcomes", "").strip() or "(Generate standard program outcomes for this discipline)"
    co_text = config.get("course_outcomes", "").strip() or "(Generate appropriate course outcomes from the description)"

    grading = config.get("grading", {})
    grading_text = "\n".join(f"- {k}: {v}%" for k, v in grading.items()) if grading \
        else "- Activities: 30%\n- Projects: 30%\n- Final Project: 40%"

    return f"""You are an expert OBE (Outcomes-Based Education) curriculum designer for Philippine Higher Education.
Create a complete, detailed course syllabus.

COURSE INFORMATION:
- Institution Type: {config.get('institution_type', 'college').upper()}
- School/University: {config.get('school_name', '')}
- College/Department: {config.get('college_dept', '')}
- Program: {config.get('program', '')}
- Course Code: {config.get('course_code', '')}
- Course Title: {course_title}
- Credit Units: {config.get('credits', '3 units')}
- Prerequisites: {config.get('prerequisites', 'None')}
- Course Type: {config.get('course_type', 'Core')}
- Academic Period: {config.get('semester', '')}
- Number of Weeks: {num_weeks}

COURSE DESCRIPTION:
{config.get('course_description', '')}

PROGRAM OUTCOMES (instructor-provided):
{po_text}

COURSE OUTCOMES (instructor-provided):
{co_text}

GRADING SYSTEM:
{grading_text}

Generate ONLY a valid JSON object (no markdown, no extra text) with this EXACT structure:
{{
  "co_po_mapping": {{"CO1": ["PO1", "PO2"], "CO2": ["PO2", "PO3"]}},
  "course_plan": [
    {{
      "week": 1,
      "topics": "Topic title with 2-3 specific subtopics",
      "ilos": "By the end of this week, students will be able to: (1) verb+outcome, (2) verb+outcome",
      "tlas": "Primary strategy (e.g. Lecture-Discussion), Secondary activity (e.g. Think-Pair-Share)",
      "assessment_tasks": "Specific output or activity (e.g. Reflective journal entry, Quiz 1)",
      "evaluation_strategies": "Rubric or scoring criteria name/reference",
      "resources": "Author (Year). Title. / URL — description",
      "due_date": ""
    }}
  ],
  "technology_requirements": "Bulleted list of required software, hardware, and platforms",
  "communication_guidelines": "Office hours, preferred contact method, LMS platform, response time",
  "submission_protocol": "Deadline policy, file format requirements, LMS submission steps",
  "course_requirements": [
    "Attendance: Minimum 80% required to avoid INC/Dropped grade",
    "Academic Integrity: All outputs must be original work. Plagiarism results in failing grade.",
    "Class Participation: Students must come prepared and actively engage."
  ],
  "rubric": {{
    "title": "Major Output Assessment Rubric",
    "criteria": [
      {{
        "criterion": "Criterion name",
        "weight": "25%",
        "excellent_4": "Exceeds all expectations; comprehensive and flawless",
        "satisfactory_3": "Meets all requirements with minor lapses",
        "developing_2": "Partially meets requirements; noticeable gaps",
        "beginning_1": "Does not meet requirements; major revisions needed"
      }}
    ]
  }},
  "references_books": [
    "Author, A. A. (Year). Title of book. Publisher."
  ],
  "references_websites": [
    "https://example.com — Description of resource"
  ]
}}

CRITICAL REQUIREMENTS:
- Generate EXACTLY {num_weeks} objects in the course_plan array (week 1 through week {num_weeks})
- ALL content must be SPECIFIC to "{course_title}" — avoid generic placeholders
- ILOs must use Bloom's Taxonomy action verbs (identify, analyze, design, evaluate, create…)
- TLAs must VARY across weeks: lectures, workshops, peer critique, lab work, presentations, etc.
- Week {num_weeks} must be Final Presentations / Summative Assessment
- References must be real, relevant, citable academic sources for this subject
- co_po_mapping keys must match exactly the CO codes parsed from the instructor's course outcomes
- Respond with ONLY the raw JSON object"""


def _call_anthropic(prompt, api_key):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=10000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _call_openai(prompt, api_key):
    import openai
    client = openai.OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=10000,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


# ── Merge & Parse ───────────────────────────────────────────────────────────

def _merge_config_with_ai(config, ai_data):
    po_list = _parse_outcomes(config.get("program_outcomes", ""), "PO")
    co_list = _parse_outcomes(config.get("course_outcomes", ""), "CO")

    co_po_map = ai_data.get("co_po_mapping", {})
    for co in co_list:
        if co["code"] in co_po_map:
            co["po_mapping"] = co_po_map[co["code"]]

    grading = config.get("grading", {"Activities": 30, "Projects": 30, "Final Project": 40})
    grading_list = [{"component": k, "weight": v} for k, v in grading.items()]

    return {
        "institution_type": config.get("institution_type", "college"),
        "school_name": config.get("school_name", ""),
        "college_dept": config.get("college_dept", ""),
        "program": config.get("program", ""),
        "course_code": config.get("course_code", ""),
        "course_title": config.get("course_title", ""),
        "credits": config.get("credits", "3 units"),
        "prerequisites": config.get("prerequisites", "None"),
        "course_type": config.get("course_type", "Core"),
        "semester": config.get("semester", ""),
        "faculty": "",
        "schedule": "",
        "course_description": config.get("course_description", ""),
        "program_outcomes": po_list,
        "course_outcomes": co_list,
        "course_plan": ai_data.get("course_plan", []),
        "technology_requirements": ai_data.get("technology_requirements", ""),
        "communication_guidelines": ai_data.get("communication_guidelines", ""),
        "submission_protocol": ai_data.get("submission_protocol", ""),
        "course_requirements": ai_data.get("course_requirements", []),
        "grading_system": grading_list,
        "rubric": ai_data.get("rubric", {}),
        "references": {
            "books": ai_data.get("references_books", []),
            "websites": ai_data.get("references_websites", []),
        },
    }


def _parse_outcomes(text, prefix):
    """Parse a freeform block of outcome text into a structured list."""
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    outcomes = []
    for i, line in enumerate(lines, 1):
        clean = re.sub(
            r"^(?:\d+[\.\):]?\s*|[-•*]\s*|(?:PO|CO|LO)\s*\d+[\.\):\s]*)", "", line
        ).strip()
        if clean:
            outcomes.append({"code": f"{prefix}{i}", "description": clean, "po_mapping": []})
    return outcomes


# ── Template Fallback ───────────────────────────────────────────────────────

def _build_template_syllabus(config):
    """Return a structured shell syllabus without AI (placeholders)."""
    num_weeks = int(config.get("num_weeks", 14))
    po_list = _parse_outcomes(config.get("program_outcomes", ""), "PO")
    co_list = _parse_outcomes(config.get("course_outcomes", ""), "CO")
    grading = config.get("grading", {"Activities": 30, "Projects": 30, "Final Project": 40})
    grading_list = [{"component": k, "weight": v} for k, v in grading.items()]

    course_plan = []
    for w in range(1, num_weeks + 1):
        if w == 1:
            topics = "Course Introduction and Overview"
            ilos = "Students will understand the course structure, requirements, and grading policy."
            tlas = "Course Orientation, Lecture-Discussion"
            ats = "Participation / Orientation Activity"
        elif w == num_weeks:
            topics = "Final Presentations and Course Synthesis"
            ilos = "Students will demonstrate mastery of all course outcomes through their final output."
            tlas = "Final Project Presentations, Peer Evaluation"
            ats = "Final Project Submission"
        else:
            topics = f"[Week {w} Topic — add specific content]"
            ilos = "[Specific, measurable learning outcomes for this week using Bloom's verbs]"
            tlas = "[Teaching and learning activities — e.g., lecture, workshop, group work]"
            ats = "[Assessment task — quiz, activity, output]"

        course_plan.append({
            "week": w,
            "topics": topics,
            "ilos": ilos,
            "tlas": tlas,
            "assessment_tasks": ats,
            "evaluation_strategies": "Rubric / Checklist",
            "resources": "[Textbook chapter / Online resource]",
            "due_date": "",
        })

    return {
        "institution_type": config.get("institution_type", "college"),
        "school_name": config.get("school_name", ""),
        "college_dept": config.get("college_dept", ""),
        "program": config.get("program", ""),
        "course_code": config.get("course_code", ""),
        "course_title": config.get("course_title", ""),
        "credits": config.get("credits", "3 units"),
        "prerequisites": config.get("prerequisites", "None"),
        "course_type": config.get("course_type", "Core"),
        "semester": config.get("semester", ""),
        "faculty": "",
        "schedule": "",
        "course_description": config.get("course_description", ""),
        "program_outcomes": po_list,
        "course_outcomes": co_list,
        "course_plan": course_plan,
        "technology_requirements": "• Computer / Laptop with internet access\n• Relevant software tools for the course\n• LMS account (e.g., Canvas, Google Classroom, or Moodle)\n• Cloud storage (Google Drive or OneDrive) for submissions",
        "communication_guidelines": "Students may contact the instructor via the school's official email or LMS messaging system. Responses will be given within 24–48 hours on weekdays. For urgent concerns, use the designated class group chat.",
        "submission_protocol": "All outputs must be submitted through the official LMS before the deadline. Late submissions will be deducted 10% per day unless prior arrangements are made. Files must be in the specified format (PDF/DOCX/etc.) and named properly: SURNAME_CourseCode_WeekNo_Output.",
        "course_requirements": [
            "Attendance: Minimum 80% required. Exceeding 20% absences may result in INC or DRP.",
            "Academic Integrity: All outputs must be the student's own work. Plagiarism will result in a failing grade for the output and may lead to disciplinary action.",
            "Active Participation: Students are expected to come prepared, contribute to discussions, and respect all members of the class.",
        ],
        "grading_system": grading_list,
        "rubric": {
            "title": "Course Output Assessment Rubric",
            "criteria": [
                {
                    "criterion": "Content & Accuracy",
                    "weight": "30%",
                    "excellent_4": "Content is comprehensive, accurate, and exceeds requirements",
                    "satisfactory_3": "Content is accurate and meets all requirements",
                    "developing_2": "Content is mostly accurate but has minor gaps or errors",
                    "beginning_1": "Content has significant inaccuracies or is incomplete",
                },
                {
                    "criterion": "Organization & Clarity",
                    "weight": "25%",
                    "excellent_4": "Exceptionally well-organized; ideas flow logically and clearly",
                    "satisfactory_3": "Well-organized with a clear presentation structure",
                    "developing_2": "Somewhat organized; minor clarity or flow issues",
                    "beginning_1": "Poorly organized; difficult to follow",
                },
                {
                    "criterion": "Creativity & Originality",
                    "weight": "25%",
                    "excellent_4": "Highly original and innovative; demonstrates unique insight",
                    "satisfactory_3": "Shows creativity and some original thinking",
                    "developing_2": "Limited creativity; mostly conventional approach",
                    "beginning_1": "Little to no creativity or originality demonstrated",
                },
                {
                    "criterion": "Technical Execution",
                    "weight": "20%",
                    "excellent_4": "Flawless technical execution; professional quality",
                    "satisfactory_3": "Good technical execution; meets stated standards",
                    "developing_2": "Adequate execution with noticeable technical issues",
                    "beginning_1": "Poor technical execution; fails to meet standards",
                },
            ],
        },
        "references": {
            "books": [
                "[Author, A. A. (Year). Title of work: Subtitle. Publisher.]",
                "[Author, B. B. & Author, C. C. (Year). Title of work. Publisher.]",
            ],
            "websites": [
                "[https://example.com] — Description of online resource",
            ],
        },
    }
