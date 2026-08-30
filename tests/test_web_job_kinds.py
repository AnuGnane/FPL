"""The kind table must wrap the same entry points the CLI calls — never a
second implementation that can drift from `gaffer advise`."""

import inspect

import gaffer.web.job_kinds as job_kinds
from gaffer.web.job_kinds import JOB_KINDS, run_evaluate, run_news_shadow


def _record(calls):
    """Fake ``save_evaluation``: records the call, answers with the path.

    (The plan's inline ``setdefault(...) or path`` lambda returns the recorded
    tuple, because ``setdefault`` hands back the truthy value it just stored.)
    """

    def save(key, payload):
        calls["saved"] = (key, payload)
        return "reports/evaluation.json"

    return save


def test_exactly_the_kinds_the_spec_allows():
    assert sorted(JOB_KINDS) == ["advise", "advise-fast", "evaluate",
                                 "news-shadow", "refresh-data", "snapshot",
                                 "track-pens"]


def test_advise_and_refresh_reuse_the_existing_router_entry_points():
    from gaffer.web.routers.advice import run_train_and_advise
    from gaffer.web.routers.meta import run_data_refresh

    assert JOB_KINDS["advise"] is run_train_and_advise
    assert JOB_KINDS["refresh-data"] is run_data_refresh


def test_evaluate_calls_evaluate_current_and_saves_under_that_key(monkeypatch):
    calls = {}
    monkeypatch.setattr("gaffer.evaluation.evaluate_current",
                        lambda: {"rmse": 2.1})
    monkeypatch.setattr("gaffer.evaluation.save_evaluation",
                        _record(calls))
    monkeypatch.setattr("gaffer.evaluation.format_report",
                        lambda key, payload: "report text")
    out = run_evaluate()
    assert calls["saved"] == ("current", {"rmse": 2.1})
    assert out == {"key": "current", "path": "reports/evaluation.json"}


def test_news_shadow_calls_evaluate_news_shadow(monkeypatch):
    calls = {}
    monkeypatch.setattr("gaffer.evaluation.evaluate_news_shadow",
                        lambda: {"gws": []})
    monkeypatch.setattr("gaffer.evaluation.save_evaluation",
                        _record(calls))
    monkeypatch.setattr("gaffer.evaluation.format_report",
                        lambda key, payload: "report text")
    out = run_news_shadow()
    assert calls["saved"] == ("news_shadow", {"gws": []})
    assert out == {"key": "news_shadow", "path": "reports/evaluation.json"}


def test_the_wrappers_import_lazily_so_the_module_stays_cheap():
    source = inspect.getsource(job_kinds)
    assert "from gaffer.evaluation import" not in source.split("def ")[0]
