"""v16 §6 — the brief: facts, the truth check, the command, the cache, the bank."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from gaffer import artifacts
from gaffer.brief import (BRIEF_PROMPT_VERSION, build_facts, build_prompt,
                          cache_key, check_brief, extract_text, fact_names,
                          fact_numbers, first_sentence, load_brief,
                          run_brief)

FACTS = {
    "gw": 4, "horizon": [4, 5, 6], "expected_pts": 61.2, "hits": 0, "hit_points": 0,
    "restraint": {"chosen_label": "free transfers only", "bar_pct": 60,
                  "steps": [{"below_label": "bank", "above_label": "free transfers only",
                             "share_pct": 79, "taken": True, "reason": "expected points alone"},
                            {"below_label": "free transfers only", "above_label": "1 hit",
                             "share_pct": 46, "taken": False,
                             "reason": "Rice is 0% to play"}]},
    "moves": [{"in": "Gibbs-White", "out": "B.Fernandes", "gain": 3.1, "sims_pct": 70}],
    "captain": {"name": "Guéhi", "sims_pct": 55, "note": None},
    "league": {"name": "Shocky Supplies", "stance": "chase", "manual": False,
               "gap": 44, "lam": 0.13, "rival": "palm it down"},
    "chip": None,
    "last_week": {"gw": 3, "you": 61, "model": 68,
                  "lanes": [{"lane": "transfers", "label": "Blunder", "delta_pts": -7}],
                  "note": {"reason": "gut", "text": "fancied Isak"}},
    "data_warning": None,
    "objective": {"agrees": False, "hits": 1,
                  "moves": [{"in": "Gibbs-White", "out": "B.Fernandes"},
                            {"in": "Isak", "out": "Rice"}]},
}


def test_the_numbers_of_the_facts_in_the_forms_the_prose_may_use():
    nums = fact_numbers(FACTS)
    for want in ("4", "5", "6", "61.2", "60", "79", "46", "3.1", "70", "55", "44",
                 "0.13", "61", "68", "-7", "7", "3", "0", "1"):
        assert want in nums, want
    assert "62" not in nums and "0.6" not in nums


def test_the_names_of_the_facts_include_every_token_of_a_name():
    names = fact_names(FACTS)
    for want in ("Gibbs-White", "B.Fernandes", "Guéhi", "Isak", "Rice", "Shocky",
                 "Supplies", "Shocky Supplies", "palm", "down"):
        assert want in names, want


def test_a_true_brief_passes():
    prose = ("The ladder chose free transfers only at a bar of 60%, taking the step "
             "from the bank at 79% and refusing the step to 1 hit at 46% because "
             "Rice is 0% to play. That brings Gibbs-White in for B.Fernandes, "
             "worth 3.1 points over the horizon and made in 70% of the sims. "
             "The armband stays on Guéhi, the sweep's pick in 55% of sims. In "
             "Shocky Supplies you are chasing, 44 behind palm it down, with the "
             "tilt at 0.13. Last week you scored 61 against the model's 68, and "
             "you said the transfers were gut: fancied Isak.")
    assert check_brief(prose, FACTS) == []


def test_a_foreign_number_fails_and_names_the_sentence():
    prose = "The step to 1 hit was refused at 52%. Guéhi keeps the armband."
    offences = check_brief(prose, FACTS)
    assert offences == ["number 52 is not in the facts: The step to 1 hit was refused at 52%."]


def test_a_foreign_name_fails():
    offences = check_brief("This week Haaland is the obvious captain.", FACTS)
    assert offences == ["name Haaland is not in the facts: This week Haaland is the obvious captain."]


def test_sentence_starts_and_the_allow_list_are_exempt():
    prose = "Friday is the deadline. GW4 is a British week. The XI is set, I think."
    assert check_brief(prose, FACTS) == []


def test_a_possessive_and_a_trailing_unit_are_stripped():
    assert check_brief("Guéhi's 55% is solid; 3.1 pts is the gain.", FACTS) == []


def test_first_sentence():
    assert first_sentence("One. Two? Three!") == "One."
    assert first_sentence("  Only one  ") == "Only one"


def test_the_prompt_carries_the_facts_and_the_rules():
    prompt = build_prompt(FACTS)
    assert '"Gibbs-White"' in prompt
    assert "British English" in prompt and "no headings" in prompt.lower()
    assert "never name a club" in prompt.lower()
    assert "do not start a sentence with a player's name" in prompt.lower()


def test_extract_text_reads_the_envelope_a_string_or_plain_text():
    assert extract_text(json.dumps({"result": "The brief."})) == "The brief."
    assert extract_text(json.dumps("The brief.")) == "The brief."
    assert extract_text("The brief.\n") == "The brief."


def test_the_cache_key_is_salted_by_the_prompt_version():
    assert BRIEF_PROMPT_VERSION == 1
    assert cache_key("2026-09-05T09:00:00", 1) != cache_key("2026-09-05T09:00:00", 2)
    assert cache_key("a", 1) == cache_key("a", 1)


# --- run_brief on real-shaped artifacts ---------------------------------------

def _fake(tmp_path: Path, text: str, exit_code: int = 0, sleep: float = 0.0) -> str:
    script = tmp_path / "fake_cli.py"
    script.write_text(
        "import sys, time, json\n"
        "sys.stdin.read()\n"
        f"time.sleep({sleep})\n"
        f"sys.stdout.write(json.dumps({{'result': {text!r}}}))\n"
        f"sys.exit({exit_code})\n", encoding="utf-8")
    return f"{sys.executable} {script}"


@pytest.fixture()
def artifacts_on_disk(tmp_path, monkeypatch):
    """A GW4 advice, ladder and solve state of the real shape, no trace."""
    monkeypatch.chdir(tmp_path)
    artifacts.REPORTS.mkdir()
    ref = lambda c, n: {"code": c, "name": n, "position": "MID", "ep": 5.0}  # noqa: E731
    (artifacts.REPORTS / "gw4-advice.json").write_text(json.dumps({
        "gw": 4, "deadline": "2026-09-11T17:30:00Z", "hits": 0, "expected_pts": 61.2,
        "buys": [ref(1, "Gibbs-White")], "sells": [ref(2, "B.Fernandes")],
        "captain": ref(3, "Guéhi"), "vice": ref(4, "Semenyo"), "xi": [], "bench": [],
        "move_frequencies": [{"kind": "buy", "code": 1, "gw": 4, "frequency": 0.7}],
        "scenarios": {"captain_frequency": 0.55}, "captain_note": None,
        "strategy": {"lam": 0.1326, "gap": 44, "stance": "chase", "rival_name": "palm it down",
                     "source": "auto"},
        "chip_table": [], "data_warning": None,
        "objective": {"buys": [ref(1, "Gibbs-White"), ref(5, "Isak")],
                      "sells": [ref(2, "B.Fernandes"), ref(6, "Rice")], "hits": 1,
                      "expected_pts": 63.0},
        "restraint": {"chosen": "hits0", "bar": 0.6, "agrees": False, "note": "x",
                      "steps": [{"below": "bank", "above": "hits0", "share": 0.7875,
                                 "taken": True, "reason": "expected points alone",
                                 "reason_kind": "points"},
                                {"below": "hits0", "above": "hits1", "share": 0.46,
                                 "taken": False, "reason": "Rice is 0% to play",
                                 "reason_kind": "flagged"}]}}))
    (artifacts.REPORTS / "ladder_gw4.json").write_text(json.dumps(
        {"gw": 4, "gws": [4, 5, 6], "chosen": "hits0", "bar": 0.6, "rungs": []}))
    monkeypatch.setattr("gaffer.brief.run_stamp", lambda gw: "2026-09-05T09:00:00")
    monkeypatch.setattr("gaffer.brief.move_gains", lambda gw: {1: 3.1})
    monkeypatch.setattr("gaffer.brief.latest_gw", lambda: 4)
    return tmp_path


TRUE = ("The ladder chose free transfers only at a bar of 60%, taking the step from "
        "the bank at 79% and refusing 1 hit at 46% because Rice is 0% to play. "
        "That brings Gibbs-White in for B.Fernandes, worth 3.1 points and made in "
        "70% of sims. The armband stays on Guéhi at 55%. In the league you are "
        "chasing, 44 behind palm it down, tilt 0.13. Expect 61.2 points.")


def test_build_facts_has_the_spec_shape_and_rounding(artifacts_on_disk):
    facts = build_facts(4)
    assert facts["gw"] == 4 and facts["horizon"] == [4, 5, 6]
    assert facts["restraint"]["chosen_label"] == "free transfers only"
    assert facts["restraint"]["bar_pct"] == 60
    assert facts["restraint"]["steps"][0]["share_pct"] == 79
    assert facts["moves"] == [{"in": "Gibbs-White", "out": "B.Fernandes", "gain": 3.1,
                               "sims_pct": 70}]
    assert facts["captain"] == {"name": "Guéhi", "sims_pct": 55, "note": None}
    assert facts["league"]["lam"] == 0.13 and facts["league"]["manual"] is False
    assert facts["objective"]["hits"] == 1 and facts["objective"]["agrees"] is False
    assert facts["last_week"] is None and facts["chip"] is None


def test_a_passing_brief_is_banked_and_the_line_printed(artifacts_on_disk, capsys):
    cfg = type("C", (), {"news_llm_command": _fake(artifacts_on_disk, TRUE),
                         "news_llm_timeout_s": 10})()
    out = run_brief(4, cfg=cfg, cache_dir=artifacts_on_disk / "cache")
    assert out["written"] is True and out["note"] is None
    banked = load_brief(4)
    assert banked["prose"] == TRUE and banked["gw"] == 4
    assert banked["prompt_version"] == 1 and banked["run_stamp"] == "2026-09-05T09:00:00"
    assert banked["facts"]["gw"] == 4 and banked["checked_at"]
    assert "Brief GW4: The ladder chose" in capsys.readouterr().out


def test_a_failing_check_writes_nothing_and_leaves_a_note(artifacts_on_disk, capsys):
    cfg = type("C", (), {"news_llm_command": _fake(artifacts_on_disk, "Haaland scores 99."),
                         "news_llm_timeout_s": 10})()
    (artifacts.REPORTS / "brief_gw4.json").write_text("{}")   # a stale one
    out = run_brief(4, cfg=cfg, cache_dir=artifacts_on_disk / "cache")
    assert out["written"] is False
    assert "did not pass its check" in out["note"]
    assert not (artifacts.REPORTS / "brief_gw4.json").exists()
    note = json.loads((artifacts.REPORTS / "brief_note.json").read_text())
    assert note["gw"] == 4 and "did not pass" in note["note"]
    assert "Haaland" in capsys.readouterr().out


@pytest.mark.parametrize("kw", [{"exit_code": 3}, {"sleep": 5}])
def test_a_dead_command_is_a_note_not_an_error(artifacts_on_disk, kw):
    cfg = type("C", (), {"news_llm_command": _fake(artifacts_on_disk, TRUE, **kw),
                         "news_llm_timeout_s": 1})()
    out = run_brief(4, cfg=cfg, cache_dir=artifacts_on_disk / "cache")
    assert out["written"] is False and "brief not written" in out["note"]


def test_a_missing_command_is_a_note(artifacts_on_disk):
    cfg = type("C", (), {"news_llm_command": "", "news_llm_timeout_s": 1})()
    out = run_brief(4, cfg=cfg, cache_dir=artifacts_on_disk / "cache")
    assert out["written"] is False and "no llm_command" in out["note"]


def test_the_cache_answers_the_second_run_without_the_command(artifacts_on_disk):
    cfg = type("C", (), {"news_llm_command": _fake(artifacts_on_disk, TRUE),
                         "news_llm_timeout_s": 10})()
    run_brief(4, cfg=cfg, cache_dir=artifacts_on_disk / "cache")
    dead = type("C", (), {"news_llm_command": "/nonexistent/claude",
                          "news_llm_timeout_s": 10})()
    out = run_brief(4, cfg=dead, cache_dir=artifacts_on_disk / "cache")
    assert out["written"] is True


def test_no_advice_on_disk_is_a_note(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("gaffer.brief.latest_gw", lambda: None)
    out = run_brief(None)
    assert out["written"] is False and "no advice" in out["note"]


# --- review fixes: reasons are sayable, chips are allowed, a ban evicts ------

def test_a_name_and_a_number_that_live_only_in_a_step_reason_are_sayable():
    facts = {**FACTS, "restraint": {**FACTS["restraint"], "steps": [
        {"below_label": "free transfers only", "above_label": "1 hit",
         "share_pct": 46, "taken": False,
         "reason": "Fernandes is 96% to drop tonight"}]}}
    prose = "The step to 1 hit was refused at 46% because Fernandes is 96% to drop tonight."
    assert check_brief(prose, facts) == []


def test_the_chips_as_the_prose_spells_them_are_not_names():
    prose = ("A Bench Boost is planned for GW5. The Triple Captain and the "
             "Free Hit stay in hand, as does the Wildcard; Plan A holds.")
    assert check_brief(prose, FACTS) == []


def test_a_failed_check_evicts_the_cached_prose(artifacts_on_disk, monkeypatch):
    from gaffer import brief as brief_mod

    calls = []

    def fake(cmd, prompt, timeout_s):
        calls.append(1)
        return "The obvious captain is Haaland."
    monkeypatch.setattr(brief_mod, "run_command", fake)
    cache = artifacts_on_disk / "cache"
    cfg = type("C", (), {"news_llm_command": "claude -p",
                         "news_llm_timeout_s": 1})()
    out = brief_mod.run_brief(4, cfg=cfg, cache_dir=cache)
    assert out["written"] is False and not list(cache.glob("*.json"))
    brief_mod.run_brief(4, cfg=cfg, cache_dir=cache)
    assert len(calls) == 2
