"""Packaging smoke test.

Skipped rather than failed when the frontend has not been built, so the
Python suite never requires node — see the README's developer flow.
"""

from importlib.resources import files

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app, static_dir

BUILT = (static_dir() / "index.html").exists()
UNBUILT_REASON = ("frontend not built — run `npm install && npm run build` in "
                  "frontend/ to exercise this test")


@pytest.mark.skipif(not BUILT, reason=UNBUILT_REASON)
def test_static_assets_are_importable_package_data():
    root = files("gaffer.web").joinpath("static")
    assert root.joinpath("index.html").is_file()
    assert root.joinpath("assets").is_dir()


@pytest.mark.skipif(not BUILT, reason=UNBUILT_REASON)
def test_create_app_serves_index_for_a_client_route():
    client = TestClient(create_app())
    for path in ["/", "/planning", "/players", "/league",
                 "/league/rival/2", "/live", "/model"]:
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "<div id=\"root\">" in resp.text


@pytest.mark.skipif(not BUILT, reason=UNBUILT_REASON)
def test_the_built_bundle_is_served_from_assets():
    client = TestClient(create_app())
    index = client.get("/").text
    start = index.index('src="/assets/')
    bundle = index[start + 5:index.index('"', start + 5)]
    assert client.get(bundle).status_code == 200


def test_wheel_declares_the_static_assets():
    import tomllib
    from pathlib import Path

    config = tomllib.loads(Path("pyproject.toml").read_text())
    artifacts = config["tool"]["hatch"]["build"]["targets"]["wheel"][
        "artifacts"]
    assert "src/gaffer/web/static/**/*" in artifacts
