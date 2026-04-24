"""
LMS Course Package Exporters
Generates Moodle .mbz, Canvas .imscc, and Brightspace .zip from module content.
"""
import html as html_lib
import io
import re
import uuid
import zipfile
from datetime import datetime


def _safe_id(s: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]', '_', s)[:32]


def _html_page(title: str, content: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html_lib.escape(title)}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:820px;margin:40px auto;padding:0 24px;color:#1a1a2e;line-height:1.75;}}
h1{{color:#1e3a5f;border-bottom:3px solid #4a90d9;padding-bottom:12px;margin-bottom:24px;}}
h2{{color:#2d5a8e;margin-top:2em;padding-top:0.5em;border-top:1px solid #e2e8f0;}}
h3{{color:#3a7ab8;margin-top:1.5em;}}
blockquote{{background:#f0f7ff;border-left:4px solid #4a90d9;margin:16px 0;padding:14px 20px;border-radius:0 8px 8px 0;font-style:italic;}}
table{{width:100%;border-collapse:collapse;margin:16px 0;}}
th{{background:#1e3a5f;color:#fff;padding:10px 14px;text-align:left;}}
td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;}}
tr:nth-child(even) td{{background:#f8fafc;}}
ul,ol{{padding-left:1.5em;}}
li{{margin-bottom:6px;}}
strong{{color:#1e3a5f;}}
.objectives li{{background:#f0fdf4;border-left:3px solid #22c55e;padding:8px 12px;border-radius:0 6px 6px 0;list-style:none;margin-bottom:8px;}}
.objectives{{padding-left:0;}}
.check-q li{{background:#fefce8;border-left:3px solid #eab308;padding:10px 14px;border-radius:0 6px 6px 0;margin-bottom:10px;}}
.check-q{{padding-left:0;}}
.activity{{background:#f5f3ff;border:1px solid #ddd6fe;border-radius:8px;padding:16px 20px;margin-bottom:16px;}}
.activity h4{{color:#6d28d9;margin:0 0 8px;}}
</style>
</head>
<body>
<h1>{html_lib.escape(title)}</h1>
{content}
</body>
</html>"""


# ── IMS Common Cartridge 1.1 — Canvas & Brightspace ──────────────────────────

def build_imscc(course_data: dict, platform: str = 'canvas') -> io.BytesIO:
    """
    Build an IMS Common Cartridge 1.1 (.imscc) package.
    platform: 'canvas' | 'brightspace'
    """
    course_title = course_data.get('course_title', 'Untitled Course')
    course_desc  = course_data.get('course_description', '')
    modules      = course_data.get('modules', [])

    items_xml     = ''
    resources_xml = ''
    files         = {}

    for mod in modules:
        mod_id   = _safe_id(mod['id'])
        mod_items = ''
        for sub in mod.get('submodules', []):
            sub_id    = _safe_id(sub['id'])
            res_id    = f'RES_{sub_id}'
            file_path = f'{mod_id}/{sub_id}.html'
            mod_items += (
                f'<item identifier="{sub_id}" identifierref="{res_id}">'
                f'<title>{html_lib.escape(sub["title"])}</title>'
                f'</item>\n'
            )
            resources_xml += (
                f'<resource identifier="{res_id}" type="webcontent" href="{file_path}">'
                f'<file href="{file_path}"/>'
                f'</resource>\n'
            )
            files[file_path] = _html_page(sub['title'], sub.get('content_html', ''))

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
            d2l_meta = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<Properties Version="1.0">\n'
                f'  <Property Name="Title" Value="{html_lib.escape(course_title)}"/>\n'
                '</Properties>'
            )
            zf.writestr('d2l_content.xml', d2l_meta.encode('utf-8'))
    buf.seek(0)
    return buf


# ── Moodle Backup .mbz ────────────────────────────────────────────────────────

def build_moodle_mbz(course_data: dict) -> io.BytesIO:
    """Build a Moodle 4.x-compatible backup (.mbz) package."""
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
            pid = page_id
            page_id += 1
            page_ids_in_section.append(str(pid))
            p_title   = html_lib.escape(sub['title'])
            p_content = sub.get('content_html', '')

            activity_files[f'activities/page_{pid}/page.xml'] = (
                f'<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<activity id="{pid}" moduleid="{pid}" modulename="page" contextid="{pid}">\n'
                f'  <page id="{pid}">\n'
                f'    <name>{p_title}</name>\n'
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
                f'<title>{p_title}</title>'
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

    # Section 0 is always required (general/intro section)
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
