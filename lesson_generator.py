"""
AI Lesson Plan Generator Engine
Generates DepEd MATATAG-aligned lesson plans using curriculum data + AI.
Supports customizable template sections.
"""

import json
import os
from curriculum_loader import (
    get_competency_by_id, get_competencies,
    get_pedagogical_approaches, get_21st_century_skills,
    get_crosscutting_concepts, SUBJECT_DISPLAY
)

# All available template sections with defaults
TEMPLATE_SECTIONS = {
    "title_info": {
        "label": "Lesson Plan Title, Subject, Grade Level & Time Allotment",
        "enabled": True,
        "order": 1,
        "customizable_fields": {
            "time_allotment": "60 minutes",
            "custom_title": "",
        }
    },
    "twenty_first_century_skills": {
        "label": "21st Century Skills Focus",
        "enabled": True,
        "order": 2,
        "customizable_fields": {
            "focus_skills": [],
        }
    },
    "learning_objectives": {
        "label": "Learning Objectives (SWBAT)",
        "enabled": True,
        "order": 3,
        "customizable_fields": {
            "num_objectives": 3,
            "custom_objectives": [],
        }
    },
    "materials_technology": {
        "label": "Materials / Technology",
        "enabled": True,
        "order": 4,
        "customizable_fields": {
            "include_digital_tools": True,
            "include_traditional": True,
            "custom_materials": [],
        }
    },
    "prior_knowledge": {
        "label": "Prior Knowledge / Prerequisites",
        "enabled": True,
        "order": 5,
        "customizable_fields": {
            "custom_prerequisites": [],
        }
    },
    "lesson_procedure": {
        "label": "Lesson Procedure",
        "enabled": True,
        "order": 6,
        "customizable_fields": {
            "model": "5e",  # 5e, 4as, design_thinking
            "include_timing": True,
            "custom_activities": {},
        }
    },
    "differentiation": {
        "label": "Differentiation / Scaffolding",
        "enabled": True,
        "order": 7,
        "customizable_fields": {
            "include_struggling": True,
            "include_advanced": True,
            "include_ell": True,
            "custom_strategies": [],
        }
    },
    "assessment": {
        "label": "Assessment",
        "enabled": True,
        "order": 8,
        "customizable_fields": {
            "include_formative": True,
            "include_summative": True,
            "custom_assessments": [],
        }
    },
    "reflection": {
        "label": "Teacher Reflection",
        "enabled": True,
        "order": 9,
        "customizable_fields": {
            "num_prompts": 3,
            "custom_prompts": [],
        }
    },
}

# Instructional design models
PROCEDURE_MODELS = {
    "5e": {
        "label": "5E Model (Engage, Explore, Explain, Elaborate, Evaluate)",
        "phases": ["Engage", "Explore", "Explain", "Elaborate", "Evaluate"]
    },
    "4as": {
        "label": "4A's Model (Activity, Analysis, Abstraction, Application)",
        "phases": ["Activity", "Analysis", "Abstraction", "Application"]
    },
    "design_thinking": {
        "label": "Design Thinking (Empathize, Define, Ideate, Prototype, Test)",
        "phases": ["Empathize", "Define", "Ideate", "Prototype", "Test"]
    },
    "direct_instruction": {
        "label": "Direct Instruction (Review, Present, Practice, Assess)",
        "phases": ["Review Previous Lesson", "Presentation/Modeling", "Guided Practice", "Independent Practice", "Assessment/Closure"]
    },
    "deped_dlp": {
        "label": "DepEd DLP Format (Review, Motivation, Activity, Analysis, Abstraction, Application, Assessment, Assignment)",
        "phases": ["Review Previous Lesson", "Motivation/Drill", "Activity", "Analysis", "Abstraction", "Application", "Assessment", "Assignment/Agreement"]
    }
}


def get_template_sections():
    """Return the available template sections with their defaults."""
    return TEMPLATE_SECTIONS.copy()


def get_procedure_models():
    """Return available instructional design models."""
    return PROCEDURE_MODELS.copy()


def _gather_curriculum_context(subject_id, competency_ids):
    """Gather all relevant curriculum data for the selected competencies."""
    competencies = []
    for cid in competency_ids:
        comp = get_competency_by_id(cid)
        if comp:
            competencies.append(comp)

    if not competencies:
        return None

    approaches = get_pedagogical_approaches(subject_id)
    skills = get_21st_century_skills(subject_id)
    concepts = get_crosscutting_concepts(subject_id)

    # Gather content_topic — fall back to content_standard if topic is empty
    content_topic = competencies[0].get("content_topic", "")
    content_standard = competencies[0].get("content_standard", "")
    if not content_topic and content_standard:
        content_topic = content_standard

    # Collect all unique content standards across selected competencies for richer context
    all_content_standards = list(dict.fromkeys(
        c.get("content_standard", "") for c in competencies if c.get("content_standard", "")
    ))

    # Collect all unique performance standards
    all_perf_standards = list(dict.fromkeys(
        c.get("performance_standard", "") for c in competencies if c.get("performance_standard", "")
    ))

    # Build a summary of all competency texts for context
    all_lc_texts = [c.get("learning_competency", "") for c in competencies if c.get("learning_competency", "")]

    return {
        "subject": SUBJECT_DISPLAY.get(subject_id, subject_id),
        "subject_id": subject_id,
        "competencies": competencies,
        "grade": competencies[0].get("grade", ""),
        "quarter": competencies[0].get("quarter", ""),
        "key_stage": competencies[0].get("key_stage", ""),
        "domain": competencies[0].get("domain", ""),
        "content_topic": content_topic,
        "content_standard": content_standard,
        "performance_standard": competencies[0].get("performance_standard", ""),
        "all_content_standards": all_content_standards,
        "all_performance_standards": all_perf_standards,
        "all_lc_texts": all_lc_texts,
        "blooms_level": competencies[0].get("blooms_level", ""),
        "pedagogical_approaches": approaches,
        "twenty_first_century_skills": skills,
        "crosscutting_concepts": concepts,
    }


