#!/usr/bin/env python3
"""Railway-friendly AIOS Runtime launcher."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "automation" / "central_orchestrator" / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Start AIOS Runtime for production hosting")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8888")))
    args = parser.parse_args()
    os.environ["AIOS_API_HOST"] = args.host
    os.environ["AIOS_API_PORT"] = str(args.port)
    from aios_runtime import start

    return start(host=args.host, port=args.port)


if __name__ == "__main__":
    raise SystemExit(main())
