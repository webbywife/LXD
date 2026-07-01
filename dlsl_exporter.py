"""
DLSL Canvas Course Exporter
Builds an IMS Common Cartridge 1.1 (.imscc) styled after DLSL's
"26-27 New Canvas Template" (Integrated Digital Innovative Instruction Office):
  - Green banner header (#12714d / accent #1FB36B)
  - Lesson pages with 6 tabs: Objectives, Introduction, Discussion, Application, Conclusion, Resources
  - One Discussion Prompt + Graded Task Instruction page per module
  - A Homepage page with grade-level banner image
"""
import html as html_lib
import io
import os
import re
import uuid
import zipfile

GREEN_DARK = '#12714d'
GREEN_ACCENT = '#1FB36B'

BANNER_ASSETS = {
    'gs':  'grade_school_banner.png',
    'jhs': 'junior_high_banner.png',
    'shs': 'senior_high_banner.png',
}
INSTRUCTOR_PLACEHOLDER_ASSET = 'instructor_placeholder.png'
COPYRIGHT_ASSET = 'copyright_notice.png'
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'dlsl_assets')
CC_ASSETS_HREF = 'web_resources/DLSL Assets'

LESSON_TABS = [
    ('objectives',   'Objectives'),
    ('introduction', 'Introduction'),
    ('discussion',   'Discussion'),
    ('application',  'Application'),
    ('conclusion',   'Conclusion'),
    ('resources',    'Resources'),
]


def _safe_id(s: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]', '_', s)[:32]


def _footer_html() -> str:
    return f"""<div style="background-color: #f5f5f5; padding: 20px; text-align: center; border-top: 1px solid #e1e1e1;">
<p style="font-size: 12px; color: #999;">&copy; 2026-2027 Integrated Digital Innovative Instruction Office | De La Salle Lipa</p>
<p><img src="$IMS-CC-FILEBASE$/{CC_ASSETS_HREF}/{COPYRIGHT_ASSET}" alt="DLSL Copyright Notice" loading="lazy"></p>
</div>"""


def _page_shell(banner_html: str, body_html: str) -> str:
    return f"""<html>
<body>
<div style="max-width: 1000px; margin: 20px auto; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #ffffff; border-radius: 8px; overflow: hidden; border: 1px solid #e1e1e1;">
{banner_html}
{body_html}
{_footer_html()}
</div>
</body>
</html>"""


def _lesson_page_html(course_title: str, sub_title: str, sections: dict) -> str:
    """Build a DLSL-styled lesson page with 6 tabs (Canvas native jQuery-UI tabs)."""
    banner = f"""<div style="background-color: {GREEN_DARK}; padding: 20px; text-align: center; border-bottom: 6px solid {GREEN_ACCENT};">
<h1 style="color: #ffffff; font-size: 28px; margin: 0;">{html_lib.escape(course_title)}</h1>
<div style="background-color: #ffffff; display: inline-block; padding: 5px 20px; margin-top: 10px; border-radius: 4px;"><span style="color: {GREEN_DARK}; font-size: 16px;">{html_lib.escape(sub_title)}</span></div>
</div>"""

    tabs_nav = ''.join(f'<li><a href="#fragment-{i+1}">{html_lib.escape(label)}</a></li>'
                        for i, (_, label) in enumerate(LESSON_TABS))
    tabs_body = ''
    for i, (key, label) in enumerate(LESSON_TABS):
        content = sections.get(key, '') or f'<p>{html_lib.escape(label)} content goes here.</p>'
        tabs_body += f"""<div id="fragment-{i+1}" style="padding: 20px;">
{content}
</div>"""

    body = f"""<div class="enhanceable_content tabs" style="padding: 20px;">
<ul>
{tabs_nav}
</ul>
{tabs_body}
</div>"""
    return _page_shell(banner, body)


def _homepage_html(course_title: str, course_desc: str, grade_level: str) -> str:
    banner_asset = BANNER_ASSETS.get(grade_level, BANNER_ASSETS['shs'])
    banner = f"""<div style="background-color: {GREEN_DARK}; padding: 20px 20px; text-align: center; border-bottom: 6px solid {GREEN_ACCENT};">
<h1 style="color: #ffffff; font-size: 26px; margin: 0;">{html_lib.escape(course_title)}</h1>
<div style="background-color: #ffffff; display: inline-block; padding: 4px 15px; margin-top: 10px; border-radius: 4px;"><span style="color: {GREEN_DARK}; font-size: 14px;">All About the Course</span></div>
</div>"""

    body = f"""<div style="padding: 20px;">
<div style="text-align: center; margin-bottom: 25px;"><img src="$IMS-CC-FILEBASE$/{CC_ASSETS_HREF}/{banner_asset}" alt="Course Banner" loading="lazy"></div>
<div style="background-color: #f9f9f9; padding: 25px; border-radius: 8px; border-left: 6px solid {GREEN_DARK}; margin-bottom: 30px;">
<h2 style="color: {GREEN_DARK}; margin-top: 0;">Welcome Message from the Teaching Team!</h2>
<p style="font-size: 16px; line-height: 1.6; color: #444;">{html_lib.escape(course_desc) or 'Welcome to the course! We look forward to learning together this term.'}<br><br><em><strong>Be near, go far Lasallians!</strong></em></p>
</div>
<h3 style="color: {GREEN_DARK}; border-bottom: 2px solid {GREEN_ACCENT}; padding-bottom: 5px;">Meet Your Instructor(s)</h3>
<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px;">
<div style="background: #ffffff; border-width: 4px 1px 1px; border-style: solid; border-color: {GREEN_DARK} #eeeeee #eeeeee; padding: 20px; border-radius: 8px; text-align: center;">
<img style="width: 100px; height: 100px; border-radius: 50%; margin-bottom: 12px; border: 3px solid {GREEN_ACCENT};" src="$IMS-CC-FILEBASE$/{CC_ASSETS_HREF}/{INSTRUCTOR_PLACEHOLDER_ASSET}" alt="Instructor" loading="lazy">
<h4 style="color: {GREEN_DARK}; margin: 0;">[Instructor Name]</h4>
<p style="font-size: 13px; color: #777; margin: 5px 0 0 0;">[Subject / Section]</p>
</div>
</div>
</div>"""
    return _page_shell(banner, body)


