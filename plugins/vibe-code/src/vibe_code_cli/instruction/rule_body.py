import re
from xml.parsers import expat

from vibe_code_cli.findings import Finding, error, warning
from vibe_code_cli.subagent.body import Tag, scan_sections, section_tags

REQUIRED_SECTIONS = ('scope', 'conventions', 'examples', 'anti_patterns', 'verification')
OPTIONAL_SECTIONS = frozenset({'rationale'})
VOCABULARY = frozenset(REQUIRED_SECTIONS) | OPTIONAL_SECTIONS
LINE_LIMIT = 200
EMPHASIS_LIMIT = 1

ROOT_WRAPPER = re.compile(r'\s*<([a-z_]+)>')
EMPHASIS = re.compile(r'\b(?:IMPORTANT|ALWAYS|NEVER|MUST)\b')
BARE_AMPERSAND = re.compile(r'&(?![a-zA-Z]+;|#\d+;)')
XML_DECLARATION = re.compile(r'<!\s*(?:doctype|entity)\b', re.IGNORECASE)
FINAL_CHUNK = True


def check_body(body: str) -> list[Finding]:
    tags = section_tags(body)
    scan = scan_sections([tag for tag in tags if tag.name in VOCABULARY])
    return [
        *scan.findings,
        *check_stray_tags(tags),
        *check_required_sections(scan.top_level),
        *check_root_wrapper(body),
        *check_size(body),
        *check_emphasis(body),
        *check_strict_xml(body),
    ]


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


def check_size(body: str) -> list[Finding]:
    lines = body.count('\n') + 1
    if lines <= LINE_LIMIT:
        return []
    return [
        warning(f'{lines} lines; this loads whenever the rule applies, aim well under {LINE_LIMIT}')
    ]


def check_emphasis(body: str) -> list[Finding]:
    count = len(EMPHASIS.findall(body))
    if count <= EMPHASIS_LIMIT:
        return []
    return [
        warning(
            f'{count} emphasis markers (IMPORTANT/ALWAYS/NEVER/MUST); '
            'one per file at most keeps the one that matters visible'
        )
    ]


def check_strict_xml(body: str) -> list[Finding]:
    escaped = BARE_AMPERSAND.sub('&amp;', body)
    if XML_DECLARATION.search(escaped):
        return [warning('document and entity declarations are not supported in rule bodies')]
    parser = expat.ParserCreate()
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    try:
        parser.Parse(f'<rule>{escaped}</rule>', FINAL_CHUNK)
    except expat.ExpatError as problem:
        return [
            warning(
                f'not strictly parseable ({problem}); if section tags balance above, '
                "a bare '<' or '&' in Markdown is the cause and is acceptable"
            )
        ]
    return []
