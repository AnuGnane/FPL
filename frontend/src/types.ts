/**
 * The client's types, in two halves (v12 W5 §6.6).
 *
 * The generated half is every pydantic response model, compiled from
 * `src/schemas.json` — which `scripts/gen_types.py` writes from
 * `src/gaffer/web/schemas.py`. It is re-exported below, so
 * `import { PlayerRow } from '../types'` keeps working everywhere it already
 * does and no import in the tree changed.
 *
 * This file keeps what a generator cannot produce: the interfaces that type
 * the *inside* of payloads the server declares as `dict[str, Any]`, and the
 * eleven narrowings of the `Wire*` models — each one an `Omit` (or, for
 * `PlayerRef`, a `Partial`) of its generated twin, so the shared fields are
 * described in exactly one place.
 */

// The generated half: every pydantic response model, compiled from
// src/schemas.json. Re-exported so `import { PlayerRow } from '../types'`
// keeps working everywhere it already does.
export * from './types.generated'

// `export *` re-exports without binding, so the generated names this file
// *uses* are imported as well.
import type {
  CategoryMetrics, PlanAlternative, ReviewLane,
  WireAdviceLatest, WireCalibrationReport, WireHealth, WireHistory,
  WireModelHealth, WirePlanTimeline, WirePlayerExplain, WirePlayerRef,
  WirePlayerRow, WireReview, WireReviewSummary,
} from './types.generated'

/** `WirePlayerRef` as the *advice artifact* carries it, which is looser than
 *  the response model in both directions.
 *
 *  `AdviceLatest.advice` is `dict[str, Any]` on the server: the artifact goes
 *  to the browser unvalidated, so nothing fills a default on the way out. The
 *  identity fields are added at serve time by `/api/advice/latest` and are
 *  absent from a payload that was never enriched — `null` is a blank gameweek,
 *  `undefined` is "never enriched" — and `position` is absent from an older
 *  artifact. The other direction: the artifact carries `tag` and `frequency`,
 *  which no response model declares.
 *
 *  `/api/plan` and the what-if lab go through the model, so their refs are
 *  `WirePlayerRef` and every field is present. */
export interface PlayerRef extends Partial<WirePlayerRef> {
  code: number
  name: string
  ep: number
  /** The artifact's own label on a move — "captain", "vice". */
  tag?: string
  /** Share of noised scenarios that contained this move. Absent when the
   *  scenario sweep did not run ([scenarios] n = 0). */
  frequency?: number
}

export interface MoveFrequency {
  kind: 'buy' | 'sell' | 'hit' | 'chip' | 'captain' | 'no_transfer'
  code: number
  gw: number
  label: string
  count: number
  frequency: number
}

export interface ScenarioReport {
  n: number
  completed: number
  failures: number
  seed: number
  hold: boolean
  captain_frequency: number
  near_misses: Array<{ kind: string; code: number; gw: number; label: string
                       frequency: number }>
}

export interface Strategy {
  lam: number
  gap: number
  weeks_left: number
  stance: string
  rival_name: string
}

/** One row of the advice payload's own chip table.
 *
 *  `threshold`, `play_now` and `note` are written by `run_advise` alongside
 *  the raw `evaluate_chips` columns — optional here because a payload banked
 *  before the chip policy landed (and, for `note`, any non-free-hit row) has
 *  none of them. */
export interface AdviceChipRow {
  chip: string
  gw: number
  gain: number
  per_week?: number | null
  threshold?: number | null
  play_now?: boolean
  note?: string | null
}

