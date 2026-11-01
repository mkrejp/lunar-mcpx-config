#!/bin/sh
# Seed git-tracked defaults onto the Railway volume, force-enable MCPX auth
# on the existing volume app.yaml (without touching mcp.json), then start.
# Upstream ENTRYPOINT still wraps this command (privileged/DinD probe).
set -eu

CONFIG_DIR="${MCPX_CONFIG_DIR:-/lunar/packages/mcpx-server/config}"
DEFAULTS_DIR="${MCPX_DEFAULTS_DIR:-/defaults/config}"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENSURE_APP_AUTH="${ENSURE_APP_AUTH:-${SCRIPT_DIR}/ensure_app_auth.py}"
ENSURE_MCP_SERVERS="${ENSURE_MCP_SERVERS:-${SCRIPT_DIR}/ensure_mcp_servers.py}"

mkdir -p "${CONFIG_DIR}/audit-logs"

if [ -d "${DEFAULTS_DIR}" ]; then
  # mcp.json: seed once. Never overwrite UI / user edits on the volume.
  if [ ! -e "${CONFIG_DIR}/mcp.json" ] && [ -f "${DEFAULTS_DIR}/mcp.json" ]; then
    echo "RAILWAY: seeding ${CONFIG_DIR}/mcp.json from image defaults"
    cp "${DEFAULTS_DIR}/mcp.json" "${CONFIG_DIR}/mcp.json"
  fi
  # app.yaml: seed only when missing. Auth is merged below on every start
  # so an existing volume that still has auth.enabled:false actually flips.
  if [ ! -e "${CONFIG_DIR}/app.yaml" ] && [ -f "${DEFAULTS_DIR}/app.yaml" ]; then
    echo "RAILWAY: seeding ${CONFIG_DIR}/app.yaml from image defaults"
    cp "${DEFAULTS_DIR}/app.yaml" "${CONFIG_DIR}/app.yaml"
  fi
fi

if [ ! -f "${CONFIG_DIR}/app.yaml" ]; then
  echo "RAILWAY: writing minimal auth-enabled app.yaml (no image default found)"
  cat > "${CONFIG_DIR}/app.yaml" <<'EOF'
auth:
  enabled: true
  header: x-lunar-api-key
EOF
fi

# Add git-tracked MCP servers that are missing on the volume. Never deletes
# or overwrites an existing server name (keeps UI / user edits).
if [ -f "${CONFIG_DIR}/mcp.json" ]; then
  python3 "${ENSURE_MCP_SERVERS}" "${CONFIG_DIR}/mcp.json" \
    --defaults "${DEFAULTS_DIR}/mcp.json"
fi

# Merge auth.enabled=true into the volume file. Does not rewrite mcp.json
# or other app.yaml keys (permissions, toolGroups, toolExtensions).
python3 "${ENSURE_APP_AUTH}" merge "${CONFIG_DIR}/app.yaml"

# Fail closed. Upstream buildApiKeyGuard is fail-open when AUTH_KEY is empty.
python3 "${ENSURE_APP_AUTH}" check-auth-key

# Volume is mounted as root; MCPX then drops to user `lunar` (uid 1002).
if id lunar >/dev/null 2>&1; then
  chown -R lunar:lunar "${CONFIG_DIR}" 2>/dev/null || true
  chmod -R ug+rwX "${CONFIG_DIR}" 2>/dev/null || true
fi

export APP_CONFIG_PATH="${APP_CONFIG_PATH:-${CONFIG_DIR}/app.yaml}"
export SERVERS_CONFIG_PATH="${SERVERS_CONFIG_PATH:-${CONFIG_DIR}/mcp.json}"
export AUDIT_LOG_DIR="${AUDIT_LOG_DIR:-${CONFIG_DIR}/audit-logs}"

if [ "${MCPX_SKIP_START:-}" = "1" ]; then
  echo "RAILWAY: MCPX_SKIP_START=1, not execing startup.sh"
  exit 0
fi

exec /usr/local/bin/startup.sh