def build_ai_prompt(context, template_config):
    """Build the AI prompt for lesson plan generation."""
    subject = context["subject"]
    grade = context["grade"]
    quarter = context["quarter"]
    domain = context["domain"]
    topic = context["content_topic"]

    competency_texts = []
    for c in context["competencies"]:
        lc = c.get("learning_competency", "")
        lc_id = c.get("lc_id", "")
        bloom = c.get("blooms_level", "")
        cs = c.get("content_standard", "")
        ps = c.get("performance_standard", "")
        extra_info = ""
        if c.get("extra_data"):
            try:
                ed = json.loads(c["extra_data"])
                extra_parts = []
                for k, v in ed.items():
                    if v and k not in ("AI-Searchable Tags", "Notes"):
                        extra_parts.append(f"{k}: {v}")
                if extra_parts:
                    extra_info = " | " + " | ".join(extra_parts[:3])
            except (json.JSONDecodeError, TypeError):
                pass
        competency_texts.append(f"- [{lc_id}] {lc} (Bloom's: {bloom}, Content Standard: {cs}){extra_info}")

    content_std = context.get("content_standard", "")
    perf_std = context.get("performance_standard", "")

    # Include ALL content standards and performance standards across selected competencies
    all_cs = context.get("all_content_standards", [])
    all_ps = context.get("all_performance_standards", [])
    all_cs_text = "\n".join(f"- {cs}" for cs in all_cs) if all_cs else content_std
    all_ps_text = "\n".join(f"- {ps}" for ps in all_ps) if all_ps else perf_std

    approaches_text = "\n".join(
        f"- {a['approach_name']}: {a.get('description', '')}"
        for a in context["pedagogical_approaches"][:5]
    )

    skills_text = "\n".join(
        f"- {s['skill_name']}: {s.get('description', '')}"
        for s in context["twenty_first_century_skills"][:8]
    )

    concepts_text = "\n".join(
        f"- {c['concept_name']}: {c.get('description', '')}"
        for c in context["crosscutting_concepts"][:5]
    )

    # Determine which sections to generate
    enabled_sections = {k: v for k, v in template_config.items() if v.get("enabled", True)}

    # Build the procedure model info
    proc_config = template_config.get("lesson_procedure", {})
    proc_fields = proc_config.get("customizable_fields", {})
    model_key = proc_fields.get("model", "5e")
    model_info = PROCEDURE_MODELS.get(model_key, PROCEDURE_MODELS["5e"])

    prompt = f"""You are an expert Philippine DepEd curriculum specialist and instructional designer.
Generate a detailed, classroom-ready lesson plan based on the MATATAG curriculum data below.
The lesson plan MUST directly teach the specific learning competencies listed. Every activity, question, and assessment must relate to these competencies.

=== CURRICULUM DATA ===
Subject: {subject}
Grade Level: Grade {grade}
Quarter: {quarter}
Key Stage: {context.get('key_stage', '')}
Domain: {domain}
Content Topic: {topic}

Content Standards (what students should know):
{all_cs_text}

Performance Standards (what students should be able to do):
{all_ps_text}

Learning Competencies (THESE are the specific skills to teach — each one must be addressed):
{chr(10).join(competency_texts)}

Recommended Pedagogical Approaches:
{approaches_text}

21st Century Skills (for this subject):
{skills_text}

Crosscutting Concepts:
{concepts_text}
=== END CURRICULUM DATA ===

Generate a COMPLETE lesson plan with the following sections (generate ONLY the sections listed below):

"""

    section_instructions = []

    if "title_info" in enabled_sections:
        fields = enabled_sections["title_info"].get("customizable_fields", {})
        time = fields.get("time_allotment", "60 minutes")
        custom_title = fields.get("custom_title", "")
        title_note = f' Use this title: "{custom_title}"' if custom_title else " Create an engaging, descriptive title."
        section_instructions.append(
            f"## 1. LESSON PLAN HEADER\n"
            f"- Title:{title_note}\n"
            f"- Subject: {subject}\n"
            f"- Grade Level: Grade {grade}\n"
            f"- Quarter: {quarter}\n"
            f"- Time Allotment: {time}\n"
            f"- Content Topic: {topic}"
        )

    if "twenty_first_century_skills" in enabled_sections:
        fields = enabled_sections["twenty_first_century_skills"].get("customizable_fields", {})
        focus = fields.get("focus_skills", [])
        if focus:
            focus_note = f" Focus on these skills: {', '.join(focus)}."
        else:
            focus_note = " Select the most relevant 3-4 skills from the curriculum data above."
        section_instructions.append(
            f"## 2. 21ST CENTURY SKILLS FOCUS\n"
            f"List the specific 21st century skills this lesson develops.{focus_note}\n"
            f"For each skill, briefly explain HOW the lesson develops it."
        )

    if "learning_objectives" in enabled_sections:
        fields = enabled_sections["learning_objectives"].get("customizable_fields", {})
        num = fields.get("num_objectives", 3)
        custom = fields.get("custom_objectives", [])
        if custom:
            obj_note = f" Include these objectives: {'; '.join(custom)}. Add more as needed."
        else:
            obj_note = ""
        section_instructions.append(
            f"## 3. LEARNING OBJECTIVES (SWBAT)\n"
            f"Write {num} clear, measurable objectives using 'Students Will Be Able To...' format.\n"
            f"Align with the Bloom's taxonomy level specified in the competencies.{obj_note}\n"
            f"Each objective must be specific and assessable."
        )

    if "materials_technology" in enabled_sections:
        fields = enabled_sections["materials_technology"].get("customizable_fields", {})
        include_digital = fields.get("include_digital_tools", True)
        include_trad = fields.get("include_traditional", True)
        custom_mats = fields.get("custom_materials", [])
        mat_parts = []
        if include_trad:
            mat_parts.append("traditional classroom materials")
        if include_digital:
            mat_parts.append("digital tools and technology resources")
        if custom_mats:
            mat_parts.append(f"Include these specific items: {', '.join(custom_mats)}")
        section_instructions.append(
            f"## 4. MATERIALS / TECHNOLOGY\n"
            f"List all needed {' and '.join(mat_parts)}.\n"
            f"Be specific (e.g., 'Manila paper, markers, ruler' not just 'art supplies').\n"
            f"Consider resources available in typical Filipino classrooms."
        )

    if "prior_knowledge" in enabled_sections:
        fields = enabled_sections["prior_knowledge"].get("customizable_fields", {})
        custom_prereqs = fields.get("custom_prerequisites", [])
        prereq_note = f" Include: {'; '.join(custom_prereqs)}." if custom_prereqs else ""
        section_instructions.append(
            f"## 5. PRIOR KNOWLEDGE / PREREQUISITES\n"
            f"List what students should already know or be able to do before this lesson.{prereq_note}\n"
            f"Reference previous quarter/grade competencies where applicable."
        )

    if "lesson_procedure" in enabled_sections:
        include_timing = proc_fields.get("include_timing", True)
        timing_note = " Include suggested time allocation for each phase." if include_timing else ""
        custom_activities = proc_fields.get("custom_activities", {})
        activity_note = ""
        if custom_activities:
            parts = [f"  - {phase}: {act}" for phase, act in custom_activities.items()]
            activity_note = "\nInclude these specific activities:\n" + "\n".join(parts)
        section_instructions.append(
            f"## 6. LESSON PROCEDURE ({model_info['label']})\n"
            f"Use the {model_info['label']} instructional model.\n"
            f"For each phase ({', '.join(model_info['phases'])}), provide:\n"
            f"- Clear teacher actions and instructions\n"
            f"- Student activities and expected responses\n"
            f"- Key questions to ask\n"
            f"- Transition cues{timing_note}{activity_note}\n"
            f"Make activities culturally relevant to Filipino students."
        )

    if "differentiation" in enabled_sections:
        fields = enabled_sections["differentiation"].get("customizable_fields", {})
        diff_parts = []
        if fields.get("include_struggling", True):
            diff_parts.append("Struggling Learners: specific scaffolding strategies, simplified tasks, visual aids")
        if fields.get("include_advanced", True):
            diff_parts.append("Advanced Learners: extension activities, higher-order thinking challenges")
        if fields.get("include_ell", True):
            diff_parts.append("English Language Learners (ELL): vocabulary support, L1 bridging strategies, visual/contextual clues")
        custom_strats = fields.get("custom_strategies", [])
        if custom_strats:
            diff_parts.append(f"Additional strategies: {'; '.join(custom_strats)}")
        section_instructions.append(
            f"## 7. DIFFERENTIATION / SCAFFOLDING\n"
            f"Provide specific strategies for:\n" +
            "\n".join(f"- {p}" for p in diff_parts)
        )

    if "assessment" in enabled_sections:
        fields = enabled_sections["assessment"].get("customizable_fields", {})
        assess_parts = []
        if fields.get("include_formative", True):
            assess_parts.append("Formative Assessment: ongoing checks for understanding during the lesson (observation, exit tickets, think-pair-share responses, etc.)")
        if fields.get("include_summative", True):
            assess_parts.append("Summative Assessment: end-of-lesson or end-of-unit evaluation aligned to the performance standard")
        custom_assess = fields.get("custom_assessments", [])
        if custom_assess:
            assess_parts.append(f"Include these specific assessments: {'; '.join(custom_assess)}")
        section_instructions.append(
            f"## 8. ASSESSMENT\n"
            f"Provide detailed assessment strategies:\n" +
            "\n".join(f"- {p}" for p in assess_parts) +
            f"\nEnsure assessments directly measure the learning objectives."
        )

    if "reflection" in enabled_sections:
        fields = enabled_sections["reflection"].get("customizable_fields", {})
        num_prompts = fields.get("num_prompts", 3)
        custom_prompts = fields.get("custom_prompts", [])
        reflection_note = f" Include these reflection prompts: {'; '.join(custom_prompts)}." if custom_prompts else ""
        section_instructions.append(
            f"## 9. TEACHER REFLECTION\n"
            f"Provide {num_prompts} reflection prompts for the teacher to evaluate:\n"
            f"- Lesson effectiveness and student engagement\n"
            f"- What worked well and what needs improvement\n"
            f"- Plans for re-teaching or follow-up{reflection_note}"
        )

    prompt += "\n\n".join(section_instructions)

    prompt += """

IMPORTANT GUIDELINES:
- All content must align with Philippine DepEd MATATAG curriculum standards
- Activities should be culturally relevant and appropriate for Filipino classrooms
- Use both English and Filipino terms where appropriate (especially for subjects taught in Filipino)
- Be specific and practical — a teacher should be able to use this plan directly
- Use markdown formatting for clear structure
- Reference the specific Learning Competency codes (LC_IDs) provided
"""

    return prompt


