"""The brief (v16 §6): the week, written by an LLM from a facts document
and checked mechanically before it is banked.

Three properties make this safe to serve:

*Facts first.* :func:`build_facts` gathers everything the prose may say —
the rung, the steps, the moves with the trace's gain and the sweep's
frequency, the captain, the league, a chip, last week's grade and note, a
data warning — rounded to the precision the UI shows (plan R13).

*The classifier's command.* ``cfg.news_llm_command`` is the same no-tools
``claude -p`` the presser classifier runs; the prompt says "from these facts
only". The reply is cached by the advice run's stamp and the prompt
version, so a page rebuild never re-asks.

*The truth check.* Every number and every name in the prose has to be in
the facts (:func:`check_brief`). A failure bans the brief: nothing is
banked, the stale one is removed, the card falls back to the digest with
a note. A dead command is the same event with a different note.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from gaffer import artifacts
from gaffer.artifacts import latest_gw, load_advice, load_solve_state
from gaffer.data.news.classifier import LLM_CACHE
from gaffer.io import atomic_write
from gaffer.config import Config
from gaffer.ladder import CHIP_LABEL, load_ladder, narrated

BRIEF_PROMPT_VERSION = 3
"""Bumped whenever :func:`build_prompt` changes; salts the cache key."""

BRIEF_CACHE = LLM_CACHE / "brief"

NOTE_FILE = "brief_note.json"
"""Why there is no brief for the newest gameweek, for the card."""

ALLOW = frozenset({
    "GW", "FPL", "XI", "I", "British", "Premier", "League", "Bank", "Free",
    "Hit", "Bench", "Boost", "Triple", "Captain", "Wildcard", "Fantasy",
    "Gameweek", "Gameweeks",
    "Plan", "A", "B", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    "Sunday", "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
})
"""Capitalised tokens that are never a name (plan R8): the product, the
chips as the prose spells them ("Bench Boost", "Triple Captain", "Free
Hit"), "Plan A"/"Plan B", days and months."""

_NUMBER = re.compile(r"[-+−]?\d+(?:[.,]\d+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_POSSESSIVE = re.compile(r"[’']s$")
_STRIP = ".,;:!?()\"'“”‘’%"


def brief_path(gw: int) -> Path:
    return artifacts.REPORTS / f"brief_gw{int(gw)}.json"


def note_path() -> Path:
    return artifacts.REPORTS / NOTE_FILE


def load_brief(gw: int) -> dict | None:
    path = brief_path(gw)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, dict) and payload.get("prose") else None
    except Exception as exc:  # noqa: BLE001 — a corrupt brief is no brief
        print(f"brief GW{gw} unreadable: {exc}")
        return None


def load_note() -> dict | None:
    try:
        return json.loads(note_path().read_text()) if note_path().exists() else None
    except Exception:  # noqa: BLE001
        return None


def first_sentence(prose: str) -> str:
    return _SENTENCE.split(str(prose or "").strip(), maxsplit=1)[0].strip()


# --- the facts --------------------------------------------------------------

def run_stamp(gw: int) -> str:
    """The advice run's own stamp, off the solve state."""
    return str(load_solve_state(gw).generated_at)


def move_gains(gw: int) -> dict[int, float]:
    """``{buy code: decayed gain}`` off the plan trace, or ``{}``."""
    try:
        from gaffer.web.routers.plan import plan as plan_timeline
        week = plan_timeline(gw).weeks[0]
        if week.trace is None:
            return {}
        return {int(m.buy_code): float(m.ep_gain) for m in week.trace.moves
                if m.buy_code is not None and m.ep_gain is not None}
    except Exception as exc:  # noqa: BLE001 — a gain is decoration
        print(f"brief: no trace gains ({exc})")
        return {}


def _pct(value) -> int | None:
    return None if value is None else int(round(float(value) * 100))


def _last_week(gw: int) -> dict | None:
    from gaffer.decisions import note_for
    from gaffer.review import load_ledger

    rows = [r for r in load_ledger() if int(r.get("gw", -1)) < int(gw)]
    if not rows:
        return None
    row = max(rows, key=lambda r: int(r["gw"]))
    note = note_for(int(row["gw"]))
    return {"gw": int(row["gw"]), "you": row.get("my_points"),
            "model": row.get("model_points"),
            "lanes": [{"lane": ln.get("lane"), "label": ln.get("label"),
                       "delta_pts": ln.get("delta_pts")}
                      for ln in row.get("lanes") or [] if ln.get("delta_pts") is not None],
            "note": ({"reason": note["reason"], "text": note["text"]}
                     if note.get("reason") else None)}


def build_facts(gw: int) -> dict:
    """Everything the prose may say, rounded as the UI rounds (§6.2)."""
    # v17b §3.3: the blocks carry their prose; an advice banked before this
    # cycle gets it here, from the one author, never composed in the brief.
    advice = narrated(load_advice(gw))
    ladder = load_ladder(gw) or {}
    gains = move_gains(gw)
    freq = {(str(r.get("kind")), int(r.get("code"))): float(r.get("frequency"))
            for r in advice.get("move_frequencies") or []
            if r.get("code") is not None and r.get("frequency") is not None}
    restraint = advice.get("restraint") or {}
    # v17b §3.3: the steps are the served lines; the prose and the cards agree
    # by construction, and the checker already reads numbers and names out of
    # strings.
    steps = [{"line": s.get("line") or "", "taken": bool(s.get("taken"))}
             for s in restraint.get("steps") or []]
    buys, sells = advice.get("buys") or [], advice.get("sells") or []
    moves = [{"in": b["name"], "out": (sells[i]["name"] if i < len(sells) else None),
              "gain": (None if gains.get(int(b["code"])) is None
                       else round(gains[int(b["code"])], 1)),
              "sims_pct": _pct(freq.get(("buy", int(b["code"]))))}
             for i, b in enumerate(buys)]
    strat = advice.get("strategy") or None
    league = None
    if strat:
        league = {"name": _focus_name(), "stance": strat.get("stance"),
                  "manual": strat.get("source") == "manual",
                  "gap": (None if strat.get("gap") is None else int(round(abs(float(strat["gap"]))))),
                  "lam": (None if strat.get("lam") is None else round(float(strat["lam"]), 2)),
                  "rival": strat.get("rival_name")}
    chip = next(({"chip": CHIP_LABEL.get(str(r.get("chip")), str(r.get("chip"))),
                  "gw": int(r["gw"]),
                  "gain": round(float(r.get("gain") or 0), 1),
                  "threshold": (None if r.get("threshold") is None
                                else round(float(r["threshold"]), 1))}
                 for r in advice.get("chip_table") or [] if r.get("play_now")), None)
    objective = advice.get("objective") or None
    obj = None
    if objective is not None:
        osells = objective.get("sells") or []
        obj = {"agrees": bool(restraint.get("agrees", True)),
               "hits": int(objective.get("hits") or 0),
               "moves": [{"in": b["name"],
                          "out": osells[i]["name"] if i < len(osells) else None}
                         for i, b in enumerate(objective.get("buys") or [])],
               "line": objective.get("line")}
    hits = int(advice.get("hits") or 0)
    # v17b §3.3: the served cost, or the config's own default for an advice
    # banked before the block carried one; never a literal.
    cost = restraint.get("hit_cost")
    hit_points = hits * int(cost if cost is not None else Config.hit_cost)
    # ``narrated`` labelled any block with a chosen rung; none chosen is bank.
    chosen_label = restraint.get("label") or "bank"
    return {
        "gw": int(gw), "horizon": [int(g) for g in ladder.get("gws") or [int(gw)]],
        "expected_pts": (None if advice.get("expected_pts") is None
                         else round(float(advice["expected_pts"]), 1)),
        "hits": hits, "hit_points": hit_points,
        "restraint": {"chosen_label": chosen_label,
                      "bar_pct": _pct(restraint.get("bar")),
                      "line": restraint.get("line"), "steps": steps},
        "moves": moves,
        "captain": {"name": (advice.get("captain") or {}).get("name"),
                    "sims_pct": _pct((advice.get("scenarios") or {}).get("captain_frequency")),
                    "note": advice.get("captain_note") or None},
        "league": league, "chip": chip, "last_week": _last_week(gw),
        "data_warning": advice.get("data_warning") or None, "objective": obj,
    }


def _focus_name() -> str | None:
    """The focus league's name, when something on disk already knows it.

    Nothing does. The overview's ``focus_name`` is built inside
    ``web.routers.league.leagues`` from ``_league_rows(fpl_client(), cfg)``,
    which is a live call to the FPL API, and no artifact under ``reports/``
    banks the name: the advice payload carries the gap, the stance and the
    *rival's* team name, never the league's. A brief written by a launchd
    job at 17:00 on a Friday may not depend on the network, so this stays
    ``None`` and the prompt's league sentence says "your league" — the
    facts' ``rival`` is the name the prose actually needs.

    The moment a loader banks it (a league snapshot, say), read it here.
    """
    return None


# --- the prompt and the command ------------------------------------------

def build_prompt(facts: dict) -> str:
    return "\n".join([
        "You are writing this week's Fantasy Premier League brief for one "
        "manager, from the facts below and nothing else.",
        "",
        "Rules:",
        "- British English. Six to twelve sentences of plain prose in one or "
        "two paragraphs. No headings, no bullet points, no numbered lists.",
        "- Use only numbers that appear in the facts, written exactly as they "
        "appear: a share as a whole percent such as 46%, points to one decimal.",
        "- Name only the players, the league and the rival named in the facts. "
        "Never name a club. Do not start a sentence with a player's name.",
        "- Do not invent a fact, a reason or a caveat. If a field is null, "
        "leave it out.",
        "- expected_pts is this gameweek's starting eleven alone, before any "
        "hit is paid; say it as this week's number, never as a total over "
        "the horizon. horizon is the run of gameweeks the plan was solved "
        "over. A move's gain is over that horizon.",
        "- hits is the number of hits this week and hit_points what they "
        "cost.",
        "",
        "Say, in this order: which rung the ladder chose and every step's line, "
        "taken or refused; each move with its gain and "
        "its sims share; the captain, his sims share and any note; the league "
        "(name, stance, whether it was set by hand, the gap and the tilt); a "
        "chip if there is one; last week's grade per lane and the manager's "
        "own note, quoted; any data warning. When objective.agrees is false, "
        "say in one sentence what the objective wanted instead.",
        "",
        "Facts (JSON):",
        json.dumps(facts, ensure_ascii=False, indent=1),
        "",
        "Reply with the brief only.",
    ])


def extract_text(stdout: str) -> str:
    """The model's text out of ``claude -p --output-format json``'s envelope,
    a JSON string, or plain text."""
    raw = str(stdout or "").strip()
    try:
        payload = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(payload, dict):
        return str(payload.get("result") or "").strip()
    if isinstance(payload, str):
        return payload.strip()
    return raw


def run_command(cmd: str, prompt: str, timeout_s: int) -> str:
    """One call. Raises on a non-zero exit, a timeout or an empty reply."""
    proc = subprocess.run(shlex.split(cmd), input=prompt, capture_output=True,
                          text=True, timeout=timeout_s, check=True)
    text = extract_text(proc.stdout)
    if not text:
        raise ValueError("the command returned no text")
    return text


def cache_key(stamp: str, version: int = BRIEF_PROMPT_VERSION) -> str:
    return hashlib.sha256(f"{version}\x00{stamp}".encode("utf-8")).hexdigest()[:16]


# --- the truth check ---------------------------------------------------------

def _leaves(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v)
    elif isinstance(node, list):
        for v in node:
            yield from _leaves(v)
    else:
        yield node


def fact_numbers(facts: dict) -> set[str]:
    """Every number in the facts, in the forms the prose may write it —
    the numeric leaves, and the numbers inside the strings: a step's reason
    ("Fernandes is 96% to drop tonight"), the note, a data warning. The
    prompt asks for every reason to be said, so what a reason says has to
    be sayable."""
    out: set[str] = set()
    for leaf in _leaves(facts):
        if isinstance(leaf, str):
            out |= {tok.replace("−", "-").replace(",", ".").lstrip("+")
                    for tok in _NUMBER.findall(leaf)}
            continue
        if isinstance(leaf, bool) or not isinstance(leaf, (int, float)):
            continue
        forms = {str(leaf)}
        if isinstance(leaf, float):
            forms |= {f"{leaf:.1f}", f"{leaf:.2f}", f"{leaf:g}"}
            if leaf.is_integer():
                forms.add(str(int(leaf)))
        out |= forms
        out |= {f.lstrip("-") for f in forms}
    return out


def fact_names(facts: dict) -> set[str]:
    """Every string in the facts, whole and token by token (``"Shocky
    Supplies"``, ``"Shocky"``, ``"Supplies"``; a hyphenated name stays
    whole). Every string, not only the name fields: a refused step's reason
    names the player the rung above would have sold, who is in no move
    list, and the prompt asks for that reason to be said."""
    out: set[str] = set()
    for leaf in _leaves(facts):
        if isinstance(leaf, str) and leaf:
            out.add(leaf)
            out.update(_POSSESSIVE.sub("", tok.strip(_STRIP))
                       for tok in leaf.split())
    out.discard("")
    return out


def check_brief(prose: str, facts: dict) -> list[str]:
    """The offences, one string each; ``[]`` is a pass (§6.4, plan R8)."""
    numbers, names = fact_numbers(facts), fact_names(facts)
    offences: list[str] = []
    for sentence in _SENTENCE.split(str(prose or "").strip()):
        if not sentence:
            continue
        for tok in _NUMBER.findall(sentence):
            norm = tok.replace("−", "-").replace(",", ".").lstrip("+")
            if norm not in numbers and norm.lstrip("-") not in numbers:
                offences.append(f"number {norm} is not in the facts: {sentence}")
        for i, word in enumerate(sentence.split()):
            clean = _POSSESSIVE.sub("", word.strip(_STRIP))
            if i == 0 or not clean or not clean[0].isupper():
                continue
            if clean in ALLOW or re.fullmatch(r"GW\d+", clean):
                continue
            if clean not in names:
                offences.append(f"name {clean} is not in the facts: {sentence}")
    return offences


# --- the run ------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _bank_note(gw: int | None, note: str) -> None:
    try:
        artifacts.REPORTS.mkdir(parents=True, exist_ok=True)
        atomic_write(note_path(), json.dumps({"gw": gw, "note": note, "at": _now()}))
    except Exception as exc:  # noqa: BLE001
        print(f"brief note not written: {exc}")


def run_brief(gw: int | None = None, *, cfg=None,
              cache_dir: Path = BRIEF_CACHE) -> dict:
    """Build, check and bank the brief. Never raises.

    Returns ``{"gw", "written", "note", "path"}``. A dead command, a timeout,
    a failed check and a missing advice are all ``written: False`` with a
    note — a finished job, not a failed one (§6.5).
    """
    try:
        gw = latest_gw() if gw is None else int(gw)
    except Exception:  # noqa: BLE001
        gw = None
    if gw is None:
        note = "no advice on disk — run `gaffer advise` first"
        print(f"brief not written: {note}")
        return {"gw": None, "written": False, "note": note, "path": None}
    if cfg is None:
        from gaffer.config import config_in_force
        cfg = config_in_force()
    cmd = str(getattr(cfg, "news_llm_command", "") or "").strip()
    if not cmd:
        note = "no llm_command configured under [news]"
        _bank_note(gw, note)
        return {"gw": gw, "written": False, "note": note, "path": None}
    try:
        facts = build_facts(gw)
        stamp = run_stamp(gw)
    except Exception as exc:  # noqa: BLE001
        note = f"brief not written: the facts could not be built ({exc})"
        print(note)
        _bank_note(gw, note)
        return {"gw": gw, "written": False, "note": note, "path": None}
    key = cache_key(stamp)
    cache_dir = Path(cache_dir)
    cached = cache_dir / f"{key}.json"
    prose = None
    if cached.is_file():
        try:
            prose = json.loads(cached.read_text(encoding="utf-8")).get("prose")
        except Exception:  # noqa: BLE001 — a corrupt entry is a miss
            prose = None
    if not prose:
        try:
            prose = run_command(cmd, build_prompt(facts),
                                int(getattr(cfg, "news_llm_timeout_s", 300)))
        except Exception as exc:  # noqa: BLE001 — the brief never blocks
            note = f"brief not written: the command did not answer ({exc})"
            print(note)
            _bank_note(gw, note)
            return {"gw": gw, "written": False, "note": note, "path": None}
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps({"prose": prose, "model": shlex.split(cmd)[0],
                                          "at": _now()}), encoding="utf-8")
        except Exception:  # noqa: BLE001 — an unwritable cache is not an outage
            pass
    offences = check_brief(prose, facts)
    if offences:
        for line in offences:
            print(f"brief check: {line}")
        note = f"the brief did not pass its check this week ({offences[0]})"
        brief_path(gw).unlink(missing_ok=True)
        # The banned prose leaves the cache too: a retry from the button is
        # a fresh sample, not the same sentence refused a second time.
        cached.unlink(missing_ok=True)
        _bank_note(gw, note)
        return {"gw": gw, "written": False, "note": note, "path": None}
    payload = {"gw": gw, "run_stamp": stamp, "prose": prose, "facts": facts,
               "model_command": shlex.split(cmd)[0], "prompt_version": BRIEF_PROMPT_VERSION,
               "checked_at": _now()}
    artifacts.REPORTS.mkdir(parents=True, exist_ok=True)
    atomic_write(brief_path(gw), json.dumps(payload, indent=1, ensure_ascii=False))
    note_path().unlink(missing_ok=True)
    print(f"Brief GW{gw}: {first_sentence(prose)}")
    return {"gw": gw, "written": True, "note": None, "path": str(brief_path(gw))}


def latest_brief() -> dict | None:
    """The newest banked brief by gameweek, or ``None``."""
    try:
        paths = sorted(artifacts.REPORTS.glob("brief_gw*.json"),
                       key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    except Exception:  # noqa: BLE001
        return None
    for path in reversed(paths):
        payload = load_brief(int(re.sub(r"\D", "", path.stem) or 0))
        if payload is not None:
            return payload
    return None
