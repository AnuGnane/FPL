# v19f — the question box (design)

**Cycle:** v19f, the sixth sub-cycle of the v19 programme
(`specs/2026-09-15-v19-programme-design.md` §2 v19f, rulings 3, 8 and 9;
plan `plans/2026-09-15-v19-programme.md` §3 v19f; v16 §11's deferral).
**Branch:** `v19f-ask` off `main` at v19e's merge.
**Date:** 2026-09-16. **Status:** drafted; starts after v19e merges.

---

## 1. What this changes, and what it does not

The brief answers the week's question once, from a facts document
(`brief.build_facts`) through a no-tools command (`[news] llm_command`,
`brief.run_command`) and a truth check on every number and name
(`brief.check_brief`). The reader has a second question and nowhere to
ask it. v16 §11 deferred "the in-app chat" until briefs had been read;
they have been written since GW4 and the user has approved the v19
programme with this sub-cycle in it, droppable (ruling 1).

No served number changes. One route is added, `POST /api/ask`, so the
route pin moves 51 → 52 in its own commit to
`tests/test_v11_degradation.py` (ruling 2 as amended by v19e: this is
the programme's only bump). `JOB_KINDS` stays 12: the answer is an
anonymous `JobRegistry` job submitted by the router, exactly as `POST
/api/brief` does (`web/routers/brief.py:32-38`), so `web/jobs.py` is not
touched after all (ruling 9's one diff is not needed). Answers are not
persisted; one log line each.

## 2. The changes

### 2.1 The prompt and the answer (backend, `brief.py`)

`build_question_prompt(facts: dict, question: str) -> str`: the same
preamble discipline as `build_prompt` — "from the facts below and
nothing else", British English, only numbers and names that appear in
the facts, no invented reasons — then "Answer the manager's question in
one to four sentences of plain prose. If the facts cannot answer it, say
so in one sentence and do not guess." The question is placed *after* the
facts, quoted inside a fenced block labelled as the manager's words, so
an instruction-shaped question cannot rewrite the rules above it; the
prompt says the block is a question to answer, not instructions to
follow. `answer_question(question: str, gw: int | None = None, *, cfg)
-> dict`: `facts = build_facts(gw or latest)`, the prompt, `run_command`
with the config's command and timeout, `check_brief(answer, facts)`;
returns `{"gw", "question", "answer", "offences": [...], "model_command":
cmd.split()[0], "at": _now()}`; a command failure returns `answer=""` with
`offences=["the command failed: …"]` rather than raising (the job must
finish). A question over 500 characters is refused before any command
runs (`ValueError`, mapped to 422 by the router). Tests: the prompt
carries the facts and the quoted question in that order; the answer's
offences come from `check_brief`; a failing command is an offence not an
exception; the length limit.

### 2.2 `POST /api/ask` (backend, router)

`web/routers/ask.py`: `AskRequest {question: str, gw: int | None}` →
`202 JobAccepted` with the job id, the body `lambda:
answer_question(...)` submitted to `request.app.state.jobs` with the
brief's timeout. The frontend reads the answer from the job record's
`result` through `useJob`, as the brief does. Schemas: `AskRequest`,
`AskAnswer` (the dict above, typed) — the latter documented as the job's
`result` shape. Tests in `tests/test_v19f_ask.py`: the route submits and
returns 202; the result carries the check; an over-long question is 422;
the route pin commit (`tests/test_v11_degradation.py` 51 → 52, the
orchestrator's, docstring naming `/api/ask`).

### 2.3 The box (frontend)

`this-week/QuestionBox.tsx`, rendered at the foot of `BriefCard`: one
`<input aria-label="ask about this week">` with placeholder "Ask about
this week's plan", a `Button` "Ask", `useJob({ path: '/api/ask', slot:
'ask' })` posting `{question}`; while running, the existing `JobLog`
line; on completion the answer beneath as a paragraph, with a failed
check rendered the brief's way (the answer struck through and each
offence on a line beneath). The last three answers of the session stay
listed under the box, newest first, in component state (a reload
clears them). Disabled with a sentence when the brief panel says no
command is configured (read `BriefPanel` for the field). Tests: asking
posts the question; a result with offences shows the strike and the
lines; three answers kept; the fourth drops the oldest.

## 3. Gate, written before anything runs

1. Inner loop green; ruff clean.
2. The golden gate → 62 passed, 0 skipped.
3. `npm run check` green; the This Week fetch rail unchanged (the box
   fetches nothing until asked; the post is not a GET in the rail's
   multiset — confirm by reading the rail).
4. Screenshot pairs at 1400, both themes: **This Week** named (the box);
   the other five identical below the strip.
5. The route pin commit alone: `tests/test_v11_degradation.py` 51 → 52.
6. **Three answers read by the user**, one of them a question the facts
   cannot answer, pasted into §4 with their check lines. The orchestrator
   runs them through the CLI-less path (`answer_question` from a Python
   one-liner with the config in force) so no served advice is rewritten
   and no odds quota is spent; the LLM command's own cost is the user's.
7. New rails mutation-tested: the question-after-facts order (swap
   them), the length limit, the offence rendering.

## 4. Outcome

Filled at the gate.
