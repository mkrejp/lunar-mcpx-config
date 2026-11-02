"""Tests for volume-safe MCPX auth merge and fail-closed AUTH_KEY checks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ensure_app_auth import (
    DEFAULT_API_KEY_HEADER,
    apply_auth_to_file,
    auth_key_is_configured,
    main,
    merge_auth_yaml,
)

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.monkeypatch import MonkeyPatch

DOCKER_DIR = Path(__file__).resolve().parents[1] / "docker"
ENSURE_SCRIPT = DOCKER_DIR / "ensure_app_auth.py"
ENTRYPOINT = DOCKER_DIR / "railway-entrypoint.sh"

EXISTING_VOLUME_APP_YAML = """# MCPX application config (ACL, auth, tool groups).
# Official Helm/Terraform default is `permissions.base: allow`.

auth:
  enabled: false

permissions:
  base: "allow"
  default:
    block: []
  consumers: {}

toolGroups: []

toolExtensions:
  services: {}
"""

USER_EDITED_MCP_JSON = """{
  "mcpServers": {
    "custom": {
      "type": "stdio",
      "command": "echo"
    }
  }
}
"""


def test_merge_flips_seeded_auth_false() -> None:
    """Flip ``auth.enabled: false`` on a first-start volume file."""
    merged = merge_auth_yaml(EXISTING_VOLUME_APP_YAML)

    assert "auth:\n  enabled: true\n  header: x-lunar-api-key\n" in merged
    assert "enabled: false" not in merged
    assert 'base: "allow"' in merged
    assert "toolGroups: []" in merged
    assert "consumers: {}" in merged


def test_merge_preserves_custom_header() -> None:
    """Do not overwrite an operator-set ``auth.header``."""
    source = "auth:\n  enabled: false\n  header: x-custom-key\n"
    merged = merge_auth_yaml(source)

    assert "enabled: true" in merged
    assert "header: x-custom-key" in merged
    assert merged.count("header:") == 1


def test_merge_appends_auth_block_when_missing() -> None:
    """Add a top-level auth block when the volume file has none."""
    merged = merge_auth_yaml("permissions:\n  base: allow\n")

    assert merged.endswith("\n")
    assert "permissions:\n  base: allow\n" in merged
    assert "auth:\n  enabled: true\n  header: x-lunar-api-key\n" in merged


def test_merge_is_idempotent() -> None:
    """A second merge must not keep rewriting the file."""
    first = merge_auth_yaml(EXISTING_VOLUME_APP_YAML)
    second = merge_auth_yaml(first)
    assert first == second


def test_apply_auth_to_file_rewrites_once(tmp_path: Path) -> None:
    """Write the merge to disk only when the content changes.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "app.yaml"
    path.write_text(EXISTING_VOLUME_APP_YAML, encoding="utf-8")

    assert apply_auth_to_file(path) is True
    assert apply_auth_to_file(path) is False
    assert "enabled: true" in path.read_text(encoding="utf-8")


def test_auth_key_is_configured_rejects_blank(monkeypatch: MonkeyPatch) -> None:
    """Whitespace-only AUTH_KEY must not count as configured.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.delenv("AUTH_KEY", raising=False)
    assert auth_key_is_configured("secret") is True
    assert auth_key_is_configured("") is False
    assert auth_key_is_configured("   \n") is False
    assert auth_key_is_configured(None) is False


def test_check_auth_key_fails_closed(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    """``check-auth-key`` exits 1 when AUTH_KEY is missing.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        capsys: Capture of stdout/stderr.
    """
    monkeypatch.delenv("AUTH_KEY", raising=False)
    assert main(["check-auth-key"]) == 1
    captured = capsys.readouterr()
    assert "FATAL: AUTH_KEY" in captured.err
    assert DEFAULT_API_KEY_HEADER in captured.err


def test_check_auth_key_passes_when_set(
    monkeypatch: MonkeyPatch,
) -> None:
    """``check-auth-key`` exits 0 when AUTH_KEY is present.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setenv("AUTH_KEY", "unit-test-secret")
    assert main(["check-auth-key"]) == 0


def test_cli_merge_missing_file_fails(tmp_path: Path) -> None:
    """Merge must fail closed when app.yaml is absent.

    Args:
        tmp_path: Pytest temporary directory.
    """
    missing = tmp_path / "missing.yaml"
    assert main(["merge", str(missing)]) == 1


