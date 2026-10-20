"""The clauses the analysis_rerun sweep selects default analyses with."""

from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql

from skyportal.models import DBSession, DefaultAnalysis, init_db
from skyportal.models.analysis import (
    _default_analysis_gated,
    _default_analysis_rerun_blocked,
    _default_analysis_under_limit,
)
from skyportal.tests import cfg
from skyportal.utils.naive_datetime import utcnow_naive


def compiled(clause):
    return str(clause.compile(dialect=psql.dialect()))


def test_the_gate_indexes_the_parameters_column():
    # JSONType carries no getitem comparator, so building this raised
    # NotImplementedError before the column's json type was named.
    sql = compiled(_default_analysis_gated())
    assert "default_analysis_parameters ->>" in sql
    assert "IS NOT NULL" in sql


def test_the_whole_sweep_query_builds():
    sql = compiled(
        sa.select(DefaultAnalysis).where(
            _default_analysis_gated(), _default_analysis_under_limit()
        )
    )
    assert "default_analysis_parameters ->>" in sql
    assert "stats ->>" in sql


def _rerun_blocked(analysis):
    clause = _default_analysis_rerun_blocked(
        analysis.analysis_service_id, analysis.obj_id
    )
    return DBSession().scalar(sa.select(clause))


def test_a_queued_run_blocks_a_rerun(public_obj_analysis):
    assert _rerun_blocked(public_obj_analysis)


def test_an_insufficient_run_blocks_until_a_new_detection(public_obj_analysis):
    public_obj_analysis.status = "completed"
    public_obj_analysis.status_message = "4 detections [insufficient_data]"
    DBSession().commit()
    assert _rerun_blocked(public_obj_analysis)

    public_obj_analysis.created_at = datetime(2000, 1, 1)
    DBSession().commit()
    assert not _rerun_blocked(public_obj_analysis)


def test_the_sweep_stops_at_the_daily_limit(
    public_default_analysis,
    public_group,
    public_source,
    public_source_two_groups,
    monkeypatch,
):
    from services.analysis_rerun import analysis_rerun

    init_db(**cfg["database"])  # undo the service's import-time init_db()

    now = utcnow_naive()
    public_default_analysis.source_filter = {"group_id": public_group.id}
    public_default_analysis.default_analysis_parameters = {"min_detections": 0}
    stats = {
        "daily_limit": 1,
        "daily_count": 0,
        "last_run": now.strftime("%Y-%m-%dT%H:%M:%S.%f"),
    }
    public_default_analysis.stats = stats
    DBSession().commit()

    calls = []

    def run_default_analysis(default_analysis_id, author_id, obj_id, trigger):
        calls.append(obj_id)
        public_default_analysis.stats = {**stats, "daily_count": len(calls)}
        DBSession().commit()

    monkeypatch.setattr(analysis_rerun, "_run_default_analysis", run_default_analysis)
    analysis_rerun._sweep_default_analysis(
        DBSession(), public_default_analysis, now - timedelta(days=1)
    )
    assert len(calls) == 1
