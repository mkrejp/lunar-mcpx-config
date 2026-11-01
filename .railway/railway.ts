import {
  defineRailway,
  github,
  project,
  service,
  volume,
} from "railway/iac";

/**
 * Desired Railway state for the existing `lunar-mcpx` service.
 *
 * Do not `railway config apply` this file unless you intend IaC to own the
 * service. This GitHub repo is already connected to `lunar-mcpx`; deploy
 * settings also live in `/railway.json`. Railway does not allow both models
 * to manage the same service at once.
 *
 * Region matches the live service (europe-west4-drams3a).
 */
export default defineRailway(() => {
  const data = volume("lunar-mcpx-data", {
    region: "europe-west4",
    sizeMB: 1024,
  });

  const mcpx = service("lunar-mcpx", {
    source: github("mkrejp/lunar-mcpx-config", { branch: "main" }),
    healthcheck: "/healthcheck",
    healthcheckTimeout: 300,
    replicas: {
      "europe-west4-drams3a": 1,
    },
    volumeMounts: {
      "/lunar/packages/mcpx-server/config": data,
    },
    env: {
      PORT: "9000",
      MCPX_PORT: "9000",
      MCPX_SERVER_PORT: "9000",
      MCPX_SERVER_URL: "http://127.0.0.1:9000",
      UI_PORT: "5173",
      UI_URL: "http://127.0.0.1:5173",
      SERVE_METRICS_PORT: "3000",
      ENABLE_METRICS: "true",
      LOG_LEVEL: "info",
      ENABLE_STDIO_MCP_SERVERS: "true",
      DIND_ENABLED: "false",
      ENABLE_CONTROL_PLANE_REST: "true",
      ENABLE_CONTROL_PLANE_STREAMING: "true",
      LUNAR_TELEMETRY: "false",
      RAILWAY_RUN_UID: "0",
      APP_CONFIG_PATH: "/lunar/packages/mcpx-server/config/app.yaml",
      SERVERS_CONFIG_PATH: "/lunar/packages/mcpx-server/config/mcp.json",
      AUDIT_LOG_DIR: "/lunar/packages/mcpx-server/config/audit-logs",
      CORS_ORIGINS: "https://${{RAILWAY_PUBLIC_DOMAIN}}",
      VITE_MCPX_SERVER_URL: "https://${{RAILWAY_PUBLIC_DOMAIN}}",
      VITE_MCPX_SERVER_PORT: "443",
      VITE_WS_URL: "wss://${{RAILWAY_PUBLIC_DOMAIN}}",
      OAUTH_CALLBACK_BASE_URL: "https://${{RAILWAY_PUBLIC_DOMAIN}}",
    },
  });

  return project("perfect-eagerness", {
    resources: [mcpx, data],
  });
});
