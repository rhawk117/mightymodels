"""Findings, questions and probe tools the forms suites build from.

A resolver's annotations are read at runtime by the SDK, so every name in a resolver signature
is a module-level plain assignment here rather than a `TYPE_CHECKING` import.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Literal

from mcp.server.mcpserver.resolve import Elicit, Resolve
from mcp.types import ElicitRequestFormParams, ElicitResult, ToolAnnotations
from mightymodels_core.primitives import RedactedText
from mightymodels_core.reviews.records import FindingRecord
from mightymodels_mcp.forms.choices import (
    Choice,
    ChoiceOutcome,
    ChoiceQuestion,
    ChoiceRound,
    answers_of,
    complete_request,
)
from mightymodels_mcp.forms.needs_input import needs_input_text
from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.server.registration import ToolCatalog, ToolDefinition
from mightymodels_mcp.server.requests import RequestModel
from pydantic import BaseModel

if TYPE_CHECKING:
    from mcp.client.session import ClientRequestContext
    from mcp.types import ElicitRequestParams
    from mightymodels_core.vocabulary.reviews import StoredSeverity
    from mightymodels_mcp.server.registration import ToolContext

CHAIN_TOOL = 'probe_chain'

type ElicitAction = Literal['accept', 'decline', 'cancel']
MODE = ChoiceQuestion(
    argument='mode',
    title='Which review mode?',
    description='How the review reads the change.',
    choices=(Choice(value='quick', title='Quick pass'), Choice(value='deep', title='Deep read')),
)
DEPTH = ChoiceQuestion(
    argument='depth',
    title='Which depth?',
    description='How far the review looks past the diff.',
    choices=(Choice(value='diff', title='The diff'), Choice(value='branch', title='The branch')),
)
REVIEW_ROUND = ChoiceRound(message='Choose how to review', questions=(MODE, DEPTH))


def create_finding(position: int, severity: StoredSeverity = 'High') -> FindingRecord:
    return FindingRecord(
        key=f'MV-{position}',
        sources=('merge-vader', 'uncle-bob'),
        severity=severity,
        kind='defect',
        security=False,
        title=RedactedText(f'finding {position} summary'),
        location=RedactedText(f'src/module.py:{position}'),
        fix=RedactedText(f'apply fix {position}'),
        verify=RedactedText('uv run pytest'),
        evidence=None,
        conflict=None,
    )


def create_findings(count: int) -> tuple[FindingRecord, ...]:
    return tuple(create_finding(position) for position in range(1, count + 1))


class ChainRequest(RequestModel):
    slug: str
    mode: str | None = None
    depth: str | None = None


class ChainView(BaseModel):
    text: str


RoundAsk = Elicit[BaseModel] | BaseModel


@dataclass(slots=True, kw_only=True, frozen=True)
class ModeAsker:
    def ask(self, request: ChainRequest) -> RoundAsk:
        round_ = ChoiceRound(message='Choose a mode', questions=(MODE,))
        return round_.omitted_by(request).ask()


MODE_RESOLVER = Resolve(ModeAsker().ask)
ModeOutcome = Annotated[ChoiceOutcome, MODE_RESOLVER]


@dataclass(slots=True, kw_only=True, frozen=True)
class DepthAsker:
    def ask(self, request: ChainRequest, mode: ModeOutcome) -> RoundAsk:
        answers = answers_of(mode)
        if answers is None:
            return ChoiceRound(message='Nothing to ask', questions=()).ask()

        chosen = answers.get('mode') or request.mode
        round_ = ChoiceRound(message=f'Choose a depth for the {chosen} review', questions=(DEPTH,))
        return round_.omitted_by(request).ask()


DEPTH_RESOLVER = Resolve(DepthAsker().ask)


@dataclass(slots=True, kw_only=True, frozen=True)
class ChainTool:
    handled: list[str] = field(default_factory=list)

    async def run(
        self,
        request: ChainRequest,
        _: ToolContext,
        *,
        mode: ChoiceOutcome,
        depth: ChoiceOutcome,
    ) -> ChainView:
        """Choose a mode, then a depth that depends on it."""
        self.handled.append(request.slug)
        with_mode = complete_request(request, mode)
        chosen = complete_request(with_mode, depth) if with_mode else None
        if chosen is None:
            return ChainView(text=needs_input_text(REVIEW_ROUND.omitted_by(request).questions))

        return ChainView(text=f'{chosen.mode} {chosen.depth}')


def create_chain_catalog(tool: ChainTool) -> ToolCatalog:
    definition = ToolDefinition(
        name=CHAIN_TOOL,
        title='Probe chain',
        annotations=ToolAnnotations(
            read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        ),
        icon=load_icon('server'),
        request_model=ChainRequest,
        result_model=ChainView,
        handler=tool.run,
        resolvers={'mode': MODE_RESOLVER, 'depth': DEPTH_RESOLVER},
    )
    return ToolCatalog().register(definition)


@dataclass(slots=True, kw_only=True, frozen=True)
class ScriptedAnswerer:
    answers: dict[str, str]
    action: ElicitAction = 'accept'
    messages: list[str] = field(default_factory=list)

    async def answer(
        self, context: ClientRequestContext, params: ElicitRequestParams
    ) -> ElicitResult:
        assert context
        assert isinstance(params, ElicitRequestFormParams)
        self.messages.append(params.message)
        if self.action != 'accept':
            return ElicitResult(action=self.action)

        properties = params.requested_schema['properties']
        return ElicitResult(
            action='accept', content={name: self.answers[name] for name in properties}
        )
