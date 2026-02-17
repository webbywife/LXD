"""
SCORM 1.2 Package Builder
Creates SCORM-compliant ZIP packages from lesson plans and assessments.
Compatible with Moodle 3-5, Canvas, Brightspace, and other SCORM 1.2 LMS.
"""

import os
import zipfile
import io
import re
import html as html_lib

SCORM_MANIFEST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{manifest_id}" version="1.0"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd
                       http://www.imsglobal.org/xsd/imsmd_rootv1p2p1 imsmd_rootv1p2p1.xsd
                       http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="ORG-001">
    <organization identifier="ORG-001">
      <title>{title}</title>
      {items_xml}
    </organization>
  </organizations>
  <resources>
    {resources_xml}
  </resources>
</manifest>
"""

SCORM_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&family=Lora:wght@400;500;600;700&family=Open+Sans:wght@400;500;600&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root {{
    --bg: #f1f1f2;
    --color1: #00bbd6;
    --color1-dark: #009bb3;
    --color2: #237194;
    --color2-dark: #1a5670;
    --accent: #faa32b;
    --accent-light: #fff3e0;
    --white: #ffffff;
    --text: #2d3436;
    --text-sec: #636e72;
    --border: #dfe6e9;
    --success: #00b894;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: 'Open Sans', 'Roboto', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.8;
    padding: 0;
}}
.scorm-container {{
    max-width: 900px;
    margin: 0 auto;
    padding: 20px;
}}

/* Header Banner */
.lp-header {{
    background: linear-gradient(135deg, var(--color2) 0%, var(--color1) 100%);
    color: white;
    padding: 32px 36px;
    border-radius: 16px;
    margin-bottom: 24px;
    position: relative;
    overflow: hidden;
}}
.lp-header::after {{
    content: '';
    position: absolute;
    top: -30px; right: -30px;
    width: 150px; height: 150px;
    background: rgba(255,255,255,0.08);
    border-radius: 50%;
}}
.lp-header h1 {{
    font-family: 'Poppins', sans-serif;
    font-size: 26px;
    font-weight: 800;
    margin-bottom: 6px;
    letter-spacing: -0.5px;
}}
.lp-header .lp-meta {{
    font-size: 13px;
    opacity: 0.9;
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-top: 10px;
}}
.lp-header .meta-item {{
    background: rgba(255,255,255,0.15);
    padding: 4px 14px;
    border-radius: 20px;
    font-weight: 500;
}}

/* Info Table */
.info-table {{
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    background: white;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}}
.info-table td {{
    padding: 10px 18px;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
}}
.info-table td:first-child {{
    font-weight: 600;
    color: var(--color2);
    width: 35%;
    background: #f8fffe;
    font-family: 'Poppins', sans-serif;
}}

/* Section Cards */
.section-card {{
    background: white;
    border-radius: 14px;
    margin-bottom: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    border: 1px solid var(--border);
    overflow: hidden;
}}
.section-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 18px 24px;
    background: linear-gradient(135deg, var(--color2) 0%, var(--color1) 50%);
    color: white;
    font-family: 'Poppins', sans-serif;
}}
.section-icon {{
    font-size: 24px;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255,255,255,0.2);
    border-radius: 10px;
    flex-shrink: 0;
}}
.section-title {{
    font-size: 16px;
    font-weight: 700;
}}
.section-body {{
    padding: 20px 24px;
}}

/* Tip Boxes */
.tip-box {{
    display: flex;
    gap: 10px;
    background: var(--accent-light);
    border-left: 4px solid var(--accent);
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
    margin: 12px 0;
    font-size: 13px;
    align-items: flex-start;
}}
.tip-box .tip-icon {{
    font-size: 18px;
    flex-shrink: 0;
    margin-top: 1px;
}}
.tip-box .tip-text {{
    line-height: 1.5;
    color: #5a4310;
}}

/* Phase Cards (Lesson Procedure) */
.phase-card {{
    border: 2px solid var(--border);
    border-radius: 12px;
    margin: 12px 0;
    overflow: hidden;
}}
.phase-header {{
    background: linear-gradient(90deg, var(--color1), var(--color2));
    color: white;
    padding: 10px 18px;
    font-family: 'Poppins', sans-serif;
    font-weight: 700;
    font-size: 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}}
.phase-body {{
    padding: 16px 18px;
}}

/* Rubric Table */
.rubric-table {{
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
    font-size: 13px;
}}
.rubric-table th {{
    background: var(--color2);
    color: white;
    padding: 10px 12px;
    font-family: 'Poppins', sans-serif;
    font-weight: 600;
    text-align: left;
}}
.rubric-table td {{
    padding: 10px 12px;
    border: 1px solid var(--border);
    vertical-align: top;
}}
.rubric-table tr:nth-child(even) td {{
    background: #f8fffe;
}}

/* General Tables */
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0;
    font-size: 13px;
}}
th {{
    background: var(--color2);
    color: white;
    padding: 10px 14px;
    font-family: 'Poppins', sans-serif;
    font-weight: 600;
    text-align: left;
}}
td {{
    padding: 8px 14px;
    border: 1px solid var(--border);
}}
tr:nth-child(even) td {{ background: #fafafa; }}

/* Lists */
ul, ol {{ padding-left: 22px; margin: 8px 0; }}
li {{ margin-bottom: 6px; font-size: 14px; }}

/* Diff Cards */
.diff-card {{
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 18px;
    margin: 8px 0;
    background: #fafafa;
}}
.diff-card h4 {{
    font-family: 'Poppins', sans-serif;
    color: var(--color2);
    font-size: 14px;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 6px;
}}

/* Checklist */
.checklist {{ list-style: none; padding-left: 0; }}
.checklist li {{
    padding: 6px 0;
    padding-left: 28px;
    position: relative;
}}
.checklist li::before {{
    content: '\\2610';
    position: absolute;
    left: 0;
    font-size: 18px;
    color: var(--color1);
}}

/* Assessment Form */
.form-field {{
    border-bottom: 1px solid var(--border);
    padding: 8px 0;
    margin-bottom: 8px;
}}

/* Blockquotes */
blockquote {{
    border-left: 4px solid var(--accent);
    background: var(--accent-light);
    padding: 12px 18px;
    border-radius: 0 8px 8px 0;
    margin: 12px 0;
    font-style: italic;
    font-size: 13px;
}}

/* Headings */
h1 {{
    font-family: 'Poppins', sans-serif;
    font-size: 24px;
    font-weight: 800;
    color: var(--color2);
    margin: 28px 0 14px;
    padding-bottom: 8px;
    border-bottom: 3px solid var(--color1);
}}
h2 {{
    font-family: 'Poppins', sans-serif;
    font-size: 20px;
    font-weight: 700;
    color: var(--color2);
    margin: 24px 0 12px;
    padding-bottom: 6px;
    border-bottom: 2px solid var(--color1);
}}
h3 {{
    font-family: 'Poppins', sans-serif;
    font-size: 16px;
    font-weight: 600;
    color: var(--color2-dark);
    margin: 16px 0 8px;
}}
h4 {{
    font-family: 'Poppins', sans-serif;
    font-size: 14px;
    font-weight: 600;
    margin: 12px 0 6px;
}}
p {{ margin: 6px 0; font-size: 14px; }}
strong {{ color: var(--text); }}
em {{ color: var(--text-sec); }}
hr {{
    border: none;
    height: 3px;
    background: linear-gradient(90deg, var(--color1), var(--accent), var(--color2));
    border-radius: 2px;
    margin: 30px 0;
}}

/* Footer */
.lp-footer {{
    text-align: center;
    padding: 20px;
    font-size: 11px;
    color: var(--text-sec);
    border-top: 1px solid var(--border);
    margin-top: 30px;
}}

/* Section Tabs */
.section-tabs {{
    display: flex;
    gap: 4px;
    padding: 12px 0;
    overflow-x: auto;
    flex-wrap: wrap;
    margin-bottom: 8px;
}}
.section-tab {{
    padding: 8px 18px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    border: 2px solid var(--border);
    background: var(--white);
    cursor: pointer;
    font-family: 'Poppins', sans-serif;
    transition: all 0.2s;
    white-space: nowrap;
}}
.section-tab:hover {{
    border-color: var(--color1);
}}
.section-tab.active {{
    background: var(--color2);
    color: var(--white);
    border-color: var(--color2);
}}
.section-pane {{
    display: none;
}}
.section-pane.active {{
    display: block;
}}

@media print {{
    body {{ background: white; }}
    .scorm-container {{ padding: 0; }}
    .section-card {{ box-shadow: none; page-break-inside: avoid; }}
    .section-tabs {{ display: none; }}
    .section-pane {{ display: block !important; }}
}}
</style>
<script>
// SCORM 1.2 API wrapper
var API = null;
function findAPI(win) {{
    try {{
        while (win.API == null && win.parent != null && win.parent != win) {{
            win = win.parent;
        }}
        return win.API;
    }} catch(e) {{ return null; }}
}}
function initSCORM() {{
    API = findAPI(window);
    if (API) {{
        API.LMSInitialize("");
        API.LMSSetValue("cmi.core.lesson_status", "completed");
        API.LMSCommit("");
    }}
}}
function finishSCORM() {{
    if (API) {{
        API.LMSSetValue("cmi.core.lesson_status", "completed");
        API.LMSCommit("");
        API.LMSFinish("");
    }}
}}

function initTabs() {{
    var container = document.querySelector('.scorm-container');
    if (!container) return;
    var html = container.innerHTML;
    var parts = html.split(/<h2>/i);
    if (parts.length < 2) return;
    var intro = parts[0];
    var sections = [];
    for (var i = 1; i < parts.length; i++) {{
        var closeIdx = parts[i].indexOf('</h2>');
        if (closeIdx === -1) {{
            sections.push({{ title: 'Section ' + i, content: '<h2>' + parts[i] }});
        }} else {{
            var title = parts[i].substring(0, closeIdx).replace(/<[^>]*>/g, '').trim();
            var content = parts[i].substring(closeIdx + 5);
            sections.push({{ title: title, content: content }});
        }}
    }}
    if (sections.length < 2) return;
    var tabBar = '<div class="section-tabs">';
    tabBar += '<div class="section-tab active" data-idx="all">View All</div>';
    for (var i = 0; i < sections.length; i++) {{
        tabBar += '<div class="section-tab" data-idx="' + i + '">' + sections[i].title + '</div>';
    }}
    tabBar += '</div>';
    var panes = '<div class="section-pane active" data-pane="all">' + intro;
    for (var i = 0; i < sections.length; i++) {{
        panes += '<h2>' + sections[i].title + '</h2>' + sections[i].content;
    }}
    panes += '</div>';
    for (var i = 0; i < sections.length; i++) {{
        panes += '<div class="section-pane" data-pane="' + i + '">';
        panes += '<h2>' + sections[i].title + '</h2>' + sections[i].content;
        panes += '</div>';
    }}
    container.innerHTML = tabBar + panes;
    var tabs = container.querySelectorAll('.section-tab');
    tabs.forEach(function(tab) {{
        tab.addEventListener('click', function() {{
            tabs.forEach(function(t) {{ t.classList.remove('active'); }});
            tab.classList.add('active');
            var idx = tab.getAttribute('data-idx');
            container.querySelectorAll('.section-pane').forEach(function(p) {{
                p.classList.remove('active');
                if (p.getAttribute('data-pane') === idx) p.classList.add('active');
            }});
        }});
    }});
}}

window.onload = function() {{ initSCORM(); initTabs(); }};
window.onbeforeunload = finishSCORM;
</script>
</head>
<body>
<div class="scorm-container">
{content}
</div>
<div class="lp-footer">
    Generated by MATATAG AI Lesson Plan Generator &bull; Philippine DepEd MATATAG Curriculum &bull; SCORM 1.2 Compliant
</div>
</body>
</html>
"""