def generate_lesson_plan_local(context, template_config):
    """Generate a lesson plan using template-based approach (no AI API needed)."""
    subject = context["subject"]
    grade = context["grade"]
    quarter = context["quarter"]
    domain = context["domain"]
    topic = context["content_topic"]

    # Gather enabled sections
    enabled = {k: v for k, v in template_config.items() if v.get("enabled", True)}
    proc_fields = template_config.get("lesson_procedure", {}).get("customizable_fields", {})
    model_key = proc_fields.get("model", "5e")
    model_info = PROCEDURE_MODELS.get(model_key, PROCEDURE_MODELS["5e"])

    sections = []

    # Include all content/performance standards in header
    all_cs = context.get("all_content_standards", [])
    all_ps = context.get("all_performance_standards", [])
    cs_display = "; ".join(all_cs) if all_cs else context.get("content_standard", "")
    ps_display = "; ".join(all_ps) if all_ps else context.get("performance_standard", "")

    if "title_info" in enabled:
        fields = enabled["title_info"].get("customizable_fields", {})
        time_allot = fields.get("time_allotment", "60 minutes")
        custom_title = fields.get("custom_title", "")
        title_parts = [p for p in [topic, domain] if p]
        title = custom_title if custom_title else " - ".join(title_parts) if title_parts else subject
        sections.append(f"""## Lesson Plan

| | |
|---|---|
| **Title** | {title} |
| **Subject** | {subject} |
| **Grade Level** | Grade {grade} |
| **Quarter** | {quarter} |
| **Key Stage** | {context.get('key_stage', '')} |
| **Domain** | {domain} |
| **Content Topic** | {topic} |
| **Time Allotment** | {time_allot} |
| **Content Standard** | {cs_display} |
| **Performance Standard** | {ps_display} |
""")

    if "twenty_first_century_skills" in enabled:
        fields = enabled["twenty_first_century_skills"].get("customizable_fields", {})
        focus = fields.get("focus_skills", [])
        skills = context.get("twenty_first_century_skills", [])
        sections.append("## 21st Century Skills Focus\n")
        if focus:
            for s in focus:
                sections.append(f"- **{s}**")
        elif skills:
            for s in skills[:4]:
                desc = s.get("description", "")
                sections.append(f"- **{s['skill_name']}**: {desc}")
        sections.append("")

    if "learning_objectives" in enabled:
        fields = enabled["learning_objectives"].get("customizable_fields", {})
        custom = fields.get("custom_objectives", [])
        sections.append("## Learning Objectives (SWBAT)\n")
        sections.append("At the end of this lesson, students will be able to:\n")
        if custom:
            for i, obj in enumerate(custom, 1):
                sections.append(f"{i}. {obj}")
        else:
            for i, c in enumerate(context["competencies"], 1):
                lc = c.get("learning_competency", "")
                bloom = c.get("blooms_level", "")
                sections.append(f"{i}. {lc} *(Bloom's: {bloom})*")
        sections.append("")

    if "materials_technology" in enabled:
        fields = enabled["materials_technology"].get("customizable_fields", {})
        custom_mats = fields.get("custom_materials", [])
        sections.append("## Materials / Technology\n")
        if custom_mats:
            for m in custom_mats:
                sections.append(f"- {m}")
        else:
            sections.append("- Textbook / DepEd learning module")
            sections.append("- Manila paper, markers, and writing materials")
            sections.append("- Visual aids and charts related to the topic")
            if fields.get("include_digital_tools", True):
                sections.append("- Laptop/projector for multimedia presentation (if available)")
                sections.append("- Educational apps or online resources")
        sections.append("")

    if "prior_knowledge" in enabled:
        fields = enabled["prior_knowledge"].get("customizable_fields", {})
        custom_prereqs = fields.get("custom_prerequisites", [])
        sections.append("## Prior Knowledge / Prerequisites\n")
        sections.append("Students should already be able to:\n")
        if custom_prereqs:
            for p in custom_prereqs:
                sections.append(f"- {p}")
        else:
            sections.append(f"- Demonstrate foundational understanding of {domain}")
            if context.get("competencies"):
                extra = context["competencies"][0].get("extra_data")
                if extra:
                    try:
                        ed = json.loads(extra)
                        prereqs = ed.get("Prerequisites", "")
                        if prereqs:
                            sections.append(f"- {prereqs}")
                    except (json.JSONDecodeError, TypeError):
                        pass
        sections.append("")

    if "lesson_procedure" in enabled:
        include_timing = proc_fields.get("include_timing", True)
        custom_activities = proc_fields.get("custom_activities", {})
        sections.append(f"## Lesson Procedure ({model_info['label']})\n")
        for phase in model_info["phases"]:
            sections.append(f"### {phase}")
            if include_timing:
                sections.append(f"*Suggested time: ___ minutes*\n")
            if phase in custom_activities:
                sections.append(f"{custom_activities[phase]}\n")
            else:
                sections.append(f"**Teacher Activity:**\n- [Describe teacher actions for {phase} phase]\n")
                sections.append(f"**Student Activity:**\n- [Describe student activities for {phase} phase]\n")
                sections.append(f"**Key Questions:**\n- [List guiding questions]\n")
        sections.append("")

    if "differentiation" in enabled:
        fields = enabled["differentiation"].get("customizable_fields", {})
        custom_strats = fields.get("custom_strategies", [])
        sections.append("## Differentiation / Scaffolding\n")
        if fields.get("include_struggling", True):
            sections.append("### Struggling Learners")
            sections.append("- Provide step-by-step visual guides")
            sections.append("- Use peer tutoring and collaborative grouping")
            sections.append("- Simplify tasks while maintaining learning objectives\n")
        if fields.get("include_advanced", True):
            sections.append("### Advanced Learners")
            sections.append("- Provide extension activities with higher-order thinking")
            sections.append("- Assign leadership roles in group activities")
            sections.append("- Offer open-ended problems for deeper exploration\n")
        if fields.get("include_ell", True):
            sections.append("### English Language Learners (ELL)")
            sections.append("- Use bilingual (English-Filipino) vocabulary cards")
            sections.append("- Provide visual and contextual clues")
            sections.append("- Allow L1 (Mother Tongue) support during discussions\n")
        if custom_strats:
            sections.append("### Additional Strategies")
            for s in custom_strats:
                sections.append(f"- {s}")
        sections.append("")

    if "assessment" in enabled:
        fields = enabled["assessment"].get("customizable_fields", {})
        custom_assess = fields.get("custom_assessments", [])
        sections.append("## Assessment\n")
        if fields.get("include_formative", True):
            sections.append("### Formative Assessment (During Lesson)")
            sections.append("- Observation of student participation and engagement")
            sections.append("- Think-Pair-Share responses")
            sections.append("- Exit ticket / quick check questions\n")
        if fields.get("include_summative", True):
            sections.append("### Summative Assessment (End of Lesson/Unit)")
            sections.append(f"- Performance task aligned to: *{context.get('performance_standard', '')}*")
            sections.append("- Written quiz or activity sheet")
            sections.append("- Portfolio entry or project output\n")
        if custom_assess:
            sections.append("### Custom Assessments")
            for a in custom_assess:
                sections.append(f"- {a}")
        sections.append("")

    if "reflection" in enabled:
        fields = enabled["reflection"].get("customizable_fields", {})
        num = fields.get("num_prompts", 3)
        custom = fields.get("custom_prompts", [])
        sections.append("## Teacher Reflection\n")
        if custom:
            for p in custom:
                sections.append(f"- {p}")
        else:
            default_prompts = [
                "What percentage of students met the learning objectives? What evidence supports this?",
                "Which part of the lesson was most effective? Which needs improvement?",
                "What difficulties did students encounter? How can I address these in the next session?",
                "Were the activities culturally relevant and engaging for the students?",
                "What adjustments should I make for the next lesson?",
            ]
            for p in default_prompts[:num]:
                sections.append(f"- {p}")
        sections.append("")

    return "\n".join(sections)


def generate_lesson_plan_ai(context, template_config, api_key=None, provider="anthropic"):
    """Generate a lesson plan using AI API (Anthropic Claude or OpenAI)."""
    prompt = build_ai_prompt(context, template_config)

    if provider == "anthropic":
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        except ImportError:
            return "ERROR: anthropic package not installed. Run: pip install anthropic"
        except Exception as e:
            return f"ERROR: AI generation failed: {str(e)}"

    elif provider == "openai":
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an expert Philippine DepEd curriculum specialist."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4096
            )
            return response.choices[0].message.content
        except ImportError:
            return "ERROR: openai package not installed. Run: pip install openai"
        except Exception as e:
            return f"ERROR: AI generation failed: {str(e)}"

    return "ERROR: Unknown AI provider."


## ============================================================
## AUTHENTIC ASSESSMENT GENERATOR
## ============================================================

ASSESSMENT_TYPES = {
    "performance_task": {
        "label": "Performance Task",
        "description": "Real-world task where students demonstrate competency through doing",
    },
    "rubric": {
        "label": "Scoring Rubric",
        "description": "Criteria-based scoring guide (4-point scale)",
    },
    "portfolio": {
        "label": "Portfolio Assessment",
        "description": "Collection of student work showing growth over time",
    },
    "project_based": {
        "label": "Project-Based Assessment",
        "description": "Extended project applying knowledge to real-world problems",
    },
    "product_based": {
        "label": "Product-Based Assessment",
        "description": "Students create a tangible output (model, poster, presentation)",
    },
    "self_peer": {
        "label": "Self & Peer Assessment",
        "description": "Reflection and peer evaluation forms",
    },
}