export interface Advice {
  gw: number
  xi: PlayerRef[]
  bench: PlayerRef[]
  captain: PlayerRef
  vice: PlayerRef
  buys: PlayerRef[]
  sells: PlayerRef[]
  hits: number
  expected_pts: number
  chip_table: AdviceChipRow[]
  strategy: Strategy | null
  // v4c: present only when the scenario sweep ran. Optional so an advice
  // payload written before v4c still types.
  move_frequencies?: MoveFrequency[]
  raw_optimum_agrees?: boolean | null
  scenarios?: ScenarioReport | null
  captain_field?: CaptainField
  /** The half-sentence the league tilt puts after the captain's name
   *  ("covering Dave's last armband"). Written by `advise.py:160` and served
   *  inside `AdviceLatest.advice`, which the server declares as
   *  `dict[str, Any]` — so it needs no schema field and has none.
   *
   *  Empty string, not null, when the tilt changed nothing
   *  (`league_mode.py:425`). Test it for truthiness, exactly as
   *  `cli.py:81` does. */
  captain_note?: string | null
}

/** Where the captain stands against the top 10k (v10b §F1a).
 *
 * Absent — not null — when the backend had nothing to say: no field log, no
 * events row, or an element it could not resolve to a player. `eo` is null
 * when only the bootstrap's modal captain was available. `note` is the
 * server's own sentence and is rendered verbatim; formatting it here would be
 * a second voice saying the same number a slightly different way.
 */
export interface CaptainField {
  code: number
  eo: number | null
  se: number | null
  n: number | null
  gw: number
  /** The same projection the explorer's row carries. Null means no trend,
   *  and never 0. */
  deadline_eo?: number | null
  eo_delta?: number | null
  field_class: 'shield' | 'sword' | null
  most_captained?: { code: number; name: string | null; gw: number } | null
  note: string
}

/** `WireAdviceLatest` with `advice` narrowed. The server declares that field
 *  as `dict[str, Any]`, so the generator can only describe it as an open
 *  record — but every consumer in this tree reads `advice.captain.name`. */
export interface AdviceLatest extends Omit<WireAdviceLatest, 'advice'> {
  advice: Advice
}

/** `WirePlayerExplain`, overriding `set_pieces_manual` to keep the sentence
 *  that says why it is optional.
 *
 *  Which of `set_pieces`' three orders came from the user's override file, a
 *  cleared one included. Optional, not merely default-empty: a payload banked
 *  before the field existed omits it, which is why every read site goes
 *  through `?? []`, and the type has to admit what those guards are for.
 *  Absent reads as "nothing overridden".
 *
 *  The generated twin types it required, which is what *this* server sends;
 *  the override is the older-payload case, and deleting it would make every
 *  `?? []` downstream read as dead defence. */
export interface PlayerExplain
  extends Omit<WirePlayerExplain, 'set_pieces_manual'> {
  set_pieces_manual?: string[]
}

/** `WirePlayerRow`, overriding `set_piece_manual` to keep the sentence that
 *  says why it is optional.
 *
 *  Kinds of set piece whose order came from the user's `data/set_pieces.toml`
 *  rather than from FPL — a cleared one included, since a blank his file
 *  caused is his file's word too. Empty on every machine with no override
 *  file; optional because the read sites guard it with `?? []`, which is only
 *  honest if it can be absent.
 *
 *  As with `PlayerExplain`, the generated twin types it required — that is
 *  what this server sends — and the override is the older-payload case. */
export interface PlayerRow extends Omit<WirePlayerRow, 'set_piece_manual'> {
  set_piece_manual?: string[]
}

/** `WireHistory` with `backtests` narrowed. The server declares it as
 *  `list[dict[str, Any]]` — one row per backtest run, keyed by whatever that
 *  run banked — and the History tab reads each row by hand. */
export interface HistoryData extends Omit<WireHistory, 'backtests'> {
  backtests: Array<Record<string, unknown>>
}

/** `WireModelHealth` with `metrics` narrowed. The server declares it as
 *  `dict[str, Any]`, keyed by whatever the retrain wrote, and the health card
 *  reads the keys it knows.
 *
 *  There was no client type for this model before the split — `HealthData`
 *  inlined it — so the name is new, and `HealthData.models` now points at it
 *  through the generated file. */
export interface ModelHealth extends Omit<WireModelHealth, 'metrics'> {
  metrics: Record<string, unknown>
}

