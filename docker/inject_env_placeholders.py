#!/usr/bin/env python3
"""Expand ``${VAR}`` placeholders in volume mcp.json from the process env.

Used so Git-tracked defaults can reference secrets (e.g. PIPEWORX_API_KEY)
without storing their values in the repo or in image defaults. Only the
volume copy is rewritten. Unresolved placeholders are left as-is and
reported; set REQUIRE_VARS to fail closed when a name is missing/empty.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Sequence

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_string(value: str, env: dict[str, str]) -> tuple[str, list[str]]:
    """Replace ``${VAR}`` in ``value`` using ``env``.

    Returns:
        The expanded string and names that were missing or empty in ``env``.
    """
    missing: list[str] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        raw = env.get(name)
        if raw is None or raw == "":
            missing.append(name)
            return match.group(0)
        return raw

    return _PLACEHOLDER.sub(repl, value), missing


def expand_document(node: Any, env: dict[str, str]) -> list[str]:
    """Recursively expand placeholders in strings inside ``node`` in place.

    Returns:
        Deduplicated list of missing variable names, in first-seen order.
    """
    missing: list[str] = []
    seen: set[str] = set()

    def walk(value: Any) -> Any:
        if isinstance(value, str):
            expanded, miss = expand_string(value, env)
            for name in miss:
                if name not in seen:
                    seen.add(name)
                    missing.append(name)
            return expanded
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        return value

    # mutate caller's structure via reassignment at top only when dict/list
    if isinstance(node, dict):
        for key in list(node.keys()):
            node[key] = walk(node[key])
    elif isinstance(node, list):
        for index, item in enumerate(list(node)):
            node[index] = walk(item)
    return missing


def apply_env_placeholders(
    path: Path,
    *,
    env: dict[str, str] | None = None,
    require: Sequence[str] | None = None,
) -> list[str]:
    """Expand placeholders in ``path`` and rewrite when anything changed.

    Args:
        path: Volume ``mcp.json``.
        env: Environment mapping (defaults to ``os.environ``).
        require: Variable names that must be non-empty after expansion.

    Returns:
        Missing variable names encountered during expansion.

    Raises:
        OSError / json.JSONDecodeError / ValueError: On I/O or schema errors.
        SystemExit-equivalent via ValueError when a required var is missing.
    """
    env_map = dict(os.environ if env is None else env)
    original = path.read_text(encoding="utf-8")
    document = json.loads(original)
    if not isinstance(document, dict):
        raise ValueError("mcp.json root must be a JSON object")
    missing = expand_document(document, env_map)
    required = list(require or ())
    unresolved_required = [name for name in required if not env_map.get(name)]
    if unresolved_required:
        raise ValueError(
            "required env vars missing or empty: " + ", ".join(unresolved_required)
        )
    rewritten = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if rewritten != original:
        path.write_text(rewritten, encoding="utf-8")
    return missing


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mcp_json", type=Path)
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        help="Fail if this env var is missing/empty (repeatable)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    path: Path = args.mcp_json
    if not path.is_file():
        print(f"RAILWAY: FATAL: {path} is missing; cannot inject env placeholders", file=sys.stderr)
        return 1
    try:
        missing = apply_env_placeholders(path, require=args.require)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"RAILWAY: FATAL: cannot inject env placeholders: {exc}", file=sys.stderr)
        return 1
    if missing:
        # Non-required placeholders may remain; warn only.
        print("RAILWAY: unresolved mcp.json placeholders: " + ", ".join(missing))
    else:
        print(f"RAILWAY: mcp.json env placeholders resolved ({path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
