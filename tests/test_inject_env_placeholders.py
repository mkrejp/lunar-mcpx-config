"""Tests for ${VAR} expansion in volume mcp.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inject_env_placeholders import apply_env_placeholders, expand_string, main


def test_expand_string_replaces_known_vars() -> None:
    out, missing = expand_string("Bearer ${PIPEWORX_API_KEY}", {"PIPEWORX_API_KEY": "secret"})
    assert out == "Bearer secret"
    assert missing == []


def test_expand_string_keeps_missing() -> None:
    out, missing = expand_string("Bearer ${PIPEWORX_API_KEY}", {})
    assert out == "Bearer ${PIPEWORX_API_KEY}"
    assert missing == ["PIPEWORX_API_KEY"]


def test_apply_rewrites_headers(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "pipeworx": {
                        "type": "streamable-http",
                        "url": "https://gateway.pipeworx.io/mcp",
                        "headers": {"Authorization": "Bearer ${PIPEWORX_API_KEY}"},
                    }
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    missing = apply_env_placeholders(path, env={"PIPEWORX_API_KEY": "tok_test"}, require=["PIPEWORX_API_KEY"])
    assert missing == []
    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert parsed["mcpServers"]["pipeworx"]["headers"]["Authorization"] == "Bearer tok_test"


def test_apply_requires_var(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text('{"mcpServers":{}}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="PIPEWORX_API_KEY"):
        apply_env_placeholders(path, env={}, require=["PIPEWORX_API_KEY"])


def test_cli_require(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(
        '{"mcpServers":{"pipeworx":{"headers":{"Authorization":"Bearer ${PIPEWORX_API_KEY}"}}}}\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("PIPEWORX_API_KEY", raising=False)
    assert main([str(path), "--require", "PIPEWORX_API_KEY"]) == 1
