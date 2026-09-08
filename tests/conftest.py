"""Suite-wide fixtures.

v17e §2.2: ``config_in_force`` is a process-lifetime cache, so a test that
fails between writing a ``tmp_path`` config and its trailing clear would pin
every later test in the process to a deleted directory. Clearing around every
test makes that impossible to write by accident.
"""
from __future__ import annotations

import functools

import pytest

import gaffer.config


@pytest.fixture(autouse=True)
def _config_cache_is_never_shared_between_tests():
    gaffer.config.invalidate()
    yield
    gaffer.config.invalidate()


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
