"""Tests for adding missing default MCP servers onto a volume mcp.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from merge_mcp_servers import apply_missing_servers, main, merge_missing_servers


def test_merge_adds_only_missing_servers() -> None:
    """Insert a default server and leave an edited existing entry alone."""
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

    added = merge_missing_servers(volume, defaults)

    assert added == ["openstreetmap-mcp-server"]
    assert volume["mcpServers"]["time"]["args"] == ["custom"]
    assert volume["mcpServers"]["ui-only"]["command"] == "echo"
    assert volume["mcpServers"]["openstreetmap-mcp-server"] == {"command": "npx"}


def test_apply_does_not_rewrite_when_nothing_is_missing(tmp_path: Path) -> None:
    """A volume that already has every default server keeps its exact bytes.

    Args:
        tmp_path: Pytest temporary directory.
    """
    volume = tmp_path / "mcp.json"
    defaults = tmp_path / "defaults.json"
    original = '{\n  "mcpServers": {\n    "time": { "command": "uvx" }\n  }\n}\n'
    volume.write_text(original, encoding="utf-8")
    defaults.write_text('{"mcpServers":{"time":{"command":"other"}}}\n', encoding="utf-8")

    assert apply_missing_servers(volume, defaults) == []
    assert volume.read_text(encoding="utf-8") == original


def test_apply_writes_added_server(tmp_path: Path) -> None:
    """Rewrite the volume file when a default server name is absent.

    Args:
        tmp_path: Pytest temporary directory.
    """
    volume = tmp_path / "mcp.json"
    defaults = tmp_path / "defaults.json"
    volume.write_text('{"mcpServers":{"custom":{"command":"echo"}}}\n', encoding="utf-8")
    defaults.write_text(
        '{"mcpServers":{"openstreetmap-mcp-server":{"command":"npx","args":["-y"]}}}\n',
        encoding="utf-8",
    )

    added = apply_missing_servers(volume, defaults)

    assert added == ["openstreetmap-mcp-server"]
    parsed = json.loads(volume.read_text(encoding="utf-8"))
    assert list(parsed["mcpServers"]) == ["custom", "openstreetmap-mcp-server"]
    assert parsed["mcpServers"]["openstreetmap-mcp-server"]["args"] == ["-y"]


def test_cli_rejects_invalid_json(tmp_path: Path) -> None:
    """A corrupt volume file must fail the start instead of being replaced.

    Args:
        tmp_path: Pytest temporary directory.
    """
    volume = tmp_path / "mcp.json"
    defaults = tmp_path / "defaults.json"
    volume.write_text("{", encoding="utf-8")
    defaults.write_text('{"mcpServers":{}}\n', encoding="utf-8")

    assert main([str(volume), str(defaults)]) == 1
    assert volume.read_text(encoding="utf-8") == "{"


def test_cli_second_run_is_quiet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Running twice must not keep appending the same server.

    Args:
        tmp_path: Pytest temporary directory.
        capsys: Pytest stdout/stderr capture.
    """
    volume = tmp_path / "mcp.json"
    defaults = tmp_path / "defaults.json"
    volume.write_text('{"mcpServers":{}}\n', encoding="utf-8")
    defaults.write_text('{"mcpServers":{"time":{"command":"uvx"}}}\n', encoding="utf-8")

    assert main([str(volume), str(defaults)]) == 0
    first = json.loads(volume.read_text(encoding="utf-8"))
    assert main([str(volume), str(defaults)]) == 0
    assert json.loads(volume.read_text(encoding="utf-8")) == first
    captured = capsys.readouterr()
    assert "added mcp servers to volume: time" in captured.out
    assert "already has every default server" in captured.out


def test_seeded_mcp_json_includes_osrm_and_openstreetmap() -> None:
    """The Git default must name the upstreams this deploy is expected to add."""
    path = Path(__file__).resolve().parents[1] / "config" / "mcp.json"
    servers = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]

    assert servers["openstreetmap-mcp-server"]["command"] == "npx"
    assert servers["openstreetmap-mcp-server"]["args"][-1] == "@cyanheads/openstreetmap-mcp-server"
    assert servers["osrm"]["type"] == "streamable-http"
    assert servers["osrm"]["url"] == "https://gateway.pipeworx.io/osrm/mcp"
    assert "command" not in servers["osrm"]
    assert servers["geocode-mcp"]["args"][-1] == "geocode-mcp"
    assert servers["mcp-nominatim"]["args"][-1] == "@pipeworx/mcp-nominatim"
    assert servers["open-streetmap-mcp"]["args"] == ["osm-mcp-server"]
    assert servers["switzerland-mcp"]["args"][-1] == "mcp-swiss"
    assert servers["clio-geojson"]["args"] == ["clio-kit", "mcp-server", "geojson"]
