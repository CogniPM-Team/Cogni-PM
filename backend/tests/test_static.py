"""The API can serve the built website. Deep links must load the app, API paths must never return the page, and a
request must not be able to read files outside the website's folder."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cognipm.api.static import frontend_dist, mount_frontend


@pytest.fixture
def site(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>the app</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log('app')")
    (tmp_path / "favicon.png").write_bytes(b"png")
    (tmp_path.parent / "secret.txt").write_text("not for the web")
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"ok": True}

    assert mount_frontend(app, tmp_path)
    return TestClient(app)


def test_the_site_root_and_its_files_are_served(site):
    assert site.get("/").text == "<html>the app</html>"
    assert site.get("/assets/app.js").text == "console.log('app')"
    assert site.get("/favicon.png").content == b"png"


@pytest.mark.parametrize("path", ["/approvals/abc-123", "/console/some-chat", "/activity", "/no/such/page"])
def test_a_page_opened_directly_or_reloaded_still_loads_the_app(site, path):
    assert site.get(path).text == "<html>the app</html>"


def test_the_api_still_answers_and_an_unknown_api_path_is_a_404_not_the_page(site):
    assert site.get("/api/health").json() == {"ok": True}
    unknown = site.get("/api/nothing-here")
    assert unknown.status_code == 404 and "the app" not in unknown.text
    assert site.get("/api").status_code == 404


@pytest.mark.parametrize(
    "path", ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt", "/..%2fsecret.txt"]
)
def test_a_path_cannot_reach_a_file_outside_the_website(site, path):
    response = site.get(path)

    assert "not for the web" not in response.text


def test_without_a_built_website_nothing_is_added(tmp_path):
    app = FastAPI()

    assert mount_frontend(app, tmp_path) is False
    assert TestClient(app).get("/").status_code == 404


def test_the_website_folder_can_be_set_by_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("COGNIPM_FRONTEND_DIST", str(tmp_path))

    assert frontend_dist() == tmp_path
