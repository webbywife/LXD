"""
activities_generator.py
AI-powered extraction of interactive game content from lesson markdown.
"""

import json
import re
import os


def generate_activity_content(lesson_md, quiz_md, api_key, ai_provider="anthropic"):
    """
    Extract structured game content from lesson + quiz markdown using AI.
    Returns a dict with vocabulary, true_false, multiple_choice, fill_blanks,
    sequence_steps, and matching_pairs.
    """
    if api_key:
        content, error = _generate_with_ai(lesson_md, quiz_md, api_key, ai_provider)
        if not error and content:
            return content, None

    # Fallback: parse markdown with regex
    return _parse_markdown_fallback(lesson_md, quiz_md), None


def _generate_with_ai(lesson_md, quiz_md, api_key, ai_provider):
    prompt = f"""You are an educational content extractor. Analyze the lesson plan and quiz below, then extract structured content for interactive classroom games.

Return ONLY a valid JSON object (no markdown, no explanation) with this exact structure:
{{
  "topic": "short topic name",
  "subject": "subject name",
  "grade": "grade level",
  "vocabulary": [
    {{"word": "term", "definition": "definition"}}
  ],
  "true_false": [
    {{"statement": "A statement about the topic.", "answer": true}}
  ],
  "multiple_choice": [
    {{"question": "Question text?", "options": ["Option A", "Option B", "Option C", "Option D"], "answer": 0}}
  ],
  "fill_blanks": [
    {{"sentence": "The ___ is important because ...", "answer": "word"}}
  ],
  "sequence_steps": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
  "matching_pairs": [
    {{"term": "term", "definition": "definition"}}
  ]
}}

Requirements:
- vocabulary: 10-15 key terms with clear definitions from the lesson
- true_false: 10-15 statements (mix of true and false), answer is boolean
- multiple_choice: 10 questions, answer is 0-based index of correct option
- fill_blanks: 8-10 sentences with ONE blank each, answer is the missing word/phrase
- sequence_steps: 5-8 steps representing the lesson flow or a key process
- matching_pairs: 8-10 term-definition pairs (can overlap with vocabulary)

LESSON PLAN:
{lesson_md[:4000]}

QUIZ:
{quiz_md[:2000] if quiz_md else "(no quiz provided)"}
"""

    try:
        if ai_provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = msg.content[0].text.strip()
        else:
            return None, "Unsupported AI provider"

        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        data = json.loads(raw)
        return _validate_and_fill(data), None

    except Exception as e:
        return None, str(e)


def _validate_and_fill(data):
    """Ensure all required keys exist with correct types."""
    defaults = {
        "topic": "Lesson Topic",
        "subject": "Subject",
        "grade": "Grade",
        "vocabulary": [],
        "true_false": [],
        "multiple_choice": [],
        "fill_blanks": [],
        "sequence_steps": [],
        "matching_pairs": [],
    }
    for k, v in defaults.items():
        if k not in data or not data[k]:
            data[k] = v
    return data


def _parse_markdown_fallback(lesson_md, quiz_md):
    """Parse markdown with regex to extract game content when AI is unavailable."""
    # Extract topic from first H1
    topic_match = re.search(r'^#\s+(.+)$', lesson_md, re.MULTILINE)
    topic = topic_match.group(1).strip() if topic_match else "Lesson"

    # Extract subject/grade from header lines
    subject = "General"
    grade = "Grade"
    for line in lesson_md.split('\n')[:30]:
        if re.search(r'subject|learning area', line, re.I):
            m = re.search(r':\s*(.+)', line)
            if m:
                subject = m.group(1).strip()
        if re.search(r'grade|year level', line, re.I):
            m = re.search(r':\s*(.+)', line)
            if m:
                grade = m.group(1).strip()

    # Extract bold terms as vocabulary (** Term ** pattern)
    vocab_words = re.findall(r'\*\*([A-Za-z][a-z]+(?:\s+[A-Za-z][a-z]+)*)\*\*', lesson_md)
    vocab_words = list(dict.fromkeys(vocab_words))[:15]  # deduplicate, keep order

    vocabulary = [{"word": w, "definition": f"A key term related to {topic}."}
                  for w in vocab_words[:12]]

    # Extract bullet points as sequence steps
    bullets = re.findall(r'^[\s]*[-*]\s+(.+)$', lesson_md, re.MULTILINE)
    sequence_steps = [b.strip() for b in bullets[:8] if len(b.strip()) > 10]

    # Build basic true/false from lesson content sentences
    sentences = re.findall(r'[A-Z][^.!?]{20,100}[.!?]', lesson_md)
    true_false = []
    for s in sentences[:10]:
        true_false.append({"statement": s.strip(), "answer": True})

    # Build matching pairs from vocabulary
    matching_pairs = [{"term": v["word"], "definition": v["definition"]}
                      for v in vocabulary[:10]]

    # Fill in blanks from sentences
    fill_blanks = []
    for s in sentences[:8]:
        words = s.split()
        if len(words) > 5:
            idx = len(words) // 2
            answer = re.sub(r'[^a-zA-Z]', '', words[idx])
            if answer:
                words[idx] = "___"
                fill_blanks.append({"sentence": " ".join(words), "answer": answer})

    # Multiple choice placeholders
    multiple_choice = []
    for i, v in enumerate(vocabulary[:10]):
        multiple_choice.append({
            "question": f"What does '{v['word']}' mean?",
            "options": [v["definition"], "An unrelated term", "A different concept", "None of the above"],
            "answer": 0
        })

    return {
        "topic": topic,
        "subject": subject,
        "grade": grade,
        "vocabulary": vocabulary if vocabulary else [
            {"word": "Term 1", "definition": "Definition 1"},
            {"word": "Term 2", "definition": "Definition 2"},
        ],
        "true_false": true_false if true_false else [
            {"statement": f"This lesson covers {topic}.", "answer": True},
            {"statement": f"{topic} is unrelated to the curriculum.", "answer": False},
        ],
        "multiple_choice": multiple_choice if multiple_choice else [
            {"question": f"What is the main topic of this lesson?",
             "options": [topic, "Mathematics", "History", "Science"], "answer": 0}
        ],
        "fill_blanks": fill_blanks if fill_blanks else [
            {"sentence": f"The lesson focuses on ___.", "answer": topic}
        ],
        "sequence_steps": sequence_steps if sequence_steps else [
            "Introduction to the topic",
            "Exploration of key concepts",
            "Practice and application",
            "Review and assessment",
        ],
        "matching_pairs": matching_pairs if matching_pairs else [
            {"term": "Term 1", "definition": "Definition 1"},
            {"term": "Term 2", "definition": "Definition 2"},
        ],
    }
