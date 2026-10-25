from mightymodels_core.primitives import Slug, create_routing_table, redact
from mightymodels_core.reviews import AddedFindings, RunListing
from mightymodels_core.similarity.records import Duplicate, Match
from mightymodels_mcp.review.views import (
    NO_RUNS,
    render_added,
    render_listing,
    render_overridden,
    render_started,
)

from tests.mcp.review.review_builders import RUN, create_finding, create_run, create_summary


class TestStartedAndOverridden:
    def test_started_names_the_run_directory_and_models(self) -> None:
        view = render_started(create_run(), '.mightymodels/reviews/20260101-000001')

        assert view.text == (
            'run 20260101-000001 at .mightymodels/reviews/20260101-000001\n'
            'standard review: merge-vader on opus, uncle-bob on opus\n'
        )
        assert view.run_id == RUN
        assert view.verdict is None

    def test_overridden_names_the_heavier_reviewer_and_effort(self) -> None:
        view = render_overridden(create_run(), create_routing_table())

        assert view.text == (
            'run 20260101-000001: merge-vader on fable\ndispatch it with effort high\n'
        )
        assert view.run_id == RUN


class TestAdded:
    def test_added_lists_the_recorded_findings_and_the_reopened(self) -> None:
        added = AddedFindings(
            received=3,
            changed=(create_finding(1), create_finding(2)),
            reopened=('F2',),
            duplicates=(),
        )

        assert render_added(RUN, added).text == (
            '3 findings in, 2 recorded: F1, F2; back to undecided: F2\n'
        )

    def test_added_with_nothing_changed_says_none(self) -> None:
        added = AddedFindings(received=1, changed=(), reopened=(), duplicates=())

        assert render_added(RUN, added).text == '1 findings in, 0 recorded: none\n'

    def test_added_shows_a_near_duplicate_on_one_line(self) -> None:
        earlier = Match(
            kind='review-finding',
            reference='20251231-000001 F4',
            text=redact('first line\nsecond  line ' + 'x' * 200),
            overlap=0.876,
        )
        added = AddedFindings(
            received=1,
            changed=(create_finding(1),),
            reopened=(),
            duplicates=(Duplicate(written='20260101-000001 F1', earlier=earlier),),
        )

        lines = render_added(RUN, added).text.splitlines()

        assert lines[1].startswith(
            'near-duplicate: 20260101-000001 F1 resembles review-finding 20251231-000001 F4 '
            '(overlap 0.88): first line second line xxx'
        )
        assert lines[1].endswith('...')


class TestListing:
    def test_listing_without_runs_says_so(self) -> None:
        view = render_listing(RunListing(runs=(), older_left_out=False), 50)

        assert view.text == NO_RUNS
        assert view.run_id is None

    def test_listing_shows_a_line_per_run(self) -> None:
        runs = (
            create_summary('20260101-000002', slug=Slug('probe'), findings=2, verdict='BLOCK'),
            create_summary('20260101-000001', slug=None, findings=0),
        )

        view = render_listing(RunListing(runs=runs, older_left_out=False), 50)

        assert view.text == (
            '20260101-000002\tprobe\tstandard\t2 findings\tBLOCK\n'
            '20260101-000001\t-\tstandard\t0 findings\tCLEAR\n'
        )

    def test_listing_says_when_older_runs_are_left_out(self) -> None:
        runs = (create_summary('20260101-000001', slug=None, findings=0),)

        view = render_listing(RunListing(runs=runs, older_left_out=True), 50)

        assert view.text.endswith('\nolder review runs are left out: these are the latest 50\n')
