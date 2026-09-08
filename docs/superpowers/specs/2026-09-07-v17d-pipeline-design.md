# v17d — one weekly pipeline module

Programme: `docs/superpowers/plans/2026-09-07-v17-deepening-programme.md`
§v17d. Review card `#c4` in
`docs/superpowers/research/2026-09-07-architecture-review.html`. Branch
`v17d-pipeline` off `main` at `0cff561` (v17c's docs commit; merge hash
`ee02520`).

## 0. Why

The weekly run — train, advise, render, brief — is defined today inside an
HTTP router (`web/routers/advice.py::run_train_and_advise`), imported from
there by the job registry (`web/job_kinds.py`), and re-assembled by hand
in the CLI (`cli.py::advise`), which builds only three of the four steps.
That is why the Thursday launchd job, which runs the CLI, produces advice
with no brief, and why GUIDE §12.4 carries an open note saying the plist
needs `gaffer brief` appended. The fix is not the plist. It is one module
with one interface that the CLI, the job kind and therefore launchd all
call, so that a step present in one is present in all (locality), and the
router keeps request handling only.

## 1. Gate, stated before anything runs (CONVENTIONS §2, §7, §10)

Run by the orchestrator on the branch after the suites are green. All four
must hold.

1. **The golden board is unmoved.** `.venv/bin/pytest -q tests/test_golden_board.py`
   passes on the branch with `tests/data/golden_board/` untouched, no test
   skipped. `run_golden` still calls `run_advise(golden_config(), client)`
   directly, so this proves the advise step itself is untouched; the
   verdict rule allows no key to differ.