def generate_authentic_assessment_local(context, assessment_config):
    """Generate authentic assessment using template approach."""
    subject = context["subject"]
    grade = context["grade"]
    quarter = context["quarter"]
    domain = context["domain"]
    topic = context["content_topic"]
    perf_std = context.get("performance_standard", "")
    content_std = context.get("content_standard", "")

    selected_types = assessment_config.get("types", ["performance_task", "rubric"])
    custom_context = assessment_config.get("custom_context", "")
    grade_weighting = assessment_config.get("grade_weighting", "")

    competency_texts = []
    for c in context["competencies"]:
        lc = c.get("learning_competency", "")
        bloom = c.get("blooms_level", "")
        competency_texts.append(f"- {lc} *(Bloom's: {bloom})*")

    sections = []

    # Header
    sections.append(f"""## Authentic Assessment Package

| | |
|---|---|
| **Subject** | {subject} |
| **Grade Level** | Grade {grade} |
| **Quarter** | {quarter} |
| **Domain** | {domain} |
| **Content Topic** | {topic} |
| **Content Standard** | {content_std} |
| **Performance Standard** | {perf_std} |

### Target Learning Competencies

{chr(10).join(competency_texts)}
""")

    if custom_context:
        sections.append(f"### Assessment Context\n{custom_context}\n")

    # Performance Task
    if "performance_task" in selected_types:
        sections.append("""## Performance Task

### Task Title
*[Create an engaging, real-world task title]*

### Scenario / Context
You are a ___ (role) who needs to ___ (task) for ___ (audience). Your goal is to ___ (purpose) by applying what you have learned about """ + topic + """.

### Task Description
Students will:
1. Research and gather information about the topic
2. Apply learning competencies to a real-world scenario
3. Create a product/output that demonstrates understanding
4. Present or submit their work for evaluation

### Success Criteria
- Demonstrates understanding of the content standard
- Applies knowledge to a realistic context
- Shows evidence of critical thinking and creativity
- Communicates ideas clearly and effectively

### Timeline
| Phase | Activity | Duration |
|-------|----------|----------|
| Day 1 | Introduction and planning | 30 minutes |
| Day 2 | Research and development | 45 minutes |
| Day 3 | Finalization and presentation | 30 minutes |
""")

    # Rubric
    if "rubric" in selected_types:
        sections.append("""## Scoring Rubric

### 4-Point Assessment Rubric

| Criteria | 4 - Exemplary | 3 - Proficient | 2 - Developing | 1 - Beginning |
|----------|--------------|----------------|-----------------|---------------|
| **Content Knowledge** | Demonstrates thorough and accurate understanding of all concepts | Demonstrates solid understanding of most concepts | Demonstrates partial understanding; some errors present | Demonstrates minimal understanding; significant errors |
| **Application** | Expertly applies learning to real-world context with originality | Correctly applies learning to the given context | Attempts to apply learning but with inconsistencies | Unable to apply learning to the context |
| **Critical Thinking** | Shows deep analysis, evaluation, and creative problem-solving | Shows good analysis and logical reasoning | Shows some analysis but lacks depth | Shows little to no analytical thinking |
| **Communication** | Presents ideas with exceptional clarity, organization, and creativity | Presents ideas clearly and in an organized manner | Presents ideas but lacks clarity or organization | Presentation is unclear and disorganized |
| **Collaboration** *(if applicable)* | Leads and contributes significantly to group success | Actively participates and contributes to the group | Participates minimally in group activities | Does not participate or contribute |

### Scoring Guide
| Score Range | Description | Grade Equivalent |
|-------------|-------------|------------------|
| 18-20 | Exemplary / Outstanding | 90-100% |
| 14-17 | Proficient / Very Satisfactory | 85-89% |
| 10-13 | Developing / Satisfactory | 80-84% |
| 5-9 | Beginning / Needs Improvement | 75-79% |
""")

    # Portfolio
    if "portfolio" in selected_types:
        sections.append(f"""## Portfolio Assessment

### Portfolio Requirements for {topic}

**Purpose:** Document student growth and learning throughout the quarter.

### Required Entries

1. **Baseline Work Sample**
   - Initial activity or pre-assessment output
   - Date and self-reflection note

2. **Process Documentation**
   - Drafts, sketches, or working notes
   - Evidence of revision and improvement

3. **Best Work Sample**
   - Polished final output demonstrating mastery
   - Alignment to performance standard: *{perf_std}*

4. **Self-Reflection Journal**
   - What did I learn?
   - What was challenging and how did I overcome it?
   - How can I apply this to real life?

5. **Peer Feedback Form**
   - Feedback received from at least one classmate
   - Response to feedback showing growth mindset

### Portfolio Assessment Criteria
| Criteria | Weight |
|----------|--------|
| Completeness of entries | 20% |
| Quality and depth of work | 30% |
| Evidence of growth/improvement | 25% |
| Self-reflection quality | 15% |
| Organization and presentation | 10% |
""")

    # Project-Based
    if "project_based" in selected_types:
        sections.append(f"""## Project-Based Assessment

### Project Title
*[Real-world project connecting {topic} to students' community]*

### Driving Question
How can we use our knowledge of {domain} to solve a real problem in our school or community?

### Project Overview
Students will work in groups of 3-4 to investigate a real-world issue related to {topic} and develop a solution or product.

### Project Phases

**Phase 1: Launch & Inquiry (Day 1-2)**
- Present the driving question
- Brainstorm problems related to {topic} in local context
- Form groups and select a focus area

**Phase 2: Research & Plan (Day 3-4)**
- Gather information from textbooks, interviews, and observation
- Create a project plan with roles and timeline
- Teacher checkpoint: Review plans and provide feedback

**Phase 3: Create & Develop (Day 5-7)**
- Develop the solution/product
- Document the process with photos or journal entries
- Apply learning competencies to the project

**Phase 4: Present & Reflect (Day 8)**
- Group presentations to the class (5-7 minutes each)
- Q&A from classmates and teacher
- Individual reflection on learning and teamwork

### Deliverables
1. Project plan document
2. Final product or presentation
3. Process journal/documentation
4. Individual reflection paper

### Assessment Criteria
| Criteria | Points |
|----------|--------|
| Research quality and relevance | 20 |
| Application of learning competencies | 25 |
| Creativity and originality | 15 |
| Presentation and communication | 20 |
| Teamwork and collaboration | 10 |
| Reflection depth | 10 |
| **Total** | **100** |
""")

    # Product-Based
    if "product_based" in selected_types:
        sections.append(f"""## Product-Based Assessment

### Product Options
Students may choose ONE of the following to demonstrate their learning about {topic}:

| Product | Description | Key Requirements |
|---------|-------------|-----------------|
| **Infographic/Poster** | Visual representation of key concepts | Must include at least 5 key facts, visuals, and references |
| **Model/Diorama** | 3D representation of concepts | Must be labeled, accurate, and accompanied by explanation |
| **Multimedia Presentation** | Digital slideshow or video | 5-8 slides/2-3 minutes, must cover all learning competencies |
| **Comic Strip/Storyboard** | Narrative visual explaining concepts | At least 6 panels, dialogue must demonstrate understanding |
| **Song/Jingle/Poem** | Creative expression of learning | Must incorporate key vocabulary and concepts accurately |

### Product Assessment Checklist
- [ ] Product addresses the learning competencies
- [ ] Content is accurate and based on the curriculum
- [ ] Creativity and originality are evident
- [ ] Product is neat, organized, and presentable
- [ ] Student can explain their product and answer questions about it
""")

    # Self & Peer Assessment
    if "self_peer" in selected_types:
        sections.append(f"""## Self & Peer Assessment

### Student Self-Assessment Form

**Name:** _______________ **Date:** _______________
**Topic:** {topic}

Rate yourself (4=Strongly Agree, 3=Agree, 2=Disagree, 1=Strongly Disagree):

| Statement | 4 | 3 | 2 | 1 |
|-----------|---|---|---|---|
| I understand the key concepts of this lesson | | | | |
| I can explain the topic to a classmate | | | | |
| I participated actively in class activities | | | | |
| I completed all required tasks on time | | | | |
| I can apply what I learned to real-life situations | | | | |

**What I learned best:** _______________________________________________

**What I still need to improve:** ________________________________________

**My goal for next lesson:** _____________________________________________

---

### Peer Evaluation Form

**Evaluator:** _______________ **Person Evaluated:** _______________

| Criteria | Excellent (4) | Good (3) | Fair (2) | Needs Work (1) |
|----------|:---:|:---:|:---:|:---:|
| Contributed ideas to the group | | | | |
| Listened to others respectfully | | | | |
| Completed assigned tasks | | | | |
| Helped others when needed | | | | |
| Showed positive attitude | | | | |

**Best contribution:** ________________________________________________

**Suggestion for improvement:** ________________________________________
""")

    if grade_weighting:
        sections.append(f"## Grade Weighting\n{grade_weighting}\n")

    return "\n".join(sections)


def build_assessment_ai_prompt(context, assessment_config):
    """Build AI prompt for authentic assessment generation."""
    subject = context["subject"]
    grade = context["grade"]
    quarter = context["quarter"]
    domain = context["domain"]
    topic = context["content_topic"]
    perf_std = context.get("performance_standard", "")
    content_std = context.get("content_standard", "")

    competency_texts = "\n".join(
        f"- [{c.get('lc_id', '')}] {c.get('learning_competency', '')} (Bloom's: {c.get('blooms_level', '')})"
        for c in context["competencies"]
    )

    selected_types = assessment_config.get("types", ["performance_task", "rubric"])
    custom_context = assessment_config.get("custom_context", "")
    type_labels = [ASSESSMENT_TYPES[t]["label"] for t in selected_types if t in ASSESSMENT_TYPES]

    prompt = f"""You are an expert Philippine DepEd assessment specialist. Generate a DETAILED authentic assessment package for the following curriculum data.

=== CURRICULUM DATA ===
Subject: {subject}
Grade Level: Grade {grade}
Quarter: {quarter}
Domain: {domain}
Content Topic: {topic}
Content Standard: {content_std}
Performance Standard: {perf_std}

Learning Competencies:
{competency_texts}
=== END CURRICULUM DATA ===

{f"Additional Context: {custom_context}" if custom_context else ""}

Generate the following assessment types: {', '.join(type_labels)}

For EACH assessment type, provide:
- Complete, ready-to-use assessment materials
- Clear instructions for both teacher and students
- Specific criteria aligned to the learning competencies and performance standards
- Scoring guides with point values
- Real-world, culturally relevant contexts for Filipino students

For Performance Tasks: Include a GRASPS scenario (Goal, Role, Audience, Situation, Product, Standards)
For Rubrics: Use a 4-point scale (Exemplary, Proficient, Developing, Beginning) with specific descriptors
For Portfolios: Include required entries, reflection prompts, and criteria
For Projects: Include phases, timeline, deliverables, and assessment criteria
For Products: Include multiple product options with checklists
For Self/Peer Assessment: Include ready-to-print forms with rating scales

Use markdown formatting. Make everything specific to {topic} for Grade {grade} students.
All content must align with Philippine DepEd MATATAG curriculum standards.
"""
    return prompt


def generate_authentic_assessment_ai(context, assessment_config, api_key=None, provider="anthropic"):
    """Generate authentic assessment using AI."""
    prompt = build_assessment_ai_prompt(context, assessment_config)

    if provider == "anthropic":
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        except ImportError:
            return "ERROR: anthropic package not installed."
        except Exception as e:
            return f"ERROR: AI generation failed: {str(e)}"
    elif provider == "openai":
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an expert Philippine DepEd assessment specialist."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4096
            )
            return response.choices[0].message.content
        except ImportError:
            return "ERROR: openai package not installed."
        except Exception as e:
            return f"ERROR: AI generation failed: {str(e)}"
    return "ERROR: Unknown AI provider."


def generate_assessment(subject_id, competency_ids, assessment_config,
                        use_ai=False, api_key=None, ai_provider="anthropic"):
    """Main entry point: generate authentic assessment."""
    context = _gather_curriculum_context(subject_id, competency_ids)
    if not context:
        return None, "No competencies found for the given IDs."

    if use_ai and api_key:
        content = generate_authentic_assessment_ai(context, assessment_config, api_key, ai_provider)
        if content.startswith("ERROR:"):
            ai_error = content
            content = generate_authentic_assessment_local(context, assessment_config)
            content = (
                "> **Note:** AI generation failed — showing template-based output instead.\n"
                f"> *Reason: {ai_error.replace('ERROR: ', '')}*\n\n"
            ) + content
    else:
        content = generate_authentic_assessment_local(context, assessment_config)

    return content, None


