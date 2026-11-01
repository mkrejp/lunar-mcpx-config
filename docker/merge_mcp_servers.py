#!/usr/bin/env python3
"""Add MCP servers from image defaults that are missing on the volume.

Railway seeds ``mcp.json`` only when the volume file is absent, so a later
Git commit never reaches a service that already started. This helper inserts
default servers whose names are not already present. It does not rewrite an
existing server entry and it does not delete servers that exist only on the
volume (Control Plane / UI additions).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


def merge_missing_servers(
    volume: dict[str, Any],
    defaults: dict[str, Any],
) -> list[str]:
    """Insert default servers that the volume config does not already name.

    Args:
        volume: Parsed volume ``mcp.json``. Mutated in place when servers are added.
        defaults: Parsed image-default ``mcp.json``.

    Returns:
        Names of servers that were inserted, in default-file order.

    Raises:
        ValueError: If either document's ``mcpServers`` value is not an object.
    """
    volume_servers = _servers(volume, label="volume")
    default_servers = _servers(defaults, label="defaults")
    added: list[str] = []
    for name, spec in default_servers.items():
        if name in volume_servers:
            continue
        volume_servers[name] = spec
        added.append(name)
    return added


def apply_missing_servers(volume_path: Path, defaults_path: Path) -> list[str]:
    """Merge missing servers into ``volume_path``.

    The file is rewritten only when at least one server is added, so an
    already-complete volume keeps its exact bytes (including UI formatting).

    Args:
        volume_path: Existing volume ``mcp.json``.
        defaults_path: Image-default ``mcp.json``.

    Returns:
        Names of servers inserted.

    Raises:
        OSError: If a path cannot be read or written.
        json.JSONDecodeError: If either file is not JSON.
        ValueError: If ``mcpServers`` is not an object.
    """
    volume = json.loads(volume_path.read_text(encoding="utf-8"))
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    if not isinstance(volume, dict) or not isinstance(defaults, dict):
        raise ValueError("mcp.json root must be a JSON object")
    added = merge_missing_servers(volume, defaults)
    if not added:
        return []
    volume_path.write_text(
        json.dumps(volume, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return added


def _servers(document: dict[str, Any], *, label: str) -> dict[str, Any]:
    """Return the ``mcpServers`` object, creating it on the volume when absent.

    Args:
        document: Parsed mcp.json object.
        label: ``volume`` or ``defaults``, used in errors.

    Returns:
        The servers object.

    Raises:
        ValueError: If ``mcpServers`` is present and not an object.
    """
    servers = document.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(f"{label} mcp.json mcpServers must be a JSON object")
    if "mcpServers" not in document:
        document["mcpServers"] = servers
    return servers


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code. ``0`` when the merge ran; ``1`` when a file is
        missing or invalid.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("volume_mcp_json", type=Path)
    parser.add_argument("defaults_mcp_json", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)

    volume_path: Path = args.volume_mcp_json
    defaults_path: Path = args.defaults_mcp_json
    for path in (volume_path, defaults_path):
        if not path.is_file():
            print(f"RAILWAY: FATAL: {path} is missing; cannot merge mcp servers", file=sys.stderr)
            return 1
    try:
        added = apply_missing_servers(volume_path, defaults_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"RAILWAY: FATAL: cannot merge mcp servers: {exc}", file=sys.stderr)
        return 1
    if added:
        print("RAILWAY: added mcp servers to volume: " + ", ".join(added))
    else:
        print(f"RAILWAY: volume mcp.json already has every default server ({volume_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
