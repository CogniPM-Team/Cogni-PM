"""Writes the API's OpenAPI schema to frontend/src/api/openapi.json.

The frontend's TypeScript types are generated from this file, so a field renamed in the backend becomes a
compile error in the frontend instead of a silent mismatch. A test fails when the committed file is out of
date, so run this after changing any route or schema in backend/cognipm/api/:

    python scripts/export_openapi.py

Needs no database and no network: it only reads the app's definition.
"""

from __future__ import annotations

import json
import sys

from cognipm.api.main import app
from cognipm.config import REPO_ROOT

TARGET = REPO_ROOT / "frontend" / "src" / "api" / "openapi.json"


def schema_text() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(schema_text(), encoding="utf-8")
    print(f"Wrote {TARGET.relative_to(REPO_ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
