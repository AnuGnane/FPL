"""scripts/v20_appendix.py, the §6 evidence lines collected (holiday F-34).

Two logs in a temporary directory, their modification times set by hand: an
older v20b replay with its lever lines and a head reading, and a newer one
mixing the v20c harness and clip with a tag no arm claims. A third log has
no evidence line at all.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, "scripts")

import v20_appendix as ap  # noqa: E402 — scripts/ is not a package; the path insert must come first

OLD = datetime(2026, 10, 13, 22, 0, tzinfo=timezone.utc).timestamp()
NEW = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc).timestamp()

B_LOG = """\
starting replay
LEVER minutes cols=[minutes_r1, home]
LEVER bonus cols=[bps_r3, e_goals, e_assists]
V7B_ARM_DONE v20b-bonus-branch-s20260901 {"total": 1850}
MULTISEED_DONE v20b-bonus-branch {"totals": [1850], "mean": 1850.0}
V20B_HEAD {"overall": 0.41, "verdict": "pass"}
RUN_EXIT 0
"""

C_LOG = """\
REPLAY_TEAM_MODEL p_cs min=0.0812 max=0.6123 distinct=310 n=380
V7B_ARM_DONE v20c0-harness-branch-s20260901 {"total": 1849}
DC_CLIP n=12 of 380
V7B_ARM_DONE v20c-clip-branch-s20260901 {"total": 1851}
V20C_HEAD {"verdict": "fail: extreme"}
V7B_ARM_DONE v19x-other-s20260901 {"total": 1700}
V20D_BRIER {"n": 0, "reason": "no log"}
"""


@pytest.fixture()
def logs(tmp_path):
    (tmp_path / "b.log").write_text(B_LOG)
    (tmp_path / "c.log").write_text(C_LOG)
    (tmp_path / "quiet.log").write_text("nothing to see\nRUN_EXIT 0\n")
    os.utime(tmp_path / "b.log", (OLD, OLD))
    os.utime(tmp_path / "c.log", (NEW, NEW))
    os.utime(tmp_path / "quiet.log", (NEW, NEW))
    return tmp_path


def _lines(grouped, arm):
    return [ln for _, _, lines in grouped[arm] for ln in lines]


def test_each_line_lands_under_its_arm_verbatim(logs):
    g = ap.collect([logs])
    assert _lines(g, "v20b") == [ln for ln in B_LOG.splitlines()
                                 if ln.split()[0] in {"LEVER", "V7B_ARM_DONE",
                                                      "MULTISEED_DONE",
                                                      "V20B_HEAD"}]
    assert _lines(g, "v20c0") == [
        "REPLAY_TEAM_MODEL p_cs min=0.0812 max=0.6123 distinct=310 n=380",
        'V7B_ARM_DONE v20c0-harness-branch-s20260901 {"total": 1849}']
    assert _lines(g, "v20c") == [
        "DC_CLIP n=12 of 380",
        'V7B_ARM_DONE v20c-clip-branch-s20260901 {"total": 1851}',
        'V20C_HEAD {"verdict": "fail: extreme"}']
    assert _lines(g, "v20d") == ['V20D_BRIER {"n": 0, "reason": "no log"}']
    assert _lines(g, "v20a") == []


def test_a_tag_no_arm_claims_goes_under_unclaimed(logs):
    assert _lines(ap.collect([logs]), "unclaimed") == [
        'V7B_ARM_DONE v19x-other-s20260901 {"total": 1700}']


def test_files_are_ordered_by_modification_time(logs):
    os.utime(logs / "b.log", (NEW + 60, NEW + 60))
    os.utime(logs / "c.log", (OLD, OLD))
    (logs / "c.log").write_text(C_LOG + "V20B_HEAD {\"late\": true}\n")
    os.utime(logs / "c.log", (OLD, OLD))
    g = ap.collect([logs])
    assert [f.name for f, _, _ in g["v20b"]] == ["c.log", "b.log"]


def test_since_keeps_only_files_modified_on_or_after_the_date(logs):
    g = ap.collect([logs], since=date(2026, 10, 14))
    assert g["v20b"] == []
    assert _lines(g, "v20d") == ['V20D_BRIER {"n": 0, "reason": "no log"}']
    assert ap.collect([logs], since=date(2026, 10, 13))["v20b"]


def test_a_log_with_no_such_line_prints_nothing(tmp_path, capsys):
    (tmp_path / "quiet.log").write_text("nothing to see\nRUN_EXIT 0\n")
    assert ap.main([str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def test_a_missing_path_prints_nothing(tmp_path, capsys):
    assert ap.main([str(tmp_path / "absent")]) == 0
    assert capsys.readouterr().out == ""


def test_the_block_is_section_six_shaped(logs, capsys):
    assert ap.main([str(logs / "b.log")]) == 0
    out = capsys.readouterr().out
    assert out.startswith("### v20b\n\n`")
    assert "modified 2026-10-13 (UTC)" in out
    body = out.split("```\n", 1)[1].rsplit("\n```", 1)[0]
    assert body.splitlines()[0] == "LEVER minutes cols=[minutes_r1, home]"
    assert len(body.splitlines()) == 5


def test_the_arms_print_in_order(logs, capsys):
    ap.main([str(logs)])
    heads = [ln for ln in capsys.readouterr().out.splitlines()
             if ln.startswith("### ")]
    assert heads == ["### v20b", "### v20c0", "### v20c", "### v20d",
                     "### unclaimed"]


def test_a_lever_line_after_the_last_tag_takes_that_replays_arm():
    out = ap.file_lines("V7B_ARM_DONE v20a-role-main-s1 {}\n"
                        "LEVER bonus cols=[bps_r3]\n")
    assert out[-1] == ("v20a", "LEVER bonus cols=[bps_r3]")


def test_the_corr_lever_line_goes_with_its_v20b_replay():
    """Holiday F-64: v20b's second lever line is collected like its first."""
    out = ap.file_lines("LEVER bonus cols=[bps_r3, e_goals]\n"
                        "LEVER bonus corr(e_goals,e_bonus)=0.412300 n=640\n"
                        "V7B_ARM_DONE v20b-bonus-branch-s1 {}\n")
    assert out[1] == ("v20b",
                      "LEVER bonus corr(e_goals,e_bonus)=0.412300 n=640")


