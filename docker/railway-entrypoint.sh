#!/bin/sh
# Seed git-tracked defaults onto the Railway volume, then start upstream MCPX.
# Upstream ENTRYPOINT still wraps this command (privileged/DinD probe).
set -eu

CONFIG_DIR="${MCPX_CONFIG_DIR:-/lunar/packages/mcpx-server/config}"
DEFAULTS_DIR="${MCPX_DEFAULTS_DIR:-/defaults/config}"

mkdir -p "${CONFIG_DIR}/audit-logs"

if [ -d "${DEFAULTS_DIR}" ]; then
  for name in mcp.json app.yaml; do
    if [ ! -e "${CONFIG_DIR}/${name}" ] && [ -f "${DEFAULTS_DIR}/${name}" ]; then
      echo "RAILWAY: seeding ${CONFIG_DIR}/${name} from image defaults"
      cp "${DEFAULTS_DIR}/${name}" "${CONFIG_DIR}/${name}"
    fi
  done
fi

# Volume is mounted as root; MCPX then drops to user `lunar` (uid 1002).
if id lunar >/dev/null 2>&1; then
  chown -R lunar:lunar "${CONFIG_DIR}" 2>/dev/null || true
  chmod -R ug+rwX "${CONFIG_DIR}" 2>/dev/null || true
fi

export APP_CONFIG_PATH="${APP_CONFIG_PATH:-${CONFIG_DIR}/app.yaml}"
export SERVERS_CONFIG_PATH="${SERVERS_CONFIG_PATH:-${CONFIG_DIR}/mcp.json}"
export AUDIT_LOG_DIR="${AUDIT_LOG_DIR:-${CONFIG_DIR}/audit-logs}"

exec /usr/local/bin/startup.sh
