#!/usr/bin/env python3
"""Generate assistant-runtime/assistant-tools.json from the backend registry.

The OpenCode plugin registers one tool per entry, using the entry's strict JSON
Schema. Generating the manifest (rather than hand-writing it) keeps the plugin,
the manifest file, and the authoritative backend registry in lockstep; a drift
test regenerates it and compares.

Run:  api/.venv/bin/python assistant-runtime/generate_tools.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from app.assistant import tools  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "assistant-tools.json"

KIND_BY_NAME = {
    **{name: "read" for name in tools.read_tool_names()},
    **{name: "proposal" for name in tools.proposal_tool_names()},
    **{name: "status" for name in tools.STATUS_TOOL_NAMES},
}


def build() -> dict:
    entries = []
    for entry in tools.plugin_manifest():
        entries.append(
            {
                "name": entry["name"],
                "kind": KIND_BY_NAME.get(entry["name"], "read"),
                "codemode": False,
                "description": entry["description"],
                "schema": entry["input_schema"],
            }
        )
    return {
        "namespace": "architecture",
        "description": (
            "Generated from the backend tool registry (api/app/assistant/tools.py). "
            "Every tool is codemode:false, read-only or proposal-only, dispatches to "
            "the authoritative backend, and is validated again server-side."
        ),
        "tools": entries,
    }


def main() -> int:
    OUTPUT.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(build()['tools'])} tools)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