def _sanitize_id(text):
    """Create a safe identifier from text."""
    clean = re.sub(r'[^a-zA-Z0-9]', '_', text)
    return clean[:60] or "ITEM"


def md_to_styled_html(md_content):
    """Convert markdown to professionally styled HTML for SCORM output."""
    if not md_content:
        return ""

    h = html_lib.escape(md_content)

    # Blockquotes
    h = re.sub(r'^&gt; (.+)$', r'<blockquote>\1</blockquote>', h, flags=re.MULTILINE)
    h = h.replace('</blockquote>\n<blockquote>', '<br>')

    # Horizontal rules
    h = re.sub(r'^---$', '<hr>', h, flags=re.MULTILINE)

    # Checkboxes
    h = h.replace('- [ ]', '<span style="font-size:18px;color:var(--color1);">&#9744;</span>')
    h = h.replace('- [x]', '<span style="font-size:18px;color:var(--success);">&#9745;</span>')

    # Headers
    h = re.sub(r'^### (.+)$', r'<h3>\1</h3>', h, flags=re.MULTILINE)
    h = re.sub(r'^## (.+)$', r'<h2>\1</h2>', h, flags=re.MULTILINE)
    h = re.sub(r'^# (.+)$', r'<h1>\1</h1>', h, flags=re.MULTILINE)

    # Bold/italic
    h = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', h)
    h = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', h)
    h = re.sub(r'\*(.+?)\*', r'<em>\1</em>', h)

    # Tables
    def table_row(match):
        cells = match.group(0).split('|')
        cells = [c.strip() for c in cells if c.strip()]
        if all(re.match(r'^[\s\-:]+$', c) for c in cells):
            return '<!--sep-->'
        tds = ''.join(f'<td>{c}</td>' for c in cells)
        return f'<tr>{tds}</tr>'

    h = re.sub(r'^\|(.+)\|$', table_row, h, flags=re.MULTILINE)
    h = re.sub(r'((?:<tr>.*?</tr>\n?)+)', r'<table>\1</table>', h)
    h = h.replace('<!--sep-->\n', '').replace('<!--sep-->', '')

    # Lists
    h = re.sub(r'^[-*] (.+)$', r'<li>\1</li>', h, flags=re.MULTILINE)
    h = re.sub(r'^\d+\.\s+(.+)$', r'<li>\1</li>', h, flags=re.MULTILINE)
    h = re.sub(r'((?:<li>.*?</li>\n?)+)', r'<ul>\1</ul>', h)

    # Paragraphs
    h = re.sub(r'^(?!<[a-z/])((?!<).+)$', r'<p>\1</p>', h, flags=re.MULTILINE)
    h = re.sub(r'<p>\s*</p>', '', h)

    return h


