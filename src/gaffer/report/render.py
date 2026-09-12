"""Render an :class:`~gaffer.advise.Advice` into a standalone HTML report.

The template reads a plain dict (``asdict`` of the dataclass) rather than the
dataclass itself, so a payload round-tripped through the advice artifact
renders identically to one straight off the pipeline.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from gaffer.advise import Advice
from gaffer.config import Config


def render_report(advice: Advice, out_dir: Path | str = "reports",
                  model_health: dict | None = None) -> Path:
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=True)
    # v18b Task 6: the served hit cost when the ladder built the restraint
    # block, else the config's own default — cli.py's ~98-101 fallback,
    # mirrored exactly so the report's sentence and the terminal's agree.
    cost = (getattr(advice, "restraint", None) or {}).get("hit_cost")
    hit_cost = int(cost if cost is not None else Config.hit_cost)
    html = env.get_template("report.html.j2").render(
        a=asdict(advice), health=model_health or {}, hit_cost=hit_cost)
    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    path = out / f"gw{advice.gw}-report.html"
    path.write_text(html)
    return path