def test_a_lever_line_with_no_v20_replay_falls_back_by_its_prefix():
    out = dict((line.split()[0], arm) for arm, line in ap.file_lines(
        "DC_CLIP n=3 of 10\nREPLAY_TEAM_MODEL p_cs n=0\n"
        "LEVER minutes cols=missing\n"))
    assert out == {"DC_CLIP": "v20c", "REPLAY_TEAM_MODEL": "v20c0",
                   "LEVER": "unclaimed"}


@pytest.mark.parametrize("tag, arm", [("v20c0-harness-main", "v20c0"),
                                      ("v20c-clip-main", "v20c"),
                                      ("v20c", "v20c"),
                                      ("v20cx-thing", "unclaimed"),
                                      ("v7b-old", "unclaimed")])
def test_the_tag_prefix_rule(tag, arm):
    assert ap.tag_arm(tag) == arm


def test_a_lever_line_of_a_replay_no_arm_claims_is_unclaimed():
    out = ap.file_lines("LEVER bonus cols=[a]\n"
                        "V7B_ARM_DONE v19x-s1 {}\n"
                        "LEVER bonus cols=[b]\n"
                        "V7B_ARM_DONE v20b-x-s1 {}\n")
    assert out == [("unclaimed", "LEVER bonus cols=[a]"),
                   ("unclaimed", "V7B_ARM_DONE v19x-s1 {}"),
                   ("v20b", "LEVER bonus cols=[b]"),
                   ("v20b", "V7B_ARM_DONE v20b-x-s1 {}")]


def test_a_head_runs_clip_lines_go_with_its_reading_not_the_next_replay():
    out = ap.file_lines("DC_CLIP n=4 of 90\n"
                        "V20C_HEAD {}\n"
                        "REPLAY_TEAM_MODEL p_cs n=0\n"
                        "V7B_ARM_DONE v20c0-harness-main-s1 {}\n")
    assert [arm for arm, _ in out] == ["v20c", "v20c", "v20c0", "v20c0"]


def test_a_file_named_twice_is_read_once(logs):
    g = ap.collect([logs, logs / "b.log"])
    assert [f.name for f, _, _ in g["v20b"]] == ["b.log"]


# Holiday F-40: the holiday reading scripts' one-line readings, each under the
# script that prints it, between the v20 arms and "unclaimed".

READINGS_LOG = """\
V7B_ARM_DONE v20d-price-main-s20260901 {"total": 1848}
C2_PPLAY {"top_bin": 0.93}
WALK_HITS_GW {"gw": 5, "walk": 1, "objective": 0}
WALK_HITS {"above": 1, "verdict": "hold"}
LEVER minutes cols=[minutes_r1]
V7B_ARM_DONE v20a-role-main-s20260901 {"total": 1852}
C2_PPLAY {"top_bin": 0.91}
"""


