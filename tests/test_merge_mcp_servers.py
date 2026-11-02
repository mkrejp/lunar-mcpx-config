"""Tests for reconciling default MCP servers onto a volume mcp.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from merge_mcp_servers import (
    apply_default_servers,
    apply_missing_servers,
    main,
    merge_missing_servers,
    reconcile_default_servers,
)


def test_reconcile_upserts_and_preserves_ui_only() -> None:
    """Default specs overwrite same-name entries; UI-only servers stay."""
    volume = {
        "mcpServers": {
            "time": {"command": "uvx", "args": ["custom"]},
            "ui-only": {"command": "echo"},
        }
    }
    defaults = {
        "mcpServers": {
            "time": {"command": "uvx", "args": ["from-git"]},
            "openstreetmap-mcp-server": {"command": "npx"},
        }
    }

    added, updated, removed = reconcile_default_servers(volume, defaults, prune=["geocode-mcp"])

    assert added == ["openstreetmap-mcp-server"]
    assert updated == ["time"]
    assert removed == []
    assert volume["mcpServers"]["time"]["args"] == ["from-git"]
    assert volume["mcpServers"]["ui-only"]["command"] == "echo"
    assert volume["mcpServers"]["openstreetmap-mcp-server"] == {"command": "npx"}


def test_reconcile_prunes_retired_servers() -> None:
    """Prune list deletes volume servers even when they are not in defaults."""
    volume = {
        "mcpServers": {
            "geocode-mcp": {"command": "npx"},
            "time": {"command": "uvx"},
        }
    }
    defaults = {"mcpServers": {"time": {"command": "uvx"}}}

    added, updated, removed = reconcile_default_servers(
        volume, defaults, prune=["geocode-mcp", "mcp-nominatim"]
    )

    assert added == []
    assert updated == []
    assert removed == ["geocode-mcp"]
    assert "geocode-mcp" not in volume["mcpServers"]
    assert "time" in volume["mcpServers"]


def test_merge_missing_servers_compat_only_adds() -> None:
    """Legacy helper still reports only newly added names."""
    volume = {"mcpServers": {"time": {"command": "old"}}}
    defaults = {
        "mcpServers": {
            "time": {"command": "new"},
            "pipeworx": {"type": "streamable-http", "url": "https://gateway.pipeworx.io/mcp"},
        }
    }
    # Legacy merge_missing_servers uses reconcile but returns only added.
    # Note: reconcile will also update time; compat wrapper returns added only.
    added = merge_missing_servers(volume, defaults)
    assert "pipeworx" in added
    assert volume["mcpServers"]["time"]["command"] == "new"


def test_apply_does_not_rewrite_when_already_synced(tmp_path: Path) -> None:
    """A volume that already matches defaults keeps its exact bytes."""
    volume = tmp_path / "mcp.json"
    defaults = tmp_path / "defaults.json"
    original = '{\n  "mcpServers": {\n    "time": {\n      "command": "uvx"\n    }\n  }\n}\n'
    volume.write_text(original, encoding="utf-8")
    defaults.write_text('{"mcpServers":{"time":{"command":"uvx"}}}\n', encoding="utf-8")

    added, updated, removed = apply_default_servers(volume, defaults)
    assert (added, updated, removed) == ([], [], [])
    assert volume.read_text(encoding="utf-8") == original


def test_apply_writes_updates_and_prunes(tmp_path: Path) -> None:
    """Rewrite when a default changes or a prune name is present."""
    volume = tmp_path / "mcp.json"
    defaults = tmp_path / "defaults.json"
    prune = tmp_path / "prune.json"
    volume.write_text(
        '{"mcpServers":{"osrm":{"type":"streamable-http","url":"https://old"},'
        '"geocode-mcp":{"command":"npx"},"custom":{"command":"echo"}}}\n',
        encoding="utf-8",
    )
    defaults.write_text(
        '{"mcpServers":{"osrm":{"type":"stdio","command":"npx","args":["-y","@pipeworx/mcp-osrm"]},'
        '"pipeworx":{"type":"streamable-http","url":"https://gateway.pipeworx.io/pipeworx-catalog/mcp"}}}\n',
        encoding="utf-8",
    )
    prune.write_text('["geocode-mcp","mcp-nominatim"]\n', encoding="utf-8")

    added, updated, removed = apply_default_servers(volume, defaults, prune_path=prune)

    assert added == ["pipeworx"]
    assert updated == ["osrm"]
    assert removed == ["geocode-mcp"]
    parsed = json.loads(volume.read_text(encoding="utf-8"))
    assert parsed["mcpServers"]["osrm"]["type"] == "stdio"
    assert parsed["mcpServers"]["pipeworx"]["url"] == "https://gateway.pipeworx.io/pipeworx-catalog/mcp"
    assert "geocode-mcp" not in parsed["mcpServers"]
    assert parsed["mcpServers"]["custom"]["command"] == "echo"


def test_cli_rejects_invalid_json(tmp_path: Path) -> None:
    """A corrupt volume file must fail the start instead of being replaced."""
    volume = tmp_path / "mcp.json"
    defaults = tmp_path / "defaults.json"
    volume.write_text("{", encoding="utf-8")
    defaults.write_text('{"mcpServers":{}}\n', encoding="utf-8")

    assert main([str(volume), str(defaults)]) == 1
    assert volume.read_text(encoding="utf-8") == "{"


def test_cli_second_run_is_quiet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Running twice must not keep rewriting after sync."""
    volume = tmp_path / "mcp.json"
    defaults = tmp_path / "defaults.json"
    volume.write_text('{"mcpServers":{}}\n', encoding="utf-8")
    defaults.write_text('{"mcpServers":{"time":{"command":"uvx"}}}\n', encoding="utf-8")

    assert main([str(volume), str(defaults)]) == 0
    first = json.loads(volume.read_text(encoding="utf-8"))
    assert main([str(volume), str(defaults)]) == 0
    assert json.loads(volume.read_text(encoding="utf-8")) == first
    captured = capsys.readouterr()
    assert "added time" in captured.out
    assert "already matches defaults" in captured.out


