"""v12 W1's degradation rails, and the two absolute pins the suite has left.

Every rail here is a state a real machine reaches, and several are the state
this machine is in today: a write interrupted, a season log carrying two
seasons, a report that would overwrite a good one with a degraded one, a tree
with no backups at all, a phone on the LAN with no token.

The file also holds **the only absolute config-field count in the suite**.
Seven protected degradation files used to assert it, which meant every cycle
entitled to add a config key first had to buy seven authorizations — and one
cycle did not: ``tests/test_v10_config_providers.py``'s docstring records v10
abandoning a designed dataclass field for a module-level reader because two of
them pinned the number. v12 W1 applied v11's route-pin restructure to the
config pin. The route total stays where v11 left it, in
``tests/test_v11_degradation.py``; the asymmetry is deliberate, because what
matters is that each total lives in exactly one file and moving the route pin
here would be a protected edit that bought nothing.
"""

from __future__ import annotations


# =====================================================================
# Block 8 — the counts
# =====================================================================

def test_the_config_gained_exactly_five_fields():
    """48 at 27f7933 and 53 now, and **this is the only absolute config-field
    pin in the suite.**

    Seven protected files used to assert 48. That is not a hypothetical cost:
    ``tests/test_v10_config_providers.py``'s docstring records v10 abandoning
    a designed dataclass field because two of them did, and settling for a
    module-level reader instead. v12 W1 replaced each with the by-name claim
    its own cycle is entitled to make — v11's route-pin restructure, applied
    to the other pin — and a future cycle that adds a key moves this number,
    here, and nowhere else.

    Pinned as a total *and* by name: a count alone would let a key be added
    and another removed in one cycle, and W1's claim is precisely which five.
    """
    import dataclasses

    from gaffer.config import Config

    names = {f.name for f in dataclasses.fields(Config)}
    assert len(names) == 53
    assert {"backup_dir", "backup_rsync_target", "backup_keep",
            "top_n", "web_token"} <= names


def _suite_files():
    """Anchored to this file's own directory, not the working directory —
    v11's rail learned that the hard way: a ``pytest`` run from anywhere but
    the repo root globbed nothing, and a sweep over an empty list passes by
    saying nothing at all."""
    import pathlib

    files = sorted(pathlib.Path(__file__).parent.glob("test_*.py"))
    assert len(files) > 1
    return files


def test_only_one_file_pins_the_absolute_config_field_count():
    """A rail on the rails, exactly as v11 wrote for routes. Without it the
    eighth pin grows back the next time somebody adds a key and reaches for
    the nearest example."""
    import re

    # Anchored to `assert` at the start of a line, because seven files now
    # carry a *comment* saying the count used to be here — the restructure's
    # own audit trail must not read as the pin it replaced. And qualified by
    # `fields(Config)` somewhere in the file, because `len(names) == N` is a
    # shape other suites use about other sets (`test_v12_io.py` counts temp
    # files that way).
    pin = re.compile(r"^\s*assert\s+len\(\s*(?:names"
                     r"|(?:dataclasses\.)?fields\(\s*Config\s*\))\s*\)"
                     r"\s*==\s*\d+", re.M)
    hits = [p.name for p in _suite_files()
            if "fields(Config)" in (text := p.read_text()) and pin.search(text)]
    assert hits == ["test_v12_w1_degradation.py"]


def test_only_one_file_pins_the_absolute_route_count():
    """The other half of the same rail, and the reason this file does not hold
    that number: v11 built the single home for it and W1 spent it there. Two
    files pinning one total is the shape both restructures existed to end, so
    "exactly one, and it is v11's" is the claim rather than "not here"."""
    import re

    pin = re.compile(r"^\s*assert\s+len\(\s*(?:set\()?\s*paths\)?\s*\)"
                     r"\s*==\s*\d+", re.M)
    hits = [p.name for p in _suite_files() if pin.search(p.read_text())]
    assert hits == ["test_v11_degradation.py"]


def test_the_job_kinds_are_still_twelve():
    """W1 adds three CLI commands and no lane. A thirteenth kind would also
    need a row in ABANDON_TIMEOUT_S or SLOW_ABANDON_KINDS, pinned as jointly
    exhaustive in the protected test_v9d_degradation.py."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 12
