"""Suite-wide fixtures.

v17e §2.2: ``config_in_force`` is a process-lifetime cache, so a test that
fails between writing a ``tmp_path`` config and its trailing clear would pin
every later test in the process to a deleted directory. Clearing around every
test makes that impossible to write by accident.
"""
from __future__ import annotations

import functools
import sys

import pytest

import gaffer.config


@pytest.fixture(autouse=True)
def _config_cache_is_never_shared_between_tests():
    gaffer.config.invalidate()
    yield
    gaffer.config.invalidate()


def _clear_process_lifetime_caches():
    """Empty every process-lifetime cache a test can fill (v18g §2.4).

    A cache that survives a test is a hidden dependency between tests: the
    second test reads the first one's fixture and passes, or fails, for a
    reason that is not in its own body. Looked up through ``sys.modules`` so
    ``conftest`` does not import the web app at collection, and so a test that
    never reached the web layer does not pay to import it.
    """
    for name, clear in (
        ("gaffer.web.identity", lambda m: m.clear_cache()),
        ("gaffer.web.field_frame", lambda m: m.clear_cache()),
        ("gaffer.optimize.scenarios", lambda m: m.scenario_noise.cache_clear()),
        ("gaffer.web.routers.league", lambda m: m._OVERVIEW.clear()),
        ("gaffer.web.routers.league_sim", lambda m: m._CACHE.clear()),
        ("gaffer.web.routers.live", lambda m: (m.RACE_SERIES.clear(),
                                               m.RACE_RIVAL.clear())),
    ):
        module = sys.modules.get(name)
        if module is not None:
            clear(module)


@pytest.fixture(autouse=True)
def _module_caches_are_never_shared_between_tests():
    _clear_process_lifetime_caches()
    yield
    _clear_process_lifetime_caches()


def patch_view(monkeypatch, reader, module=None):
    """Stand in for the one config read (v17e §2.2). Wrapped in
    ``lru_cache`` because ``invalidate()`` clears through the attribute it
    replaces, so an ``invalidate()`` reached while the patch is live (a
    fixture body, the test itself) would otherwise raise ``AttributeError``.
    Patched on ``module`` when the caller bound the name at import
    (``gaffer.price_timing``, ``gaffer.models.train``) and on
    ``gaffer.config`` when it imports lazily (``gaffer.ladder``)."""
    monkeypatch.setattr(module or gaffer.config, "config_in_force",
                        functools.lru_cache(maxsize=1)(reader))

@pytest.fixture(autouse=True)
def _the_price_step_never_reaches_the_network(request, monkeypatch):
    """v19b §2.1: ``weekly_run`` banks a price reading through the live
    bootstrap before the solve. Every test that stubs ``run_advise`` and runs
    the CLI or the job kind would otherwise reach FPL for real and write a
    row into the working tree's ``data/live/price_log.parquet`` — which one
    did, on 2026-09-16, before this fixture existed. The seam is one
    module-level name, so it is stubbed here for the whole suite; only
    ``test_pipeline.py`` sees the real function, because it is the file that
    tests it (and it stubs the seam itself wherever it runs the pipeline).
    """
    if request.node.fspath.basename == "test_pipeline.py":
        return
    import gaffer.pipeline

    monkeypatch.setattr(gaffer.pipeline, "bank_price_reading",
                        lambda client=None, log=print: None)
