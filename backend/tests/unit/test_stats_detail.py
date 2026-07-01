"""DB-free unit tests for stats_detail pure metric functions."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import (
    Application,
    ApplicationEvent,
    ApplicationEventKind,
    ApplicationStatus,
    Interaction,
    InteractionChannel,
    InteractionDirection,
)
from app.services.stats_detail import (
    Ghost,
    Interview,
    MeanMedian,
    Outcomes,
    compute_decline_timeline,
    compute_declines_weekly,
    compute_ghost,
    compute_interview,
    compute_outcomes,
    compute_rejection_stage,
    compute_velocity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER_ID = uuid.uuid4()


def _app(
    status: ApplicationStatus, created_at: datetime, aid: uuid.UUID | None = None
) -> Application:
    return Application(
        id=aid or uuid.uuid4(),
        user_id=USER_ID,
        url="https://example.com/job",
        url_hash="h",
        status=status,
        created_at=created_at,
    )


def _ev(
    aid: uuid.UUID,
    to_value: str,
    occurred_at: datetime,
    from_value: str | None = None,
) -> ApplicationEvent:
    return ApplicationEvent(
        application_id=aid,
        kind=ApplicationEventKind.status_change,
        from_value=from_value,
        to_value=to_value,
        occurred_at=occurred_at,
    )


def _interaction(
    aid: uuid.UUID,
    occurred_at: datetime,
    direction: InteractionDirection = InteractionDirection.in_,
    channel: InteractionChannel = InteractionChannel.mail,
) -> Interaction:
    return Interaction(
        application_id=aid,
        occurred_at=occurred_at,
        direction=direction,
        channel=channel,
    )


# ---------------------------------------------------------------------------
# compute_outcomes
# ---------------------------------------------------------------------------


class TestComputeOutcomes:
    def test_empty(self):
        result = compute_outcomes([])
        assert result == Outcomes(
            active=0, accepted=0, offer=0, rejected=0, withdrawn=0, discarded=0, total=0
        )

    def test_single_rejected(self):
        a = _app(ApplicationStatus.rejected, datetime(2026, 1, 1))
        result = compute_outcomes([a])
        assert result.total == 1
        assert result.rejected == 1
        assert result.active == 0
        assert result.accepted == 0

    def test_active_excludes_terminals_and_offer(self):
        apps = [
            _app(ApplicationStatus.draft, datetime(2026, 1, 1)),
            _app(ApplicationStatus.applied, datetime(2026, 1, 2)),
            _app(ApplicationStatus.need_call, datetime(2026, 1, 3)),
            _app(ApplicationStatus.apply_direct, datetime(2026, 1, 4)),
            _app(ApplicationStatus.interview, datetime(2026, 1, 5)),
            _app(ApplicationStatus.offer, datetime(2026, 1, 6)),        # NOT active
            _app(ApplicationStatus.accepted, datetime(2026, 1, 7)),     # NOT active
            _app(ApplicationStatus.rejected, datetime(2026, 1, 8)),     # NOT active
            _app(ApplicationStatus.withdrawn, datetime(2026, 1, 9)),    # NOT active
            _app(ApplicationStatus.discarded, datetime(2026, 1, 10)),   # NOT active
        ]
        result = compute_outcomes(apps)
        assert result.total == 10
        assert result.active == 5
        assert result.offer == 1
        assert result.accepted == 1
        assert result.rejected == 1
        assert result.withdrawn == 1
        assert result.discarded == 1

    def test_all_active_statuses(self):
        apps = [
            _app(ApplicationStatus.draft, datetime(2026, 1, 1)),
            _app(ApplicationStatus.applied, datetime(2026, 1, 2)),
            _app(ApplicationStatus.need_call, datetime(2026, 1, 3)),
        ]
        result = compute_outcomes(apps)
        assert result.active == 3
        assert result.total == 3
        assert result.rejected == 0


# ---------------------------------------------------------------------------
# compute_declines_weekly
# ---------------------------------------------------------------------------


class TestComputeDeclinesWeekly:
    def test_empty(self):
        result = compute_declines_weekly([], [])
        assert result == []

    def test_rejected_app_uses_event_week(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.rejected, datetime(2026, 1, 1), aid)
        # event in 2026-W02
        ev = _ev(aid, "rejected", datetime(2026, 1, 5, tzinfo=UTC))
        result = compute_declines_weekly([a], [ev])
        assert len(result) == 1
        assert result[0].week == "2026-W02"
        assert result[0].rejected == 1
        assert result[0].withdrawn == 0
        assert result[0].discarded == 0

    def test_rejected_falls_back_to_created_at_when_no_event(self):
        a = _app(ApplicationStatus.rejected, datetime(2026, 1, 5))  # 2026-W02, no event
        result = compute_declines_weekly([a], [])
        assert len(result) == 1
        assert result[0].week == "2026-W02"
        assert result[0].rejected == 1

    def test_multiple_decline_kinds_in_same_week(self):
        aid1 = uuid.uuid4()
        aid2 = uuid.uuid4()
        aid3 = uuid.uuid4()
        a1 = _app(ApplicationStatus.rejected, datetime(2026, 1, 1), aid1)
        a2 = _app(ApplicationStatus.withdrawn, datetime(2026, 1, 1), aid2)
        a3 = _app(ApplicationStatus.discarded, datetime(2026, 1, 1), aid3)
        ev1 = _ev(aid1, "rejected", datetime(2026, 1, 5, tzinfo=UTC))
        ev2 = _ev(aid2, "withdrawn", datetime(2026, 1, 5, tzinfo=UTC))
        ev3 = _ev(aid3, "discarded", datetime(2026, 1, 5, tzinfo=UTC))
        result = compute_declines_weekly([a1, a2, a3], [ev1, ev2, ev3])
        assert len(result) == 1
        assert result[0].rejected == 1
        assert result[0].withdrawn == 1
        assert result[0].discarded == 1

    def test_sorted_ascending_by_week(self):
        aid1 = uuid.uuid4()
        aid2 = uuid.uuid4()
        a1 = _app(ApplicationStatus.rejected, datetime(2026, 1, 1), aid1)
        a2 = _app(ApplicationStatus.rejected, datetime(2026, 1, 1), aid2)
        ev1 = _ev(aid1, "rejected", datetime(2026, 1, 12, tzinfo=UTC))  # W03
        ev2 = _ev(aid2, "rejected", datetime(2026, 1, 5, tzinfo=UTC))   # W02
        result = compute_declines_weekly([a1, a2], [ev1, ev2])
        assert result[0].week < result[1].week

    def test_non_decline_statuses_excluded(self):
        a = _app(ApplicationStatus.applied, datetime(2026, 1, 5))
        result = compute_declines_weekly([a], [])
        assert result == []


# ---------------------------------------------------------------------------
# compute_decline_timeline
# ---------------------------------------------------------------------------


class TestComputeDeclineTimeline:
    def test_empty(self):
        result = compute_decline_timeline([], [], [], {})
        assert result == []

    def test_single_item_with_postings(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.rejected, datetime(2026, 1, 5), aid)
        ev = _ev(aid, "rejected", datetime(2026, 1, 10, tzinfo=UTC))
        postings = {aid: ("Acme Corp", "Engineer")}
        result = compute_decline_timeline([a], [ev], [], postings)
        assert len(result) == 1
        item = result[0]
        assert item.app_id == str(aid)
        assert item.company == "Acme Corp"
        assert item.role == "Engineer"
        assert item.kind == "rejected"
        assert item.stage_reached == "applied"

    def test_missing_posting_gives_none(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.rejected, datetime(2026, 1, 5), aid)
        result = compute_decline_timeline([a], [], [], {})
        assert len(result) == 1
        assert result[0].company is None
        assert result[0].role is None

    def test_ordered_desc_by_occurred_at(self):
        aid1 = uuid.uuid4()
        aid2 = uuid.uuid4()
        a1 = _app(ApplicationStatus.rejected, datetime(2026, 1, 5), aid1)
        a2 = _app(ApplicationStatus.rejected, datetime(2026, 1, 10), aid2)
        # no events, so falls back to created_at
        result = compute_decline_timeline([a1, a2], [], [], {})
        assert result[0].occurred_at >= result[1].occurred_at

    def test_limit_truncates(self):
        apps = []
        for _ in range(5):
            aid = uuid.uuid4()
            apps.append(_app(ApplicationStatus.rejected, datetime(2026, 1, 5), aid))
        result = compute_decline_timeline(apps, [], [], {}, limit=3)
        assert len(result) == 3

    def test_stage_reached_interview_before_rejection(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.rejected, datetime(2026, 1, 20), aid)
        # interview event before rejection
        ev_interview = _ev(aid, "interview", datetime(2026, 1, 10, tzinfo=UTC))
        ev_rejected = _ev(aid, "rejected", datetime(2026, 1, 15, tzinfo=UTC))
        result = compute_decline_timeline([a], [ev_interview, ev_rejected], [], {})
        assert result[0].stage_reached == "interview"

    def test_stage_reached_offer_before_rejection(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.rejected, datetime(2026, 1, 20), aid)
        ev_offer = _ev(aid, "offer", datetime(2026, 1, 10, tzinfo=UTC))
        ev_rejected = _ev(aid, "rejected", datetime(2026, 1, 15, tzinfo=UTC))
        result = compute_decline_timeline([a], [ev_offer, ev_rejected], [], {})
        assert result[0].stage_reached == "offer"

    def test_stage_reached_responded_via_in_interaction(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.rejected, datetime(2026, 1, 20), aid)
        ev_rejected = _ev(aid, "rejected", datetime(2026, 1, 15, tzinfo=UTC))
        it = _interaction(aid, datetime(2026, 1, 5), direction=InteractionDirection.in_)
        result = compute_decline_timeline([a], [ev_rejected], [it], {})
        assert result[0].stage_reached == "responded"


# ---------------------------------------------------------------------------
# compute_rejection_stage
# ---------------------------------------------------------------------------


class TestComputeRejectionStage:
    def test_empty_returns_four_zero_entries(self):
        result = compute_rejection_stage([], [], [])
        assert len(result) == 4
        stages = [r.stage for r in result]
        assert stages == ["applied", "responded", "interview", "offer"]
        assert all(r.count == 0 for r in result)

    def test_fixed_order(self):
        result = compute_rejection_stage([], [], [])
        assert [r.stage for r in result] == ["applied", "responded", "interview", "offer"]

    def test_basic_applied_stage(self):
        a = _app(ApplicationStatus.rejected, datetime(2026, 1, 5))
        result = compute_rejection_stage([a], [], [])
        by_stage = {r.stage: r.count for r in result}
        assert by_stage["applied"] == 1
        assert by_stage["responded"] == 0
        assert by_stage["interview"] == 0
        assert by_stage["offer"] == 0

    def test_interview_stage_counted(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.rejected, datetime(2026, 1, 20), aid)
        ev_interview = _ev(aid, "interview", datetime(2026, 1, 10, tzinfo=UTC))
        ev_rejected = _ev(aid, "rejected", datetime(2026, 1, 15, tzinfo=UTC))
        result = compute_rejection_stage([a], [ev_interview, ev_rejected], [])
        by_stage = {r.stage: r.count for r in result}
        assert by_stage["interview"] == 1
        assert by_stage["applied"] == 0

    def test_offer_stage_counted(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.rejected, datetime(2026, 1, 20), aid)
        ev_offer = _ev(aid, "offer", datetime(2026, 1, 10, tzinfo=UTC))
        ev_rejected = _ev(aid, "rejected", datetime(2026, 1, 15, tzinfo=UTC))
        result = compute_rejection_stage([a], [ev_offer, ev_rejected], [])
        by_stage = {r.stage: r.count for r in result}
        assert by_stage["offer"] == 1

    def test_multiple_apps_distributed(self):
        aid1 = uuid.uuid4()
        aid2 = uuid.uuid4()
        a1 = _app(ApplicationStatus.rejected, datetime(2026, 1, 20), aid1)
        a2 = _app(ApplicationStatus.withdrawn, datetime(2026, 1, 20), aid2)
        ev1 = _ev(aid1, "rejected", datetime(2026, 1, 15, tzinfo=UTC))
        # a2 had interview interaction before withdrawal
        ev2 = _ev(aid2, "withdrawn", datetime(2026, 1, 15, tzinfo=UTC))
        it = _interaction(
            aid2,
            datetime(2026, 1, 5),
            direction=InteractionDirection.in_,
        )
        result = compute_rejection_stage([a1, a2], [ev1, ev2], [it])
        by_stage = {r.stage: r.count for r in result}
        assert by_stage["applied"] == 1
        assert by_stage["responded"] == 1


# ---------------------------------------------------------------------------
# compute_velocity
# ---------------------------------------------------------------------------


class TestComputeVelocity:
    def test_empty_gives_none_means(self):
        result = compute_velocity([], [], [])
        assert result.applied_to_response_h == MeanMedian(mean=None, median=None)
        assert result.response_to_interview_h == MeanMedian(mean=None, median=None)
        assert result.interview_to_offer_h == MeanMedian(mean=None, median=None)
        assert result.offer_to_decision_h == MeanMedian(mean=None, median=None)

    def test_applied_to_response_single_app(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.applied, datetime(2026, 1, 1), aid)
        # applied event at Jan 1 00:00, response interaction at Jan 1 24:00 (24h later)
        ev_applied = _ev(aid, "applied", datetime(2026, 1, 1, tzinfo=UTC))
        it_in = _interaction(
            aid,
            datetime(2026, 1, 2, tzinfo=UTC),  # 24h later
            direction=InteractionDirection.in_,
        )
        result = compute_velocity([a], [ev_applied], [it_in])
        assert result.applied_to_response_h.mean == 24.0
        assert result.applied_to_response_h.median == 24.0

    def test_fallback_applied_at_to_created_at(self):
        aid = uuid.uuid4()
        # created_at Jan 1, no applied event → uses created_at
        a = _app(ApplicationStatus.applied, datetime(2026, 1, 1), aid)
        it_in = _interaction(
            aid,
            datetime(2026, 1, 2),  # 24h later, naive
            direction=InteractionDirection.in_,
        )
        result = compute_velocity([a], [], [it_in])
        assert result.applied_to_response_h.mean == 24.0

    def test_median_across_two_apps(self):
        aid1 = uuid.uuid4()
        aid2 = uuid.uuid4()
        a1 = _app(ApplicationStatus.applied, datetime(2026, 1, 1), aid1)
        a2 = _app(ApplicationStatus.applied, datetime(2026, 1, 1), aid2)
        ev1 = _ev(aid1, "applied", datetime(2026, 1, 1, tzinfo=UTC))
        ev2 = _ev(aid2, "applied", datetime(2026, 1, 1, tzinfo=UTC))
        # a1: 10h response, a2: 30h response → median = 20h
        it1 = _interaction(
            aid1, datetime(2026, 1, 1, 10, tzinfo=UTC), direction=InteractionDirection.in_
        )
        it2 = _interaction(
            aid2, datetime(2026, 1, 2, 6, tzinfo=UTC), direction=InteractionDirection.in_
        )
        result = compute_velocity([a1, a2], [ev1, ev2], [it1, it2])
        assert result.applied_to_response_h.median == 20.0

    def test_no_response_gives_none(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.applied, datetime(2026, 1, 1), aid)
        result = compute_velocity([a], [], [])
        assert result.applied_to_response_h.mean is None
        assert result.applied_to_response_h.median is None

    def test_negative_delta_excluded(self):
        """If response is before applied, that sample should be excluded."""
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.applied, datetime(2026, 1, 10), aid)
        ev = _ev(aid, "applied", datetime(2026, 1, 10, tzinfo=UTC))
        # response BEFORE applied — invalid, must be excluded
        it = _interaction(aid, datetime(2026, 1, 5, tzinfo=UTC), direction=InteractionDirection.in_)
        result = compute_velocity([a], [ev], [it])
        assert result.applied_to_response_h.mean is None


# ---------------------------------------------------------------------------
# compute_ghost
# ---------------------------------------------------------------------------


class TestComputeGhost:
    def test_empty(self):
        result = compute_ghost([], [], [], ghost_days=30)
        assert result == Ghost(count=0, threshold_days=30)

    def test_old_applied_no_response_counts(self):
        aid = uuid.uuid4()
        # created_at well in the past (60 days ago)
        old = datetime.utcnow() - timedelta(days=60)
        a = _app(ApplicationStatus.applied, old, aid)
        result = compute_ghost([a], [], [], ghost_days=30)
        assert result.count == 1

    def test_old_applied_with_incoming_interaction_excluded(self):
        aid = uuid.uuid4()
        old = datetime.utcnow() - timedelta(days=60)
        a = _app(ApplicationStatus.applied, old, aid)
        it = _interaction(aid, old + timedelta(days=5), direction=InteractionDirection.in_)
        result = compute_ghost([a], [], [it], ghost_days=30)
        assert result.count == 0

    def test_recent_applied_excluded(self):
        aid = uuid.uuid4()
        recent = datetime.utcnow() - timedelta(days=5)
        a = _app(ApplicationStatus.applied, recent, aid)
        result = compute_ghost([a], [], [], ghost_days=30)
        assert result.count == 0

    def test_non_applied_set_status_excluded(self):
        aid = uuid.uuid4()
        old = datetime.utcnow() - timedelta(days=60)
        a = _app(ApplicationStatus.draft, old, aid)
        result = compute_ghost([a], [], [], ghost_days=30)
        assert result.count == 0

    def test_threshold_days_preserved_in_result(self):
        result = compute_ghost([], [], [], ghost_days=45)
        assert result.threshold_days == 45

    def test_uses_applied_event_timestamp_when_present(self):
        """applied_at from event, not created_at, determines ghosting."""
        aid = uuid.uuid4()
        # created_at is ancient, but applied event is recent
        a = _app(ApplicationStatus.applied, datetime(2020, 1, 1), aid)
        recent_applied = datetime.utcnow() - timedelta(days=5)
        ev = _ev(aid, "applied", recent_applied.replace(tzinfo=UTC))
        result = compute_ghost([a], [ev], [], ghost_days=30)
        # applied recently, so NOT a ghost
        assert result.count == 0


# ---------------------------------------------------------------------------
# compute_interview
# ---------------------------------------------------------------------------


class TestComputeInterview:
    def test_empty(self):
        result = compute_interview([], [], [])
        assert result == Interview(reached=0, won=0, lost=0, win_rate=None)

    def test_win_rate_none_when_no_outcome(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.interview, datetime(2026, 1, 1), aid)
        result = compute_interview([a], [], [])
        assert result.reached == 1
        assert result.won == 0
        assert result.lost == 0
        assert result.win_rate is None

    def test_reached_via_status(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.interview, datetime(2026, 1, 1), aid)
        result = compute_interview([a], [], [])
        assert result.reached == 1

    def test_reached_via_interview_event(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.applied, datetime(2026, 1, 1), aid)
        ev = _ev(aid, "interview", datetime(2026, 1, 10, tzinfo=UTC))
        result = compute_interview([a], [ev], [])
        assert result.reached == 1

    def test_reached_via_interview_interaction(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.applied, datetime(2026, 1, 1), aid)
        it = _interaction(aid, datetime(2026, 1, 5), channel=InteractionChannel.interview)
        result = compute_interview([a], [], [it])
        assert result.reached == 1

    def test_won_via_accepted_status(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.accepted, datetime(2026, 1, 1), aid)
        ev = _ev(aid, "interview", datetime(2026, 1, 10, tzinfo=UTC))
        result = compute_interview([a], [ev], [])
        assert result.won == 1
        assert result.lost == 0

    def test_lost_via_rejected_event(self):
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.rejected, datetime(2026, 1, 1), aid)
        ev_interview = _ev(aid, "interview", datetime(2026, 1, 10, tzinfo=UTC))
        ev_rejected = _ev(aid, "rejected", datetime(2026, 1, 15, tzinfo=UTC))
        result = compute_interview([a], [ev_interview, ev_rejected], [])
        assert result.lost == 1
        assert result.won == 0

    def test_won_takes_precedence_over_lost(self):
        """App that reached interview, got offer, then later rejected → counts as won."""
        aid = uuid.uuid4()
        a = _app(ApplicationStatus.rejected, datetime(2026, 1, 1), aid)
        ev_interview = _ev(aid, "interview", datetime(2026, 1, 10, tzinfo=UTC))
        ev_offer = _ev(aid, "offer", datetime(2026, 1, 15, tzinfo=UTC))
        ev_rejected = _ev(aid, "rejected", datetime(2026, 1, 20, tzinfo=UTC))
        result = compute_interview([a], [ev_interview, ev_offer, ev_rejected], [])
        assert result.won == 1
        assert result.lost == 0

    def test_win_rate_computed(self):
        aid1 = uuid.uuid4()
        aid2 = uuid.uuid4()
        a1 = _app(ApplicationStatus.accepted, datetime(2026, 1, 1), aid1)
        a2 = _app(ApplicationStatus.rejected, datetime(2026, 1, 1), aid2)
        ev1 = _ev(aid1, "interview", datetime(2026, 1, 10, tzinfo=UTC))
        ev2 = _ev(aid2, "interview", datetime(2026, 1, 10, tzinfo=UTC))
        ev2r = _ev(aid2, "rejected", datetime(2026, 1, 15, tzinfo=UTC))
        result = compute_interview([a1, a2], [ev1, ev2, ev2r], [])
        assert result.won == 1
        assert result.lost == 1
        assert result.win_rate == pytest.approx(0.5)
