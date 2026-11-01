#!/usr/bin/env python3
"""Merge MCPX auth settings into an existing volume ``app.yaml``.

Upstream MCPX 0.5.8 (``mcpx-server/src/server/auth.ts``) reads the shared
secret from env ``AUTH_KEY`` and compares it to header ``x-lunar-api-key``
(override: ``auth.header`` in app.yaml). ``auth.enabled`` lives only in
app.yaml — it is not an env var.

Railway mounts a persistent volume at the config dir and the entrypoint
seeds files only when they are missing. This helper therefore *merges*
``auth.enabled: true`` (and a default header if absent) into the existing
file so a redeploy actually turns auth on without rewriting ``mcp.json``
or wiping UI-edited ACL / tool groups.

When ``auth.enabled`` is true and ``AUTH_KEY`` is empty, upstream
``buildApiKeyGuard`` logs a warning and returns a no-op guard (fail-open).
This script refuses that path: ``check-auth-key`` exits non-zero.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Sequence

DEFAULT_API_KEY_HEADER = "x-lunar-api-key"
AUTH_KEY_ENV = "AUTH_KEY"

_TOP_LEVEL_AUTH = re.compile(r"^auth:\s*(?:#.*)?$")
_ENABLED_LINE = re.compile(
    r"^([ \t]+)enabled:\s*(?:['\"]?(true|false)['\"]?)?(.*)$",
    re.IGNORECASE,
)
_HEADER_LINE = re.compile(r"^[ \t]+header:\s*")


def merge_auth_yaml(
    text: str,
    *,
    header: str = DEFAULT_API_KEY_HEADER,
) -> str:
    """Return ``text`` with ``auth.enabled: true`` and a default header.

    Preserves comments and every key outside the top-level ``auth:`` block.
    Does not overwrite an existing ``auth.header`` value.

    Args:
        text: Existing app.yaml contents.
        header: Header name to set only when ``auth.header`` is missing.

    Returns:
        YAML text ending with a newline.
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()

    auth_start = next(
        (index for index, line in enumerate(lines) if _TOP_LEVEL_AUTH.match(line)),
        -1,
    )
    if auth_start < 0:
        body = text.rstrip("\r\n")
        suffix = (
            f"{newline}auth:{newline}"
            f"  enabled: true{newline}"
            f"  header: {header}{newline}"
        )
        if body:
            return f"{body}{newline}{suffix}"
        return suffix

    auth_end = len(lines)
    for index in range(auth_start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        if not lines[index].startswith((" ", "\t")):
            auth_end = index
            break

    block = lines[auth_start:auth_end]
    has_enabled = False
    has_header = False
    enabled_index = -1
    for index in range(1, len(block)):
        enabled_match = _ENABLED_LINE.match(block[index])
        if enabled_match:
            has_enabled = True
            enabled_index = index
            indent = enabled_match.group(1)
            suffix = enabled_match.group(3) or ""
            comment = suffix.strip()
            if comment.startswith("#"):
                block[index] = f"{indent}enabled: true {comment}"
            else:
                block[index] = f"{indent}enabled: true"
        if _HEADER_LINE.match(block[index]):
            has_header = True

    if not has_enabled:
        block.insert(1, "  enabled: true")
        enabled_index = 1
    if not has_header:
        insert_at = enabled_index + 1 if enabled_index >= 0 else 2
        block.insert(insert_at, f"  header: {header}")

    merged = lines[:auth_start] + block + lines[auth_end:]
    return newline.join(merged) + newline


def apply_auth_to_file(
    path: Path,
    *,
    header: str = DEFAULT_API_KEY_HEADER,
) -> bool:
    """Merge auth into ``path`` in place.

    Args:
        path: Existing app.yaml path (must already exist).
        header: Default API key header when the file has none.

    Returns:
        True when the file content changed.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    original = path.read_text(encoding="utf-8")
    merged = merge_auth_yaml(original, header=header)
    if merged == original:
        return False
    path.write_text(merged, encoding="utf-8")
    return True


def auth_key_is_configured(value: str | None = None) -> bool:
    """Return True when ``AUTH_KEY`` is present and not whitespace-only.

    Args:
        value: Explicit value; defaults to ``os.environ['AUTH_KEY']``.

    Returns:
        Whether a usable shared secret is configured.
    """
    secret = os.environ.get(AUTH_KEY_ENV, "") if value is None else value
    return bool(secret.strip())


def _build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    merge = sub.add_parser("merge", help="Merge auth.enabled into an app.yaml")
    merge.add_argument("app_yaml", type=Path)
    merge.add_argument(
        "--header",
        default=DEFAULT_API_KEY_HEADER,
        help="Header written only when auth.header is absent",
    )

    check = sub.add_parser(
        "check-auth-key",
        help="Fail closed when AUTH_KEY is missing (stdout/stderr warning)",
    )
    check.add_argument(
        "--allow-missing",
        action="store_true",
        help="Warn instead of exiting non-zero (not used by the Railway entrypoint)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "merge":
        path: Path = args.app_yaml
        if not path.is_file():
            print(f"RAILWAY: FATAL: {path} is missing; cannot enable auth", file=sys.stderr)
            return 1
        changed = apply_auth_to_file(path, header=args.header)
        if changed:
            print(f"RAILWAY: merged auth.enabled=true into {path}")
        else:
            print(f"RAILWAY: auth already enabled in {path}")
        return 0

    if args.command == "check-auth-key":
        if auth_key_is_configured():
            print("RAILWAY: AUTH_KEY is set; MCP clients must send x-lunar-api-key")
            return 0
        message = (
            "RAILWAY: FATAL: AUTH_KEY is unset or empty.\n"
            "RAILWAY: auth.enabled is true in app.yaml; without AUTH_KEY, "
            "upstream MCPX 0.5.8 fail-OPENs /mcp (noOpAuthGuard).\n"
            "RAILWAY: Set AUTH_KEY on lunar-mcpx (Railway Variables) and redeploy.\n"
            "RAILWAY: Clients send header x-lunar-api-key: <AUTH_KEY>."
        )
        print(message, file=sys.stderr)
        if args.allow_missing:
            return 0
        return 1

    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