## ============================================================
## QUIZ GENERATOR
## ============================================================

QUIZ_TYPES = {
    "multiple_choice": {"label": "Multiple Choice", "default_count": 5},
    "true_false": {"label": "True or False", "default_count": 5},
    "identification": {"label": "Identification", "default_count": 5},
    "matching": {"label": "Matching Type", "default_count": 5},
}


def generate_quiz_local(context, quiz_config):
    """Generate a quiz using template approach (no AI)."""
    subject = context["subject"]
    grade = context["grade"]
    quarter = context["quarter"]
    topic = context["content_topic"]
    domain = context["domain"]
    content_std = context.get("content_standard", "")
    perf_std = context.get("performance_standard", "")

    selected_types = quiz_config.get("types", ["multiple_choice", "true_false"])
    num_questions = quiz_config.get("num_questions", 5)

    competency_texts = []
    for c in context["competencies"]:
        lc = c.get("learning_competency", "")
        bloom = c.get("blooms_level", "")
        competency_texts.append(f"- {lc} *(Bloom's: {bloom})*")

    sections = []

    # Header
    sections.append(f"""## Quiz / Assessment

| | |
|---|---|
| **Subject** | {subject} |
| **Grade Level** | Grade {grade} |
| **Quarter** | {quarter} |
| **Domain** | {domain} |
| **Content Topic** | {topic} |
| **Content Standard** | {content_std} |
| **Performance Standard** | {perf_std} |

### Target Learning Competencies

{chr(10).join(competency_texts)}
""")

    answer_key = []

    # Multiple Choice
    if "multiple_choice" in selected_types:
        sections.append(f"## I. Multiple Choice ({num_questions} items)\n")
        sections.append("**Directions:** Choose the letter of the best answer.\n")
        for i in range(1, num_questions + 1):
            sections.append(f"{i}. [Question about {topic} aligned to the learning competency]")
            sections.append(f"   - A. [Option A]")
            sections.append(f"   - B. [Option B]")
            sections.append(f"   - C. [Option C]")
            sections.append(f"   - D. [Option D]\n")
            answer_key.append(f"{i}. [A/B/C/D]")
        sections.append("")

    # True or False
    if "true_false" in selected_types:
        offset = len(answer_key)
        sections.append(f"## II. True or False ({num_questions} items)\n")
        sections.append("**Directions:** Write TRUE if the statement is correct, FALSE if it is not.\n")
        for i in range(1, num_questions + 1):
            n = offset + i
            sections.append(f"{n}. [Statement about {topic} that is either true or false]\n")
            answer_key.append(f"{n}. [TRUE/FALSE]")
        sections.append("")

    # Identification
    if "identification" in selected_types:
        offset = len(answer_key)
        sections.append(f"## III. Identification ({num_questions} items)\n")
        sections.append("**Directions:** Write the correct answer on the blank.\n")
        for i in range(1, num_questions + 1):
            n = offset + i
            sections.append(f"{n}. __________________ [Clue/description related to {topic}]\n")
            answer_key.append(f"{n}. [Answer]")
        sections.append("")

    # Matching Type
    if "matching" in selected_types:
        offset = len(answer_key)
        sections.append(f"## IV. Matching Type ({num_questions} items)\n")
        sections.append("**Directions:** Match Column A with Column B. Write the letter of the correct answer.\n")
        sections.append("| Column A | Column B |")
        sections.append("|----------|----------|")
        letters = "ABCDEFGHIJ"
        for i in range(num_questions):
            n = offset + i + 1
            letter = letters[i] if i < len(letters) else str(i + 1)
            sections.append(f"| {n}. [Term/concept from {topic}] | {letter}. [Definition/description] |")
            answer_key.append(f"{n}. [{letter}]")
        sections.append("")

    # Answer Key
    sections.append("---\n")
    sections.append("## Answer Key\n")
    for a in answer_key:
        sections.append(a)
    sections.append("")

    return "\n".join(sections)


def build_quiz_ai_prompt(context, quiz_config):
    """Build AI prompt for quiz generation."""
    subject = context["subject"]
    grade = context["grade"]
    quarter = context["quarter"]
    domain = context["domain"]
    topic = context["content_topic"]
    content_std = context.get("content_standard", "")
    perf_std = context.get("performance_standard", "")

    competency_texts = "\n".join(
        f"- [{c.get('lc_id', '')}] {c.get('learning_competency', '')} (Bloom's: {c.get('blooms_level', '')})"
        for c in context["competencies"]
    )

    selected_types = quiz_config.get("types", ["multiple_choice", "true_false"])
    num_questions = quiz_config.get("num_questions", 5)
    type_labels = [QUIZ_TYPES[t]["label"] for t in selected_types if t in QUIZ_TYPES]

    type_instructions = []
    item_num = 1
    for t in selected_types:
        if t == "multiple_choice":
            type_instructions.append(
                f"## I. Multiple Choice ({num_questions} items, starting at #{item_num})\n"
                f"- Provide a question stem + 4 options (A-D)\n"
                f"- Questions should align to the Bloom's taxonomy level of the competencies\n"
                f"- Include plausible distractors"
            )
            item_num += num_questions
        elif t == "true_false":
            type_instructions.append(
                f"## II. True or False ({num_questions} items, starting at #{item_num})\n"
                f"- Write clear, unambiguous statements\n"
                f"- Mix true and false answers"
            )
            item_num += num_questions
        elif t == "identification":
            type_instructions.append(
                f"## III. Identification ({num_questions} items, starting at #{item_num})\n"
                f"- Provide a clue/description, student writes the answer\n"
                f"- Use underscores for the blank"
            )
            item_num += num_questions
        elif t == "matching":
            type_instructions.append(
                f"## IV. Matching Type ({num_questions} items, starting at #{item_num})\n"
                f"- Create Column A (terms) and Column B (definitions) as a table\n"
                f"- Shuffle Column B so items don't match directly"
            )
            item_num += num_questions

    prompt = f"""You are an expert Philippine DepEd quiz maker. Generate a READY-TO-USE quiz based on the MATATAG curriculum data below.

=== CURRICULUM DATA ===
Subject: {subject}
Grade Level: Grade {grade}
Quarter: {quarter}
Domain: {domain}
Content Topic: {topic}
Content Standard: {content_std}
Performance Standard: {perf_std}

Learning Competencies:
{competency_texts}
=== END CURRICULUM DATA ===

Generate a quiz with the following sections:

{chr(10).join(type_instructions)}

IMPORTANT:
- Start with a header table showing Subject, Grade, Quarter, Topic
- Number items continuously across all sections
- All questions must directly assess the learning competencies listed above
- Match the Bloom's taxonomy level (if Remember, ask recall questions; if Analyze, ask analysis questions)
- Make questions specific to {topic} for Grade {grade} Filipino students
- Use clear, age-appropriate language
- At the END, include a complete "## Answer Key" section with all correct answers
- Use markdown formatting throughout
"""
    return prompt


def generate_quiz_ai(context, quiz_config, api_key=None, provider="anthropic"):
    """Generate quiz using AI."""
    prompt = build_quiz_ai_prompt(context, quiz_config)

    if provider == "anthropic":
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        except ImportError:
            return "ERROR: anthropic package not installed."
        except Exception as e:
            return f"ERROR: AI generation failed: {str(e)}"
    elif provider == "openai":
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an expert Philippine DepEd quiz maker."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4096
            )
            return response.choices[0].message.content
        except ImportError:
            return "ERROR: openai package not installed."
        except Exception as e:
            return f"ERROR: AI generation failed: {str(e)}"
    return "ERROR: Unknown AI provider."


def generate_quiz(subject_id, competency_ids, quiz_config,
                  use_ai=False, api_key=None, ai_provider="anthropic"):
    """Main entry point: generate a quiz."""
    context = _gather_curriculum_context(subject_id, competency_ids)
    if not context:
        return None, "No competencies found for the given IDs."

    if use_ai and api_key:
        content = generate_quiz_ai(context, quiz_config, api_key, ai_provider)
        if content.startswith("ERROR:"):
            ai_error = content
            content = generate_quiz_local(context, quiz_config)
            content = (
                "> **Note:** AI generation failed — showing template-based quiz instead.\n"
                f"> *Reason: {ai_error.replace('ERROR: ', '')}*\n\n"
            ) + content
    else:
        content = generate_quiz_local(context, quiz_config)

    return content, None