def test_readings_land_under_their_script_beside_a_v20_line(tmp_path):
    (tmp_path / "r.log").write_text(READINGS_LOG)
    g = ap.collect([tmp_path])
    assert _lines(g, "scripts/c2_pplay_bins.py") == [
        'C2_PPLAY {"top_bin": 0.93}', 'C2_PPLAY {"top_bin": 0.91}']
    assert _lines(g, "scripts/walk_hits.py") == [
        'WALK_HITS_GW {"gw": 5, "walk": 1, "objective": 0}',
        'WALK_HITS {"above": 1, "verdict": "hold"}']
    assert _lines(g, "v20d") == [
        'V7B_ARM_DONE v20d-price-main-s20260901 {"total": 1848}']
    # A reading is not a run: the lever line still takes the next replay's arm.
    assert _lines(g, "v20a") == [
        "LEVER minutes cols=[minutes_r1]",
        'V7B_ARM_DONE v20a-role-main-s20260901 {"total": 1852}']
    assert _lines(g, "unclaimed") == []


def test_reading_groups_print_after_the_arms_and_before_unclaimed(
        tmp_path, capsys):
    (tmp_path / "r.log").write_text(
        READINGS_LOG + "V7B_ARM_DONE v19x-other-s1 {}\n")
    ap.main([str(tmp_path)])
    heads = [ln for ln in capsys.readouterr().out.splitlines()
             if ln.startswith("### ")]
    assert heads == ["### v20a", "### v20d", "### scripts/c2_pplay_bins.py",
                     "### scripts/walk_hits.py", "### unclaimed"]


def test_a_log_with_only_presser_serve_prints_that_group_alone(
        tmp_path, capsys):
    line = 'PRESSER_SERVE {"n": 0, "reason": "no log", "verdict": "insufficient"}'
    (tmp_path / "p.log").write_text(f"starting\n{line}\nRUN_EXIT 0\n")
    ap.main([str(tmp_path)])
    out = capsys.readouterr().out
    assert [ln for ln in out.splitlines() if ln.startswith("### ")] == [
        "### scripts/presser_serve.py"]
    assert out.split("```\n", 1)[1].rsplit("\n```", 1)[0] == line


@pytest.mark.parametrize("line, group", [
    ("C1_BUCKETS {}", "scripts/c1_news_buckets.py"),
    ("C2_PPLAY {}", "scripts/c2_pplay_bins.py"),
    ("C3_HOME_AWAY {}", "scripts/c3_home_away.py"),
    ("B1_STATUS_AGE {}", "scripts/b1_status_age.py"),
    ("DENSITY_HEAD {}", "scripts/density_head.py"),
    ("TOP10K_PROJ {}", "scripts/top10k_projection.py"),
    ("WALK_HITS_GW {}", "scripts/walk_hits.py"),
    ("WALK_HITS {}", "scripts/walk_hits.py"),
    ("PCS_WINDOW {}", "scripts/pcs_window.py"),
    ("PCS_WINDOWS {}", "scripts/pcs_window.py"),
    ("PRESSER_GW {}", "scripts/presser_serve.py"),
    ("PRESSER_SERVE {}", "scripts/presser_serve.py"),
    ("BACKFILL_RANK gw=1 was=null now=123456",
     "scripts/backfill_overall_rank.py"),
])
def test_each_reading_prefix_has_its_script(line, group):
    assert ap.file_lines(line) == [(group, line)]


def test_a_prefix_inside_a_longer_word_is_not_a_reading():
    assert ap.file_lines("WALK_HITS_TOTAL {}\nC2_PPLAYS {}\n") == []


NOT_EVIDENCE = {
    # scripts/v12_w4_arms.py: a skip notice for an arm already shipped, not a
    # measurement, so the night shift has nothing to transcribe from it.
    "W4_ARM_SHIPPED",
}
"""Holiday F-43: printed prefixes the appendix leaves out on purpose."""

_PRINTED = re.compile(r'print\(f"([A-Z][A-Z0-9_]+) \{')


def test_every_reading_prefix_a_script_prints_is_collected():
    """Holiday F-43 (F-40's risk): a script that prints a new one-line
    reading must have it collected under its script or a v20 arm, or be
    named in ``NOT_EVIDENCE``; else it falls outside even ``unclaimed``."""
    printed = {m.group(1) for path in sorted(Path("scripts").glob("*.py"))
               for m in _PRINTED.finditer(path.read_text())}
    assert "C2_PPLAY" in printed and "V20D_BRIER" in printed
    missed = sorted(p for p in printed - NOT_EVIDENCE
                    if not ap.file_lines(p + " {}"))
    assert missed == []
    assert NOT_EVIDENCE <= printed
