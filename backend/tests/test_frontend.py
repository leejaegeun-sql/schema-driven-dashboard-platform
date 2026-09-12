"""The UI is served by the API and only calls endpoints the API exposes."""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest
from app.main import FRONTEND_INDEX

PAGE = FRONTEND_INDEX.read_text(encoding="utf-8")

#: Every api(...) call in the page, as (method, path).
CALLS = re.findall(r'api\(\s*"(GET|POST)",\s*"([^"]+)"', PAGE)


def test_index_is_served_as_html(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Schema-Driven Dashboard Platform</title>" in response.text


def test_the_page_is_self_contained():
    """No build step and no external assets: one FileResponse is enough."""
    assert not re.search(r'<(script|link)[^>]+\b(src|href)=', PAGE)


def test_openapi_and_docs_are_still_served(client):
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths) == {
        "/schema",
        "/schemas",
        "/ingest",
        "/dashboard",
        "/dashboards",
        "/dashboard/{name}",
    }


def test_the_page_covers_all_four_workflow_steps():
    called = {(method, path) for method, path in CALLS}
    assert ("POST", "/schema") in called
    assert ("POST", "/ingest") in called
    assert ("POST", "/dashboard") in called
    assert ("GET", "/dashboard/") in called  # concatenated with the name


@pytest.mark.parametrize(("method", "path"), sorted(set(CALLS)))
def test_every_endpoint_the_page_calls_exists(client, method, path):
    routed = path if path != "/dashboard/" else "/dashboard/{name}"
    assert routed in client.get("/openapi.json").json()["paths"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_inline_script_parses():
    script = re.search(r'<script>\n(.*?)\n</script>', PAGE, re.S).group(1)
    result = subprocess.run(
        ["node", "--check", "-"], input=script, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr
