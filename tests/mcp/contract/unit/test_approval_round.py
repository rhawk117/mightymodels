from mightymodels_mcp.contract.schemas import ContractApproveRequest
from mightymodels_mcp.contract.tools import create_approval_round

COMMAND_TEXT = 'T1.check: uv run pytest'


def create_request() -> ContractApproveRequest:
    return ContractApproveRequest.model_validate({
        'slug': 'probe-ticket',
        'commands': ({'id': 'T1.check', 'argv': ('uv', 'run', 'pytest')},),
    })


class TestCreateApprovalRound:
    def test_command_text_occurs_once_across_message_and_question_titles(self) -> None:
        approval_round = create_approval_round(create_request())
        shown = [approval_round.message, *(question.title for question in approval_round.questions)]

        assert sum(text.count(COMMAND_TEXT) for text in shown) == 1

    def test_question_title_carries_the_commands(self) -> None:
        approval_round = create_approval_round(create_request())

        assert COMMAND_TEXT in approval_round.questions[0].title