def test_seeded_mcp_json_split_osrm_and_pipeworx() -> None:
    """Git defaults: clean OSRM stdio, authenticated Pipeworx HTTP, no geocode dupes."""
    path = Path(__file__).resolve().parents[1] / "config" / "mcp.json"
    servers = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]

    assert servers["openstreetmap-mcp-server"]["command"] == "npx"
    assert servers["openstreetmap-mcp-server"]["args"][-1] == "@cyanheads/openstreetmap-mcp-server"
    assert servers["osrm"]["type"] == "stdio"
    assert servers["osrm"]["args"][-1] == "@pipeworx/mcp-osrm"
    assert servers["osrm"]["env"]["PIPEWORX_API_KEY"] == "${PIPEWORX_API_KEY}"
    assert servers["pipeworx"]["type"] == "streamable-http"
    assert servers["pipeworx"]["url"] == "https://gateway.pipeworx.io/pipeworx-catalog/mcp"
    assert servers["pipeworx"]["headers"]["X-API-Key"] == "${PIPEWORX_API_KEY}"
    assert "geocode-mcp" not in servers
    assert "mcp-nominatim" not in servers
    assert "open-streetmap-mcp" not in servers
    assert "clio-geojson" not in servers
    assert servers["switzerland-mcp"]["args"][-1] == "mcp-swiss"
    assert "openstreetmap-mcp-server" in servers

    prune = json.loads(
        (Path(__file__).resolve().parents[1] / "config" / "mcp.prune.json").read_text(encoding="utf-8")
    )
    assert prune == [
        "geocode-mcp",
        "mcp-nominatim",
        "open-streetmap-mcp",
        "clio-geojson",
    ]
