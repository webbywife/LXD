"""
DLSL Content Generator
Generates Canvas-ready content matching the DLSL "26-27 New Canvas Template"
(Integrated Digital Innovative Instruction Office) design:
  - Lesson pages: 6 tabs — Objectives, Introduction, Discussion, Application, Conclusion, Resources
  - Per-module extras: Discussion Prompt + Graded Task Instruction page
"""
import json
import re
from typing import Optional, Tuple

GRADE_LEVEL_LABELS = {
    'gs': 'Grade School',
    'jhs': 'Junior High School',
    'shs': 'Senior High School',
}

LESSON_TABS = ['objectives', 'introduction', 'discussion', 'application', 'conclusion', 'resources']


def _call_claude(prompt: str, api_key: str, max_tokens: int) -> Tuple[Optional[dict], str]:
    if not api_key:
        return None, 'API key is required.'
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=max_tokens,
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


def generate_dlsl_lesson_content(
    course_title: str,
    module_title: str,
    submodule: dict,
    course_context: str,
    grade_level: str,
    api_key: str,
) -> Tuple[Optional[dict], str]:
    """
    Generate the 6-tab DLSL lesson page content for a submodule/lesson.
    Returns (sections_dict, error) where sections_dict has keys:
      objectives, introduction, discussion, application, conclusion, resources
    Each value is an HTML fragment (no html/body/head tags).
    """
    level_label = GRADE_LEVEL_LABELS.get(grade_level, 'Senior High School')
    topics_list = '\n'.join(f'- {t}' for t in submodule.get('topics', []))
    sub_title = submodule['title']

    prompt = f"""You are an instructional designer writing a Canvas lesson page for De La Salle Lipa ({level_label}).

Course: {course_title}
Module: {module_title}
Lesson: {sub_title}
Description: {submodule.get('description', '')}
Key Topics:
{topics_list}

Context: {course_context[:1500]}

Return ONLY a valid JSON object, no markdown fences, in this exact format:
{{
  "objectives": "<p>1-3 SMART learning objectives as an HTML paragraph or list, written for {level_label} students.</p>",
  "introduction": "<p>A short, warm 'Words from the Instructor' style hook (2-4 sentences) introducing the lesson.</p>",
  "discussion": "<p>Guiding discussion content or a short explanation to set up class discussion on the topic (2-4 sentences).</p>",
  "application": "<p>One applied activity or exercise students do to practice the lesson's key skill. Include clear instructions.</p>",
  "conclusion": "<p>A concise wrap-up summarizing the key takeaways (2-3 sentences).</p>",
  "resources": "<p>2-4 real-sounding references (readings, videos, sites) relevant to the topic, as a list.</p>"
}}

Requirements:
- Tone appropriate for {level_label} students
- All HTML: valid fragments only, no html/body/head/style tags, use only p/ul/li/strong/em/h3/a tags
- Keep each section focused — this fills one tab of a 6-tab lesson page, not a full essay"""

    data, err = _call_claude(prompt, api_key, max_tokens=3000)
    if err:
        return None, err
    for key in LESSON_TABS:
        if key not in data:
            data[key] = ''
    return data, None


def generate_dlsl_module_extras(
    course_title: str,
    module_title: str,
    submodules: list,
    course_context: str,
    grade_level: str,
    api_key: str,
) -> Tuple[Optional[dict], str]:
    """
    Generate the per-module Discussion Prompt and Graded Task Instruction content.
    Returns (extras_dict, error) where extras_dict has keys:
      discussion_title, discussion_guidelines, discussion_prompt,
      graded_task_title, graded_task_overview
    """
    level_label = GRADE_LEVEL_LABELS.get(grade_level, 'Senior High School')
    topics = ', '.join(t for s in submodules for t in s.get('topics', [])) or module_title

    prompt = f"""You are an instructional designer writing Canvas discussion and assessment content for De La Salle Lipa ({level_label}).

Course: {course_title}
Module: {module_title}
Key topics covered in this module: {topics}
Context: {course_context[:1000]}

Return ONLY a valid JSON object, no markdown fences, in this exact format:
{{
  "discussion_title": "A short discussion topic title (5-8 words)",
  "discussion_guidelines": "<ul><li>2-3 participation guidelines as list items</li></ul>",
  "discussion_prompt": "An open-ended discussion question (1-2 sentences) tied to the module's topics, written for {level_label} students.",
  "graded_task_title": "Graded Task: [short descriptive title]",
  "graded_task_overview": "<p>1-2 sentence description of the assessment task (e.g. quiz, short paper, project) covering this module's topics.</p>"
}}

Requirements:
- Tone appropriate for {level_label} students
- HTML fields: valid fragments only, no html/body/head/style tags"""

    data, err = _call_claude(prompt, api_key, max_tokens=1500)
    if err:
        return None, err
    for key in ('discussion_title', 'discussion_guidelines', 'discussion_prompt',
                'graded_task_title', 'graded_task_overview'):
        if key not in data:
            data[key] = ''
    return data, None
