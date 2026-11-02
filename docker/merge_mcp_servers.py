#!/usr/bin/env python3
"""Reconcile image-default MCP servers onto the Railway volume mcp.json.

Railway seeds ``mcp.json`` only when the volume file is absent, so a later
Git commit never reaches a service that already started. This helper:

- **upserts** every server from image defaults (add missing names; replace
  existing specs so renames / URL / command changes from Git take effect)
- **prunes** volume servers listed in an optional prune file (retired defaults)
- **keeps** volume-only servers that are neither in defaults nor pruned
  (Control Plane / UI additions)

UI edits to a Git-managed server name are overwritten on the next start; that
is intentional so ``config/mcp.json`` stays the source of truth for those
names.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


def reconcile_default_servers(
    volume: dict[str, Any],
    defaults: dict[str, Any],
    prune: Sequence[str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Upsert default servers and remove pruned names.

    Args:
        volume: Parsed volume ``mcp.json``. Mutated in place.
        defaults: Parsed image-default ``mcp.json``.
        prune: Optional server names to delete from the volume.

    Returns:
        ``(added, updated, removed)`` name lists in encounter order.

    Raises:
        ValueError: If either document's ``mcpServers`` value is not an object.
    """
    volume_servers = _servers(volume, label="volume")
    default_servers = _servers(defaults, label="defaults")
    added: list[str] = []
    updated: list[str] = []
    for name, spec in default_servers.items():
        if name not in volume_servers:
            volume_servers[name] = spec
            added.append(name)
        elif volume_servers[name] != spec:
            volume_servers[name] = spec
            updated.append(name)
    removed: list[str] = []
    for name in prune or ():
        if name in volume_servers:
            del volume_servers[name]
            removed.append(name)
    return added, updated, removed


def merge_missing_servers(
    volume: dict[str, Any],
    defaults: dict[str, Any],
) -> list[str]:
    """Backward-compatible wrapper: insert default servers that are missing.

    Args:
        volume: Parsed volume ``mcp.json``. Mutated in place when servers are added.
        defaults: Parsed image-default ``mcp.json``.

    Returns:
        Names of servers that were inserted, in default-file order.
    """
    added, _updated, _removed = reconcile_default_servers(volume, defaults, prune=())
    return added


def apply_default_servers(
    volume_path: Path,
    defaults_path: Path,
    prune_path: Path | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Reconcile defaults (and optional prune list) into ``volume_path``.

    The file is rewritten only when something changed, so an already-matching
    volume keeps its exact bytes (including UI formatting).

    Args:
        volume_path: Existing volume ``mcp.json``.
        defaults_path: Image-default ``mcp.json``.
        prune_path: Optional JSON array of server names to delete.

    Returns:
        ``(added, updated, removed)``.

    Raises:
        OSError: If a path cannot be read or written.
        json.JSONDecodeError: If a file is not JSON.
        ValueError: If ``mcpServers`` is not an object, or prune is not a
            string array.
    """
    volume = json.loads(volume_path.read_text(encoding="utf-8"))
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    if not isinstance(volume, dict) or not isinstance(defaults, dict):
        raise ValueError("mcp.json root must be a JSON object")
    prune = _load_prune(prune_path) if prune_path is not None else []
    added, updated, removed = reconcile_default_servers(volume, defaults, prune=prune)
    if not (added or updated or removed):
        return [], [], []
    volume_path.write_text(
        json.dumps(volume, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return added, updated, removed


def apply_missing_servers(volume_path: Path, defaults_path: Path) -> list[str]:
    """Backward-compatible wrapper around :func:`apply_default_servers`.

    Args:
        volume_path: Existing volume ``mcp.json``.
        defaults_path: Image-default ``mcp.json``.

    Returns:
        Names of servers inserted (not updated/removed).
    """
    added, _updated, _removed = apply_default_servers(volume_path, defaults_path)
    return added


def _load_prune(prune_path: Path) -> list[str]:
    """Load a JSON array of server names to prune.

    Args:
        prune_path: Path to the prune file. Missing file means no prune.

    Returns:
        Server names to delete.

    Raises:
        json.JSONDecodeError: If the file is not JSON.
        ValueError: If the root is not an array of strings.
        OSError: If the file exists but cannot be read.
    """
    if not prune_path.is_file():
        return []
    data = json.loads(prune_path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError("mcp.prune.json must be a JSON array of strings")
    return data


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
    parser.add_argument(
        "prune_json",
        type=Path,
        nargs="?",
        default=None,
        help="Optional JSON array of server names to remove from the volume",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    volume_path: Path = args.volume_mcp_json
    defaults_path: Path = args.defaults_mcp_json
    prune_path: Path | None = args.prune_json
    for path in (volume_path, defaults_path):
        if not path.is_file():
            print(f"RAILWAY: FATAL: {path} is missing; cannot merge mcp servers", file=sys.stderr)
            return 1
    try:
        added, updated, removed = apply_default_servers(
            volume_path, defaults_path, prune_path=prune_path
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"RAILWAY: FATAL: cannot merge mcp servers: {exc}", file=sys.stderr)
        return 1
    if added or updated or removed:
        parts: list[str] = []
        if added:
            parts.append("added " + ", ".join(added))
        if updated:
            parts.append("updated " + ", ".join(updated))
        if removed:
            parts.append("removed " + ", ".join(removed))
        print("RAILWAY: mcp servers on volume: " + "; ".join(parts))
    else:
        print(f"RAILWAY: volume mcp.json already matches defaults ({volume_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
