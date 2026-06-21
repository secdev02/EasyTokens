# EasyTokens

A device-code phishing server for adversary emulation. Captures Microsoft 365 OAuth tokens via the [Device Authorization Grant](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-device-code) flow. Inspired by [GraphSpy](https://github.com/RedByte1337/GraphSpy).

> **Warning — Authorized Use Only.** This tool is intended for penetration testers and red teamers operating under explicit written authorization. Misuse may violate computer fraud laws.

---

## How It Works

1. Operator creates a **device code campaign** via the operator UI.
2. A victim-facing enrollment page (Dunder Mifflin themed) displays the user code and prompts the target to authenticate at `microsoft.com/devicelogin`.
3. A background poller detects when the target completes authentication and stores the captured access/refresh token in SQLite.
4. The victim's browser is redirected to a post-auth search page.
5. The operator can search the victim's OneDrive and email via Microsoft Graph using the captured token.

---

## Architecture

Python backend (one port per campaign) + nginx front-end + SQLite persistence.

```
main_server.py          ← unified entry point (run this)
db.py                   ← SQLite persistence layer
html_enroll.py          ← victim enrollment page builder
html_search.py          ← victim post-auth search page builder
css_shared.py           ← shared CSS for operator UI
nginx_helper.py         ← auto-generates and reloads nginx reverse-proxy config
nginx.conf              ← base nginx config (includes /etc/nginx/conf.d/*.conf)
```

### Routes

| Method | Path | Audience | Description |
|--------|------|----------|-------------|
| `GET` | `/` | Victim | Device-code enrollment page (Dunder Mifflin theme) |
| `POST` | `/poll` | Victim (JS) | Polls MS token endpoint; stores token on success |
| `GET` | `/search?s=<id>` | Victim | Post-auth OneDrive/email search page |
| `GET` | `/app` | Operator | Dashboard — stats + recent captures |
| `GET` | `/app/device-codes` | Operator | All campaigns with live poll status |
| `POST` | `/app/device-codes/new` | Operator | Create a new device code campaign |
| `GET` | `/app/tokens` | Operator | All captured tokens |
| `GET` | `/app/search?id=<id>` | Operator | OneDrive + email search for a specific token |
| `POST` | `/webhook` | Relay node | Ingest a token from an authenticated relay node |
| `POST` | `/relay/checkin` | Relay node | Register a relay node; returns `node_id` |

---

## Nginx — Domain Campaigns

When a campaign is created with a **domain** set, `nginx_helper.py` automatically writes a per-domain server block to `NGINX_CONF` (`/etc/nginx/conf.d/easytokens.conf` by default) and reloads nginx. Victim traffic arriving on port 80 for that domain is proxied to the correct Python server instance.

- Campaigns **without** a domain are served directly on the Python port (default 3000).
- Campaigns **with** a domain are served through nginx on port 80.
- The base `nginx.conf` drops any request whose `Host` header does not match a known campaign (`return 444`), preventing accidental exposure of the Python backend.
- Set `NGINX_CONF=''` or `NGINX_RELOAD_CMD=''` to disable automatic nginx management.

---

## Quick Start (Docker)

```bash
docker compose up --build
```

Ports exposed by Docker:

| Port | Purpose |
|------|---------|
| `80` | nginx — domain-based victim traffic |
| `3000` | Python — operator UI + direct victim access |

- Victim page (direct): `http://localhost:3000/`
- Operator UI: `http://localhost:3000/app`
- Domain campaigns: `http://<campaign-domain>/` (routed through nginx on port 80)

Captured tokens and logs are persisted to Docker volumes:

| Volume | Path in container | Purpose |
|--------|------------------|---------|
| `easytokens-data` | `/data/easytokens.db` | SQLite database |
| `./logs` | `/logs/` | Per-request log files |

---

## Manual Setup

**Requirements:** Python 3.12+, no third-party packages.

```bash
python main_server.py
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3000` | Listening port for the Python server |
| `PORT_MAX` | `3010` | Upper bound of port range exposed by Docker |
| `DB_PATH` | `/data/easytokens.db` | SQLite database path |
| `LOG_DIR` | `/logs` | Per-request log directory |
| `NGINX_CONF` | `/etc/nginx/conf.d/easytokens.conf` | Path nginx_helper writes generated config to; set to `''` to disable |
| `NGINX_RELOAD_CMD` | `nginx -s reload` | Shell command to reload nginx after config changes; set to `''` to disable |
| `RELAY_SECRET` | *(unset)* | Shared secret for relay node authentication. Generate with `openssl rand -hex 32`. Must match `RELAY_SECRET` in `php-relay/.env`. Leave unset to disable relay support. |

---

## PHP Relay Node

The `php-relay/` directory contains a standalone Apache/PHP container that acts as a distributed victim-facing node. It serves the same device-code enrollment page as the main server, polls Microsoft directly, and forwards captured tokens to the main panel via `POST /webhook`.

### How It Works

1. On startup, `checkin.php` POSTs to `POST /relay/checkin` on the main panel, authenticating with `RELAY_SECRET`. The panel registers the node and returns a `node_id`.
2. Victims browse to the relay's enrollment page (`index.php`), which initiates a fresh device-code flow.
3. Browser-side JS polls `poll.php`. When a token is captured, `poll.php` forwards it to `POST /webhook` on the main panel, tagged with the `node_id`.

### Relay Environment Variables

Configure in `php-relay/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAIN_SERVER_URL` | `http://easytokens:3000` | URL of the main panel reachable from inside the relay container |
| `RELAY_SECRET` | *(required)* | Must match `RELAY_SECRET` on the main panel |
| `RELAY_PORT` | `8082` | Host port to expose the relay on |
| `RELAY_LABEL` | hostname | Human-readable name shown in the panel for this node |
| `CHECKIN_RETRIES` | `10` | Check-in retry attempts before giving up |
| `CHECKIN_DELAY` | `5` | Seconds between check-in retries |
| `NODE_ID_FILE` | `/tmp/relay_node_id` | Path where the node_id is cached after check-in |

### Quick Start

**Both containers simultaneously (recommended):**

```bash
# from EasyTokens/
docker compose -f docker-compose.yml -f php-relay/docker-compose.yml up --build
```

Running both with a single `-f` merge puts them on the same Docker network, so `MAIN_SERVER_URL=http://easytokens:3000` resolves correctly.

**Access:**

| URL | Purpose |
|-----|---------|
| `http://localhost:8082/` | Relay victim enrollment page |
| `http://localhost:3000/app/nodes` | Operator view of registered relay nodes |

**Relay only (remote panel):**

```bash
cd php-relay
# Set MAIN_SERVER_URL to the public panel URL in .env
docker compose up --build
```

### Shared Secret Setup

1. Generate a secret: `openssl rand -hex 32`
2. Set `RELAY_SECRET=<secret>` in `EasyTokens/.env` (picked up by the main panel via `docker-compose.yml`)
3. Set the same value in `php-relay/.env`

---

## Database

Two tables in the SQLite database:

- **`tokens`** — every captured access/refresh token (UPN, access token, refresh token, id token, scope, source, capture timestamp)
- **`device_codes`** — operator-initiated campaigns (user code, device code, verification URL, status, linked token ID, port, domain)

---

## Microsoft OAuth Details

| Field | Value |
|-------|-------|
| Client ID | `d3590ed6-52b3-4102-aeff-aad2292ab01c` (Microsoft Office) |
| Resource | `https://graph.microsoft.com` |
| Scopes | `openid profile email offline_access Mail.Read Files.Read` |
| Device code URL | `https://login.microsoftonline.com/common/oauth2/devicecode` |
| Token URL | `https://login.microsoftonline.com/Common/oauth2/token` |

---

## License

MIT — Copyright (c) 2026 Casey Smith
