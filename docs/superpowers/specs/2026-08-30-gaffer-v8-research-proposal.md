# gaffer v8 — research-driven improvement proposal

Date: 2026-08-30. Status: PROPOSAL — awaiting user prioritization. Each chosen cycle gets its own spec → plan → implementation run per the standing workflow.

Three parallel research sweeps informed this: (1) the FPL tools landscape (FFS, FPL Review, Fantasy Football Fix/Hub, LiveFPL, FPL Statistics, planners, the 2026 AI-assistant wave), (2) the modeling/optimization frontier (OpenFPL and successors, xMins approaches, betting-market signals, the sertalpbilal solver ecosystem, rank-EV), (3) adjacent domains (chess game review, poker EV trainers, portfolio attribution, DFS win-probability simulators, habit-app rituals, forecast-verification UX). Source links live in the research transcripts; the load-bearing citations are inlined below.

## 0. The three headline findings

**F1 — Our zeros gap is a minutes-information problem, and the literature proves it.** OpenFPL (arXiv 2508.09992) benchmarked prospectively against FPL Review Massive Data: OpenFPL *wins* on haulers and tickers but loses Zeros by 16% (0.818 vs 0.689 RMSE) — attributed explicitly to FPL Review's xMins pipeline (team news, congestion, rotation, odds drift) vs crude availability flags. That is exactly our residual (zeros 1.063→1.053 post-Z1, still the biggest gap; v7-model's diagnostic already localized the error to "regulars who unexpectedly sit"). Nothing published beats GBM ensembles on architecture; the frontier is minutes inputs. Best-value attacks, none exotic: rotation-propensity priors per manager, short-horizon congestion features, an ordinal minutes head (P(start)/P(60+)/P(cameo)/P(0) fed as a distribution, not a mean), lineup-consensus ingestion, and an LLM pass over presser quotes.

**F2 — The most-loved features in every FPL tool are *relative*, not absolute.** LiveFPL's safety score and rank-tier effective ownership, Fix's rank what-if machine, FPL Pulse's mini-league Monte Carlo ("23% chance you win the league"), the sword/shield captaincy framing — all answer "how am I doing *versus the field/my rivals*", which is the question a mini-league player actually has. gaffer simulates scenarios and tracks rivals but never fuses them into win probability or EO-aware advice. Public top-10k picks are scrapeable (LiveFPL/FFP do it via the entry API).

**F3 — The stickiest mechanics in adjacent domains close the decision loop.** chess.com Game Review (grade every move vs the engine, one accuracy number), GTO Wizard's EV-loss ledger ("your captaincy leaks 0.8 pts/wk"), Sharesight's contribution analysis, Whoop's fixed Monday ritual. gaffer gives advice and logs decisions but never grades them afterwards — the counterfactual machinery (optimizer + replay) already exists; nobody in the FPL space does this well yet.

## 1. Candidate cycles

Ordered by my recommendation. Effort in cycle-equivalents relative to recent cycles (v7d ≈ 1.0).

### v8a — "minutes intelligence" [model] — effort ~1.2, attacks the #1 measured gap

The zeros attack, in ascending order of speculation, every piece gated on the standing Zeros/Blanks/Tickers/Haulers replay breakdown:

1. **Rotation-propensity priors per manager** (S/M): from historical lineups (already held), compute per-*manager* P(regular benched | rested opportunity), XI churn rate, roulette index; join on current manager. No season-indicator confound (computed across seasons of lineup history, not from the one-season cup archive that sank v5's congestion features).
2. **Short-horizon congestion features** (S): minutes-in-last-3/7-days, days-since-last-match, midweek-European/cup flag from the fixture calendar. ⚠️ Prior art: v5 withdrew congestion features because the cup archive spanned one training season and acted as a season indicator. These are *different* (league fixture spacing, live per-week values, no archive dependency), but the spec must pre-register that confound check and be ready to withdraw again.
3. **Ordinal minutes head** (M): extend ThreeModeModel to an explicit P(start)/P(60+)/P(cameo)/P(0) distribution consumed by per-component EP and the MC layer — a coin-flip 51-xMin starter and a nailed 51-minute sub are different EP profiles that a scalar xMins conflates. This is FPL Review's sim-based xMins in disguise.
4. **Lineup-consensus feature** (S): we already parse FFS predicted lineups (277 hints live); promote hints from availability nudge to a first-class categorical model feature (predicted starter/bench/out + freshness), optionally adding a second free source (fpl.page) for consensus.
5. **LLM presser/quote classifier** (M, speculative but cheaply falsifiable): an LLM pass over the injury-news prose and presser quotes we already collect, emitting {confirmed starter, rotation risk ↑/↓, knock, "we'll assess"} with confidence — shadow-logged through the existing N2 harness before it touches serving. Needs an LLM API key decision (cost is small).

Gate: pre-registered Zeros improvement on the gated replay, multi-seed per CONVENTIONS.md, per-feature ablation so any regressor is withdrawn individually (v5 discipline).

### v8b — "the decision loop" [functionality/ui] — effort ~1.2, highest user-facing value

One engine, four faces — chess.com Game Review for FPL. After each GW resolves:

1. **Gameweek Review**: grade each decision (every transfer, captain, vice, bench order, chip/no-chip) against the model's counterfactual, chess-style labels (Brilliant = beat the model and it paid / Good / Inaccuracy / Blunder / Miss = model-flagged move you skipped that hauled), one 0–100 GW accuracy score, counterfactual point lines on click.
2. **EV-loss ledger**: season-running "points left on the table vs model-optimal path", decomposed by decision type (captaincy / transfers / bench / chip timing) → periodic leak report ("your transfers are +EV; captaincy costs you 0.8/wk").
3. **Points attribution**: where your total actually came from — by player, position, price band, GW1-draft vs in-season buys, captaincy premium, bench losses (Sharesight-style).
4. **Hindsight dream team**: best possible XI you could have fielded from your squad + points-on-bench (community staple, cheap once 1–3 exist).

Feeds the existing decision journal; sets up a near-free Season-in-Review page in May and a rolling "manager form" number. Separates process from outcome — the honest companion to a model that admits variance. Nobody in the FPL tool space does this properly.

### v8c — "field intelligence" [model/functionality] — effort ~1.3, the relative-position layer

1. **Rank-tier EO scrape**: sample top-1k/10k squads post-deadline via the public entry API (rate-limited, LiveFPL-style) → per-player EO by tier + league EO we already have; sword/shield classification on every captaincy and transfer suggestion ("if he hauls you gain on 2 of 5 rivals / you tread water vs top-10k").
2. **Mini-league win probability**: Monte-carlo the rest of season (our squad + tracked rival squads + EP variance) → "you have a 23% chance of winning the league", sparkline over the season, and Δwin% annotation on every advised move — makes the league-chase tilt legible and automatically produces correct late-season risk appetite. (FPL Pulse's flagship, DFS playoff-odds mechanic.)
3. **Sampled-field MC opponents**: use the scraped real squads instead of parametric EO in rank sims.
4. **What-if simulator**: toggle hypothetical events ("my differential hauls", "rival's captain blanks") → live league/rank movement.

Depends on nothing; pairs beautifully with v8b (Δwin% becomes the grading currency). New scrape = new failure surface → same degradation-rail discipline as the news feed.

### v8d — "live matchday" [functionality/ui] — effort ~0.8

1. **Live bonus prediction** from in-match BPS (universally expected in any live tracker; feels broken without it).
2. **Live EP race chart**: cumulative your-score vs nearest rival(s) vs pre-GW projection across the GW's fixtures, event markers (xG-race-chart mechanic) — the Saturday-afternoon screen.
3. **Auto-sub projection** (who comes on if X stays at 0 minutes).
4. **Safety score, league edition**: the GW score needed to hold/climb each mini-league place (global-rank safety needs field data we don't have; league-relative is fully computable from tracked rivals).

Builds directly on the v6/v7 live tracker + rival data. Mostly UI + one BPS model of the deterministic bonus rules.

### v8e — "solver trust" [functionality] — effort ~0.8

1. **Sensitivity re-solves** (sertalpbilal-standard): perturb projections / resample MC scenarios, re-solve N times, report pick frequencies ("Salah-in appears in 84% of solves; the B plan is within 0.4 EV") instead of one gospel plan.
2. **Editable xMins/EP overrides**: the most-praised FPL Review feature — user pins a player's xMins or EP before solving; overrides logged and visible in explain-why (and gradeable by v8b: "your overrides cost/earned X").
3. **Multi-draft compare**: save named plan drafts, side-by-side EV over the horizon (FFS Draft Rating / FPL Review multi-draft mechanic).
4. **Chip-EV sanity rails**: assert optimizer chip valuations against community base rates (SGW BB ≈ 8–12, DGW BB ≈ 15–25, optimal-vs-random ≈ 20–30 pts) as replay-harness tests — bias toward avoiding terrible windows over hunting perfect ones (best-vs-2nd-best strategy gap ≈ 3 pts).

### v8f — "daily companion" [functionality] — effort ~0.8

1. **Price-change feed ingestion**: consume a public predictor (LiveFPL/fplform) rather than building our own (predictors' own true-alarm precision tops out ~60–70%; the official FPL site now ships a basic predictor, commoditizing it). Use as (a) tonight's risers/fallers filtered to squad/watchlist/plan, (b) a solver tiebreaker on transfer timing when EV-indifferent. Low ceiling (~few pts/season via team value) but nearly free and the single most habit-forming feature in FPL tooling.
2. **Watchlist + alert rules**: star players; alerts on predicted price move, news flag, EP swing > threshold after retrain, dropped-from-predicted-XI. Delivered by the existing job-runner via local/push notification (ntfy or similar — delivery channel is a spec decision).
3. **Monday debrief + Friday briefing**: two fixed scheduled digests composed from existing outputs (GW review once v8b exists, flagged players, deadline countdown, the advised move) — Whoop's ritual-cadence mechanic; makes everything else get used.
4. **Retrain diff view**: after every train/refresh, "what changed: these 8 players moved >0.5 EP, this advice flipped, why" — the anti-silent-drift view for an auto-retraining local model.

### v8g — "honest uncertainty" [ui/model] — effort ~0.9

1. **Calibration dashboard**: predicted-vs-actual EP scatter per GW, reliability curves (P(haul) said 25% → happened how often?), rolling MAE by position/price band, biggest misses with hypothesis tags — we already log everything needed (evaluate + shadow logs); this is surfacing, and it's the trust engine (weather-verification mechanic; absent from every consumer FPL tool).
2. **Uncertainty-first EP display**: floor/ceiling bands, P(blank)/P(return)/P(haul) chips, steady-vs-boom-bust tags everywhere EP appears; captaincy framed as "higher mean vs higher P(20+) — pick by league position". Needs the MC layer's per-player distributions surfaced (cheap) and benefits from v8a's ordinal minutes head (better tails).
3. **Advice confidence tags** derived from the calibration history ("model historically 78% right in this spot" vs "coin-flip — your call").
4. **Radar compare** in the existing compare view (EP components as overlaid radar — answers "different or just worse?" at a glance).

### Grab bag (S items, attachable to any cycle)

- **Set-piece scrape beyond penalties**: FFS corner/direct-FK taker tables as xA priors (corner-taking defenders). [model]
- **Rotation-pairing finder**: cheap GK/DEF pairs with interleaving fixtures, on top of the fixture matrix. [functionality]
- **Predicted-lineups browser page**: all 20 clubs on pitch graphics from our minutes model + FFS hints — the single most-browsed page class on FFS/Fix/Hub. [ui]
- **Bonus model upgrade**: replace the scalar bonus multiplier with conditional BPS simulation per position/event (E[bonus | DEF scores + CS] ≈ 60%+ of 3 bonus) inside the MC layer. [model]
- **Scoring-table currency check**: confirm defensive-contribution points (tackles/CBI thresholds, 25/26 rule) are fully reflected in scoring + BPS handling. [model]

## 2. Explicitly deprioritized (with reasons)

- **Team rating 0–100 / screenshot import / conversational chatbot** — growth/onboarding features for multi-user products; gaffer is single-user and the explain-why panels already answer "why". Revisit only if the app grows an audience.
- **AGS/assist player-prop odds as EP inputs** — the blend likely helps haulers, but player props need The Odds API Business tier (~$99/mo) or brittle scraping; FPL Review's own published claim is that a good stats model beats odds-inference. Park until the free signals (v8a) are exhausted. Team-total/BTTS odds (core tier, cheap) are the affordable slice if we go here.
- **Late odds-drift lineup leakage monitor** — sound mechanism, same paywall problem.
- **Building our own price predictor** — commoditized (official predictor now exists); ingest instead.
- **Global live overall rank / safety score** — needs field-wide live data only LiveFPL has; league-relative versions (v8d) capture the personal value.
- **Stochastic multi-week solver, GNNs, broadcast CV, quantile-GBM rearchitecture** — community's own conclusion: projections quality ≫ solver sophistication; no demonstrated FPL lift for the exotic stuff. Sensitivity re-solves (v8e) capture most robustness value at S cost.
- **Rival transfer prediction** — genuinely novel (nobody does it well) but speculative; a natural v8c follow-on once tier-EO and field sampling exist.
- **Drill mode / historical replay training** — needs point-in-time snapshot infrastructure; the daily availability log only started accruing this week. Season-2 idea.

## 3. Recommended sequencing

1. **v8a minutes intelligence** — the one measured model gap, highest confidence of real EP improvement, and this is the sweet spot of the season to fix minutes (34 GWs left to harvest it).
2. **v8b decision loop** — biggest user-value leap, zero new data dependencies, strengthens trust in everything else; its counterfactual engine also quantifies the model's own worth.
3. **v8c field intelligence** — the relative-position layer the whole tool ecosystem says matters most; makes the league tilt legible as win%.
4. **v8d live matchday** and **v8f daily companion** — smaller, high-delight; slot into GW downtime.
5. **v8g honest uncertainty** — best after v8a (better tails to display) and alongside accumulating calibration history.
6. **v8e solver trust** — any time; pairs well with v8b's override grading.

Decisions needed from the user: (a) which cycles, in what order; (b) LLM API key/cost approval for the presser classifier (v8a.5, can ship without it); (c) alert delivery channel preference for v8f (ntfy/other); (d) comfort with the top-10k entry-API scrape volume for v8c (public API, rate-limited, but it's a new standing fetch job).