2. **Parity across the two entries, with a stubbed LLM.** A new
   `golden`-marked test in `tests/test_pipeline.py` runs the weekly run
   twice on the golden board, each in its own fresh scratch tree over the
   recorded client, with the train step stubbed to a no-op (the models are
   the golden's pinned input, §2.6) and with `news_llm_command` set to the
   stub command
   `python3 -c "print('The plan holds. Bank the free transfer and keep the armband where it is.')"`.
   Entry A is the CLI: `CliRunner().invoke(app, ["advise"])`. Entry B is the
   job kind: `JOB_KINDS["advise"]()`. The rule: after `strip_volatile`,
   both runs' `reports/gw4-advice.json` equal each other **and** equal
   `tests/data/golden_board/expected/advice.json`; both runs wrote
   `reports/brief_gw4.json` whose `prose` is the stub's sentence and for
   which `check_brief(prose, facts)` is `[]`; the CLI exit code is 0 and
   entry B's return value is `{"gw": 4, "expected_pts": <the expected
   file's>, "brief": {"written": True, ...}}`. The stub answering in both
   trees is what shows the brief step ran through each entry rather than
   an empty diff on a step that never fired (CONVENTIONS §10).
3. **The router is not imported by non-web code.**
   `grep -rn "routers.advice" src/gaffer/web/job_kinds.py src/gaffer/pipeline.py src/gaffer/cli.py`
   prints nothing, and `grep -c "def run_train_and_advise" src/gaffer/web/routers/advice.py`
   prints 0.
4. **The plist, unchanged, now yields a brief.** `git diff main -- scripts/com.gaffer.advise.plist`
   is empty; the plist still runs `gaffer train && gaffer advise`; and a
   unit test in `tests/test_pipeline.py` shows the CLI `advise` command
   calls `weekly_run` and that `weekly_run` calls `brief.run_brief` after
   `render_report` on success and not at all when advise raises. GUIDE
   §12.4's note "The brief is chained only on the web advise job" is
   removed in the docs commit.

Also required, not part of the verdict rule: `.venv/bin/pytest -q` green
with the new tests counted; `cd frontend && npx tsc --noEmit && npx vitest run`
unchanged (no frontend file changes); pins routes 51, job kinds 12, `Config`
fields 59 unchanged; the security ritual from CLAUDE.md after the push.

Verdict: pass if all four hold on the first full run after the
implementation is complete. A failure is fixed on the branch and the gate
is rerun in full; §10 records every run. If the brief cannot be made to
pass its check on the golden board through a fixed-prose stub (item 2), the
run's note goes in §10, nothing merges, and the tracker's hand-off note
says which fact the check tripped on.

## 2. The decisions the grilling settled

1. **The interface.**

   ```python
   @dataclass
   class RunResult:
       advice: Advice          # what run_advise returned
       report_path: Path       # what render_report wrote
       brief: dict             # run_brief's {"gw", "written", "note", "path"}
       trained: bool           # whether the train step ran this call
       training_rows: int | None   # len(frame) when it did, else None

       def record(self) -> dict:
           """The dict the job runner stores: {"gw", "expected_pts",
           "brief"} — byte-for-byte what run_train_and_advise returned."""

   def weekly_run(cfg: Config, *, client: FPLClient | None = None,
                  train: bool = True, log: Callable[[str], None] = print
                  ) -> RunResult:
   ```

   Steps, in order: train (when `train`), advise, render, brief. The
   config is an argument, never read inside: `load_config()` is the
   callers' business, as `run_advise`'s already is. `client` passes
   straight to `run_advise(cfg, client=client)` — the seam v17c made real.
   Neither gate entry can hand a client in (the CLI has no such flag; the
   runner calls the kind with no arguments), so the parity test patches
   `gaffer.advise.FPLClient` to answer the `RecordedClient` it built and
   hands the same instance to `golden_cwd` so the politeness hush applies.

2. **What raises and what does not.** Train, advise and render raise
   exactly as they do today: `SystemExit` from `run_advise` when a model is
   missing (before any network call), `GafferError` when there is no next
   gameweek, anything else as itself. The brief never raises: `run_brief`
   already promises that, and the pipeline wraps the *import and call* in
   the same `except Exception` the web body has, so an `ImportError` in
   `brief.py` is a note in the result, not a failed run. "Never raising
   past the brief" means exactly this and no more; a pipeline that
   swallowed a missing model would turn the CLI's one-line exit into a
   traceback-free silence.

3. **What each caller keeps.**

   | Caller | Calls | Keeps |
   |---|---|---|
   | `cli.py::advise` | `weekly_run(cfg, train=False)` | `advice` for its printed summary, `report_path` for the `Report:` line, `brief["note"]` echoed when present (as `gaffer brief` does); its two `except` arms and `typer.Exit(1)` stay around the call |
   | `job_kinds.py::run_train_and_advise(cfg=None)` | `weekly_run(cfg or load_config())` | `.record()` — the runner's stored result, unchanged in shape |
   | `job_kinds.py::run_train_and_advise_fast` | the body above under `scenarios_n=0` | unchanged |
   | launchd `com.gaffer.advise` | the CLI | stdout into `logs/advise.log`; gains the brief's line |

   The `advise` command does not train. The plist runs `gaffer train &&
   gaffer advise`, and a CLI that trained again would double the most
   expensive step on every Thursday; `train=True` is the job kind's
   default because the button has no separate train step. The plist is
   therefore unchanged (gate item 4), and `gaffer advise --fast` keeps its
   one flag.

4. **The config reaches the brief.** The web body called `run_brief(gw)`
   and let the brief read `serving_config()` for its command; the pipeline
   calls `run_brief(advice.gw, cfg=cfg)`. Same file, same values on every
   path that exists today (the CLI and the job both hold `load_config()`'s
   answer to the same `config.toml`), and the only path where it differs —
   a config handed in by a test — is the one the parity gate rides on.
   `advise-fast`'s `scenarios_n=0` is not read by the brief.

5. **Output order in the terminal.** The brief runs inside `weekly_run`,
   so its own printed line (`Brief GW4: …` or `brief not written: …`)
   appears *before* the CLI's `=== GW4` banner and summary. A hook to
   print the summary between render and brief was considered and refused:
   one adapter is a hypothetical seam. The order is recorded here and in
   the GUIDE; the launchd log reads train, brief, summary.

6. **The parity test stubs training.** `models/` is the golden's pinned
   input, hashed by SHA-256; a real `train_all(save=True)` inside the
   parity run would rewrite it through the scratch tree's symlink and fail
   the third golden test on purpose. So the test patches
   `gaffer.models.train.load_training_frame` and `train_all` to no-ops
   for entry B, and the train step's own contract (it runs when `train`
   is true, with `save=True`, and `trained` / `training_rows` report it)
   is pinned by unit tests with the same stubs. The train step's real
   behaviour is `cli.py::train`'s two lines, moved, not changed.

