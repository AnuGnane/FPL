"""The vendored pre-v5 minutes head imports as its docstring says (holiday F-175).

``scripts/v7b_legacy_minutes.py`` is the v7b Q2 ablation's head, vendored
verbatim; ``tests/test_v7b_driver.py`` fits it. This only proves the module
loads on its own with the class and ``LGB_KW`` its docstring names. No fit.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import v7b_legacy_minutes


def test_the_vendored_class_and_its_lgb_kw_exist():
    assert isinstance(v7b_legacy_minutes.LGB_KW, dict)
    assert v7b_legacy_minutes.LGB_KW["n_estimators"] == 300
    assert callable(v7b_legacy_minutes.LegacyMinutesModel.fit)
    assert callable(v7b_legacy_minutes.LegacyMinutesModel.predict)


def test_the_docstring_names_what_the_module_vendors():
    doc = v7b_legacy_minutes.__doc__
    assert "LGB_KW" in doc and "v7b Q2" in doc
