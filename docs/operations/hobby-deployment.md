# Zero-cost hobby deployment (public demo)

> **Hobby / non-commercial demo only.** This profile exists so VISiOnRoute can be
> tried publicly without paying for infrastructure. It is **not** the production
> architecture (see [deployment.md](deployment.md) for the AWS/Terraform stack) and
> must only ever hold **synthetic** data (`data_origin=synthetic`, `environment=demo`).

## Topology

```
Browser ──► Vercel Hobby (Next.js web)
              │  rewrites /api/*  (same-origin: refresh cookie stays first-party)
              ▼
            Render Free web service (one Docker container, `visionroute hobby serve`)
              ├─ alembic upgrade head (on every start, must succeed)
              ├─ uvicorn API on 0.0.0.0:$PORT
              ├─ outbox worker        ┐ separate OS processes supervised together;
              └─ scheduler            ┘ if one dies the container exits and restarts
              │
              ├─► Neon Free       PostgreSQL 17 + PostGIS (TLS, direct endpoint)
              ├─► Upstash Free    Redis (rediss://) — rate limiting only
              ├─► Backblaze B2    S3-compatible private evidence/export bucket
              └─► Brevo Free      SMTP relay on port 2525 (STARTTLS)
```

Why these choices (verified September 2026):

| Need | Provider | Notes |
|------|----------|-------|
| Web | Vercel Hobby | Personal/non-commercial use only. |
| API + worker + scheduler | Render Free web service | No free background workers, so the three processes share one container. Sleeps after ~15 min idle; the first request after that takes up to about a minute. 512 MB RAM. Blocks outbound SMTP ports 25/465/587. |
| Database | Neon Free | Persistent (Render's free Postgres expires, so it is not used). PostGIS extension is supported; migrations run `CREATE EXTENSION postgis`. |
| Redis | Upstash Free | TLS URL (`rediss://…`). |
| Object storage | Backblaze B2 (10 GB free) | Account creation needs no card. **Cloudflare R2 is not used**: it requires a payment method on file even for its free tier. |
| E-mail | Brevo Free | SMTP relay `smtp-relay.brevo.com:2525` works from Render Free. Requires a verified sender. |

`VISIONROUTE_ENVIRONMENT=demo` is production-like: the API refuses to start without
TLS database, non-local Redis, `https` public URL in CORS, SMTP, S3 storage, a
field-encryption key and DejaVu fonts (`Settings.validate_for_runtime`). API docs
are hidden and webhook URLs use the strict SSRF policy.

## Why the web proxies `/api`

The refresh token is an HttpOnly `SameSite=Lax` cookie. If the browser called
`*.onrender.com` directly from `*.vercel.app` it would be a third-party cookie and
every page reload would log the user out. Instead the Vercel project sets
`API_PROXY_TARGET=https://<render-service>.onrender.com` and
`NEXT_PUBLIC_API_URL=""`; `next.config.ts` rewrites `/api/*` to the API, so the
browser only ever talks to its own origin. Devices may call either address.

Live operations use server-sent events through the proxy; if the stream is cut the
page automatically falls back to 10-second polling.

## Secrets — generate fresh, never reuse local values

```bash
poetry run visionroute keys generate --out /tmp/vr-demo-keys      # JWT RS256 pair
poetry run visionroute keys generate-field-key --key-id demo1     # field encryption
```

Paste values into the Render dashboard (every secret in `render.yaml` is
`sync: false`), then delete `/tmp/vr-demo-keys`. PEM values may be pasted with real
newlines or with literal `\n`.

## Step by step

1. **Neon**: create a project in `aws-eu-central-1`. Copy the **direct** (non-pooled)
   connection string — LISTEN/NOTIFY for live operations does not work through the
   pooler. Convert it for asyncpg:
   `postgresql+asyncpg://USER:PASSWORD@HOST/DB?ssl=require` (drop `sslmode` /
   `channel_binding` parameters).
2. **Upstash**: create a Redis database in `eu-central-1`; copy the `rediss://` URL.
3. **Backblaze B2**: create a **private** bucket and an application key restricted
   to it. Endpoint looks like `https://s3.eu-central-003.backblazeb2.com`, region
   `eu-central-003`. Add a bucket CORS rule allowing `PUT`/`GET` from the Vercel
   origin (browsers upload evidence directly with short-lived signed URLs).
4. **Brevo**: verify a sender address; create an SMTP key. Username is the SMTP
   login shown by Brevo, password is the SMTP key.
5. **Render**: New → Blueprint → this repository (`render.yaml`). Fill the
   `sync: false` values:

   | Variable | Value |
   |----------|-------|
   | `VISIONROUTE_PUBLIC_APP_URL` | `https://<vercel-project>.vercel.app` |
   | `VISIONROUTE_CORS_ORIGINS` | `["https://<vercel-project>.vercel.app"]` (never `*`) |
   | `VISIONROUTE_DATABASE_URL` | Neon URL from step 1 |
   | `VISIONROUTE_REDIS_URL` | Upstash URL |
   | `VISIONROUTE_JWT_PRIVATE_KEY` / `…_PUBLIC_KEY` | fresh PEM pair |
   | `VISIONROUTE_FIELD_ENCRYPTION_KEYS` / `…_PRIMARY_KEY_ID` | fresh key ring |
   | `VISIONROUTE_SMTP_USERNAME` / `…_PASSWORD` / `…_FROM` | Brevo |
   | `VISIONROUTE_S3_*` | B2 endpoint, region, bucket, key id, key |

6. **Vercel**: import the repository with root directory `apps/web` and set
   `API_PROXY_TARGET=https://<render-service>.onrender.com`,
   `NEXT_PUBLIC_API_URL=` (empty) and `NEXT_PUBLIC_DEMO_MODE=true` (shows the
   synthetic-data banner). Deploy.
7. **Verify**: `https://<render-service>.onrender.com/health/ready` returns
   `{"status":"ok"}`; register on the Vercel URL; the verification e-mail arrives;
   seed synthetic telemetry with the simulator against the public URL.

## Free-tier limitations (honest list)

- Cold starts: after ~15 minutes without traffic the API sleeps; the UI shows a
  "server is waking up" banner and GET requests retry automatically.
- The scheduler and worker only run while the container is awake, so periodic jobs
  (usage metering, retention purge, stale-trip marking) run late after sleep.
- One 512 MB instance: no redundancy, no horizontal scaling, deploys cause downtime.
- Neon/Upstash/B2/Brevo free quotas (storage, commands, daily e-mails) cap usage.
- Vercel Hobby is for personal, non-commercial projects only.
- No backups beyond what the free providers offer; treat all demo data as disposable.
