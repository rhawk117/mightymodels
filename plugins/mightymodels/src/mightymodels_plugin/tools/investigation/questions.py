"""The question `investigation` puts to the user when `start` leaves the kind of target out.

`AskedKind` is a plain assignment because the SDK does not see a `Resolve` marker behind a PEP 695
`type` alias and would put the parameter in the tool's schema.
"""

from typing import Annotated

from mcp.server.elicitation import ElicitationResult
from mcp.server.mcpserver import Elicit, Resolve

from mightymodels_plugin.tools.asking import Choice, Question, enumerated
from mightymodels_plugin.tools.investigation.schema import (
    InvestigationAction,
    InvestigationPayload,
    InvestigationStartRequest,
    TargetKind,
)

KindChoices = Annotated[TargetKind, enumerated(TargetKind)]
KindAnswer = Choice[KindChoices]


def kind_question(target: str) -> Question:
    return Question(
        message=f'What kind of target is this? {target}',
        answer=KindAnswer,
        argument='payload.request.kind',
    )


def ask_kind(
    action: InvestigationAction, payload: InvestigationPayload | None
) -> KindAnswer | Elicit[KindAnswer]:
    request = None if payload is None else payload.request
    if action is not InvestigationAction.START or not isinstance(
        request, InvestigationStartRequest
    ):
        return KindAnswer(choice=None)
    if request.kind is not None:
        return KindAnswer(choice=None)
    return Elicit(kind_question(request.target).message, KindAnswer)


AskedKind = Annotated[ElicitationResult[KindAnswer], Resolve(ask_kind)]
