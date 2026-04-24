"""
LMS Course Package Exporters
Builds Moodle .mbz, Canvas .imscc, and Brightspace .zip from 5-section module content.

Each submodule contains 5 instructional sections:
  a. Overview       — objectives + resources
  b. Teach & Learn  — lesson content
  c. Practice       — reinforcement activities
  d. Assessment     — formative quiz + authentic assessment
  e. Rubric         — scoring rubric
"""
import html as html_lib
import io
import re
import uuid
import zipfile
from datetime import datetime

SECTION_LABELS = [
    ('overview',       'a. Overview'),
    ('teach_and_learn','b. Teach & Learn'),
    ('practice',       'c. Practice'),
    ('assessment',     'd. Assessment'),
    ('rubric',         'e. Rubric'),
]

SECTION_COLORS = {
    'overview':       ('#1e3a5f', '#e8f0fe'),
    'teach_and_learn':('#155724', '#d4edda'),
    'practice':       ('#7b2d00', '#fce8d5'),
    'assessment':     ('#4a235a', '#f3e8fd'),
    'rubric':         ('#0c3547', '#d1ecf1'),
}


def _safe_id(s: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]', '_', s)[:32]


def _section_html(section_key: str, sub_title: str, sections: dict) -> str:
    """Build a full styled HTML page for one of the 5 instructional sections."""
    label  = dict(SECTION_LABELS)[section_key]
    header_color, bg_color = SECTION_COLORS.get(section_key, ('#1a1a2e', '#f8f9fa'))
    s      = sections.get(section_key, {})

    body_html = ''

    if section_key == 'overview':
        objs = s.get('objectives', [])
        res  = s.get('resources', [])
        body_html += s.get('html', '')
        if objs:
            items = ''.join(f'<li>{html_lib.escape(o)}</li>' for o in objs)
            body_html += f'<h2>Learning Objectives</h2><ul class="obj-list">{items}</ul>'
        if res:
            items = ''.join(f'<li>{html_lib.escape(r)}</li>' for r in res)
            body_html += f'<h2>Resources</h2><ul class="res-list">{items}</ul>'

    elif section_key == 'teach_and_learn':
        body_html = s.get('html', '')

    elif section_key == 'practice':
        body_html = s.get('html', '')

    elif section_key == 'assessment':
        quiz_html     = s.get('quiz_html', '')
        authentic_html = s.get('authentic_html', '')
        body_html = (
            '<div class="section-block">' + quiz_html + '</div>'
            '<hr/>'
            '<div class="section-block">' + authentic_html + '</div>'
        )

    elif section_key == 'rubric':
        body_html = _rubric_html(s)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html_lib.escape(label)}: {html_lib.escape(sub_title)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:#f5f5f5;color:#1a1a2e;line-height:1.75;}}
.page-header{{background:{header_color};color:#fff;padding:28px 40px;}}
.page-header .section-badge{{font-size:11px;font-weight:800;letter-spacing:.1em;
  text-transform:uppercase;opacity:.75;margin-bottom:6px;}}
.page-header h1{{font-size:22px;font-weight:700;}}
.page-header .sub{{font-size:13px;opacity:.7;margin-top:4px;}}
.content{{max-width:840px;margin:32px auto;padding:0 24px 60px;}}
.content h2{{color:{header_color};font-size:17px;font-weight:700;
  margin:28px 0 10px;padding-bottom:6px;border-bottom:2px solid {bg_color.replace('#','').join(['#',''])};
  border-bottom-color:{header_color}33;}}
.content h3{{color:{header_color};font-size:14px;font-weight:700;margin:18px 0 8px;}}
.content p{{margin-bottom:12px;font-size:14px;}}
.content ul,.content ol{{padding-left:1.5em;margin-bottom:14px;font-size:14px;}}
.content li{{margin-bottom:6px;}}
blockquote{{background:{bg_color};border-left:4px solid {header_color};
  padding:12px 18px;margin:14px 0;border-radius:0 8px 8px 0;font-style:italic;font-size:14px;}}
.obj-list li{{background:#f0fdf4;border-left:3px solid #22c55e;
  padding:8px 12px;border-radius:0 6px 6px 0;list-style:none;margin-bottom:8px;}}
.res-list li{{background:{bg_color};padding:8px 12px;border-radius:6px;
  list-style:none;margin-bottom:6px;font-size:13px;}}
table{{width:100%;border-collapse:collapse;margin:16px 0;font-size:13px;}}
th{{background:{header_color};color:#fff;padding:10px 14px;text-align:left;}}
td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:top;}}
tr:nth-child(even) td{{background:#f8fafc;}}
.section-block{{margin-bottom:24px;}}
hr{{border:none;border-top:2px solid {bg_color};margin:28px 0;}}
em{{color:{header_color};font-weight:600;}}
strong{{font-weight:700;}}
</style>
</head>
<body>
<div class="page-header">
  <div class="section-badge">{html_lib.escape(label)}</div>
  <h1>{html_lib.escape(sub_title)}</h1>
</div>
<div class="content">
{body_html}
</div>
</body>
</html>"""


def _rubric_html(rubric: dict) -> str:
    """Build the rubric table HTML."""
    if rubric.get('html'):
        return rubric['html']
    criteria = rubric.get('criteria', [])
    if not criteria:
        return '<p>No rubric data available.</p>'
    rows = ''
    for c in criteria:
        rows += (
            f"<tr>"
            f"<td><strong>{html_lib.escape(c.get('criterion',''))}</strong></td>"
            f"<td>{html_lib.escape(c.get('excellent',''))}</td>"
            f"<td>{html_lib.escape(c.get('proficient',''))}</td>"
            f"<td>{html_lib.escape(c.get('developing',''))}</td>"
            f"<td>{html_lib.escape(c.get('beginning',''))}</td>"
            f"</tr>"
        )
    return (
        f"<h2>{html_lib.escape(rubric.get('title','Assessment Rubric'))}</h2>"
        "<table><thead><tr>"
        "<th>Criterion</th><th>Excellent (4)</th><th>Proficient (3)</th>"
        "<th>Developing (2)</th><th>Beginning (1)</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


def _get_sections(sub: dict) -> dict:
    """Return the 5-section dict regardless of old/new format."""
    if 'sections' in sub:
        return sub['sections']
    # Legacy: single content_html → put in teach_and_learn
    if sub.get('content_html'):
        return {'teach_and_learn': {'html': sub['content_html']}}
    return {}


# ── IMS Common Cartridge 1.1 — Canvas & Brightspace ──────────────────────────

def build_imscc(course_data: dict, platform: str = 'canvas') -> io.BytesIO:
    """Build an IMS Common Cartridge 1.1 (.imscc) for Canvas or Brightspace."""
    course_title = course_data.get('course_title', 'Untitled Course')
    course_desc  = course_data.get('course_description', '')
    modules      = course_data.get('modules', [])

    items_xml     = ''
    resources_xml = ''
    files         = {}

    for mod in modules:
        mod_id    = _safe_id(mod['id'])
        mod_items = ''

        for sub in mod.get('submodules', []):
            sub_id   = _safe_id(sub['id'])
            sections = _get_sections(sub)
            sub_items = ''

            for sec_key, sec_label in SECTION_LABELS:
                file_path = f'{mod_id}/{sub_id}_{sec_key}.html'
                item_id   = f'{sub_id}_{sec_key}'
                res_id    = f'RES_{item_id}'
                page_html = _section_html(sec_key, sub['title'], sections)

                sub_items += (
                    f'<item identifier="{item_id}" identifierref="{res_id}">'
                    f'<title>{html_lib.escape(sec_label)}: {html_lib.escape(sub["title"])}</title>'
                    f'</item>\n'
                )
                resources_xml += (
                    f'<resource identifier="{res_id}" type="webcontent" href="{file_path}">'
                    f'<file href="{file_path}"/>'
                    f'</resource>\n'
                )
                files[file_path] = page_html

            mod_items += (
                f'<item identifier="{sub_id}">'
                f'<title>{html_lib.escape(sub["title"])}</title>'
                f'{sub_items}'
                f'</item>\n'
            )

        items_xml += (
            f'<item identifier="{mod_id}">'
            f'<title>{html_lib.escape(mod["title"])}</title>'
            f'{mod_items}'
            f'</item>\n'
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
        <lomimscc:title>
          <lomimscc:string language="en">{html_lib.escape(course_title)}</lomimscc:string>
        </lomimscc:title>
        <lomimscc:description>
          <lomimscc:string language="en">{html_lib.escape(course_desc)}</lomimscc:string>
        </lomimscc:description>
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
        if platform == 'canvas':
            zf.writestr('course_settings/canvas_export.txt', b'true')
        elif platform == 'brightspace':
            d2l = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<Properties Version="1.0">\n'
                f'  <Property Name="Title" Value="{html_lib.escape(course_title)}"/>\n'
                '</Properties>'
            )
            zf.writestr('d2l_content.xml', d2l.encode('utf-8'))
    buf.seek(0)
    return buf


# ── Moodle Backup .mbz ────────────────────────────────────────────────────────

def build_moodle_mbz(course_data: dict) -> io.BytesIO:
    """Build a Moodle 4.x-compatible backup (.mbz). Each submodule → 5 page activities."""
    course_title = course_data.get('course_title', 'Untitled Course')
    course_desc  = course_data.get('course_description', '')
    modules      = course_data.get('modules', [])
    now          = int(datetime.now().timestamp())
    short_name   = re.sub(r'[^a-zA-Z0-9]', '', course_title)[:10].upper() or 'COURSE'

    page_id      = 100
    section_id   = 1
    section_entries  = []
    activity_entries = []
    section_files    = {}
    activity_files   = {}
    settings_extra   = ''

    for mod in modules:
        sid = section_id
        section_id += 1
        page_ids_in_section = []

        for sub in mod.get('submodules', []):
            sections = _get_sections(sub)

            for sec_key, sec_label in SECTION_LABELS:
                pid       = page_id
                page_id  += 1
                page_ids_in_section.append(str(pid))

                p_title   = f'{sec_label}: {sub["title"]}'
                p_content = _section_html(sec_key, sub['title'], sections)

                activity_files[f'activities/page_{pid}/page.xml'] = (
                    f'<?xml version="1.0" encoding="UTF-8"?>\n'
                    f'<activity id="{pid}" moduleid="{pid}" modulename="page" contextid="{pid}">\n'
                    f'  <page id="{pid}">\n'
                    f'    <name>{html_lib.escape(p_title)}</name>\n'
                    f'    <intro></intro>\n'
                    f'    <introformat>1</introformat>\n'
                    f'    <content><![CDATA[{p_content}]]></content>\n'
                    f'    <contentformat>1</contentformat>\n'
                    f'    <legacyfiles>0</legacyfiles>\n'
                    f'    <legacyfileslast>$@NULL@$</legacyfileslast>\n'
                    f'    <display>5</display>\n'
                    f'    <displayoptions>a:0:{{}}</displayoptions>\n'
                    f'    <revision>1</revision>\n'
                    f'    <timemodified>{now}</timemodified>\n'
                    f'  </page>\n'
                    f'</activity>'
                )
                activity_files[f'activities/page_{pid}/module.xml'] = (
                    f'<?xml version="1.0" encoding="UTF-8"?>\n'
                    f'<module id="{pid}" version="2022041900">\n'
                    f'  <modulename>page</modulename>\n'
                    f'  <sectionid>{sid}</sectionid>\n'
                    f'  <sectionnumber>{sid}</sectionnumber>\n'
                    f'  <idnumber></idnumber>\n'
                    f'  <added>{now}</added>\n'
                    f'  <score>0</score>\n'
                    f'  <indent>0</indent>\n'
                    f'  <visible>1</visible>\n'
                    f'  <visibleoncoursepage>1</visibleoncoursepage>\n'
                    f'  <visibleold>1</visibleold>\n'
                    f'  <groupmode>0</groupmode>\n'
                    f'  <groupingid>0</groupingid>\n'
                    f'  <completion>0</completion>\n'
                    f'  <completiongradeitemnumber>$@NULL@$</completiongradeitemnumber>\n'
                    f'  <completionview>0</completionview>\n'
                    f'  <completionexpected>0</completionexpected>\n'
                    f'  <availability>$@NULL@$</availability>\n'
                    f'  <showdescription>0</showdescription>\n'
                    f'  <tags></tags>\n'
                    f'</module>'
                )
                for stub_name in ('inforef.xml', 'grades.xml', 'roles.xml',
                                  'filters.xml', 'comments.xml', 'competencies.xml'):
                    activity_files[f'activities/page_{pid}/{stub_name}'] = _mbz_stub(stub_name)

                activity_entries.append(
                    f'<activity>'
                    f'<modulename>page</modulename>'
                    f'<sectionid>{sid}</sectionid>'
                    f'<sectionnumber>{sid}</sectionnumber>'
                    f'<title>{html_lib.escape(p_title)}</title>'
                    f'<directory>activities/page_{pid}</directory>'
                    f'</activity>'
                )
                settings_extra += (
                    f'<setting><level>activity</level><activity>page_{pid}</activity>'
                    f'<name>page_{pid}_included</name><value>1</value></setting>'
                    f'<setting><level>activity</level><activity>page_{pid}</activity>'
                    f'<name>page_{pid}_userinfo</name><value>0</value></setting>'
                )

        seq = ','.join(page_ids_in_section)
        section_files[f'sections/section_{sid}/section.xml'] = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<section id="{sid}">\n'
            f'  <number>{sid}</number>\n'
            f'  <name>{html_lib.escape(mod["title"])}</name>\n'
            f'  <summary>{html_lib.escape(mod.get("description", ""))}</summary>\n'
            f'  <summaryformat>1</summaryformat>\n'
            f'  <sequence>{seq}</sequence>\n'
            f'  <visible>1</visible>\n'
            f'  <availabilityjson>$@NULL@$</availabilityjson>\n'
            f'  <timemodified>{now}</timemodified>\n'
            f'</section>'
        )
        section_files[f'sections/section_{sid}/inforef.xml'] = _mbz_stub('inforef.xml')
        section_entries.append(
            f'<section>'
            f'<sectionid>{sid}</sectionid>'
            f'<title>{html_lib.escape(mod["title"])}</title>'
            f'<directory>sections/section_{sid}</directory>'
            f'</section>'
        )
        settings_extra += (
            f'<setting><level>section</level><section>section_{sid}</section>'
            f'<name>section_{sid}_included</name><value>1</value></setting>'
            f'<setting><level>section</level><section>section_{sid}</section>'
            f'<name>section_{sid}_userinfo</name><value>0</value></setting>'
        )

    # Section 0 is always required
    section_files['sections/section_0/section.xml'] = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<section id="0">\n'
        f'  <number>0</number>\n'
        f'  <name></name>\n'
        f'  <summary>{html_lib.escape(course_desc)}</summary>\n'
        f'  <summaryformat>1</summaryformat>\n'
        f'  <sequence></sequence>\n'
        f'  <visible>1</visible>\n'
        f'  <availabilityjson>$@NULL@$</availabilityjson>\n'
        f'  <timemodified>{now}</timemodified>\n'
        f'</section>'
    )
    section_files['sections/section_0/inforef.xml'] = _mbz_stub('inforef.xml')
    section_entries.insert(0,
        '<section><sectionid>0</sectionid><title></title>'
        '<directory>sections/section_0</directory></section>'
    )

    num_sections = section_id - 1

    course_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<course id="1" contextid="1">
  <shortname>{html_lib.escape(short_name)}</shortname>
  <fullname>{html_lib.escape(course_title)}</fullname>
  <idnumber></idnumber>
  <summary>{html_lib.escape(course_desc)}</summary>
  <summaryformat>1</summaryformat>
  <format>topics</format>
  <showgrades>1</showgrades>
  <newsitems>5</newsitems>
  <startdate>{now}</startdate>
  <enddate>0</enddate>
  <marker>0</marker>
  <maxbytes>0</maxbytes>
  <legacyfiles>0</legacyfiles>
  <showreports>0</showreports>
  <visible>1</visible>
  <groupmode>0</groupmode>
  <groupmodeforce>0</groupmodeforce>
  <defaultgroupingid>0</defaultgroupingid>
  <lang></lang>
  <theme></theme>
  <timecreated>{now}</timecreated>
  <timemodified>{now}</timemodified>
  <requested>0</requested>
  <enablecompletion>0</enablecompletion>
  <completionnotify>0</completionnotify>
  <hiddensections>0</hiddensections>
  <courseformatoptions>
    <courseformatoption><name>numsections</name><value>{num_sections}</value></courseformatoption>
    <courseformatoption><name>hiddensections</name><value>0</value></courseformatoption>
    <courseformatoption><name>coursedisplay</name><value>0</value></courseformatoption>
  </courseformatoptions>
  <category id="1">
    <name>Miscellaneous</name>
    <description></description>
  </category>
  <tags></tags>
</course>"""

    backup_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<moodle_backup>
  <information>
    <name>backup.mbz</name>
    <moodle_version>2022041900</moodle_version>
    <moodle_release>Moodle 4.0+ (Build: 20220419)</moodle_release>
    <backup_version>2022041900</backup_version>
    <backup_release>4.0</backup_release>
    <backup_date>{now}</backup_date>
    <mnet_remoteusers>0</mnet_remoteusers>
    <include_files>1</include_files>
    <include_file_references_to_external_content>0</include_file_references_to_external_content>
    <original_wwwroot>https://skooled-ai.webprvw.xyz</original_wwwroot>
    <original_site_identifier_hash>{uuid.uuid4().hex}</original_site_identifier_hash>
    <original_course_id>1</original_course_id>
    <original_course_fullname>{html_lib.escape(course_title)}</original_course_fullname>
    <original_course_shortname>{html_lib.escape(short_name)}</original_course_shortname>
    <original_course_startdate>0</original_course_startdate>
    <original_course_enddate>0</original_course_enddate>
    <original_course_contextid>1</original_course_contextid>
    <original_system_contextid>1</original_system_contextid>
    <contents>
      <activities>{''.join(activity_entries)}</activities>
      <sections>{''.join(section_entries)}</sections>
      <course>
        <courseid>1</courseid>
        <title>{html_lib.escape(course_title)}</title>
        <directory>course</directory>
      </course>
    </contents>
    <settings>
      <setting><level>root</level><name>filename</name><value>backup.mbz</value></setting>
      <setting><level>root</level><name>imscc_files</name><value>0</value></setting>
      <setting><level>root</level><name>users</name><value>0</value></setting>
      <setting><level>root</level><name>anonymize</name><value>0</value></setting>
      <setting><level>root</level><name>role_assignments</name><value>0</value></setting>
      <setting><level>root</level><name>activities</name><value>1</value></setting>
      <setting><level>root</level><name>blocks</name><value>0</value></setting>
      <setting><level>root</level><name>filters</name><value>0</value></setting>
      <setting><level>root</level><name>comments</name><value>0</value></setting>
      <setting><level>root</level><name>badges</name><value>0</value></setting>
      <setting><level>root</level><name>calendarevents</name><value>0</value></setting>
      <setting><level>root</level><name>userscompletion</name><value>0</value></setting>
      <setting><level>root</level><name>logs</name><value>0</value></setting>
      <setting><level>root</level><name>grade_histories</name><value>0</value></setting>
      <setting><level>root</level><name>questionbank</name><value>0</value></setting>
      <setting><level>root</level><name>groups</name><value>0</value></setting>
      <setting><level>root</level><name>competencies</name><value>0</value></setting>
      {settings_extra}
    </settings>
  </information>
</moodle_backup>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('moodle_backup.xml', backup_xml.encode('utf-8'))
        zf.writestr('course/course.xml', course_xml.encode('utf-8'))
        zf.writestr('course/inforef.xml', _mbz_stub('inforef.xml').encode('utf-8'))
        for path, content in section_files.items():
            zf.writestr(path, content.encode('utf-8'))
        for path, content in activity_files.items():
            zf.writestr(path, content.encode('utf-8'))
    buf.seek(0)
    return buf


def _mbz_stub(fname: str) -> str:
    return {
        'inforef.xml':      '<?xml version="1.0" encoding="UTF-8"?>\n<inforef><fileref></fileref></inforef>',
        'grades.xml':       '<?xml version="1.0" encoding="UTF-8"?>\n<activity_gradebook><grade_items></grade_items><grade_letters></grade_letters></activity_gradebook>',
        'roles.xml':        '<?xml version="1.0" encoding="UTF-8"?>\n<roles><role_overrides></role_overrides><role_assignments></role_assignments></roles>',
        'filters.xml':      '<?xml version="1.0" encoding="UTF-8"?>\n<filters><filter_actives></filter_actives><filter_configs></filter_configs></filters>',
        'comments.xml':     '<?xml version="1.0" encoding="UTF-8"?>\n<comments></comments>',
        'competencies.xml': '<?xml version="1.0" encoding="UTF-8"?>\n<course_competencies><competencies></competencies><settings></settings></course_competencies>',
    }.get(fname, '<?xml version="1.0" encoding="UTF-8"?>\n<empty/>')