def build_topic_ai_prompt(topic_context, template_config):
    """Build the AI prompt for topic-based lesson plan generation."""
    topic = topic_context.get("topic", "")
    subject = topic_context.get("subject_name", "")
    grade = topic_context.get("grade", "")
    competencies_text = topic_context.get("competencies_text", "")

    enabled_sections = {k: v for k, v in template_config.items() if v.get("enabled", True)}
    proc_config = template_config.get("lesson_procedure", {})
    proc_fields = proc_config.get("customizable_fields", {})
    model_key = proc_fields.get("model", "5e")
    model_info = PROCEDURE_MODELS.get(model_key, PROCEDURE_MODELS["5e"])

    prompt = f"""You are an expert curriculum specialist and instructional designer.
Generate a detailed, classroom-ready lesson plan for the topic below.
Every activity, question, and assessment must directly relate to the specified topic.

=== TOPIC DATA ===
Topic: {topic}
Subject / Learning Area: {subject}
Grade Level: {grade}
{f"Specific Competencies / Objectives:{chr(10)}{competencies_text}" if competencies_text else ""}
=== END TOPIC DATA ===

Generate a COMPLETE lesson plan with the following sections (generate ONLY the sections listed below):

"""

    section_instructions = []

    if "title_info" in enabled_sections:
        fields = enabled_sections["title_info"].get("customizable_fields", {})
        time = fields.get("time_allotment", "60 minutes")
        custom_title = fields.get("custom_title", "")
        title_note = f' Use this title: "{custom_title}"' if custom_title else f" Create an engaging, descriptive title about {topic}."
        section_instructions.append(
            f"## 1. LESSON PLAN HEADER\n"
            f"- Title:{title_note}\n"
            f"- Subject: {subject}\n"
            f"- Grade Level: {grade}\n"
            f"- Time Allotment: {time}\n"
            f"- Topic: {topic}"
        )

    if "twenty_first_century_skills" in enabled_sections:
        section_instructions.append(
            f"## 2. 21ST CENTURY SKILLS FOCUS\n"
            f"Select 3-4 relevant 21st century skills for this lesson on {topic}.\n"
            f"For each skill, briefly explain HOW the lesson develops it."
        )

    if "learning_objectives" in enabled_sections:
        fields = enabled_sections["learning_objectives"].get("customizable_fields", {})
        num = fields.get("num_objectives", 3)
        custom = fields.get("custom_objectives", [])
        obj_note = f" Include these objectives: {'; '.join(custom)}. Add more as needed." if custom else ""
        section_instructions.append(
            f"## 3. LEARNING OBJECTIVES (SWBAT)\n"
            f"Write {num} clear, measurable objectives using 'Students Will Be Able To...' format.\n"
            f"Align with appropriate Bloom's taxonomy levels for {subject} at {grade}.{obj_note}\n"
            f"Each objective must be specific and assessable."
        )

    if "materials_technology" in enabled_sections:
        fields = enabled_sections["materials_technology"].get("customizable_fields", {})
        include_digital = fields.get("include_digital_tools", True)
        include_trad = fields.get("include_traditional", True)
        custom_mats = fields.get("custom_materials", [])
        mat_parts = []
        if include_trad:
            mat_parts.append("traditional classroom materials")
        if include_digital:
            mat_parts.append("digital tools and technology resources")
        if custom_mats:
            mat_parts.append(f"Include these specific items: {', '.join(custom_mats)}")
        section_instructions.append(
            f"## 4. MATERIALS / TECHNOLOGY\n"
            f"List all needed {' and '.join(mat_parts)} for teaching {topic}.\n"
            f"Be specific and consider resources available in typical classrooms."
        )

    if "prior_knowledge" in enabled_sections:
        fields = enabled_sections["prior_knowledge"].get("customizable_fields", {})
        custom_prereqs = fields.get("custom_prerequisites", [])
        prereq_note = f" Include: {'; '.join(custom_prereqs)}." if custom_prereqs else ""
        section_instructions.append(
            f"## 5. PRIOR KNOWLEDGE / PREREQUISITES\n"
            f"List what students should already know before learning {topic}.{prereq_note}"
        )

    if "lesson_procedure" in enabled_sections:
        include_timing = proc_fields.get("include_timing", True)
        timing_note = " Include suggested time allocation for each phase." if include_timing else ""
        custom_activities = proc_fields.get("custom_activities", {})
        activity_note = ""
        if custom_activities:
            parts = [f"  - {phase}: {act}" for phase, act in custom_activities.items()]
            activity_note = "\nInclude these specific activities:\n" + "\n".join(parts)
        section_instructions.append(
            f"## 6. LESSON PROCEDURE ({model_info['label']})\n"
            f"Use the {model_info['label']} instructional model.\n"
            f"For each phase ({', '.join(model_info['phases'])}), provide:\n"
            f"- Clear teacher actions and instructions\n"
            f"- Student activities and expected responses\n"
            f"- Key questions to ask\n"
            f"- Transition cues{timing_note}{activity_note}"
        )

    if "differentiation" in enabled_sections:
        fields = enabled_sections["differentiation"].get("customizable_fields", {})
        diff_parts = []
        if fields.get("include_struggling", True):
            diff_parts.append("Struggling Learners: specific scaffolding strategies, simplified tasks, visual aids")
        if fields.get("include_advanced", True):
            diff_parts.append("Advanced Learners: extension activities, higher-order thinking challenges")
        if fields.get("include_ell", True):
            diff_parts.append("English Language Learners: vocabulary support, visual/contextual clues")
        custom_strats = fields.get("custom_strategies", [])
        if custom_strats:
            diff_parts.append(f"Additional strategies: {'; '.join(custom_strats)}")
        section_instructions.append(
            f"## 7. DIFFERENTIATION / SCAFFOLDING\n"
            f"Provide specific strategies for:\n" +
            "\n".join(f"- {p}" for p in diff_parts)
        )

    if "assessment" in enabled_sections:
        fields = enabled_sections["assessment"].get("customizable_fields", {})
        assess_parts = []
        if fields.get("include_formative", True):
            assess_parts.append("Formative Assessment: ongoing checks for understanding during the lesson")
        if fields.get("include_summative", True):
            assess_parts.append("Summative Assessment: end-of-lesson evaluation")
        custom_assess = fields.get("custom_assessments", [])
        if custom_assess:
            assess_parts.append(f"Include these specific assessments: {'; '.join(custom_assess)}")
        section_instructions.append(
            f"## 8. ASSESSMENT\n"
            f"Provide detailed assessment strategies:\n" +
            "\n".join(f"- {p}" for p in assess_parts) +
            f"\nEnsure assessments directly measure the learning objectives."
        )

    if "reflection" in enabled_sections:
        fields = enabled_sections["reflection"].get("customizable_fields", {})
        num_prompts = fields.get("num_prompts", 3)
        custom_prompts = fields.get("custom_prompts", [])
        reflection_note = f" Include these reflection prompts: {'; '.join(custom_prompts)}." if custom_prompts else ""
        section_instructions.append(
            f"## 9. TEACHER REFLECTION\n"
            f"Provide {num_prompts} reflection prompts for the teacher.{reflection_note}"
        )

    prompt += "\n\n".join(section_instructions)
    prompt += f"""

IMPORTANT GUIDELINES:
- All content must be appropriate for {subject} at {grade}
- Activities should be engaging and practical
- Use markdown formatting for clear structure
- Be specific and practical — a teacher should be able to use this plan directly
"""
    return prompt


def _generate_topic_local(topic_context, template_config):
    """Generate a topic-based lesson plan using template approach (no AI)."""
    topic = topic_context.get("topic", "Custom Topic")
    subject = topic_context.get("subject_name", "")
    grade = topic_context.get("grade", "")

    enabled = {k: v for k, v in template_config.items() if v.get("enabled", True)}
    proc_fields = template_config.get("lesson_procedure", {}).get("customizable_fields", {})
    model_key = proc_fields.get("model", "5e")
    model_info = PROCEDURE_MODELS.get(model_key, PROCEDURE_MODELS["5e"])

    sections = []

    if "title_info" in enabled:
        fields = enabled["title_info"].get("customizable_fields", {})
        time_allot = fields.get("time_allotment", "60 minutes")
        custom_title = fields.get("custom_title", "")
        title = custom_title if custom_title else topic
        sections.append(f"""## Lesson Plan

| | |
|---|---|
| **Title** | {title} |
| **Subject** | {subject} |
| **Grade Level** | {grade} |
| **Topic** | {topic} |
| **Time Allotment** | {time_allot} |
""")

    if "twenty_first_century_skills" in enabled:
        sections.append("## 21st Century Skills Focus\n")
        sections.append("- **Critical Thinking**: Students analyze and evaluate information related to the topic")
        sections.append("- **Communication**: Students present and discuss their understanding")
        sections.append("- **Collaboration**: Students work together in group activities")
        sections.append("")

    if "learning_objectives" in enabled:
        fields = enabled["learning_objectives"].get("customizable_fields", {})
        custom = fields.get("custom_objectives", [])
        num = fields.get("num_objectives", 3)
        sections.append("## Learning Objectives (SWBAT)\n")
        sections.append("At the end of this lesson, students will be able to:\n")
        if custom:
            for i, obj in enumerate(custom, 1):
                sections.append(f"{i}. {obj}")
        else:
            sections.append(f"1. Identify and describe key concepts related to {topic}")
            sections.append(f"2. Explain the importance and application of {topic}")
            if num >= 3:
                sections.append(f"3. Apply knowledge of {topic} to solve problems or create outputs")
            if num >= 4:
                sections.append(f"4. Evaluate and analyze examples related to {topic}")
        sections.append("")

    if "materials_technology" in enabled:
        fields = enabled["materials_technology"].get("customizable_fields", {})
        custom_mats = fields.get("custom_materials", [])
        sections.append("## Materials / Technology\n")
        if custom_mats:
            for m in custom_mats:
                sections.append(f"- {m}")
        else:
            sections.append("- Textbook / reference materials")
            sections.append("- Manila paper, markers, and writing materials")
            sections.append("- Visual aids related to the topic")
            if fields.get("include_digital_tools", True):
                sections.append("- Laptop/projector for multimedia presentation (if available)")
        sections.append("")

    if "prior_knowledge" in enabled:
        fields = enabled["prior_knowledge"].get("customizable_fields", {})
        custom_prereqs = fields.get("custom_prerequisites", [])
        sections.append("## Prior Knowledge / Prerequisites\n")
        sections.append("Students should already be able to:\n")
        if custom_prereqs:
            for p in custom_prereqs:
                sections.append(f"- {p}")
        else:
            sections.append(f"- Demonstrate basic understanding of {subject}")
            sections.append(f"- Apply foundational concepts relevant to {topic}")
        sections.append("")

    if "lesson_procedure" in enabled:
        include_timing = proc_fields.get("include_timing", True)
        custom_activities = proc_fields.get("custom_activities", {})
        sections.append(f"## Lesson Procedure ({model_info['label']})\n")
        for phase in model_info["phases"]:
            sections.append(f"### {phase}")
            if include_timing:
                sections.append(f"*Suggested time: ___ minutes*\n")
            if phase in custom_activities:
                sections.append(f"{custom_activities[phase]}\n")
            else:
                sections.append(f"**Teacher Activity:**\n- [Describe teacher actions for {phase} phase related to {topic}]\n")
                sections.append(f"**Student Activity:**\n- [Describe student activities for {phase} phase]\n")
                sections.append(f"**Key Questions:**\n- [List guiding questions about {topic}]\n")
        sections.append("")

    if "differentiation" in enabled:
        fields = enabled["differentiation"].get("customizable_fields", {})
        sections.append("## Differentiation / Scaffolding\n")
        if fields.get("include_struggling", True):
            sections.append("### Struggling Learners")
            sections.append("- Provide step-by-step visual guides")
            sections.append("- Use peer tutoring and collaborative grouping")
            sections.append("- Simplify tasks while maintaining learning objectives\n")
        if fields.get("include_advanced", True):
            sections.append("### Advanced Learners")
            sections.append("- Provide extension activities with higher-order thinking")
            sections.append("- Offer open-ended problems for deeper exploration\n")
        if fields.get("include_ell", True):
            sections.append("### English Language Learners")
            sections.append("- Use bilingual vocabulary cards")
            sections.append("- Provide visual and contextual clues\n")
        sections.append("")

    if "assessment" in enabled:
        fields = enabled["assessment"].get("customizable_fields", {})
        sections.append("## Assessment\n")
        if fields.get("include_formative", True):
            sections.append("### Formative Assessment (During Lesson)")
            sections.append("- Observation of student participation")
            sections.append("- Exit ticket / quick check questions\n")
        if fields.get("include_summative", True):
            sections.append("### Summative Assessment")
            sections.append(f"- Written quiz or activity sheet on {topic}")
            sections.append("- Portfolio entry or project output\n")
        sections.append("")

    if "reflection" in enabled:
        fields = enabled["reflection"].get("customizable_fields", {})
        num = fields.get("num_prompts", 3)
        custom = fields.get("custom_prompts", [])
        sections.append("## Teacher Reflection\n")
        if custom:
            for p in custom:
                sections.append(f"- {p}")
        else:
            default_prompts = [
                "What percentage of students met the learning objectives?",
                "Which part of the lesson was most effective?",
                "What adjustments should I make for the next lesson?",
            ]
            for p in default_prompts[:num]:
                sections.append(f"- {p}")
        sections.append("")

    return "\n".join(sections)


