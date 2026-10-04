import re
from dataclasses import dataclass
from xml.parsers import expat

from vibe_code_cli.findings import Finding, error, warning

# House style from the reference agent template: these sections, in this order, directly under
# the frontmatter.
REQUIRED_SECTIONS = (
    'role',
    'context',
    'workflow',
    'constraints',
    'output_format',
    'verification',
)
OPTIONAL_SECTIONS = frozenset({'examples', 'escalation', 'tools_guidance'})
VOCABULARY = frozenset(REQUIRED_SECTIONS) | OPTIONAL_SECTIONS

SECTION_TAG = re.compile(r'<(/?)([a-z_]+)>')
FENCE = re.compile(r'^\s*```')
INLINE_CODE = re.compile(r'`[^`\n]*`')
ROOT_WRAPPER = re.compile(r'\s*<([a-z_]+)>')
BARE_AMPERSAND = re.compile(r'&(?![a-zA-Z]+;|#\d+;)')
XML_DECLARATION = re.compile(r'<!\s*(?:doctype|entity)\b', re.IGNORECASE)
FINAL_CHUNK = True
MODEL_DIRECTIVE = re.compile(r'\bMODEL REQUIREMENT\b|\bMUST only be run with\b')


@dataclass(frozen=True)
class Tag:
    line: int
    name: str
    closing: bool


@dataclass(frozen=True)
class SectionScan:
    top_level: list[str]
    findings: list[Finding]


def check_body(body: str) -> list[Finding]:
    if not body.strip():
        return [error("the body is empty; it is the agent's system prompt")]
    tags = section_tags(body)
    scan = scan_sections([tag for tag in tags if tag.name in VOCABULARY])
    return [
        *scan.findings,
        *check_stray_tags(tags),
        *check_required_sections(scan.top_level),
        *check_root_wrapper(body),
        *check_strict_xml(body),
        *check_model_directive(body),
    ]


def section_tags(body: str) -> list[Tag]:
    """Tags outside fenced blocks and inline code, with their body line numbers."""
    tags: list[Tag] = []
    inside_fence = False
    for number, line in enumerate(body.splitlines(), start=1):
        if FENCE.match(line):
            inside_fence = not inside_fence
        elif not inside_fence:
            tags.extend(
                Tag(number, name, closing=bool(slash))
                for slash, name in SECTION_TAG.findall(INLINE_CODE.sub('', line))
            )
    return tags


def scan_sections(tags: list[Tag]) -> SectionScan:
    open_sections: list[str] = []
    top_level: list[str] = []
    findings: list[Finding] = []
    for tag in tags:
        if not tag.closing:
            if not open_sections:
                top_level.append(tag.name)
            open_sections.append(tag.name)
        elif open_sections and open_sections[-1] == tag.name:
            open_sections.pop()
        else:
            current = open_sections[-1] if open_sections else 'none'
            findings.append(
                error(f'line {tag.line} closes </{tag.name}> but the open section is <{current}>')
            )
    findings.extend(error(f'<{name}> is never closed') for name in open_sections)
    return SectionScan(top_level, findings)


def check_stray_tags(tags: list[Tag]) -> list[Finding]:
    strays = sorted({tag.name for tag in tags} - VOCABULARY)
    return [
        warning(
            f'<{stray}> is not a section tag; if it is a placeholder '
            f'write it as {stray.upper()} so it cannot be read as markup'
        )
        for stray in strays
    ]


def check_required_sections(top_level: list[str]) -> list[Finding]:
    missing = [section for section in REQUIRED_SECTIONS if section not in top_level]
    present = [section for section in top_level if section in REQUIRED_SECTIONS]
    if missing:
        return [error(f'required section <{section}> is missing') for section in missing]
    if present != list(REQUIRED_SECTIONS):
        return [error(f'required sections out of order: {present}')]
    return []


def check_root_wrapper(body: str) -> list[Finding]:
    wrapper = ROOT_WRAPPER.match(body)
    if (
        wrapper is None
        or wrapper[1] in VOCABULARY
        or not body.rstrip().endswith(f'</{wrapper[1]}>')
    ):
        return []
    return [
        error(
            f'body is wrapped in a single root element <{wrapper[1]}>; '
            'sections must sit directly under the frontmatter'
        )
    ]


def check_strict_xml(body: str) -> list[Finding]:
    escaped = BARE_AMPERSAND.sub('&amp;', body)
    if XML_DECLARATION.search(escaped):
        return [warning('document and entity declarations are not supported in agent bodies')]
    parser = expat.ParserCreate()
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    try:
        parser.Parse(f'<agent>{escaped}</agent>', FINAL_CHUNK)
    except expat.ExpatError as problem:
        return [
            warning(
                f'not strictly parseable ({problem}); if section tags balance above, '
                "a bare '<' or '&' in Markdown is the cause and is acceptable"
            )
        ]
    return []


def check_model_directive(body: str) -> list[Finding]:
    if MODEL_DIRECTIVE.search(body) is None:
        return []
    return [
        warning(
            'body contains a model-requirement directive; agents have executed '
            'such prose by spawning a nested model'
        )
    ]
