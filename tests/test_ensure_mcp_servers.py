"""Skim tests for volume-safe MCP server merge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ensure_mcp_servers import is_catalog_placeholder, merge_mcp_servers


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


def test_catalog_placeholders_are_ignored() -> None:
    """Pasted category comments must not become MCPX servers."""
    assert is_catalog_placeholder("// cat", {}) is True
    assert is_catalog_placeholder("geocode-mcp", {"command": "npx"}) is False


def test_repo_mcp_json_has_requested_names() -> None:
    """Git defaults include the requested upstream names (minus unpublished)."""
    path = Path(__file__).resolve().parents[1] / "config" / "mcp.json"
    servers = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]
    for name in (
        "geocode-mcp",
        "google-maps-mcp",
        "opencage-geocoding",
        "mapbox-mcp",
        "foursquare-places",
        "overture-maps-mcp",
        "open-meteo-mcp",
        "nws-alerts",
        "stac-search",
    ):
        assert name in servers
        assert servers[name].get("command") in {"npx", "uvx"}
    assert "postgis-mcp" not in servers
