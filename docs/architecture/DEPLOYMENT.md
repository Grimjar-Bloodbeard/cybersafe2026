# Deploying CyberSafe to `cybersafe.codynoah.net`

## Context

The team needed the demo assessment page and the real event-registration form
reachable at a public URL - for a QR code on the Dec 11 event flyer, and so
the other 3 teammates could actually open and test it instead of only seeing
it on Cody's laptop. This lives on the same server, shared nginx instance,
and Cloudflare Tunnel that already host Summit Gaming - a live,
revenue-processing site - so every step here was sequenced to keep that risk
small, isolated, and deliberate.

**What this deployment does NOT include**: any real security-scan-triggering
capability. Tiers 2-5 against real businesses don't exist yet - see
`PLAN.md` Section 7. That's why this was safe to make fully public today.
**The day the real scan-triggering admin tool gets built, it must be
Tailscale-gated, not public** - this deployment is not a precedent for that.

## Before you start - what already runs on this server

- **PM2** manages `cloudflared`, `gotify`, `summit-monitor`, and
  `summit-server` (Summit Gaming's live Node app). None of these were
  touched - CyberSafe got its own new PM2 process instead.
- **One shared nginx instance** (`C:\summitserver\nginx-1.24.0`) serves
  every `*.codynoah.net` subdomain plus Summit Gaming, each as its own
  `.conf` file explicitly `include`d in `nginx.conf`. Nginx runs on its own
  Windows Task Scheduler trigger, not under PM2 (a deliberate earlier
  decision - don't change that).
- **One Cloudflare Tunnel process** routes every hostname to that same
  shared nginx instance on port 8090 (internally, distinguished by
  `server_name`). Restarting this tunnel reconnects *every* hostname at
  once - the one genuinely shared-risk step in this whole runbook.

## The runbook, in the order it actually happened

### 1. App-level security hardening (all in-repo, zero production risk)

- Added `email-validator` as an explicit dependency (`EmailStr` needs it;
  it only worked before because it happened to already be installed).
- `backend/app/rate_limit.py` - a hand-rolled, in-process per-IP rate
  limiter (same token-bucket idea as `scrapers/common/rate_limiter.py`,
  just for inbound requests). `/api/run-demo` gets two protections: the
  per-IP throttle, plus a global concurrency semaphore (`threading.Semaphore(1)`)
  so a crowd scanning the same QR code at once can't pile onto the shared,
  slow, CPU-bound Ollama call simultaneously.
- **This is why the PM2 process runs `--workers 1`**: the rate limiter's
  state lives in one process's memory. More workers would each get their
  own independent counters, silently making the limiter N times weaker.
  Don't raise the worker count without rethinking this.
- A honeypot field (`hp_website`) on the registration form - invisible to a
  real visitor, often filled by a bot's autofill. A filled honeypot returns
  a fake success and writes nothing, so a bot doesn't learn to look for a
  different tell. No CAPTCHA - disproportionate for an event expecting
  dozens-to-low-hundreds of registrants.
- Refactored `submit_registration` to take its DB session via FastAPI's
  `Depends(get_session)` instead of a hardcoded `SessionLocal()` call - this
  is what actually makes it testable without writing real rows into the
  production database.
- New tests: `backend/tests/test_rate_limit.py` proves the 2nd rapid call
  gets blocked, different IPs are tracked independently, and the honeypot
  fakes success while writing zero rows.

Run: `python -m pytest backend/tests/ -v` (12/12 passing).

### 2. New PM2 process

Port **8098** (verified free before use - re-check with
`Get-NetTCPConnection -LocalPort 8098` if redoing this later, since the
"free" answer can change). `D:\cybersafe2026\ecosystem.config.js`, its own
file (matching `D:\Gotify\ecosystem.config.js`'s pattern) rather than an
addition to Summit's shared ecosystem file.

```
cd D:\cybersafe2026
pm2 start ecosystem.config.js
pm2 save
```

### 3. New nginx vhost

New file `C:\summitserver\nginx-1.24.0\conf\cybersafe.conf` (see that file
for the exact content) - proxies everything to `127.0.0.1:8098` rather than
serving files off disk (the app serves its own static assets), with its own
`limit_req_zone` throttles on `/api/run-demo` and `/api/register` as a
second layer on top of the app's own rate limiter, security headers, and
the same `.git`/`.env`/PHP-probe blocking the other vhosts use. One line
added to `nginx.conf`'s existing `include` list.

```
cd C:\summitserver\nginx-1.24.0
.\nginx.exe -t          # syntax check only
.\nginx.exe -s reload   # graceful reload - does NOT touch the tunnel at all
```

**Real gotcha hit here**: `-s reload` failed with `Access is denied` from a
non-elevated session - a known issue on this machine (nginx runs under a
different privilege context than a normal shell). Fixed by running the same
two commands from an elevated PowerShell/Command Prompt instead. This
doesn't restart nginx or drop any connections - just needs the right
privilege level to send the signal.

### 4. Cloudflare Tunnel route

Added one ingress entry to `C:\Users\cody\.cloudflared\config.yml`
(`cybersafe.codynoah.net -> http://localhost:8090`, inserted before the
trailing catch-all - order matters), then:

```
cloudflared tunnel route dns 6497d93a-73e5-4a15-bbd3-e628e3ae268e cybersafe.codynoah.net
```

This only touches Cloudflare's DNS/zone API - it does not restart or
reconnect the running tunnel.

### 5. The one real shared-risk step

```
pm2 restart cloudflared
```

Picks up the new ingress rule. One tunnel process serves every hostname, so
this briefly (a few seconds) drops and reconnects **all** of them at once,
Summit Gaming included. Run this alone, watch `pm2 logs cloudflared`, and
verify Summit Gaming first immediately after - it's the one with real
financial consequences:

```
pm2 list
curl -I https://summitgamingofwilkes.com
```

Only once that's confirmed clean, check the new hostname.

### 6. Two real post-deploy gotchas, both external to our own code

**Cloudflare edge caching a stale error.** The first requests to
`/static/*.png`/`.css` (made in the brief window before the tunnel route
was fully active) got cached at Cloudflare's edge as 404s, with a 4-hour
default TTL for those file extensions - even after the origin was serving
them correctly. Confirmed via the `cf-cache-status: HIT` / `Age` response
headers, and by bypassing cache with a `?cachebust=` query string, which
returned 200 immediately. Fixed with a manual **Custom Purge** in the
Cloudflare dashboard (Caching -> Configuration -> Purge Cache) for the
specific URLs. Would also have resolved itself after 4 hours regardless.

**Tunnel route propagation lag.** Right after the `cloudflared` restart,
the public hostname returned an inconsistent mix of 200s and 404s across
consecutive requests - roughly half and half. Direct testing proved uvicorn
and nginx were both 100% consistent (10/10 success each) the whole time;
only the public path through Cloudflare flapped. This is normal: a new
tunnel route takes a few minutes to propagate across Cloudflare's global
edge network, and different requests can land on different edge servers
mid-rollout. Confirmed resolved by re-testing in a loop until 10
consecutive requests all succeeded, rather than trusting a single check.

**Lesson for next time**: after any Cloudflare Tunnel config change, verify
with *repeated* requests over a short window, not one success and done -
a single 200 right after a restart doesn't prove the route has actually
finished propagating.

## Rollback, one layer at a time

- **App/PM2**: `pm2 delete cybersafe2026`
- **nginx**: delete the `include cybersafe.conf;` line from `nginx.conf`
  and the `cybersafe.conf` file itself, then `nginx -t && nginx -s reload`
  (from an elevated session)
- **Tunnel**: remove the `cybersafe.codynoah.net` entry from
  `config.yml`, then `pm2 restart cloudflared` (same shared-risk caveat
  as the original restart)

Each layer can be undone independently without touching the others.

## Verification checklist

- [x] `pm2 list` - `cybersafe2026` and `cloudflared` both `online`
- [x] `https://cybersafe.codynoah.net/` and `/register` load correctly
- [x] A real registration saves to `event_registrations`
- [x] Honeypot submissions return success but save nothing
- [x] Rate limiting blocks a 6th rapid registration attempt (429)
- [x] Security headers present (`X-Frame-Options`, `X-Content-Type-Options`,
      `Referrer-Policy`)
- [x] `/.env` returns 404, not app content
- [x] Static assets (`/static/*`) load correctly (after the cache purge)
- [x] Summit Gaming and codynoah.net confirmed unaffected, both immediately
      after the tunnel restart and afterward
- [x] 10 consecutive requests to the public URL all succeed (confirms edge
      propagation actually finished, not just one lucky check)

## Known, unrelated, non-blocking quirk

`curl -I` (HEAD requests) against `/` and `/register` returns 405/404
depending on the layer, reproducing identically on a bare local `uvicorn`
run with no reverse proxy involved at all. Real browsers always send GET
when a person opens a link or scans a QR code, so this never affects an
actual visitor - only tools that specifically probe with HEAD (like a naive
health-check script). Not fixed here since it predates this deployment and
doesn't touch anything this runbook changed; worth a small fix later
(FastAPI/Starlette can register HEAD support explicitly per-route) but not
urgent.

## Separately flagged, not part of this deployment

While verifying, Cloudflare's own dashboard surfaced a list of pre-existing
findings on the *other* domains on this account (Summit Gaming,
codynoah.net, gather, stockforge) - outdated TLS versions, missing HSTS,
HTTPS not enforced, a DMARC record error. None of these are new, none
involve `cybersafe.codynoah.net`, and none block anything in this runbook.
Worth noting for the presentation, though: those are close to the exact
categories (general hygiene, phishing/email-spoofing exposure) this project
itself is built to find - a genuine, honest real-world example. Logged as a
separate follow-up, not tackled here.