/** `WireHealth` with `model_health` narrowed. The server declares it as
 *  `dict[str, Any] | None`, and the card reads the keys it knows.
 *
 *  Three fields on the generated twin are three-state and the distinction is
 *  load-bearing. `season_ok` null is "cannot tell" — no events snapshot yet —
 *  and the mismatch banner draws on false alone. `last_backup` null is
 *  "never", rendered as "never — run `gaffer backup`" rather than as a blank
 *  cell, because a backup nobody can see is one nobody notices has stopped.
 *  `core_insights` null is a server that does not carry the block at all,
 *  where `collected: false` is a machine that has never run the collector;
 *  neither renders as zero rows. */
export interface HealthData extends Omit<WireHealth, 'model_health'> {
  model_health: Record<string, unknown> | null
}

export type StratifiedTable = Record<string, CategoryMetrics>

export interface ChipSquadPlayer {
  code: number
  name: string
  position: string
  price: number
  ep: number
}

export interface AdvicePlayerRef {
  code: number
  name: string
}

/** `WireCalibrationReport` with `excluded` narrowed. The server declares it as
 *  `list[dict[str, Any]]`; every row the report writes is a gameweek and the
 *  reason it was dropped, and the card renders both. */
export interface CalibrationData
  extends Omit<WireCalibrationReport, 'excluded'> {
  excluded: Array<{ gw: number; reason: string }>
}

export const JOB_KINDS = ['advise', 'advise-fast', 'evaluate', 'refresh-data',
  'news-shadow', 'snapshot', 'track-pens', 'field-scrape', 'review',
  'sensitivity', 'digest-friday', 'digest-tuesday'] as const

export type JobKind = typeof JOB_KINDS[number]

export const JOB_KIND_LABEL: Record<JobKind, string> = {
  advise: 'Run advise',
  'advise-fast': 'Fast advise',
  evaluate: 'Evaluate',
  'refresh-data': 'Refresh data',
  'news-shadow': 'Score news shadow',
  snapshot: 'Snapshot news',
  'track-pens': 'Track pens',
  'field-scrape': 'Field scrape',
  review: 'Review last week',
  sensitivity: 'Run sensitivity',
  'digest-friday': 'Friday briefing',
  'digest-tuesday': 'Tuesday debrief',
}

/** `WirePlanTimeline`, overriding `alternatives` to keep the sentence that
 *  says why it is optional.
 *
 *  Empty on every artifact written before v12 and on any run with
 *  `alt_plan_max_gap = 0`; the board draws no strip for an empty list.
 *  Optional, because the board reads it as `?? []` and a payload from a server
 *  older than the field is a real case — typing it as always present made that
 *  guard read as dead defence.
 *
 *  The generated twin types it required — that is what this server sends —
 *  and the override is the older-server case. */
export interface PlanTimeline
  extends Omit<WirePlanTimeline, 'alternatives'> {
  alternatives?: PlanAlternative[]
}

export type LeagueWhatIfEvent = 'haul' | 'blank' | 'score'

export type ReviewLaneName = 'transfers' | 'captaincy' | 'bench' | 'chip'

export type ReviewLabel =
  'Brilliant' | 'Good' | 'Aligned' | 'Inaccuracy' | 'Blunder'

/** `WireReviewSummary` with `best` and `worst` narrowed. The server declares
 *  both as `dict[str, Any] | None`; each is a graded lane with the gameweek it
 *  came from, and the summary card renders the lane's own fields. */
export interface ReviewSummary
  extends Omit<WireReviewSummary, 'best' | 'worst'> {
  best: (ReviewLane & { gw: number }) | null
  worst: (ReviewLane & { gw: number }) | null
}

/** `WireReview` with `summary` pointed at the narrowed `ReviewSummary`.
 *
 *  A `$ref` in the schema resolves to the *generated* twin, so the narrowing
 *  above would have stopped at the top level and `data.summary.worst.lane`
 *  would still have been an open record. A narrowed model that something else
 *  references needs its referrer narrowed too, and this is the only one. */
export interface ReviewData extends Omit<WireReview, 'summary'> {
  summary: ReviewSummary | null
}