def generate_lesson_plan_topic(topic_context, template_config, use_ai=False,
                                api_key=None, ai_provider="anthropic"):
    """Main entry point: generate a topic-based lesson plan."""
    topic = topic_context.get("topic", "").strip()
    if not topic:
        return None, "Topic is required."

    if use_ai and api_key:
        prompt = build_topic_ai_prompt(topic_context, template_config)
        if ai_provider == "anthropic":
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                message = client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}]
                )
                content = message.content[0].text
            except ImportError:
                content = "ERROR: anthropic package not installed."
            except Exception as e:
                content = f"ERROR: AI generation failed: {str(e)}"
        elif ai_provider == "openai":
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are an expert curriculum specialist and instructional designer."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=4096
                )
                content = response.choices[0].message.content
            except ImportError:
                content = "ERROR: openai package not installed."
            except Exception as e:
                content = f"ERROR: AI generation failed: {str(e)}"
        else:
            content = "ERROR: Unknown AI provider."

        if content.startswith("ERROR:"):
            ai_error = content
            content = _generate_topic_local(topic_context, template_config)
            content = (
                "> **Note:** AI generation failed — showing template-based output instead.\n"
                f"> *Reason: {ai_error.replace('ERROR: ', '')}*\n\n"
            ) + content
    else:
        content = _generate_topic_local(topic_context, template_config)

    return content, None


def build_assessment_topic_ai_prompt(topic_context, assessment_config):
    """Build AI prompt for topic-based authentic assessment generation."""
    topic = topic_context.get("topic", "")
    subject = topic_context.get("subject_name", "")
    grade = topic_context.get("grade", "")
    competencies_text = topic_context.get("competencies_text", "")

    selected_types = assessment_config.get("types", ["performance_task", "rubric"])
    custom_context = assessment_config.get("custom_context", "")
    type_labels = [ASSESSMENT_TYPES[t]["label"] for t in selected_types if t in ASSESSMENT_TYPES]

    comp_section = f"\nLearning Objectives / Competencies:\n{competencies_text}" if competencies_text else ""

    prompt = f"""You are an expert assessment specialist. Generate a DETAILED authentic assessment package for the following lesson topic.

=== TOPIC DATA ===
Topic: {topic}
Subject / Learning Area: {subject}
Grade Level: {grade}{comp_section}
=== END TOPIC DATA ===

{f"Additional Context: {custom_context}" if custom_context else ""}

Generate the following assessment types: {', '.join(type_labels)}

For EACH assessment type, provide:
- Complete, ready-to-use assessment materials
- Clear instructions for both teacher and students
- Specific criteria aligned to the learning objectives
- Scoring guides with point values
- Real-world, engaging contexts appropriate for {grade} students

For Performance Tasks: Include a GRASPS scenario (Goal, Role, Audience, Situation, Product, Standards)
For Rubrics: Use a 4-point scale (Exemplary, Proficient, Developing, Beginning) with specific descriptors
For Portfolios: Include required entries, reflection prompts, and criteria
For Projects: Include phases, timeline, deliverables, and assessment criteria
For Products: Include multiple product options with checklists
For Self/Peer Assessment: Include ready-to-print forms with rating scales

Use markdown formatting. Make everything specific to {topic} for {grade} students.
"""
    return prompt


def generate_assessment_topic(topic_context, assessment_config,
                               use_ai=False, api_key=None, ai_provider="anthropic"):
    """Generate authentic assessment for a topic-based lesson plan."""
    topic = topic_context.get("topic", "").strip()
    if not topic:
        return None, "Topic is required."

    local_context = {
        "subject": topic_context.get("subject_name", ""),
        "grade": topic_context.get("grade", ""),
        "quarter": "",
        "domain": "",
        "content_topic": topic,
        "content_standard": "",
        "performance_standard": "",
        "competencies": [],
    }

    if use_ai and api_key:
        prompt = build_assessment_topic_ai_prompt(topic_context, assessment_config)
        if ai_provider == "anthropic":
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                message = client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}]
                )
                content = message.content[0].text
            except ImportError:
                content = "ERROR: anthropic package not installed."
            except Exception as e:
                content = f"ERROR: AI generation failed: {str(e)}"
        elif ai_provider == "openai":
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are an expert assessment specialist."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=4096
                )
                content = response.choices[0].message.content
            except ImportError:
                content = "ERROR: openai package not installed."
            except Exception as e:
                content = f"ERROR: AI generation failed: {str(e)}"
        else:
            content = "ERROR: Unknown AI provider."

        if content.startswith("ERROR:"):
            ai_error = content
            content = generate_authentic_assessment_local(local_context, assessment_config)
            content = (
                "> **Note:** AI generation failed — showing template-based output instead.\n"
                f"> *Reason: {ai_error.replace('ERROR: ', '')}*\n\n"
            ) + content
    else:
        content = generate_authentic_assessment_local(local_context, assessment_config)

    return content, None


def build_quiz_topic_ai_prompt(topic_context, quiz_config):
    """Build AI prompt for topic-based quiz generation (standalone LMS activity)."""
    topic = topic_context.get("topic", "")
    subject = topic_context.get("subject_name", "")
    grade = topic_context.get("grade", "")
    competencies_text = topic_context.get("competencies_text", "")

    selected_types = quiz_config.get("types", ["multiple_choice", "true_false"])
    num_questions = quiz_config.get("num_questions", 5)

    comp_section = f"\nLearning Objectives / Competencies:\n{competencies_text}" if competencies_text else ""

    type_instructions = []
    item_num = 1
    for t in selected_types:
        if t == "multiple_choice":
            type_instructions.append(
                f"## I. Multiple Choice ({num_questions} items, starting at #{item_num})\n"
                f"- Provide a question stem + 4 options (A-D)\n"
                f"- Include plausible distractors"
            )
            item_num += num_questions
        elif t == "true_false":
            type_instructions.append(
                f"## II. True or False ({num_questions} items, starting at #{item_num})\n"
                f"- Write clear, unambiguous statements\n"
                f"- Mix true and false answers"
            )
            item_num += num_questions
        elif t == "identification":
            type_instructions.append(
                f"## III. Identification ({num_questions} items, starting at #{item_num})\n"
                f"- Provide a clue/description, student writes the answer\n"
                f"- Use underscores for the blank"
            )
            item_num += num_questions
        elif t == "matching":
            type_instructions.append(
                f"## IV. Matching Type ({num_questions} items, starting at #{item_num})\n"
                f"- Create Column A (terms) and Column B (definitions) as a table\n"
                f"- Shuffle Column B so items don't match directly"
            )
            item_num += num_questions

    prompt = f"""You are an expert quiz maker. Generate a READY-TO-USE quiz for the following topic. This quiz is a STANDALONE LMS activity (not part of the lesson plan).

=== TOPIC DATA ===
Topic: {topic}
Subject / Learning Area: {subject}
Grade Level: {grade}{comp_section}
=== END TOPIC DATA ===

Generate a quiz with the following sections:

{chr(10).join(type_instructions)}

IMPORTANT:
- Start with a header table showing Subject, Grade, Topic
- Number items continuously across all sections
- All questions must directly assess knowledge of {topic}
- Use clear, age-appropriate language for {grade} students
- At the END, include a complete "## Answer Key" section with all correct answers
- Use markdown formatting throughout
"""
    return prompt


