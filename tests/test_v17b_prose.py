"""v17b §5 — the gate's rail: for every rung key the CLI's line, the ladder
route's labels and lines, and the fixture the cards render are the same
served strings."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gaffer.ladder import RUNG_ORDER, load_ladder, save_ladder, serve_rung
# Private, but this is the one test allowed to name the rung table (v17b
# §4): every other surface reads the served ``label``.
from gaffer.ladder import _rung_label
from gaffer.web.app import create_app
from tests.test_v16_ladder import _objective, _row
from tests.test_v16_restraint import _cli
from tests.test_v4c_degradation import _fixture_advice

FIXTURE = (Path(__file__).resolve().parents[1]
           / "frontend/src/hubs/this-week/restraint-prose.fixture.json")


def _rung_row(i: int, key: str) -> dict:
    if key.startswith("hits"):
        hits = int(key[4:])
    elif key == "open":
        hits = 4
    else:
        hits = 0
    buys = [20 + j for j in range(i)]
    sells = [16 - j for j in range(i)]
    return _row(key, hits=hits, transfers=i, buys=buys, sells=sells,
                xi=list(range(1, 12)), captain=3, vice=4)


def _case(key: str, root: Path) -> dict:
    """Bank a ladder that walks from ``bank`` to ``key``, serve it, and read
    it back through every surface the gate names (v17b §5)."""
    root.mkdir(parents=True, exist_ok=True)
    rows = [_rung_row(i, k) for i, k in enumerate(RUNG_ORDER)]
    idx = RUNG_ORDER.index(key)
    steps = [{"below": RUNG_ORDER[i], "above": RUNG_ORDER[i + 1],
              "share": 0.79, "taken": True,
              "reason": "expected points alone", "reason_kind": "points"}
             for i in range(idx)]
    if idx + 1 < len(RUNG_ORDER):
        steps.append({"below": key, "above": RUNG_ORDER[idx + 1],
                      "share": 0.46, "taken": False,
                      "reason": "Filler is 0% to play",
                      "reason_kind": "flagged"})
    ladder = {"gw": 4, "gws": [4, 5], "chosen": key, "bar": 0.6,
              "free_transfers": 1, "cap": {}, "notes": [], "n_draws": 5,
              "steps": steps, "rungs": rows}
    cwd = Path.cwd()
    try:
        os.chdir(root)
        save_ladder(ladder, 4)
        banked = load_ladder(4)
        # v17f §4: serve_rung returns the typed plan; the file the route reads
        # is the dump advise writes.
        served = serve_rung(banked, _objective(), hit_cost=4, captain_note=None
                            ).model_dump(exclude_unset=True)
        Path("reports/gw4-advice.json").write_text(json.dumps({
            "gw": 4, "buys": served["buys"], "sells": served["sells"],
            "captain": {"code": 3}, "restraint": served["restraint"],
        }))
        with patch("gaffer.web.routers.ladder.latest_gw", lambda: 4):
            client = TestClient(create_app())
            payload = client.get("/api/ladder").json()
    finally:
        os.chdir(cwd)
    # The objective block's prose only: v17f §2.4 put the objective's own
    # priced week under ``week``, which the moves card never reads.
    return {"key": key, "hits": served["hits"], "restraint": served["restraint"],
            "objective": {k: v for k, v in served["objective"].items() if k != "week"},
            "payload": payload}


def _fixture(root: Path) -> dict:
    return {"cases": [_case(k, root / k) for k in RUNG_ORDER]}


@pytest.mark.parametrize("key", RUNG_ORDER)
def test_the_cli_prints_the_served_line(key, tmp_path, monkeypatch):
    case = _case(key, tmp_path)
    advice = _fixture_advice()
    advice.restraint, advice.objective = case["restraint"], case["objective"]
    out = _cli(tmp_path, monkeypatch, advice)
    assert out.exit_code == 0, out.output
    assert case["restraint"]["line"] + "\n" in out.output
    if not case["restraint"]["agrees"]:
        assert case["objective"]["line"] + "\n" in out.output


@pytest.mark.parametrize("key", RUNG_ORDER)
def test_the_route_serves_the_same_labels_and_lines(key, tmp_path):
    case = _case(key, tmp_path)
    body = case["payload"]
    assert body["chosen"] == key
    assert [r["label"] for r in body["rungs"]] == [_rung_label(k) for k in RUNG_ORDER]
    assert [s["line"] for s in body["steps"]] == [s["line"] for s in case["restraint"]["steps"]]
    assert case["restraint"]["label"] == next(r["label"] for r in body["rungs"] if r["key"] == key)
    assert all(r["label"] for r in body["rungs"]) and all(s["line"] for s in body["steps"])


def test_the_committed_fixture_is_what_the_server_serves(tmp_path):
    expected = _fixture(tmp_path)
    assert json.loads(FIXTURE.read_text()) == expected, \
        "fixture stale — run: .venv/bin/python -m tests.test_v17b_prose --write"


if __name__ == "__main__":  # .venv/bin/python -m tests.test_v17b_prose --write
    import sys
    import tempfile
    if sys.argv[1:] != ["--write"]:
        sys.exit("usage: python -m tests.test_v17b_prose --write")
    with tempfile.TemporaryDirectory() as tmp:
        FIXTURE.write_text(json.dumps(_fixture(Path(tmp)), indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {FIXTURE}")
