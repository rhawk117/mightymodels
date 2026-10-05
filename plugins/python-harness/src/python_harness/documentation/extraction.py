"""Extraction of one symbol's definition or section from an official page as Markdown."""

from itertools import takewhile
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify

from python_harness.documentation.domain import DocumentationUrl
from python_harness.documentation.errors import (
    EmptyExtractionError,
    MissingAnchorError,
    MissingDefinitionBodyError,
    MissingSectionError,
)

REMOVED_NODES = 'a.headerlink, script, style, nav'


def is_signature(element: Tag) -> bool:
    return element.name == 'dt'


def leading_signatures(description: Tag) -> list[Tag]:
    elements = (node for node in description.previous_siblings if isinstance(node, Tag))
    return list(takewhile(is_signature, elements))


def definition_html(anchor: Tag) -> str:
    description = anchor.find_next_sibling('dd')
    if not isinstance(description, Tag):
        raise MissingDefinitionBodyError
    signatures = ''.join(map(str, reversed(leading_signatures(description))))
    return f'<dl>{signatures}{description}</dl>'


def section_html(document: BeautifulSoup, fragment: str) -> str:
    anchor = document.find(id=unquote(fragment)) if fragment else None
    if not isinstance(anchor, Tag):
        raise MissingAnchorError(fragment)
    definition = anchor if anchor.name == 'dt' else anchor.find_parent('dt')
    if isinstance(definition, Tag):
        return definition_html(definition)
    section = anchor if anchor.name == 'section' else anchor.find_parent('section')
    if not isinstance(section, Tag):
        raise MissingSectionError
    return str(section)


def absolutize_links(section: BeautifulSoup, page_url: str) -> None:
    for link in section.select('a[href]'):
        link['href'] = urljoin(page_url, str(link['href']))
    for image in section.select('img[src]'):
        image['src'] = urljoin(page_url, str(image['src']))


def extract_markdown(content: bytes, source_url: DocumentationUrl) -> str:
    document = BeautifulSoup(content, 'html.parser')
    section = BeautifulSoup(section_html(document, source_url.fragment), 'html.parser')
    for node in section.select(REMOVED_NODES):
        node.decompose()
    absolutize_links(section, source_url.page_url.root)
    result = markdownify(str(section), heading_style='ATX').strip()
    if not result:
        raise EmptyExtractionError
    return result
