# scripts/archive

These are the replay and evaluation drivers of closed cycles. Nothing in the
repo runs them any more, but each one produced numbers a shipped spec quotes
verbatim, so they are kept byte-identical rather than deleted: editing a driver
in place would make the verdict it banked unreproducible (v9c §G3's rule, which
is why `scripts/replay_pair.sh` was written as a generalization instead of an
edit). A live script that still points at one of these — `replay_pair.sh` and
`v12_w4_autosub_cf.py` — cites it by its path here; a reference from one
archived driver to another was left as it stood.

- `v9c_club_eval.py` — `docs/superpowers/specs/2026-08-31-gaffer-v9c-model-debt-design.md` §D2, the as-of club coverage and divergence table.
- `v9c_rc_arm.py` — `docs/superpowers/specs/2026-08-31-gaffer-v9c-model-debt-design.md` §D1, the red-card arm's two runs.
- `v9c_replay.sh` — `docs/superpowers/specs/2026-08-31-gaffer-v9c-model-debt-design.md` §G3, the branch-against-a-re-run-`main` replay.
- `v9d_club_eval.py` — `docs/superpowers/specs/2026-09-01-gaffer-v9d-design.md` §G1, the two consumers' club measurement.
- `v10_autosub_cf.py` — `docs/superpowers/specs/2026-09-01-gaffer-v10-minutes-design.md` §G3, the autosub counterfactual.
- `v12_xgps_arm.py` — `docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md` §3.5, the xGPS arm that shipped off with its numbers.
