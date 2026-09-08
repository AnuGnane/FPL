"""Suite-wide fixtures.

v17e §2.2: ``config_in_force`` is a process-lifetime cache, so a test that
fails between writing a ``tmp_path`` config and its trailing clear would pin
every later test in the process to a deleted directory. Clearing around every
test makes that impossible to write by accident.
"""
from __future__ import annotations

import pytest

import gaffer.config


@pytest.fixture(autouse=True)
def _config_cache_is_never_shared_between_tests():
    gaffer.config.invalidate()
    yield
    gaffer.config.invalidate()