def build_scorm_package(title, lesson_plan_md=None, assessment_md=None, quiz_md=None):
    """Build a SCORM 1.2 compliant ZIP package."""
    buffer = io.BytesIO()

    items_xml = ""
    resources_xml = ""
    files_to_add = {}

    if lesson_plan_md:
        lp_html = md_to_styled_html(lesson_plan_md)
        lp_page = SCORM_HTML_TEMPLATE.format(
            title=html_lib.escape(title),
            content=lp_html
        )
        files_to_add["lesson_plan.html"] = lp_page
        items_xml += '''<item identifier="ITEM-LP" identifierref="RES-LP">
            <title>Lesson Plan</title>
        </item>\n'''
        resources_xml += '''<resource identifier="RES-LP" type="webcontent"
            adlcp:scormtype="sco" href="lesson_plan.html">
            <file href="lesson_plan.html"/>
        </resource>\n'''

    if assessment_md:
        assess_html = md_to_styled_html(assessment_md)
        assess_page = SCORM_HTML_TEMPLATE.format(
            title=html_lib.escape(title + " - Assessment"),
            content=assess_html
        )
        files_to_add["assessment.html"] = assess_page
        items_xml += '''<item identifier="ITEM-ASSESS" identifierref="RES-ASSESS">
            <title>Authentic Assessment</title>
        </item>\n'''
        resources_xml += '''<resource identifier="RES-ASSESS" type="webcontent"
            adlcp:scormtype="sco" href="assessment.html">
            <file href="assessment.html"/>
        </resource>\n'''

    if quiz_md:
        quiz_html = md_to_styled_html(quiz_md)
        quiz_page = SCORM_HTML_TEMPLATE.format(
            title=html_lib.escape(title + " - Quiz"),
            content=quiz_html
        )
        files_to_add["quiz.html"] = quiz_page
        items_xml += '''<item identifier="ITEM-QUIZ" identifierref="RES-QUIZ">
            <title>Quiz</title>
        </item>\n'''
        resources_xml += '''<resource identifier="RES-QUIZ" type="webcontent"
            adlcp:scormtype="sco" href="quiz.html">
            <file href="quiz.html"/>
        </resource>\n'''

    manifest_id = "MATATAG-" + _sanitize_id(title)
    manifest = SCORM_MANIFEST_TEMPLATE.format(
        manifest_id=manifest_id,
        title=html_lib.escape(title),
        items_xml=items_xml,
        resources_xml=resources_xml
    )

    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('imsmanifest.xml', manifest)
        for fname, content in files_to_add.items():
            zf.writestr(fname, content)

    buffer.seek(0)
    return buffer


if __name__ == "__main__":
    test_md = "## Test Lesson\n\n- Item 1\n- Item 2\n\n### Section\nHello world"
    pkg = build_scorm_package("Test Lesson Plan", lesson_plan_md=test_md)
    with open("/tmp/test_scorm.zip", "wb") as f:
        f.write(pkg.read())
    print("Test SCORM package created at /tmp/test_scorm.zip")