def _run_entrypoint(
    *,
    config_dir: Path,
    defaults_dir: Path | None,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run the Railway entrypoint with start skipped.

    Args:
        config_dir: Volume-style config directory.
        defaults_dir: Image defaults directory, or None to omit.
        env: Extra environment variables.

    Returns:
        Completed process.
    """
    run_env = os.environ.copy()
    run_env.update(env)
    run_env["MCPX_CONFIG_DIR"] = str(config_dir)
    run_env["MCPX_SKIP_START"] = "1"
    if defaults_dir is not None:
        run_env["MCPX_DEFAULTS_DIR"] = str(defaults_dir)
    else:
        run_env["MCPX_DEFAULTS_DIR"] = str(config_dir / "no-such-defaults")
    return subprocess.run(
        ["sh", str(ENTRYPOINT)],
        check=False,
        capture_output=True,
        text=True,
        env=run_env,
    )


def test_entrypoint_fails_closed_without_auth_key(
    tmp_path: Path,
) -> None:
    """Refuse to start when AUTH_KEY is missing so /mcp cannot stay public.

    Args:
        tmp_path: Pytest temporary directory.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    result = _run_entrypoint(
        config_dir=config_dir,
        defaults_dir=None,
        env={"AUTH_KEY": ""},
    )
    assert result.returncode == 1
    assert "FATAL: AUTH_KEY" in result.stderr


def test_entrypoint_merges_volume_app_yaml_and_adds_missing_mcp_servers(
    tmp_path: Path,
) -> None:
    """Existing volume servers stay; missing default servers are inserted.

    Args:
        tmp_path: Pytest temporary directory.
    """
    config_dir = tmp_path / "volume"
    defaults_dir = tmp_path / "defaults"
    config_dir.mkdir()
    defaults_dir.mkdir()
    (config_dir / "app.yaml").write_text(EXISTING_VOLUME_APP_YAML, encoding="utf-8")
    (config_dir / "mcp.json").write_text(USER_EDITED_MCP_JSON, encoding="utf-8")
    (defaults_dir / "app.yaml").write_text(
        "auth:\n  enabled: true\n  header: x-lunar-api-key\n",
        encoding="utf-8",
    )
    (defaults_dir / "mcp.json").write_text(
        '{"mcpServers":{"time":{"command":"uvx"}}}\n',
        encoding="utf-8",
    )

    result = _run_entrypoint(
        config_dir=config_dir,
        defaults_dir=defaults_dir,
        env={"AUTH_KEY": "integration-secret"},
    )
    assert result.returncode == 0, result.stderr
    servers = json.loads((config_dir / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert servers["custom"] == {"type": "stdio", "command": "echo"}
    assert servers["time"] == {"command": "uvx"}
    assert "added time" in result.stdout
    volume_app = (config_dir / "app.yaml").read_text(encoding="utf-8")
    assert "enabled: true" in volume_app
    assert "header: x-lunar-api-key" in volume_app
    assert 'base: "allow"' in volume_app
    assert "toolGroups: []" in volume_app


def test_entrypoint_seeds_defaults_only_when_missing(
    tmp_path: Path,
) -> None:
    """Empty volume gets image defaults; AUTH_KEY still required.

    Args:
        tmp_path: Pytest temporary directory.
    """
    config_dir = tmp_path / "empty-volume"
    defaults_dir = tmp_path / "defaults"
    config_dir.mkdir()
    defaults_dir.mkdir()
    (defaults_dir / "app.yaml").write_text(
        "auth:\n  enabled: true\n  header: x-lunar-api-key\npermissions:\n  base: allow\n",
        encoding="utf-8",
    )
    (defaults_dir / "mcp.json").write_text(USER_EDITED_MCP_JSON, encoding="utf-8")

    result = _run_entrypoint(
        config_dir=config_dir,
        defaults_dir=defaults_dir,
        env={"AUTH_KEY": "seed-secret"},
    )
    assert result.returncode == 0, result.stderr
    assert (config_dir / "mcp.json").read_text(encoding="utf-8") == USER_EDITED_MCP_JSON
    assert "enabled: true" in (config_dir / "app.yaml").read_text(encoding="utf-8")


@pytest.mark.skipif(not ENSURE_SCRIPT.is_file(), reason="ensure_app_auth.py missing")
def test_cli_script_is_runnable(tmp_path: Path) -> None:
    """The copied-into-image script must run under python3.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "app.yaml"
    path.write_text("auth:\n  enabled: false\n", encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(ENSURE_SCRIPT), "merge", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "enabled: true" in path.read_text(encoding="utf-8")
