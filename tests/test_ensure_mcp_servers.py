"""Tests for volume-safe MCP server merge (git defaults onto existing mcp.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ensure_mcp_servers import (
    apply_mcp_servers,
    is_catalog_placeholder,
    main,
    merge_mcp_servers,
)

REPO_MCP_JSON = Path(__file__).resolve().parents[1] / "config" / "mcp.json"

REQUESTED_SERVERS = (
    "geocode-mcp",
    "google-maps-mcp",
    "opencage-geocoding",
    "mapbox-mcp",
    "foursquare-places",
    "overture-maps-mcp",
    "open-meteo-mcp",
    "nws-alerts",
    "stac-search",
)

KEYED_SERVERS = {
    "google-maps-mcp": "GOOGLE_MAPS_API_KEY",
    "opencage-geocoding": "OPENCAGE_API_KEY",
    "mapbox-mcp": "MAPBOX_ACCESS_TOKEN",
    "foursquare-places": "FOURSQUARE_API_KEY",
    "overture-maps-mcp": "OVERTURE_API_KEY",
}


def test_merge_adds_missing_keeps_existing() -> None:
    """Add new default servers; leave an already-present name alone."""
    volume = {
        "mcpServers": {
            "time": {"command": "echo", "args": ["custom"]},
            "custom": {"command": "npx", "args": ["-y", "foo"]},
        }
    }
    defaults = {
        "mcpServers": {
            "time": {"command": "uvx", "args": ["mcp-server-time"]},
            "geocode-mcp": {"command": "npx", "args": ["-y", "geocode-mcp"]},
            "// --- CATEGORY: SKIP --- //": {},
        }
    }
    merged = merge_mcp_servers(volume, defaults)
    servers: dict[str, Any] = merged["mcpServers"]
    assert servers["time"]["command"] == "echo"
    assert servers["custom"]["args"] == ["-y", "foo"]
    assert servers["geocode-mcp"]["args"] == ["-y", "geocode-mcp"]
    assert "// --- CATEGORY: SKIP --- //" not in servers


def test_merge_is_idempotent() -> None:
    """A second merge must not keep adding or rewriting entries."""
    defaults = {"mcpServers": {"geocode-mcp": {"command": "npx", "args": ["-y", "geocode-mcp"]}}}
    first = merge_mcp_servers({"mcpServers": {}}, defaults)
    second = merge_mcp_servers(first, defaults)
    assert first == second


def test_catalog_placeholders_are_ignored() -> None:
    """Pasted category comments and empty objects must not become MCPX servers."""
    assert is_catalog_placeholder("// cat", {}) is True
    assert is_catalog_placeholder("empty", {}) is True
    assert is_catalog_placeholder("no-command", {"icon": "x"}) is True
    assert is_catalog_placeholder("geocode-mcp", {"command": "npx"}) is False
    assert is_catalog_placeholder("remote", {"url": "http://example/mcp"}) is False


def test_apply_writes_once(tmp_path: Path) -> None:
    """Write the merge to disk only when a server is actually added.

    Args:
        tmp_path: Pytest temporary directory.
    """
    volume = tmp_path / "mcp.json"
    defaults = tmp_path / "defaults.json"
    volume.write_text('{"mcpServers":{"time":{"command":"echo"}}}\n', encoding="utf-8")
    defaults.write_text(
        '{"mcpServers":{"time":{"command":"uvx"},"geocode-mcp":{"command":"npx"}}}\n',
        encoding="utf-8",
    )
    assert apply_mcp_servers(volume, defaults) is True
    assert apply_mcp_servers(volume, defaults) is False
    servers = json.loads(volume.read_text(encoding="utf-8"))["mcpServers"]
    assert servers["time"]["command"] == "echo"
    assert servers["geocode-mcp"]["command"] == "npx"


def test_cli_merge_missing_volume_fails(tmp_path: Path) -> None:
    """CLI must fail closed when the volume file is absent.

    Args:
        tmp_path: Pytest temporary directory.
    """
    defaults = tmp_path / "defaults.json"
    defaults.write_text('{"mcpServers":{}}\n', encoding="utf-8")
    assert main([str(tmp_path / "missing.json"), "--defaults", str(defaults)]) == 1


def test_cli_invalid_json_fails(tmp_path: Path) -> None:
    """Corrupt volume JSON must not be silently skipped.

    Args:
        tmp_path: Pytest temporary directory.
    """
    volume = tmp_path / "mcp.json"
    defaults = tmp_path / "defaults.json"
    volume.write_text("{not-json", encoding="utf-8")
    defaults.write_text('{"mcpServers":{}}\n', encoding="utf-8")
    assert main([str(volume), "--defaults", str(defaults)]) == 1


def test_repo_mcp_json_has_requested_names() -> None:
    """Git defaults include the requested upstream names (minus unpublished)."""
    servers = json.loads(REPO_MCP_JSON.read_text(encoding="utf-8"))["mcpServers"]
    for name in REQUESTED_SERVERS:
        assert name in servers
        assert servers[name].get("command") in {"npx", "uvx"}
        assert servers[name].get("type") == "stdio"
    assert "postgis-mcp" not in servers
    for key in servers:
        assert not key.startswith("//")


def test_repo_secrets_use_from_env_not_literals() -> None:
    """Keyed servers must reference Railway env vars, never placeholder secrets."""
    raw = REPO_MCP_JSON.read_text(encoding="utf-8")
    assert "YOUR_" not in raw
    servers = json.loads(raw)["mcpServers"]
    for name, env_name in KEYED_SERVERS.items():
        env = servers[name]["env"]
        assert env[env_name] == {"fromEnv": env_name}
