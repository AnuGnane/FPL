"""`gaffer ui --lan` — the phone-on-the-sofa path (spec §7)."""

import pytest
from typer.testing import CliRunner

import gaffer.cli as cli
from gaffer.web.lan import lan_ip, qr_lines

runner = CliRunner()


@pytest.fixture()
def no_server(monkeypatch):
    """Capture what uvicorn would have been asked to do."""
    calls = {}

    def fake_run(app, host, port, log_level):
        calls.update(host=host, port=port)

    monkeypatch.setattr("uvicorn.run", fake_run)
    monkeypatch.setattr("webbrowser.open", lambda url: None)
    return calls


def test_the_default_still_binds_loopback(no_server):
    result = runner.invoke(cli.app, ["ui", "--no-open-browser"])
    assert result.exit_code == 0
    assert no_server["host"] == "127.0.0.1"
    assert "127.0.0.1:8927" in result.stdout


def test_lan_binds_every_interface_and_prints_the_lan_url(no_server,
                                                          monkeypatch):
    monkeypatch.setattr("gaffer.web.lan.lan_ip", lambda: "192.168.1.42")
    result = runner.invoke(cli.app, ["ui", "--lan", "--no-open-browser"])
    assert result.exit_code == 0
    assert no_server["host"] == "0.0.0.0"
    assert "http://192.168.1.42:8927" in result.stdout


def test_lan_prints_a_qr_code(no_server, monkeypatch):
    monkeypatch.setattr("gaffer.web.lan.lan_ip", lambda: "192.168.1.42")
    result = runner.invoke(cli.app, ["ui", "--lan", "--no-open-browser"])
    # The block characters a terminal QR is drawn with.
    assert "█" in result.stdout


def test_lan_says_plainly_what_is_open_and_what_is_not(no_server, monkeypatch):
    """This used to assert "no auth — trusted home network only", which was an
    honest description until v12 W1 §2.8. It is now false: reads are open and
    writes need a token, and a banner that undersells its own protection
    teaches the user to route around it."""
    monkeypatch.setattr("gaffer.web.lan.lan_ip", lambda: "192.168.1.42")
    result = runner.invoke(cli.app, ["ui", "--lan", "--no-open-browser"])
    out = result.stdout.lower()
    assert "no auth" not in out
    assert "reads are open" in out
    assert "writes need" in out


def test_lan_prints_a_generated_token_and_how_to_use_it(no_server,
                                                        monkeypatch):
    """With no `[web] token` in config there is one per run, printed once and
    stored nowhere — writing it into config.toml would be the app editing the
    file that holds the user's API key."""
    monkeypatch.setattr("gaffer.web.lan.lan_ip", lambda: "192.168.1.42")
    monkeypatch.setattr("gaffer.web.app.generate_token", lambda: "TOK123")
    result = runner.invoke(cli.app, ["ui", "--lan", "--no-open-browser"])
    assert "TOK123" in result.stdout
    assert "?token=TOK123" in result.stdout


def test_loopback_prints_no_token_at_all(no_server):
    """The default. No token, no middleware, and nothing new on screen."""
    result = runner.invoke(cli.app, ["ui", "--no-open-browser"])
    assert "token" not in result.stdout.lower()


def test_lan_ip_is_a_dotted_quad_or_none():
    address = lan_ip()
    assert address is None or address.count(".") == 3


def test_qr_lines_render_the_url_as_block_text():
    lines = qr_lines("http://192.168.1.42:8927")
    assert lines and any("█" in line for line in lines)


def test_qr_lines_degrade_to_nothing_without_the_library(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "qrcode", None)
    assert qr_lines("http://192.168.1.42:8927") == []


def test_a_missing_qrcode_says_so_instead_of_going_quiet(monkeypatch, capsys):
    """Silence here reads as "this terminal cannot draw QR codes"."""
    monkeypatch.setitem(__import__("sys").modules, "qrcode", None)
    assert qr_lines("http://192.168.1.42:8927") == []
    out = capsys.readouterr().out
    assert "qrcode not installed" in out
    assert "uv sync" in out


def test_the_missing_library_notice_is_one_line(monkeypatch, capsys):
    monkeypatch.setitem(__import__("sys").modules, "qrcode", None)
    qr_lines("http://192.168.1.42:8927")
    assert len(capsys.readouterr().out.strip().splitlines()) == 1