def _graded_task_html(course_title: str, task_title: str, overview_html: str) -> str:
    banner = f"""<div style="background-color: {GREEN_DARK}; padding: 40px 20px; text-align: center; border-bottom: 8px solid {GREEN_ACCENT};">
<h1 style="color: #ffffff; font-size: 32px; margin: 0px;">{html_lib.escape(task_title or 'Graded Task')}</h1>
</div>"""
    body = f"""<div style="padding: 20px;">
<div style="background-color: #f1f8f5; padding: 20px; border-radius: 8px; border-left: 6px solid {GREEN_ACCENT}; margin-bottom: 25px;">
<h3 style="color: {GREEN_DARK}; margin-top: 0;">Task Overview</h3>
{overview_html or '<p>Task overview goes here.</p>'}
</div>
</div>"""
    return _page_shell(banner, body)


def _discussion_topic_xml(course_title: str, discussion_title: str, guidelines_html: str, prompt_text: str) -> str:
    banner = f"""<div style="background-color: {GREEN_DARK}; padding: 20px; text-align: center; border-bottom: 6px solid {GREEN_ACCENT};">
<h1 style="color: #ffffff; font-size: 28px; margin: 0;">{html_lib.escape(course_title)}</h1>
<div style="background-color: #ffffff; display: inline-block; padding: 5px 20px; margin-top: 10px; border-radius: 4px;"><span style="color: {GREEN_DARK}; font-size: 16px;">{html_lib.escape(discussion_title)}</span></div>
</div>"""
    body = f"""<div style="padding: 30px;">
<div style="margin-bottom: 30px;">
<div style="background-color: {GREEN_ACCENT}; color: white; padding: 8px 20px; font-size: 18px; border-radius: 4px; display: inline-block; margin-bottom: 15px;">PARTICIPATION GUIDELINES</div>
<div style="border-left: 4px solid {GREEN_DARK}; padding-left: 20px;">
{guidelines_html or '<p>Participate respectfully and reply to at least two classmates.</p>'}
</div>
</div>
<div style="background-color: #f9f9f9; padding: 30px; border-radius: 8px; border: 2px solid {GREEN_DARK};">
<h2 style="color: {GREEN_DARK}; margin-top: 0; font-size: 22px;">Discussion Prompt</h2>
<hr style="border: 0; border-top: 1px solid #ddd; margin: 15px 0;">
<p style="font-size: 18px; line-height: 1.6; color: #333;">{html_lib.escape(prompt_text)}</p>
</div>
</div>"""
    full_html = _page_shell(banner, body)
    # imsdt topic text carries the fragment inside <body>, not a full document
    inner = re.search(r'<body>([\s\S]*)</body>', full_html).group(1)
    escaped = html_lib.escape(inner)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<topic xmlns="http://www.imsglobal.org/xsd/imsccv1p1/imsdt_v1p1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.imsglobal.org/xsd/imsccv1p1/imsdt_v1p1 http://www.imsglobal.org/profile/cc/ccv1p1/ccv1p1_imsdt_v1p1.xsd">
  <title>{html_lib.escape(discussion_title)}</title>
  <text texttype="text/html">{escaped}</text>