7. **The stub command.** `news_llm_command` is a shell string the brief
   runs with `shlex.split` and the prompt on stdin, expecting plain text
   or the `claude -p` JSON envelope on stdout. The stub is
   `python3 -c "print('The plan holds. Bank the free transfer and keep the armband where it is.')"`:
   no digit, so the number check has nothing to test; every capitalised
   word is sentence-initial, so the name check has nothing to test; and it
   ignores stdin. The brief payload's `model_command` is then `python3`,
   which is the second thing the parity test reads to know the stub, not a
   cache, answered. Each entry runs in a fresh scratch tree so the
   brief cache (`brief.BRIEF_CACHE`, a relative path under
   `data/raw/news/llm/`) written by entry A cannot serve entry B.

8. **`golden_client.run_golden` grows a context manager, not a second
   runner.** The chdir, the `serving_config` cache clears on both sides and
   the politeness-sleep hush for a `RecordedClient` move into
   `golden_client.golden_cwd(root, client)`; `run_golden` becomes a
   `with golden_cwd(...)` around the same `run_advise` call and the two
   reads. The parity test uses the same context around the CLI invocation
   and the job kind call. Its three existing tests
   (`test_run_golden_runs_in_the_scratch_tree…`, `…keeps_the_politeness_sleep…`,
   `…restores_the_cwd_when_the_run_raises`) keep passing unchanged.

9. **Every test that invokes the CLI `advise` stubs the brief.** Today
   those tests (v4c's three, v13's one, v16's fixture, `test_cli.py`'s
   helper) stub `run_advise`, `render_report` and `latest_health` and leave
   the brief alone, because the CLI never ran it. With the brief chained
   and `DEFAULT_LLM_COMMAND` being `claude -p …`, an unstubbed brief in a
   test whose working directory is the repo would read the real
   `reports/` and run the real command. So every such test gains
   `monkeypatch.setattr("gaffer.brief.run_brief", lambda gw, cfg=None: {...written False, note None...})`.
   v4c's character-for-character rail stays byte-identical because the
   stub prints nothing and the CLI echoes a note only when there is one.
   This is the one edit the protected rails need; §7 records the ruling.

10. **Tests that move and tests that die.** The three chain tests in
    `tests/test_v16_web_brief.py` (`…chains_the_brief_on_success`,
    `…does_not_fire_when_advise_fails`, `…a_brief_that_raises_does_not_fail…`)
    are rewritten against `weekly_run` in `tests/test_pipeline.py` and
    deleted from where they are. `tests/test_web_job_kinds_v7c.py`'s two
    `run_train_and_advise` tests and `tests/test_web_job_kinds.py`'s
    "reuse the router entry points" test change their import to
    `gaffer.web.job_kinds` (orchestrator, §7). No test is weakened.

11. **The router's docstring.** `routers/advice.py` no longer describes a
    job body it does not hold; its module docstring says the body moved
    to `pipeline.py` in v17d and that `POST /api/jobs/advise` is still the
    one way in.

12. **Lazy imports inside `weekly_run`.** `pipeline.py` imports
    `run_advise`, `train_all`, `render_report`, `latest_health` and
    `run_brief` inside the function, as the CLI does, for two reasons the
    CLI already gives: `--help` must not load lightgbm, and every existing
    test stubs these by module attribute (`gaffer.advise.run_advise`),
    which only a call-time import sees.

## 3. Approach, and the two rejected

