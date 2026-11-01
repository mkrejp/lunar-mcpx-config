# Railway IaC for lunar-mcpx

`.railway/railway.ts` describes the existing service `lunar-mcpx` (GitHub source, healthcheck, volume, env).

Railway Config as Code (`/railway.json`) is deprecated for new services (hard cutoff 2026-12-01). Prefer this IaC file **or** dashboard settings from the root README — not both at once for the same service.

Do not run `railway config apply` from an agent session unless a human approved the exact plan.
