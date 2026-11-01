#!/usr/bin/env python3
"""Merge git-tracked MCP servers into a volume ``mcp.json`` without wiping it.

Railway seeds ``mcp.json`` only on first start. Later git additions would
otherwise never appear. This helper adds *missing* ``mcpServers`` entries from
the image defaults and leaves every existing name (UI edits, custom servers)
untouched.

Category comment keys (``// ...``) and empty objects are skipped so a pasted
catalog cannot break MCPX's schema.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

JsonObject = dict[str, Any]


def is_catalog_placeholder(name: str, config: object) -> bool:
    """Return True for category comments or empty pasted catalog entries.

    Args:
        name: Server key from ``mcpServers``.
        config: Value under that key.

    Returns:
        Whether the entry should be ignored.
    """
    if name.startswith("//"):
        return True
    if not isinstance(config, Mapping):
        return True
    if not config:
        return True
    return not (config.get("command") or config.get("url"))


def merge_mcp_servers(
    volume: Mapping[str, Any],
    defaults: Mapping[str, Any],
) -> JsonObject:
    """Return volume config with default servers added when missing.

    Args:
        volume: Existing on-disk ``mcp.json``.
        defaults: Image-baked ``mcp.json``.

    Returns:
        New document with a ``mcpServers`` object.
    """
    merged: JsonObject = dict(volume) if volume else {}
    servers: JsonObject = dict(merged.get("mcpServers") or {})
    for name, config in (defaults.get("mcpServers") or {}).items():
        if is_catalog_placeholder(str(name), config):
            continue
        if name in servers:
            continue
        servers[name] = config
    merged["mcpServers"] = servers
    return merged


def apply_mcp_servers(volume_path: Path, defaults_path: Path) -> bool:
    """Merge defaults into ``volume_path`` in place.

    Args:
        volume_path: Live ``mcp.json`` on the Railway volume.
        defaults_path: Image defaults to add from.

    Returns:
        True when the file changed.

    Raises:
        FileNotFoundError: If either path is missing.
        json.JSONDecodeError: If a file is not JSON.
    """
    volume = json.loads(volume_path.read_text(encoding="utf-8"))
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    if not isinstance(volume, dict) or not isinstance(defaults, dict):
        raise ValueError("mcp.json must be a JSON object")
    merged = merge_mcp_servers(volume, defaults)
    if merged == volume:
        return False
    volume_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return True


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Optional argument list.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("volume_mcp_json", type=Path)
    parser.add_argument("--defaults", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.volume_mcp_json.is_file():
        print(
            f"RAILWAY: FATAL: {args.volume_mcp_json} is missing; cannot merge servers",
            file=sys.stderr,
        )
        return 1
    if not args.defaults.is_file():
        print(f"RAILWAY: no defaults at {args.defaults}; skip server merge")
        return 0

    try:
        changed = apply_mcp_servers(args.volume_mcp_json, args.defaults)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"RAILWAY: FATAL: mcp.json merge failed: {exc}", file=sys.stderr)
        return 1

    if changed:
        print(f"RAILWAY: merged missing MCP servers into {args.volume_mcp_json}")
    else:
        print("RAILWAY: volume mcp.json already has all default servers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