def generate_quiz_topic(topic_context, quiz_config,
                        use_ai=False, api_key=None, ai_provider="anthropic"):
    """Generate a standalone quiz for a topic-based lesson plan (LMS activity)."""
    topic = topic_context.get("topic", "").strip()
    if not topic:
        return None, "Topic is required."

    local_context = {
        "subject": topic_context.get("subject_name", ""),
        "grade": topic_context.get("grade", ""),
        "quarter": "",
        "domain": "",
        "content_topic": topic,
        "content_standard": "",
        "performance_standard": "",
        "competencies": [],
    }

    if use_ai and api_key:
        prompt = build_quiz_topic_ai_prompt(topic_context, quiz_config)
        if ai_provider == "anthropic":
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                message = client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}]
                )
                content = message.content[0].text
            except ImportError:
                content = "ERROR: anthropic package not installed."
            except Exception as e:
                content = f"ERROR: AI generation failed: {str(e)}"
        elif ai_provider == "openai":
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are an expert quiz maker for LMS activities."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=4096
                )
                content = response.choices[0].message.content
            except ImportError:
                content = "ERROR: openai package not installed."
            except Exception as e:
                content = f"ERROR: AI generation failed: {str(e)}"
        else:
            content = "ERROR: Unknown AI provider."

        if content.startswith("ERROR:"):
            ai_error = content
            content = generate_quiz_local(local_context, quiz_config)
            content = (
                "> **Note:** AI generation failed — showing template-based quiz instead.\n"
                f"> *Reason: {ai_error.replace('ERROR: ', '')}*\n\n"
            ) + content
    else:
        content = generate_quiz_local(local_context, quiz_config)

    return content, None


## ============================================================
## QUIZ FORMAT CONVERTERS (GIFT / QTI 1.2)
## ============================================================

def convert_quiz_to_gift(quiz_md, api_key=None, ai_provider="anthropic"):
    """Convert markdown quiz content to Moodle GIFT format using AI."""
    if not quiz_md or not quiz_md.strip():
        return None, "No quiz content provided."

    prompt = """Convert the following quiz from Markdown format to Moodle GIFT format.

GIFT FORMAT SYNTAX REFERENCE:

// Multiple choice (= correct answer, ~ wrong answers)
::Q1:: What is the capital of the Philippines? {=Manila ~Cebu ~Davao ~Quezon City}

// True/False
::Q2:: The sun is a star. {TRUE}
::Q3:: Water has two oxygen atoms. {FALSE}

// Short answer (identification)
::Q4:: The chemical symbol for water is ___. {=H2O =h2o}

// Matching type
::Q5:: Match each term to its definition. {
=Evaporation -> Liquid changing to gas
=Condensation -> Gas changing to liquid
=Precipitation -> Water falling from clouds
}

CONVERSION RULES:
1. Number questions sequentially: Q1, Q2, Q3, etc.
2. Find correct answers in the "## Answer Key" section of the markdown
3. Copy EXACT question text — do not paraphrase or shorten
4. For multiple choice: first option after { must be =correct, others use ~
5. Skip header tables, direction lines ("**Directions:**"), and section headings
6. Escape special characters: { → \\{ } → \\} ~ → \\~ = → \\= # → \\#
7. Output ONLY valid GIFT text — no markdown, no code fences, no explanation

QUIZ TO CONVERT:
""" + quiz_md

    if ai_provider == "anthropic":
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            content = message.content[0].text
        except ImportError:
            return None, "anthropic package not installed."
        except Exception as e:
            return None, f"AI conversion failed: {str(e)}"
    elif ai_provider == "openai":
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a quiz format converter. Output only the requested format, nothing else."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4096
            )
            content = response.choices[0].message.content
        except ImportError:
            return None, "openai package not installed."
        except Exception as e:
            return None, f"AI conversion failed: {str(e)}"
    else:
        return None, "Unknown AI provider."

    # Strip any code fences the AI may have wrapped around the output
    lines = content.split("\n")
    lines = [l for l in lines if not l.strip().startswith("```")]
    return "\n".join(lines).strip(), None


def convert_quiz_to_qti(title, quiz_md, api_key=None, ai_provider="anthropic"):
    """Convert markdown quiz content to IMS QTI 1.2 XML using AI."""
    if not quiz_md or not quiz_md.strip():
        return None, "No quiz content provided."

    safe_title = title.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

    prompt = f"""Convert the following quiz to IMS QTI 1.2 XML format, compatible with Canvas, Brightspace (D2L), and any QTI 1.2 LMS.

REQUIRED QTI 1.2 STRUCTURE:
<?xml version="1.0" encoding="UTF-8"?>
<questestinterop xmlns="http://www.imsglobal.org/xsd/ims_qtiasiv1p2">
  <assessment title="Quiz Title" ident="assessment1">
    <section ident="root_section">

      <!-- MULTIPLE CHOICE -->
      <item title="Question 1" ident="q1">
        <presentation>
          <material><mattext texttype="text/plain">Question text?</mattext></material>
          <response_lid ident="response1" rcardinality="Single">
            <render_choice>
              <response_label ident="A"><material><mattext>Choice A</mattext></material></response_label>
              <response_label ident="B"><material><mattext>Choice B</mattext></material></response_label>
              <response_label ident="C"><material><mattext>Choice C</mattext></material></response_label>
              <response_label ident="D"><material><mattext>Choice D</mattext></material></response_label>
            </render_choice>
          </response_lid>
        </presentation>
        <resprocessing>
          <outcomes><decvar maxvalue="1" minvalue="0" varname="SCORE" vartype="Decimal"/></outcomes>
          <respcondition continue="No">
            <conditionvar><varequal respident="response1">A</varequal></conditionvar>
            <setvar action="Set" varname="SCORE">1</setvar>
          </respcondition>
        </resprocessing>
      </item>

      <!-- TRUE/FALSE -->
      <item title="Question 2" ident="q2">
        <presentation>
          <material><mattext texttype="text/plain">Statement here.</mattext></material>
          <response_lid ident="response2" rcardinality="Single">
            <render_choice>
              <response_label ident="TRUE"><material><mattext>True</mattext></material></response_label>
              <response_label ident="FALSE"><material><mattext>False</mattext></material></response_label>
            </render_choice>
          </response_lid>
        </presentation>
        <resprocessing>
          <outcomes><decvar maxvalue="1" minvalue="0" varname="SCORE" vartype="Decimal"/></outcomes>
          <respcondition continue="No">
            <conditionvar><varequal respident="response2">TRUE</varequal></conditionvar>
            <setvar action="Set" varname="SCORE">1</setvar>
          </respcondition>
        </resprocessing>
      </item>

      <!-- SHORT ANSWER -->
      <item title="Question 3" ident="q3">
        <presentation>
          <material><mattext texttype="text/plain">Fill in: ___</mattext></material>
          <response_str ident="response3" rcardinality="Single">
            <render_fib><response_label ident="answer"/></render_fib>
          </response_str>
        </presentation>
        <resprocessing>
          <outcomes><decvar maxvalue="1" minvalue="0" varname="SCORE" vartype="Decimal"/></outcomes>
          <respcondition continue="No">
            <conditionvar><varequal respident="response3" case="No">correct answer</varequal></conditionvar>
            <setvar action="Set" varname="SCORE">1</setvar>
          </respcondition>
        </resprocessing>
      </item>

    </section>
  </assessment>
</questestinterop>

CONVERSION RULES:
1. Use the Answer Key section to determine the correct answer for each question
2. Assign ident="q1", "q2", etc. sequentially across all question types
3. Escape XML characters: & → &amp; < → &lt; > → &gt; " → &quot;
4. For matching: convert each match pair to a separate short-answer item
5. Skip header tables, direction lines, and section headings
6. Output ONLY valid XML starting with <?xml — no markdown, no code fences, no commentary

Quiz title: {safe_title}

QUIZ TO CONVERT:
{quiz_md}"""

    if ai_provider == "anthropic":
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            content = message.content[0].text
        except ImportError:
            return None, "anthropic package not installed."
        except Exception as e:
            return None, f"AI conversion failed: {str(e)}"
    elif ai_provider == "openai":
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a quiz format converter. Output only valid XML, nothing else."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4096
            )
            content = response.choices[0].message.content
        except ImportError:
            return None, "openai package not installed."
        except Exception as e:
            return None, f"AI conversion failed: {str(e)}"
    else:
        return None, "Unknown AI provider."

    # Strip code fences
    lines = content.split("\n")
    lines = [l for l in lines if not l.strip().startswith("```")]
    content = "\n".join(lines).strip()
    # Ensure output starts with XML declaration
    if not content.startswith("<?xml"):
        idx = content.find("<?xml")
        if idx > 0:
            content = content[idx:]
    return content, None


def generate_lesson_plan(subject_id, competency_ids, template_config, use_ai=False,
                          api_key=None, ai_provider="anthropic"):
    """Main entry point: generate a lesson plan."""
    context = _gather_curriculum_context(subject_id, competency_ids)
    if not context:
        return None, "No competencies found for the given IDs."

    ai_error = None
    if use_ai and api_key:
        content = generate_lesson_plan_ai(context, template_config, api_key, ai_provider)
        # If AI failed, fall back to template mode
        if content.startswith("ERROR:"):
            ai_error = content
            content = generate_lesson_plan_local(context, template_config)
            content = (
                "> **Note:** AI generation failed — showing template-based output instead.\n"
                f"> *Reason: {ai_error.replace('ERROR: ', '')}*\n\n"
            ) + content
    else:
        content = generate_lesson_plan_local(context, template_config)

    return content, None
