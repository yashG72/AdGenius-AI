"""Write the API's OpenAPI schema to a file (no running server needed).

The frontend generates its TypeScript types from this file, so the browser code is
type-checked against the real backend contract:

    python -m scripts.export_openapi            # -> ../frontend/src/lib/api/openapi.json
    cd ../frontend && npm run gen:api           # -> src/lib/api/schema.d.ts
"""

import json
import sys
from pathlib import Path

from app.main import create_app

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "api" / "openapi.json"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    schema = create_app().openapi()
    out.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(schema['paths'])} paths to {out}")


if __name__ == "__main__":
    main()