**Chosen: one function, one result dataclass, callers keep their own
presentation.** `weekly_run` does the four steps and returns everything
each produced; the CLI prints from the result, the job kind records from
it.

*Rejected: the CLI shells out to `gaffer brief` after advise.* Closes the
plist note but leaves three copies of the sequence and the router still
imported by `job_kinds`. It fixes the symptom the card names and none of
the structure.

*Rejected: `weekly_run` takes an `on_advice` hook so the CLI prints its
summary before the brief runs.* One adapter for a seam; the terminal
order is a cosmetic cost the spec records instead (§2.5).

## 4. The interface

`src/gaffer/pipeline.py`:

```python
"""The weekly run, once (v17d §2). Train → advise → render → brief.

Three callers, one body: ``cli.advise`` (train=False; the plist trains
first), ``web.job_kinds.run_train_and_advise`` (train=True) and through the
CLI the Thursday launchd job. Nothing here decides anything about the
advice; the steps are the four functions they always were, in the order
the web job ran them, and the brief is the only step that never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from gaffer.advise import Advice
    from gaffer.api.client import FPLClient
    from gaffer.config import Config


@dataclass
class RunResult:
    advice: "Advice"
    report_path: Path
    brief: dict
    trained: bool
    training_rows: int | None

    def record(self) -> dict:
        return {"gw": self.advice.gw, "expected_pts": self.advice.expected_pts,
                "brief": self.brief}


def weekly_run(cfg: "Config", *, client: "FPLClient | None" = None,
               train: bool = True,
               log: Callable[[str], None] = print) -> RunResult:
    trained, rows = False, None
    if train:
        from gaffer.models.train import load_training_frame, train_all
        frame, team_frame, _ = load_training_frame()
        train_all(frame, team_frame, save=True)
        trained, rows = True, len(frame)
        log(f"Trained on {rows} player-GW rows. Models saved to models/.")
    from gaffer.advise import run_advise
    from gaffer.report.render import render_report
    from gaffer.tracking import latest_health
    advice = run_advise(cfg, client=client)
    report_path = Path(render_report(advice, model_health=latest_health()))
    # v16 §6.5 (plan R1), now v17d §2.2: the brief is chained here, after
    # the report, and never fails the run.
    try:
        from gaffer.brief import run_brief
        brief = run_brief(advice.gw, cfg=cfg)
    except Exception as exc:  # noqa: BLE001
        brief = {"gw": advice.gw, "written": False,
                 "note": f"brief not written: {exc}", "path": None}
        log(brief["note"])
    return RunResult(advice=advice, report_path=report_path, brief=brief,
                     trained=trained, training_rows=rows)
```

`len(frame)` is what `cli.py::train` prints today; a stubbed frame of
`None` in a test is handled by the test stubbing a frame with a length.

`src/gaffer/web/job_kinds.py` gains, in place of the import from the
router:

```python
def run_train_and_advise(cfg: "Config | None" = None) -> dict:
    """The advise kind's body: ``pipeline.weekly_run`` with the train step
    on, recorded as the runner stores it. ``cfg`` defaults to ``None`` so
    the runner's zero-argument call is untouched; ``advise-fast`` hands it
    ``scenarios_n=0``."""
    from gaffer.config import load_config
    from gaffer.pipeline import weekly_run

    return weekly_run(cfg if cfg is not None else load_config()).record()
```

`src/gaffer/cli.py::advise` replaces its `run_advise` / `latest_health` /
`render_report` lines with one `weekly_run(cfg, train=False)` inside the
same two `except` arms, prints its summary from `result.advice`, its
`Report:` line from `result.report_path`, and then `result.brief["note"]`
when present. Nothing else in the command changes, and the v4c rail is the
proof.

`src/gaffer/web/routers/advice.py` loses `run_train_and_advise`, its
`TYPE_CHECKING` import of `Config`, and the docstring paragraph about the
body.

`tests/golden_client.py` gains `golden_cwd(root, client)` (§2.8).

## 5. What sits behind the seam

