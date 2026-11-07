"""`python -m agentbuilder_control`: serve on 127.0.0.1. Needs AGENTBUILDER_CONTROL_DATABASE_URL (for example
postgresql+psycopg://agentbuilder:...@127.0.0.1:5432/agentbuilder, from `make up`) and AGENTBUILDER_CONTROL_TOKEN."""

from __future__ import annotations

import os
import sys


def main() -> int:
    url, token = os.environ.get("AGENTBUILDER_CONTROL_DATABASE_URL"), os.environ.get("AGENTBUILDER_CONTROL_TOKEN")
    if not url or not token or len(token) < 32:
        print("set AGENTBUILDER_CONTROL_DATABASE_URL and AGENTBUILDER_CONTROL_TOKEN (32+ characters)", file=sys.stderr)
        return 1
    import uvicorn

    from agentbuilder_control import create_app

    uvicorn.run(create_app(url, token), host="127.0.0.1", port=int(os.environ.get("AGENTBUILDER_CONTROL_PORT", "8700")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
