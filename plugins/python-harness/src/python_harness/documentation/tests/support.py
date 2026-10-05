"""Synthetic docs.python.org content: a Sphinx inventory, official-style pages, a site."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import anyio
import httpx
import sphobjinv

if TYPE_CHECKING:
    from collections.abc import Callable

DOCS_VERSION = '3.13'
FILLER_SENTENCE = 'Path manipulation functions operate on strings or bytes objects. '
MODULE_INTRODUCTION = FILLER_SENTENCE * 40

OS_PATH_PAGE = f"""<html><body>
<section id="os-path-common-pathname-manipulations">
<h1>os.path: Common pathname manipulations</h1>
<span id="module-os.path"></span>
<p>{MODULE_INTRODUCTION}</p>
<dl class="py function">
<dt class="sig" id="os.path.join">os.path.join(path, *paths)
<a class="headerlink" href="#os.path.join">#</a></dt>
<dd><p>Join one or more path segments, see <a href="os.html#os.sep">os.sep</a>.</p></dd>
</dl>
<dl class="py function">
<dt class="sig" id="os.path.isfile">os.path.isfile(path)</dt>
<dd><p>Return True if path is an existing regular file.</p></dd>
</dl>
</section>
<script>tracking()</script>
</body></html>"""

DATAMODEL_PAGE = """<html><body><section id="data-model">
<dl class="py method">
<dt class="sig" id="object.__getattr__">object.__getattr__(self, name)</dt>
<dd><p>Called when the default attribute access fails.</p></dd>
</dl>
</section></body></html>"""

EMPTY_ANCHOR_PAGE = '<html><body><section id="intro"></section></body></html>'


@dataclass(frozen=True, slots=True, kw_only=True)
class InventoryEntry:
    name: str
    uri: str
    role: str = 'function'
    domain: str = 'py'
    indexed: bool = True

    def as_data_object(self) -> sphobjinv.DataObjStr:
        return cast('Callable[..., sphobjinv.DataObjStr]', sphobjinv.DataObjStr)(
            name=self.name,
            domain=self.domain,
            role=self.role,
            priority='1',
            uri=self.uri,
            dispname='-',
        )


STANDARD_ENTRIES = (
    InventoryEntry(name='os.path', role='module', uri='library/os.path.html#module-$'),
    InventoryEntry(name='os.path.join', uri='library/os.path.html#$'),
    InventoryEntry(name='os.path.isfile', uri='library/os.path.html#$'),
    InventoryEntry(name='collections.OrderedDict', role='class', uri='library/collections.html#$'),
    InventoryEntry(name='collections.defaultdict', role='class', uri='library/collections.html#$'),
    InventoryEntry(name='collections.namedtuple', uri='library/collections.html#$'),
    InventoryEntry(name='typing.NamedTuple', role='class', uri='library/typing.html#$'),
    InventoryEntry(name='json.loads', uri='library/json.html#$'),
    InventoryEntry(name='asyncio.gather', uri='library/asyncio-task.html#$'),
    InventoryEntry(name='len', uri='library/functions.html#$'),
    InventoryEntry(name='object.__getattr__', role='method', uri='reference/datamodel.html#$'),
    InventoryEntry(name='broken.anchor', uri='library/empty.html#$'),
    InventoryEntry(name='howto.only', uri='howto/logging.html#$', indexed=False),
    InventoryEntry(name='PyObject_GetAttr', domain='c', uri='c-api/object.html#$', indexed=False),
)
INDEXED_NAMES = frozenset(entry.name for entry in STANDARD_ENTRIES if entry.indexed)


def inventory_plaintext(entries: Iterable[InventoryEntry]) -> bytes:
    inventory = sphobjinv.Inventory()
    inventory.project = 'Python'
    inventory.version = DOCS_VERSION
    inventory.objects.extend(entry.as_data_object() for entry in entries)
    return inventory.data_file(contract=True)


def inventory_bytes(entries: Iterable[InventoryEntry] = STANDARD_ENTRIES) -> bytes:
    return sphobjinv.compress(inventory_plaintext(entries))


def standard_pages() -> dict[str, bytes]:
    prefix = f'/{DOCS_VERSION}'
    return {
        f'{prefix}/objects.inv': inventory_bytes(),
        f'{prefix}/library/os.path.html': OS_PATH_PAGE.encode(),
        f'{prefix}/reference/datamodel.html': DATAMODEL_PAGE.encode(),
        f'{prefix}/library/empty.html': EMPTY_ANCHOR_PAGE.encode(),
    }


@dataclass(slots=True, kw_only=True, eq=False)
class DocsSite:
    pages: Mapping[str, bytes]
    redirects: Mapping[str, str] = field(default_factory=dict)
    requested_urls: list[httpx.URL] = field(default_factory=list)

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requested_urls.append(request.url)
        location = self.redirects.get(str(request.url))
        if location is not None:
            return httpx.Response(httpx.codes.FOUND, headers={'Location': location})
        body = self.pages.get(request.url.path)
        if body is None:
            return httpx.Response(httpx.codes.NOT_FOUND)
        return httpx.Response(httpx.codes.OK, content=body)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.respond)

    def request_count(self, path: str) -> int:
        return sum(url.path == path for url in self.requested_urls)

    def requested_origins(self) -> set[tuple[str, str]]:
        return {(url.scheme, url.host) for url in self.requested_urls}


@dataclass(slots=True, kw_only=True, eq=False)
class RecordingLoader:
    delay_seconds: float = 0.0
    failure: Exception | None = None
    calls: int = 0

    async def __call__(self, key: str) -> str:
        self.calls += 1
        await anyio.sleep(self.delay_seconds)
        if self.failure is not None:
            raise self.failure
        return f'value:{key}'