Behind `weekly_run`: which four functions run, in what order, with what
arguments; that the report is rendered with the latest health; that the
brief gets the config in force and cannot fail the run; the shape of the
job record. In front of it: presentation (the CLI's summary and exit
codes; the job runner's stored dict), the choice to train, and the choice
of client. Three adapters call it — the CLI, the job kind, and the parity
test's second scratch tree — so the seam is real by the review's own rule.

`run_advise` stays where it is and keeps its signature; `advise.py` is not
touched (protected, and v17g's business).

## 6. Tests (`tests/test_pipeline.py`)

Unit, all with the module-attribute stubs the v16 chain tests use:

- `test_the_steps_run_in_order_train_advise_render_brief` — a call log
  reads `["train", "advise", "render", "brief"]`; `result.trained` is true
  and `training_rows` is the stubbed frame's length.
- `test_train_false_skips_the_train_step_and_says_so` — the log has no
  `"train"`, `trained` is false, `training_rows` is `None`.
- `test_the_client_reaches_run_advise` — a sentinel client is what
  `run_advise` receives.
- `test_the_brief_gets_the_config_in_force` — `run_brief` is called with
  `advice.gw` and `cfg=cfg`.
- `test_the_brief_does_not_fire_when_advise_raises` — moved from v16.
- `test_a_brief_that_raises_is_a_note_not_a_failed_run` — moved from v16;
  the `log` callable receives the note.
- `test_record_is_the_dict_the_runner_stored` — `record()` equals the
  three-key dict, key order included.
- `test_the_cli_advise_command_runs_the_pipeline_without_training` —
  `weekly_run` stubbed on `gaffer.pipeline`; the CLI called it with
  `train=False` and echoed the brief's note.
- `test_the_cli_still_exits_one_on_a_missing_model` — `SystemExit` from
  the stubbed pipeline is the same one-line exit as before.
- `test_the_job_kind_body_records_the_result` — `run_train_and_advise()`
  returns `record()`; `advise-fast` still hands `scenarios_n=0`.
- `test_job_kinds_does_not_import_the_router` — source scan, gate item 3
  as a rail.
- `test_the_plist_is_unchanged_and_still_runs_advise` — the plist text
  contains `gaffer train &amp;&amp; gaffer advise` and does not contain
  `gaffer brief`: the brief arrives through the CLI, not the plist.

Golden-marked:

- `test_the_cli_and_the_job_kind_run_the_same_pipeline_on_the_golden_board`
  — gate item 2, exactly as §1 states it, skipping under the same
  `stale_inputs` rule as `test_golden_board.py`.

Dying: the three chain tests in `tests/test_v16_web_brief.py`. Changing
import only: `tests/test_web_job_kinds.py::test_advise_and_refresh_reuse_the_existing_router_entry_points`
(renamed `…reuse_the_job_kind_and_meta_entry_points`),
`tests/test_web_job_kinds_v7c.py::test_the_advise_body_still_defaults_to_the_config_on_disk`
and `…uses_the_config_it_is_handed`.

## 7. Pins and protected files

Pins: routes 51, job kinds 12, `Config` 59 — all unchanged, asserted by
the existing rails.

Protected files this sub-cycle touches, with the ruling (CLAUDE.md, *Pins
and protected files*; the orchestrator makes every one of these diffs):

| File | Change | Why |
|---|---|---|
| `tests/test_v4c_degradation.py` | three CLI tests gain the `run_brief` stub | §2.9; the rail's literal is unchanged and still compared verbatim |
| `tests/test_v13_degradation.py` | one CLI test gains the stub | §2.9 |
| `tests/test_v16_restraint.py` | `_cli` gains the stub | §2.9; the programme names this file |
| `tests/test_web_job_kinds.py` | one test's import moves to `job_kinds` | §2.10 |
| `tests/test_web_job_kinds_v7c.py` | two tests' import moves to `job_kinds` | §2.10 |
| `src/gaffer/cli.py` | `advise` calls `weekly_run` | the programme's prompt names the CLI pins as orchestrator-only |
| `src/gaffer/web/jobs.py` | untouched | named in the prompt; nothing here needs it |

Not protected, implementer-owned: `src/gaffer/pipeline.py` (new),
`src/gaffer/web/job_kinds.py`, `src/gaffer/web/routers/advice.py`,
`tests/golden_client.py`, `tests/test_pipeline.py` (new),
`tests/test_v16_web_brief.py`, `tests/test_cli.py`.

## 8. Process

Plan in `docs/superpowers/plans/2026-09-07-v17d-pipeline.md`. Implementer
tasks: the module and its unit tests; `job_kinds` and the router; the
golden context manager and the parity test. Orchestrator tasks: the CLI,
the protected rails, the gate, the merge. Spec review then code review
between tasks. Implementers never open `config.toml` and never run
`--record`.

## 9. Out of scope

Changing any step's behaviour; a job kind; a `--train` flag on the CLI;
moving `run_advise`; the `serving_config()` reads behind `cfg`'s back
(v17e); a hook for the CLI's summary order (§3); pruning the brief cache.

## 10. Outcome

**Verdict: pass, first full run** (2026-09-08, branch tip `77d1d59`).

| Item | Result |
|---|---|
| 1. golden board unmoved | `tests/test_golden_board.py` 29 passed, none skipped, in the same run as item 2 |
| 2. parity, stubbed LLM | `tests/test_pipeline.py::test_the_cli_and_the_job_kind_run_the_same_pipeline_on_the_golden_board` passed: both arms' advice equal `expected/advice.json`, both briefs carry the stub's sentence with `model_command == "python3"` and an empty `check_brief`, the job record's gw / expected_pts / `written` match; the post-run `stale_inputs` check is empty, so the stubbed train step wrote nothing through the symlinks |
| 3. router not imported | both greps print nothing / 0 (`tests/test_pipeline.py::test_non_web_code_does_not_import_the_advice_router` pins it) |
| 4. plist unchanged, yields a brief | `git diff main -- scripts/com.gaffer.advise.plist` empty; the plist test and the two CLI tests pass; the GUIDE §12.4 note is removed in the docs commit |

One gate run: `pytest -q tests/test_golden_board.py tests/test_pipeline.py`
→ 44 passed in 475 s (three pipeline runs over the recorded board).
Suites: Python 4329 (4325 with `-m "not golden"`, 4 golden), frontend 923
passed + 1 skipped, `tsc` clean. Pins routes 51 / job kinds 12 / `Config`
59 unchanged.

**Incident, recorded.** The plan's Task 2 Step 2 ("run to verify the new
ones fail") called `job_kinds.run_train_and_advise()` while it was still
the router's body; the plan said it would raise on the unstubbed frame,
and instead it trained for real and rewrote every file under `models/`
at 11:05 on 2026-09-08. No backup existed (the backup launchd job was
never installed, GUIDE §12.0). The golden then skipped on all fifteen
model hashes. Recovery: a worktree of `main` at `0cff561` with the
retrained `models/` and the unchanged `data/history/` linked in,
`python -m tests.golden_client --write` over the same bundle, and the
three rewritten files (`expected/advice.json`, `expected/solve_state.json`,
`header.json`) committed on the branch as `77d1d59`. Every lever count is
identical to the 09:29 record; the numbers moved with the models
(expected points 80.09 → 76.64). The gate above therefore compares the
branch against `main`'s code on the same inputs, which is the comparison
the golden exists for. Lessons: a red step must never call a body that
can reach a real trainer; and `models/` needs a backup before any
sub-cycle that touches the train step.

**Review notes carried forward.** The brief's failure note can print
twice in `logs/advise.log` (once from `run_brief`, once from the CLI's
echo), exactly as `gaffer brief` already does; `render_report` now sits
inside the CLI's two `except` arms, so a render failure is a one-line
exit rather than a traceback; `src/gaffer/advise.py`'s docstring still
calls `run_advise` "the whole weekly pipeline" (protected; v17g's
business); the golden skip helper exists in two test files and could
share a home once one exists.
