# Thin wrapper around the official Lunar MCPX all-in-one image.
# Pins the published tag and bakes git-tracked config defaults.
# Official image already has python3 (apk python3~3.12) for uvx; the
# entrypoint uses it to merge auth onto the persistent volume.
#
# Upstream image (server :9000, UI :5173, metrics :3000):
#   us-central1-docker.pkg.dev/prj-common-442813/mcpx/mcpx:<version>
#
# Change MCPX_VERSION (or the tag below) to update. See README.

ARG MCPX_VERSION=0.5.8
FROM us-central1-docker.pkg.dev/prj-common-442813/mcpx/mcpx:${MCPX_VERSION}

USER root

COPY config/mcp.json /defaults/config/mcp.json
COPY config/mcp.prune.json /defaults/config/mcp.prune.json
COPY config/app.yaml /defaults/config/app.yaml
COPY docker/railway-entrypoint.sh /usr/local/bin/railway-entrypoint.sh
COPY docker/ensure_app_auth.py /usr/local/bin/ensure_app_auth.py
COPY docker/merge_mcp_servers.py /usr/local/bin/merge_mcp_servers.py
COPY docker/inject_env_placeholders.py /usr/local/bin/inject_env_placeholders.py

RUN chmod +x /usr/local/bin/railway-entrypoint.sh /usr/local/bin/ensure_app_auth.py /usr/local/bin/merge_mcp_servers.py /usr/local/bin/inject_env_placeholders.py \
    && mkdir -p /lunar/packages/mcpx-server/config \
    && chown -R lunar:lunar /defaults /lunar/packages/mcpx-server/config

# Keep upstream ENTRYPOINT (privileged / Docker-in-Docker probe).
CMD ["/usr/local/bin/railway-entrypoint.sh"]
