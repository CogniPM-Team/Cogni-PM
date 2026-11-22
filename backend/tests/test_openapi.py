"""The frontend's types come from frontend/src/api/openapi.json. If this fails, the API changed and the file
did not: run `python scripts/export_openapi.py` (then regenerate the types) and commit both."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from cognipm.config import REPO_ROOT

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export_openapi.py"


def test_the_committed_openapi_schema_matches_the_api():
    spec = importlib.util.spec_from_file_location("export_openapi", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    committed = (REPO_ROOT / "frontend" / "src" / "api" / "openapi.json").read_text(encoding="utf-8")

    assert committed == module.schema_text(), "frontend/src/api/openapi.json is out of date"
