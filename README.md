# lunar-mcpx-config

Konfigurační a deploy repozitář pro **Lunar MCPX** (MCP gateway / agregátor) na Railway.

Cílová služba je už vytvořená:

| | |
| --- | --- |
| Projekt | `perfect-eagerness` (`87d54f99-b2b7-4f56-b2cd-f5abb6c825d6`) |
| Služba | **`lunar-mcpx`** (`9e4f6198-575b-427c-8271-668fb5ff136d`) |
| Prostředí | `production` (`547660e2-b568-4707-98a9-666ee1cbd80b`) |
| Region | `europe-west4-drams3a` |
| Git zdroj | `mkrejp/lunar-mcpx-config` @ `main` |

Dashboard: [Railway projekt](https://railway.com/project/87d54f99-b2b7-4f56-b2cd-f5abb6c825d6/service/9e4f6198-575b-427c-8271-668fb5ff136d?environmentId=547660e2-b568-4707-98a9-666ee1cbd80b)

Upstream: [TheLunarCompany/lunar `mcpx/`](https://github.com/TheLunarCompany/lunar/tree/main/mcpx), dokumentace [docs.lunar.dev](https://docs.lunar.dev/mcpx/get_started) (přesměrování na Boomi MCP Gateway).

## Co je v tomto setupu

- **Image:** oficiální all-in-one `us-central1-docker.pkg.dev/prj-common-442813/mcpx/mcpx:0.5.8` (nejnovější publikovaný tag v Artifact Registry v době sestavení; tag `latest` aktuálně ukazuje na starší `0.4.55`).
- **Služby:** jedna Railway služba `lunar-mcpx` (server + Control Plane UI v jednom kontejneru). Tenký `Dockerfile` jen proto, aby se do image zkopírovaly výchozí `mcp.json` / `app.yaml` a při startu se nahrály na volume.
- **Veřejný port:** **9000** — MCP endpoint (`/mcp`, legacy `/sse`) a healthcheck (`/healthcheck`).
- **UI port:** **5173** — Control Plane; na Railway ho zveřejníte **druhou** doménou (jedna doména = jeden cílový port).
- **Metrics:** **3000** `/metrics` (Prometheus) — nechte privátní.

## Přesné nastavení služby `lunar-mcpx`

Nastavte toto v dashboardu u **lunar-mcpx** → Settings / Variables / Volumes. `railway.json` ty samé deploy hodnoty zopakuje při buildu z Gitu (Config as Code je u nových služeb deprecated; pro jistotu nastavte i dashboard).

### Settings → Source

Už je napojené: GitHub `mkrejp/lunar-mcpx-config`, branch `main`. Po mergi do `main` Railway znovu sestaví.

### Settings → Build

| Pole | Hodnota |
| --- | --- |
| Builder | **Dockerfile** |
| Dockerfile path | `Dockerfile` |
| Watch paths | nechte výchozí |

### Settings → Deploy

| Pole | Hodnota |
| --- | --- |
| Custom start command | **prázdné** (použije se `ENTRYPOINT` + `CMD` image) |
| Healthcheck path | `/healthcheck` |
| Healthcheck timeout | `300` sekund |
| Restart policy | **On Failure** |
| Restart policy max retries | `10` |
| Replicas | `1` v `europe-west4-drams3a` |
| Overlap / zero-downtime | u služby s volume Railway stejně nenasadí dva kontejnery najednou |

### Settings → Networking

| Akce | Hodnota |
| --- | --- |
| **Generate Domain** (veřejná, primární) | target port **`9000`** — toto je veřejný MCP endpoint |
| Druhá Railway domain | target port **`5173`** — Control Plane UI |
| Metrics `:3000` | **žádná** veřejná doména |
| TCP Proxy | ne |
| Private DNS | `lunar-mcpx.railway.internal` (případně `lunar-mcpx-config.railway.internal` podle Settings → Networking) |

Klienti z internetu: `https://<doména-9000>/mcp`.  
Prohlížeč UI: `https://<doména-5173>/`.  
Ostatní služby ve stejném prostředí: `http://lunar-mcpx.railway.internal:9000`.

### Volume

Vytvořte **jeden** volume (canvas → Add volume / ⌘K), region **`europe-west4-drams3a`**, připojte k `lunar-mcpx`:

| | |
| --- | --- |
| Název (doporučený) | `lunar-mcpx-data` |
| Mount path | **`/lunar/packages/mcpx-server/config`** |
| Velikost | 1 GB stačí (audit logy + `mcp.json` + `app.yaml` + volitelně `memory.json`) |

Na tomto mountu leží:

- `mcp.json`, `app.yaml` — runtime konfigurace (UI je může přepsat)
- `audit-logs/` — audit (env `AUDIT_LOG_DIR`)
- volitelně `memory.json`, pokud přidáte MCP server Memory

Bez volume se změny z Control Plane i audit logy ztratí při každém redeploy.

### Variables (nastavit na `lunar-mcpx`)

Zkopírujte minimálně tento blok. Tajemství (`AUTH_KEY`) doplňte ručně, ne commitujte.

**Povinné pro Railway:**

```
PORT=9000
MCPX_PORT=9000
MCPX_SERVER_PORT=9000
MCPX_SERVER_URL=http://127.0.0.1:9000
UI_PORT=5173
UI_URL=http://127.0.0.1:5173
RAILWAY_RUN_UID=0
ENABLE_STDIO_MCP_SERVERS=true
DIND_ENABLED=false
APP_CONFIG_PATH=/lunar/packages/mcpx-server/config/app.yaml
SERVERS_CONFIG_PATH=/lunar/packages/mcpx-server/config/mcp.json
AUDIT_LOG_DIR=/lunar/packages/mcpx-server/config/audit-logs
LUNAR_TELEMETRY=false
ENABLE_METRICS=true
SERVE_METRICS_PORT=3000
LOG_LEVEL=info
ENABLE_CONTROL_PLANE_REST=true
ENABLE_CONTROL_PLANE_STREAMING=true
VITE_MCPX_SERVER_PORT=443
AUTH_KEY=<dlouhý náhodný secret, viz Autentizace>
```

`AUTH_KEY` nastavte **před** merge/redeploy. Bez něj kontejner skončí (fail-closed) a služba nepoběží.

**Po vygenerování veřejné domény na port 9000** (reference variables v dashboardu):

```
VITE_MCPX_SERVER_URL=https://${{RAILWAY_PUBLIC_DOMAIN}}
VITE_WS_URL=wss://${{RAILWAY_PUBLIC_DOMAIN}}
OAUTH_CALLBACK_BASE_URL=https://${{RAILWAY_PUBLIC_DOMAIN}}
CORS_ORIGINS=https://${{RAILWAY_PUBLIC_DOMAIN}}
```

Až budete mít i UI doménu na 5173, **přidejte ji** do `CORS_ORIGINS` (čárkou oddělené origin URL bez cesty). Bez toho Control Plane z prohlížeče neuvidí API.

Kompletní seznam včetně volitelných proměnných je v [`.env.example`](.env.example).

## Autentizace

Veřejný endpoint `/mcp` musí posílat API klíč. Ověřeno proti upstream MCPX **0.5.8** (`mcpx/packages/mcpx-server`):

| Co | Hodnota | Zdroj |
| --- | --- | --- |
| Env var (shared secret) | **`AUTH_KEY`** | `src/env.ts` (`AUTH_KEY: z.string().optional()`), `.env.example` |
| Zapnutí v configu | **`auth.enabled: true`** v `app.yaml` | `shared-model` `authSchema`; Helm/Boomi docs |
| Header, který klienti posílají | **`x-lunar-api-key`** | `src/server/auth.ts` `DEFAULT_API_KEY_HEADER`; IT test `auth.it.test.ts` |
| Override názvu headeru | `auth.header` v `app.yaml` | stejný guard; default se nechá `x-lunar-api-key` |

Header **`x-lunar-auth-key` se v kódu 0.5.8 nepoužívá** (starší rozpor v docs). `/healthcheck` zůstává bez klíče (Railway healthcheck).

Bez `AUTH_KEY` by upstream `buildApiKeyGuard` auth **vypnul** (fail-open, jen warning). Tento repo proto **odmítne start** a do existujícího volume `app.yaml` při každém startu **sloučí** `auth.enabled: true` — `mcp.json` a ostatní klíče (`permissions`, `toolGroups`) se nepřepisují.

### 1. Vygenerovat silný klíč

```bash
openssl rand -hex 32
# nebo
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Výsledek nikam do Gitu nedávejte.

### 2. Nastavit `AUTH_KEY` na službě `lunar-mcpx`

Dashboard: **lunar-mcpx → Variables → New Variable**

| | |
| --- | --- |
| Name | `AUTH_KEY` |
| Value | výstup z příkazu výše |

CLI:

```bash
railway variable set AUTH_KEY='<vygenerovaný-klíč>' \
  --service lunar-mcpx \
  --environment production \
  --project 87d54f99-b2b7-4f56-b2cd-f5abb6c825d6
```

Pak redeploy (merge do `main` ho spustí sám). Hodnotu si uložte; Railway ji později v OAuth/MCP nevypíše.

### 3. MCP klienti — header `x-lunar-api-key`

**Cursor / Claude Desktop** (`~/.cursor/mcp.json` nebo ekvivalent):

```json
{
  "mcpServers": {
    "mcpx": {
      "url": "https://lunar-mcpx-production.up.railway.app/mcp",
      "headers": {
        "x-lunar-api-key": "<AUTH_KEY>"
      }
    }
  }
}
```

**Claude Code:**

```bash
claude mcp add --transport http mcpx \
  "https://lunar-mcpx-production.up.railway.app/mcp" \
  --header "x-lunar-api-key: <AUTH_KEY>" \
  --scope user
```

**curl** (initialize; bez headeru očekávejte `401 Unauthorized: API key required`):

```bash
curl -sS -X POST "https://lunar-mcpx-production.up.railway.app/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "x-lunar-api-key: $AUTH_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

Špatný klíč → `403 Forbidden: Invalid API key`. Control Plane REST (`/config`, `/catalog`, …) používá stejný guard a stejný header. CORS v 0.5.8 `x-lunar-api-key` v `allowedHeaders` nemá — prohlížečové volání z jiné origin může padnout na preflight; Cursor/Claude/curl to neřeší.

## Deploy

### Dashboard (už napojený Git)

1. **Nejdřív** nastavte `AUTH_KEY` na `lunar-mcpx` (viz [Autentizace](#autentizace)). Bez něj nový kontejner skončí.
2. Mergněte tento branch do `main` (služba sleduje `main`).
3. Volume, domény a ostatní Variables podle tabulky výše.
4. Počkejte na SUCCESS. Healthcheck musí vrátit 2xx na `/healthcheck` na portu **9000** (`PORT=9000`) — healthcheck klíč neposílá.
5. Ověřte podle sekce [Ověření](#ověření) **s** headerem `x-lunar-api-key`.

### CLI

```bash
# jednorázově: Railway CLI, přihlášení, link na existující projekt
railway login
railway link --project 87d54f99-b2b7-4f56-b2cd-f5abb6c825d6

# deploy aktuálního adresáře do lunar-mcpx
railway up --service lunar-mcpx --environment production --detach -m "mcpx config"

# stav
railway deployment list --service lunar-mcpx --environment production --json
railway logs --service lunar-mcpx --lines 200
railway domain list --service lunar-mcpx --json
```

Nový projekt **nevytvářejte** — služba `lunar-mcpx` už existuje.

`railway.json` nastaví builder Dockerfile, healthcheck `/healthcheck` (timeout 300 s) a restart `ON_FAILURE` / 10. Pokud Railway u této nové služby Config as Code ignoruje, nastavte totéž ručně v Settings (viz tabulka).

## Přidání MCP serverů

Soubor [`config/mcp.json`](config/mcp.json) se při **prvním** startu zkopíruje na volume, pokud tam ještě není. Existující `mcp.json` se **nikdy** nepřepisuje (UI / ruční edity zůstanou). `app.yaml` se seeduje stejně, ale **auth blok se sloučí při každém startu** (`auth.enabled: true`), aby se zapnutí auth projevilo i na volume z PR #1. Další změny:

1. **Control Plane UI** (doména na portu 5173) → Add Server, nebo
2. úprava `mcp.json` v Gitu + smazání souboru na volume (jinak seed nepřepíše existující soubor), nebo
3. `railway volume files` / Volume browser.

Ukázkový server **`time`** (uvx / stdio) je neškodný a **nepotřebuje Docker**. Image obsahuje `uv` a Node, takže `uvx` / `npx` stdio servery na Railway můžou běžet bez privileged režimu.

Vzdálené HTTP servery (doporučené na Railway):

```json
{
  "mcpServers": {
    "fastmcp-aggregator": {
      "type": "streamable-http",
      "url": "http://fastmcp-aggregator.railway.internal:8080/mcp"
    }
  }
}
```

Hotový příklad je v [`config/mcp.remote.example.json`](config/mcp.remote.example.json). `FastMCP-aggregator` už v tomhle Railway projektu běží na privátním DNS a portu 8080.

Servery s `"command": "docker"` **na Railway nefungují** (není privileged / Docker-in-Docker). Nahraďte je vzdáleným HTTP MCP, nebo stdio přes `uvx`/`npx`.

ACL, tool groups a auth: [`config/app.yaml`](config/app.yaml). Dokumentace: [mcp.json](https://help.boomi.com/docs/Atomsphere/AIGateway/MCPGateway/config/mcp.json), [app.yaml](https://help.boomi.com/docs/Atomsphere/AIGateway/MCPGateway/config/app.yaml), [API key auth](https://help.boomi.com/docs/Atomsphere/AIGateway/MCPGateway/features/api_key_auth).

## Update verze MCPX

1. Podívejte se na tagy:  
   `https://us-central1-docker.pkg.dev/v2/prj-common-442813/mcpx/mcpx/tags/list`
2. Změňte `ARG MCPX_VERSION=…` v [`Dockerfile`](Dockerfile) a soubor [`MCPX_VERSION`](MCPX_VERSION).
3. Commit, merge do `main`, nechte Railway rebuildnout `lunar-mcpx`.
4. Volume s configem se zachová; image se vymění.

Oddělené image (kdybyste později službu rozdělili): `…/mcpx/mcpx-server:0.5.8` a `…/mcpx/mcpx-ui:0.5.8`.

## Ověření

Healthcheck (veřejná MCP doména, port 9000):

```bash
curl -sS "https://<MCP_DOMAIN>/healthcheck"
# očekává se JSON: {"status":"OK"}
```

Control Plane: otevřete `https://<UI_DOMAIN>/` a zkontrolujte, že je vidět server `time` (první spawn `uvx` může trvat minutu).

MCP klient musí posílat **`x-lunar-api-key`** (viz [Autentizace](#autentizace)). Cursor `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "mcpx": {
      "url": "https://<MCP_DOMAIN>/mcp",
      "headers": {
        "x-lunar-api-key": "<AUTH_KEY>"
      }
    }
  }
}
```

Claude Code:

```bash
claude mcp add --transport http mcpx "https://<MCP_DOMAIN>/mcp" \
  --header "x-lunar-api-key: <AUTH_KEY>" --scope user
```

Legacy SSE: `https://<MCP_DOMAIN>/sse`.  
Metrics (privátní): `http://lunar-mcpx.railway.internal:3000/metrics`.

## Limity Railway a workaroundy

| Limit | Dopad | Workaround |
| --- | --- | --- |
| Jedna veřejná HTTP doména = jeden cílový port | Image poslouchá na 9000, 5173 a 3000 | Primární doména → **9000** (MCP). Druhá doména → **5173** (UI). Metrics nechat na private network. |
| Žádný privileged / Docker-in-Docker | `command: docker` stdio servery nespustí | Vzdálené `streamable-http` / `sse`, nebo stdio `uvx`/`npx` (image je má nainstalované). |
| Volume není v buildu ani pre-deploy | Seed configu musí být ve start command | `docker/railway-entrypoint.sh` zkopíruje `mcp.json` / `app.yaml`, jen když na volume chybí; `auth.enabled` se do existujícího `app.yaml` sloučí při každém startu. |
| Volume + zero-downtime | Krátký výpadek při redeploy | Očekávané; healthcheck jen přepíná traffic až po 2xx. |
| Config as Code (`railway.json`) deprecated | Nové služby ho od 2026-12-01 nemusí číst | Stejné hodnoty nastavte v dashboardu; `.railway/railway.ts` je volitelný IaC, **nespravujte** službu oběma modely naráz. |
| `PORT` vs více portů | Healthcheck jde na `$PORT` | `PORT=9000` musí sedět s `MCPX_PORT` a target portem MCP domény. |
| Non-root user + volume | Mount je `root` | `RAILWAY_RUN_UID=0` + `chown lunar` ve start skriptu. |

## Soukromá síť

V tomhle prostředí už běží `FastMCP-aggregator` a `MCP-inspectoriat`. MCPX se na ně dostane přes `http://<service>.railway.internal:<port>` bez veřejné expozice. Prohlížeč na private DNS nedosáhne — UI musí jít na veřejnou MCP doménu.

## Otevřené otázky

- Tag `latest` v registry je `0.4.55`, zatímco nejnovější otagovaná verze je `0.5.8`. Pinujeme `0.5.8`.
- Schéma `app.yaml`: Helm používá `permissions.base: allow`, novější OSS kód `permissions.default.block: []`. Soubor obsahuje obojí; pokud 0.5.8 jednu variantu odmítne, nechte tu, kterou image přijme (chybějící app.yaml padá na built-in default).
- Privátní IPv6: nové Railway environmenty resolvují i IPv6. Pokud Node/uvx k `*.railway.internal` nepřipojí, zkuste explicitní port a HTTP (ne HTTPS).
- Jestli tato nová služba ještě čte `railway.json` (Config as Code cutoff 2026-12-01). Proto je checklist dashboardu autoritativní.
- Stdio `uvx` na Railway: první start stahuje PyPI; pokud volume/home není zapisovatelný, spawn selže — logy `lunar` / `UV_CACHE_DIR`.
- Control Plane websocket mezi UI doménou (5173) a MCP doménou (9000): `VITE_WS_URL` musí být `wss://<MCP_DOMAIN>` a CORS musí obsahovat UI origin.

## Licence / původ

MCPX je MIT, upstream Lunar.dev / Boomi. Tento repo obsahuje jen deploy konfiguraci.