</topic>"""


def build_dlsl_imscc(course_data: dict, gen_results: dict, module_extras: dict, grade_level: str = 'shs') -> io.BytesIO:
    """
    Build a DLSL-branded Canvas Common Cartridge (.imscc).
    gen_results:    {submodule_id: {objectives, introduction, discussion, application, conclusion, resources}}
    module_extras:  {module_id: {discussion_title, discussion_guidelines, discussion_prompt,
                                  graded_task_title, graded_task_overview}}
    """
    course_title = course_data.get('course_title', 'Untitled Course')
    course_desc = course_data.get('course_description', '')
    modules = course_data.get('modules', [])

    files = {}
    resources_xml = ''
    items_xml = ''

    # Homepage
    home_path = 'homepage.html'
    home_res_id = 'RES_homepage'
    files[home_path] = _homepage_html(course_title, course_desc, grade_level)
    resources_xml += (
        f'<resource identifier="{home_res_id}" type="webcontent" href="{home_path}">'
        f'<file href="{home_path}"/></resource>\n'
    )
    items_xml += (
        f'<item identifier="homepage_item" identifierref="{home_res_id}">'
        f'<title>Homepage</title></item>\n'
    )

    for mod in modules:
        mod_id = _safe_id(mod['id'])
        mod_items = ''

        for sub in mod.get('submodules', []):
            sub_id = _safe_id(sub['id'])
            sections = gen_results.get(sub['id'], {})
            file_path = f'{mod_id}/{sub_id}_lesson.html'
            res_id = f'RES_{sub_id}_lesson'
            files[file_path] = _lesson_page_html(course_title, sub['title'], sections)
            resources_xml += (
                f'<resource identifier="{res_id}" type="webcontent" href="{file_path}">'
                f'<file href="{file_path}"/></resource>\n'
            )
            mod_items += (
                f'<item identifier="{sub_id}_item" identifierref="{res_id}">'
                f'<title>{html_lib.escape(sub["title"])}</title></item>\n'
            )

        extras = module_extras.get(mod['id'], {})

        disc_path = f'{mod_id}/{mod_id}_discussion.xml'
        disc_res_id = f'RES_{mod_id}_discussion'
        disc_title = extras.get('discussion_title') or f'{mod["title"]} — Discussion'
        files[disc_path] = _discussion_topic_xml(
            course_title, disc_title,
            extras.get('discussion_guidelines', ''), extras.get('discussion_prompt', ''))
        resources_xml += (
            f'<resource identifier="{disc_res_id}" type="imsdt_xmlv1p1" href="{disc_path}">'
            f'<file href="{disc_path}"/></resource>\n'
        )
        mod_items += (
            f'<item identifier="{mod_id}_disc_item" identifierref="{disc_res_id}">'
            f'<title>{html_lib.escape(disc_title)}</title></item>\n'
        )

        task_path = f'{mod_id}/{mod_id}_graded_task.html'
        task_res_id = f'RES_{mod_id}_gradedtask'
        task_title = extras.get('graded_task_title') or f'{mod["title"]} — Graded Task'
        files[task_path] = _graded_task_html(course_title, task_title, extras.get('graded_task_overview', ''))
        resources_xml += (
            f'<resource identifier="{task_res_id}" type="webcontent" href="{task_path}">'
            f'<file href="{task_path}"/></resource>\n'
        )
        mod_items += (
            f'<item identifier="{mod_id}_task_item" identifierref="{task_res_id}">'
            f'<title>{html_lib.escape(task_title)}</title></item>\n'
        )

        items_xml += (
            f'<item identifier="{mod_id}_item">'
            f'<title>{html_lib.escape(mod["title"])}</title>'
            f'{mod_items}</item>\n'
        )

    # Bundled brand assets (banners, instructor placeholder, copyright notice)
    asset_files = set(BANNER_ASSETS.values()) | {INSTRUCTOR_PLACEHOLDER_ASSET, COPYRIGHT_ASSET}
    asset_bytes = {}
    for fname in asset_files:
        asset_path = f'{CC_ASSETS_HREF}/{fname}'
        local_path = os.path.join(ASSETS_DIR, fname)
        if os.path.exists(local_path):
            with open(local_path, 'rb') as f:
                asset_bytes[asset_path] = f.read()
            res_id = f'RES_{_safe_id(fname)}'
            resources_xml += (
                f'<resource identifier="{res_id}" type="webcontent" href="{asset_path}">'
                f'<file href="{asset_path}"/></resource>\n'
            )

    manifest = f"""<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{uuid.uuid4().hex}"
  xmlns="http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1"
  xmlns:lomimscc="http://ltsc.ieee.org/xsd/imsccv1p1/LOM/manifest"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1 http://www.imsglobal.org/profile/cc/ccv1p1/ccv1p1_imscp_v1p2_v1p0.xsd">
  <metadata>
    <schema>IMS Common Cartridge</schema>
    <schemaversion>1.1.0</schemaversion>
    <lomimscc:lom>
      <lomimscc:general>
        <lomimscc:title><lomimscc:string language="en">{html_lib.escape(course_title)}</lomimscc:string></lomimscc:title>
        <lomimscc:description><lomimscc:string language="en">{html_lib.escape(course_desc)}</lomimscc:string></lomimscc:description>
      </lomimscc:general>
    </lomimscc:lom>
  </metadata>
  <organizations>
    <organization identifier="org_1" structure="rooted-hierarchy">
      <item identifier="root">
        {items_xml}
      </item>
    </organization>
  </organizations>
  <resources>
    {resources_xml}
  </resources>
</manifest>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('imsmanifest.xml', manifest.encode('utf-8'))
        for path, content in files.items():
            zf.writestr(path, content.encode('utf-8'))
        for path, data in asset_bytes.items():
            zf.writestr(path, data)
        zf.writestr('course_settings/canvas_export.txt', b'true')
    buf.seek(0)
    return buf
