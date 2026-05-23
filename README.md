# Domain Checker API

A self-hosted **FastAPI** service that checks whether domain names are available to register, with deep enrichment: **RDAP/WHOIS**, **live DNS**, **Internet Archive (Wayback)**, and **domain age** — without paid SEO or registrar APIs.

Designed to run on a **VPS** (Docker) and integrate with automation tools like **n8n**.

**Default port:** `8585`  
**API version:** `2.0.0`

---

## Table of contents

- [Features](#features)
- [How it works](#how-it-works)
- [Supported TLDs](#supported-tlds)
- [Quick start (Docker)](#quick-start-docker)
- [Local development](#local-development)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Response format](#response-format)
- [Status values](#status-values)
- [Wayback rate limits (429)](#wayback-rate-limits-429)
- [n8n integration](#n8n-integration)
- [GitHub + VPS deployment](#github--vps-deployment)
- [HTTPS with Nginx](#https-with-nginx)
- [Project structure](#project-structure)
- [Limitations](#limitations)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

### Availability check (accurate)

| Method | Description |
|--------|-------------|
| **RDAP** (primary) | Official registry protocol; queries the correct server per TLD via [IANA RDAP bootstrap](https://data.iana.org/rdap/dns.json). |
| **Registry WHOIS** (fallback) | Direct socket WHOIS to registries (`.it`, `.de`, `.fr`, etc.). |
| **python-whois** (last resort) | Generic WHOIS when RDAP and registry WHOIS are inconclusive. |

### Enrichment (`enrich: true`, default)

| Module | Source | What you get |
|--------|--------|----------------|
| **Registration** | RDAP / WHOIS | Registered?, creation/expiry, registrar, EPP statuses, **drop status**, **domain age** |
| **Wayback** | Internet Archive CDX (public, no API key) | Was it used before?, snapshot count, first/last seen, business heuristic, risk flags |
| **DNS** | Live DNS (`dnspython`) | A/AAAA/MX/NS/TXT/CNAME, parking detection, live hosting signals |
| **Backlinks** | Homepage HTTP probe only | **Not** a real backlink index — see [Limitations](#limitations) |

### Domain age

- **Currently registered:** age from registry `creation_date` (exact).
- **Available but used before:** approximate age from Wayback `first_seen` (with `age_note`).
- **Never used:** `was_registered_before: false`, age fields `null`.

Top-level fields for easy filtering: `domain_age_days`, `domain_age_years`, `domain_age_human`, `was_registered_before`.

---

## How it works

```
Request → Normalize domain
       → RDAP lookup (per TLD registry)
       → If unknown: Registry WHOIS (socket)
       → If unknown: Generic WHOIS
       → If enrich=true:
            ├── Parse registration + drop status + age
            ├── Wayback CDX (throttled, cached, retries)
            ├── Live DNS lookup
            └── Optional homepage probe (outbound links only)
       → JSON response
```

**Availability rules (simplified):**

| RDAP HTTP | Meaning |
|-----------|---------|
| `404` | Not registered → usually **available** |
| `200` | Registered |
| Other | Fallback to WHOIS |

---

## Supported TLDs

- **Global gTLDs** (`.com`, `.net`, `.org`, `.io`, …) — via IANA RDAP bootstrap.
- **ccTLDs with explicit registry config** — see `GET /supported-tlds` or `app/registries.py` (e.g. `.it`, `.de`, `.fr`, `.es`, `.nl`, `.eu`, `.uk`, `.au`, `.br`, …).

`.it` and similar ccTLDs are **not** in IANA’s RDAP bootstrap; this API uses `whois.nic.it` and optional `rdap.nic.it` directly.

---

## Quick start (Docker)

### Prerequisites

- Docker and Docker Compose on your machine or VPS
- Git (optional)

### Steps

```bash
git clone https://github.com/YOUR_USERNAME/domain-checker-api.git
cd domain-checker-api

cp .env.example .env
# Edit .env — set API_KEY to a long random secret

chmod +x deploy.sh
./deploy.sh
```

### Verify

```bash
curl http://127.0.0.1:8585/health
```

Expected:

```json
{"status":"ok","version":"2.0.0"}
```

### Test a domain check

```bash
curl -X POST "http://127.0.0.1:8585/check" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"domains": ["google.com", "example-brand-xyz12345.com"]}'
```

Interactive docs: **http://YOUR_SERVER_IP:8585/docs**

---

## Local development

### Requirements

- Python 3.12+
- `whois` CLI (optional; included in Docker image)

### Setup

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --host 0.0.0.0 --port 8585 --reload
```

---

## Configuration

All settings are loaded from environment variables (or `.env`).

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | *(empty)* | If set, all `/check` endpoints require header `X-API-Key`. **Strongly recommended in production.** |
| `PORT` | `8585` | Port inside the container (see `docker-compose.yml`). |
| `MAX_DOMAINS_PER_REQUEST` | `50` | Max domains per single API call. |
| `REQUEST_TIMEOUT_SECONDS` | `20` | HTTP/socket timeout for lookups. |
| `MAX_CONCURRENT_CHECKS` | `10` | Parallel domain checks (RDAP/WHOIS). |
| `WAYBACK_MIN_INTERVAL_SECONDS` | `2` | Minimum delay between Internet Archive requests (reduces 429). |
| `WAYBACK_MAX_RETRIES` | `4` | Retries on 429 / 5xx from Archive.org. |
| `WAYBACK_RETRY_BASE_SECONDS` | `5` | Base delay for exponential backoff. |
| `WAYBACK_CACHE_TTL_SECONDS` | `3600` | Cache Wayback results per domain (seconds). |
| `WAYBACK_CDX_LIMIT` | `25` | Max CDX rows per domain (lower = gentler on Archive.org). |

### Recommended production `.env`

```env
API_KEY=replace-with-64-char-random-secret
PORT=8585
MAX_DOMAINS_PER_REQUEST=25
REQUEST_TIMEOUT_SECONDS=20
MAX_CONCURRENT_CHECKS=8
WAYBACK_MIN_INTERVAL_SECONDS=3
WAYBACK_MAX_RETRIES=4
WAYBACK_RETRY_BASE_SECONDS=8
WAYBACK_CACHE_TTL_SECONDS=3600
WAYBACK_CDX_LIMIT=25
```

---

## API reference

### Authentication

When `API_KEY` is set:

```http
X-API-Key: your-secret-key
```

If `API_KEY` is empty, checks are open (not recommended on a public VPS).

---

### `GET /health`

No auth. Service health check.

---

### `GET /supported-tlds`

No auth. Lists ccTLDs with explicit registry WHOIS/RDAP overrides.

---

### `GET /analysis-capabilities`

No auth. Describes enrichment modules and their limits.

---

### `POST /check`

**Auth required** (if `API_KEY` set).

**Body:**

```json
{
  "domains": ["example.com", "mybrand.it", "test-name-12345.io"],
  "enrich": true
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `domains` | `string[]` | required | Domain names (with TLD). |
| `enrich` | `boolean` | `true` | Include full `analysis` object. Set `false` for faster availability-only checks. |

---

### `GET /check?domains=...`

**Auth required** (if `API_KEY` set).

Query parameters:

| Param | Example | Description |
|-------|---------|-------------|
| `domains` | `a.com,b.it` | Comma-separated list |
| `enrich` | `true` | Full analysis on/off |

```bash
curl "http://127.0.0.1:8585/check?domains=google.com,free-name-xyz.com" \
  -H "X-API-Key: YOUR_API_KEY"
```

---

### `GET /check/{domain}`

**Auth required** (if `API_KEY` set).

Single domain. Optional `?enrich=false`.

```bash
curl "http://127.0.0.1:8585/check/example.it" \
  -H "X-API-Key: YOUR_API_KEY"
```

---

## Response format

### Top-level response

```json
{
  "results": [ { /* DomainResult */ } ],
  "checked": 1
}
```

### `DomainResult` (per domain)

| Field | Type | Description |
|-------|------|-------------|
| `domain` | string | Normalized domain |
| `status` | string | `available`, `registered`, `unavailable`, `unknown` |
| `available` | boolean | `true` if likely free to register |
| `method` | string | `rdap`, `whois-registry`, `whois` |
| `registrar` | string \| null | Registrar name if registered |
| `creation_date` | string \| null | `YYYY-MM-DD` |
| `expiry_date` | string \| null | `YYYY-MM-DD` |
| `was_registered_before` | boolean | Registered now or seen in Wayback |
| `domain_age_days` | int \| null | Age in days |
| `domain_age_years` | float \| null | Age in years (e.g. `12.4`) |
| `domain_age_human` | string \| null | e.g. `"12 years, 4 months"` |
| `message` | string \| null | Human-readable summary |
| `analysis` | object \| null | Full enrichment (`null` if `enrich=false`) |

### `analysis.registration`

| Field | Description |
|-------|-------------|
| `is_registered` | Currently registered at registry |
| `creation_date` / `expiration_date` | From RDAP/WHOIS |
| `registrar` | Registrar name |
| `domain_statuses` | EPP status strings |
| `drop_status` | `active`, `pending_delete`, `redemption_period`, `not_registered`, … |
| `was_registered_before` | Includes historical (Wayback) signal |
| `domain_age_*` | Same as top-level age fields |
| `age_source` | `registry_creation_date` or `wayback_approximate` |
| `age_note` | Explains approximate age when not from registry |

### `analysis.wayback`

| Field | Description |
|-------|-------------|
| `was_archived` | Found in Wayback Machine |
| `snapshot_count` | Approximate unique captures |
| `first_seen` / `last_seen` | `YYYY-MM-DD` |
| `likely_real_business` | Heuristic (snapshots + `/about`, `/contact`, etc.) |
| `risk_flags` | e.g. `adult`, `gambling`, `pharma`, `spam` (URL keyword heuristics) |
| `risk_level` | `none`, `medium`, `high` |
| `lookup_status` | `ok`, `not_found`, `partial`, `rate_limited`, `error` |
| `rate_limited` | `true` if Archive.org returned 429 |
| `note` | Details or error message |

> **Important:** If `rate_limited` is `true`, `was_archived: false` does **not** mean the domain was never used — only that Wayback could not be queried. Retry later.

### `analysis.dns`

| Field | Description |
|-------|-------------|
| `a_records`, `aaaa_records`, `mx_hosts`, `ns_hosts`, `txt_samples`, `cnames` | Current DNS |
| `likely_parked` | SEDO, Bodis, “for sale”, etc. |
| `had_live_hosting` | Has records and not parked |
| `had_email_setup` | Has MX records |
| `inferred_historical_hosting` | Combined with Wayback signal |

### `analysis.backlinks`

| Field | Description |
|-------|-------------|
| `supported` | Usually `false` for real inbound backlink data |
| `note` | Explains limits; may include homepage outbound probe |

---

## Status values

### Availability `status`

| Value | `available` | Meaning |
|-------|-------------|---------|
| `available` | `true` | Not registered — likely free |
| `registered` | `false` | Taken |
| `unavailable` | `false` | Not registered but blocked/reserved/premium |
| `unknown` | `false` | Could not determine — retry or verify manually |

### Drop `drop_status`

| Value | Meaning |
|-------|---------|
| `active` | Normal registered domain |
| `pending_delete` | Deletion in progress (may become available) |
| `redemption_period` | Grace period after expiry |
| `pending_restore` | Restore in progress |
| `recently_registered` | In add period |
| `not_registered` | Free or never registered |

---

## Wayback rate limits (429)

Internet Archive may return **HTTP 429** if too many CDX requests are sent at once (common with bulk n8n workflows).

**Built-in mitigations:**

- Global throttle between Wayback requests
- Retries with exponential backoff
- Per-domain cache (1 hour default)
- Smaller CDX `limit`
- Fallback to lightweight **availability API** when CDX is rate-limited (`lookup_status: partial`)

**What you should do:**

1. Set `WAYBACK_MIN_INTERVAL_SECONDS=3` (or higher) in `.env`
2. Check **≤10 domains per request** in n8n, or use a Loop with delays
3. Retry domains where `analysis.wayback.rate_limited === true`
4. Do not treat `was_archived: false` as “clean history” when `rate_limited` is `true`

---

## n8n integration

### Basic flow

```
[Trigger] → [HTTP Request POST /check] → [Split Out: results] → [IF: available] → [Slack / Sheet]
```

### HTTP Request node

| Setting | Value |
|---------|--------|
| Method | `POST` |
| URL | `http://YOUR_VPS_IP:8585/check` |
| Authentication | Header Auth → `X-API-Key` |
| Body (JSON) | `{"domains": ["{{ $json.domain }}"]}` or a static list |

### Split bulk results

**Split Out** node → Field: `results`  
Each item is one domain with all fields.

### Filter only available domains

**IF** node:

- `{{ $json.available }}` **is true**

Optional quality filters:

- `{{ $json.analysis.wayback.risk_flags.length }}` equals `0`
- `{{ $json.analysis.dns.likely_parked }}` is false
- `{{ $json.domain_age_years }}` ≥ `5`

### Filter after rate limit

Exclude inconclusive Wayback:

- `{{ $json.analysis.wayback.rate_limited }}` is false  

Or retry those in a separate workflow.

### Code node (filter available in one step)

```javascript
const results = $input.first().json.results || [];
return results
  .filter((r) => r.available === true)
  .map((r) => ({ json: r }));
```

---

## GitHub + VPS deployment

### 1. Push to GitHub (local)

```bash
git init
git add .
git commit -m "Initial commit: domain checker API"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/domain-checker-api.git
git push -u origin main
```

Use a **Personal Access Token** if prompted (GitHub no longer accepts account passwords for Git).

### 2. Deploy on VPS

```bash
ssh user@YOUR_VPS_IP

sudo apt update
sudo apt install -y docker.io docker-compose-plugin git
sudo systemctl enable --now docker

git clone https://github.com/YOUR_USERNAME/domain-checker-api.git
cd domain-checker-api

cp .env.example .env
nano .env   # set API_KEY

chmod +x deploy.sh
./deploy.sh
```

### 3. Firewall

```bash
sudo ufw allow 8585/tcp
sudo ufw enable
```

Also open port **8585** in your cloud provider’s security group (DigitalOcean, Hetzner, AWS, etc.).

### 4. Update after code changes

**Local:**

```bash
git add .
git commit -m "Describe change"
git push
```

**VPS:**

```bash
cd ~/domain-checker-api
git pull
./deploy.sh
```

---

## HTTPS with Nginx

1. Point your domain’s DNS A record to the VPS IP.
2. Copy and edit `nginx/domain-api.conf` (replace `YOUR_DOMAIN`).
3. Install Nginx and Certbot:

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo cp nginx/domain-api.conf /etc/nginx/sites-available/domain-api
sudo ln -s /etc/nginx/sites-available/domain-api /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d yourdomain.com
```

4. Use `https://yourdomain.com/check` in n8n (port 443).
5. Keep port **8585** bound to localhost only if you proxy through Nginx.

---

## Project structure

```
domain-checker-api/
├── app/
│   ├── main.py              # FastAPI routes
│   ├── checker.py           # Orchestrates lookup + enrichment
│   ├── lookup.py            # RDAP / WHOIS availability
│   ├── models.py            # Pydantic request/response models
│   ├── config.py            # Settings from environment
│   ├── registries.py        # ccTLD WHOIS/RDAP overrides
│   ├── whois_socket.py      # Raw registry WHOIS (port 43)
│   └── enrichment/
│       ├── pipeline.py      # Runs all enrichment modules
│       ├── registration.py  # Parse RDAP/WHOIS registration
│       ├── age.py           # Domain age calculation
│       ├── wayback.py         # Wayback analysis
│       ├── wayback_client.py  # Throttle, retry, cache
│       ├── dns_lookup.py    # Live DNS + parking heuristics
│       └── backlinks.py     # Homepage probe (limited)
├── nginx/
│   └── domain-api.conf      # Example reverse proxy
├── Dockerfile
├── docker-compose.yml
├── deploy.sh
├── requirements.txt
├── .env.example
└── README.md
```

---

## Limitations

| Feature | Supported without paid APIs? |
|---------|------------------------------|
| Availability (RDAP/WHOIS) | **Yes** — registry protocols |
| Registration dates / registrar | **Yes** — when registry returns data |
| Drop / lifecycle status | **Partial** — from EPP status strings |
| Domain age (registered) | **Yes** — from creation date |
| Domain age (dropped) | **Approximate** — from Wayback first seen |
| Wayback / prior use | **Yes** — Internet Archive public CDX (rate limited) |
| Spam/adult/gambling heuristics | **Partial** — URL keyword heuristics only |
| Full DNS **history** | **No** — live DNS only (+ Wayback inference) |
| Real **inbound backlink** index | **No** — requires Ahrefs, Moz, Majestic, etc. |
| 100% purchase guarantee | **No** — always confirm at your registrar before paying |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `401 Unauthorized` | Set `X-API-Key` header to match `API_KEY` in `.env` |
| Connection refused | Open port 8585 on VPS + cloud firewall; confirm `docker ps` |
| `.it` / ccTLD `unknown` | Ensure latest code is deployed; check `GET /supported-tlds` |
| Wayback `429` / `rate_limited` | Increase `WAYBACK_MIN_INTERVAL_SECONDS`; fewer domains per request; retry later |
| Slow bulk checks | Normal: Wayback is throttled (~2–3 s per domain); use `enrich: false` for speed |
| `unknown` availability | Registry timeout or unsupported TLD; retry or check manually |

### Logs (Docker)

```bash
docker logs -f domain-checker-api
```

---

## Example responses

### Registered domain (`google.com`)

```json
{
  "domain": "google.com",
  "status": "registered",
  "available": false,
  "method": "rdap",
  "registrar": "MarkMonitor Inc.",
  "creation_date": "1997-09-15",
  "expiry_date": "2028-09-14",
  "was_registered_before": true,
  "domain_age_days": 10450,
  "domain_age_years": 28.6,
  "domain_age_human": "28 years, 7 months",
  "message": "Domain is registered",
  "analysis": {
    "registration": {
      "is_registered": true,
      "creation_date": "1997-09-15",
      "drop_status": "active",
      "age_source": "registry_creation_date"
    },
    "wayback": {
      "was_archived": true,
      "snapshot_count": 25,
      "lookup_status": "ok",
      "rate_limited": false
    },
    "dns": {
      "resolves": true,
      "had_live_hosting": true,
      "likely_parked": false
    },
    "backlinks": {
      "supported": false,
      "note": "Real inbound backlink index requires third-party SEO APIs."
    }
  }
}
```

### Available domain (never used)

```json
{
  "domain": "totally-new-xyz12345.com",
  "status": "available",
  "available": true,
  "method": "rdap",
  "was_registered_before": false,
  "domain_age_days": null,
  "message": "Domain is not registered (RDAP 404)"
}
```

### Available but used before (dropped / expired)

```json
{
  "domain": "old-brand.it",
  "status": "available",
  "available": true,
  "was_registered_before": true,
  "domain_age_years": 6.0,
  "domain_age_human": "6 years, 0 months",
  "analysis": {
    "registration": {
      "is_registered": false,
      "age_source": "wayback_approximate",
      "age_note": "Approximate age from Wayback first archive date (not exact registration date)."
    },
    "wayback": {
      "was_archived": true,
      "first_seen": "2018-04-12",
      "lookup_status": "ok"
    }
  }
}
```

---

## License

MIT — use freely. No warranty on availability accuracy; always verify with your registrar before purchase.
