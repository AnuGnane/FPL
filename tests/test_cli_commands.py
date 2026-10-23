"""The six commands no test invoked beyond ``--help`` each get one (holiday F-192).

F-191's rail (``tests/test_guide_commands.py``) held them on ``UNEXERCISED``;
these tests strike the list. Each runs without the network: ``train`` and
``review`` on an empty working tree, ``field-scrape`` and ``digest`` with the
function ``cli.py`` hands off to stubbed at its module, ``backup`` on a
miniature tree, and ``mcp`` with the real server built and its ``run`` made a
no-op so nothing serves. ``cli.py`` is a golden import, so the tests pin what
it does today rather than change it.
"""

from __future__ import annotations

import asyncio
import tarfile

from typer.testing import CliRunner

from gaffer import mcp_server
from gaffer.cli import app

runner = CliRunner()


def test_train_on_an_empty_tree_exits_non_zero_naming_the_missing_history(
        tmp_path, monkeypatch):
    # The FileNotFoundError reaches typer rather than becoming a one-line
    # GafferError; making it one is a change on the golden path (F-192 ruling 1).
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["train"])
    assert result.exit_code != 0
    assert isinstance(result.exception, FileNotFoundError)
    assert "data/history/player_gw.parquet" in str(result.exception)


def test_review_without_a_config_prints_its_line_and_never_fails(
        tmp_path, monkeypatch):
    # v8b F2's contract: a scheduled job prints why and exits 0.
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["review"])
    assert result.exit_code == 0
    assert "review not written: no config.toml" in result.output
    assert result.exception is None


def test_field_scrape_hands_its_options_to_the_scrape(tmp_path, monkeypatch):
    import gaffer.data.field

    calls = []

    def fake(gw=None, force=False):
        calls.append((gw, force))
        print(f"field sample for gw{gw}: 10 entries banked")
        return 10

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gaffer.data.field, "run_field_scrape", fake)
    result = runner.invoke(app, ["field-scrape", "--gw", "7", "--force"])
    assert result.exit_code == 0
    assert calls == [(7, True)]
    assert "field sample for gw7: 10 entries banked" in result.output


def test_digest_hands_its_kind_and_the_notify_switch_to_the_digest(
        tmp_path, monkeypatch):
    import gaffer.digest

    calls = []

    def fake(kind, notify):
        calls.append((kind, notify))
        print(f"{kind} digest written")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gaffer.digest, "run_digest", fake)
    result = runner.invoke(app, ["digest", "--kind", "tuesday"])
    assert result.exit_code == 0
    # No config.toml here, so the dataclass default: notify on.
    assert calls == [("tuesday", True)]
    assert "tuesday digest written" in result.output


def test_backup_writes_its_archive_and_prints_its_size(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    live = tmp_path / "data/live/player_gw.parquet"
    live.parent.mkdir(parents=True)
    live.write_text("live")
    out = tmp_path / "out"
    result = runner.invoke(app, ["backup", "--to", str(out)])
    assert result.exit_code == 0, result.output
    archives = sorted(out.glob("gaffer-*.tar.gz"))
    assert len(archives) == 1
    assert f"Wrote {archives[0]} (" in result.output
    assert result.output.rstrip().endswith("MB)")
    with tarfile.open(archives[0]) as tar:
        assert "data/live/player_gw.parquet" in tar.getnames()


def test_mcp_builds_the_server_with_the_six_tools_and_prints_nothing(
        monkeypatch):
    real = mcp_server.build_server
    built = []

    def build_without_serving():
        server = real()
        server.run = lambda *a, **k: None
        built.append(server)
        return server

    monkeypatch.setattr(mcp_server, "build_server", build_without_serving)
    result = runner.invoke(app, ["mcp"])
    assert result.exit_code == 0
    # stdout is the protocol channel, so the command never echoes.
    assert result.output == ""
    assert len(built) == 1
    names = sorted(t.name for t in asyncio.run(built[0].list_tools()))
    assert names == sorted(mcp_server.TOOLS)
    assert len(names) == 6
