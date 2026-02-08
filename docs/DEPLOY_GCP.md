# Deploy to Google Cloud (Compute Engine VM)

This repo supports a simple Local -> Tag -> GCP promote loop. The goal is: **no cloud debugging**. We only deploy tagged, locally-gated releases.

## 0) Local Gate (required before any cloud promote)

From repo root:

```bash
make gate-local
```

To include a full end-to-end pipeline run in the gate:

```bash
VIDEO_ID=YOUTUBE_VIDEO_ID make gate-local
```

## 1) Release Freeze (tag a known-good build)

This runs the local gate and **requires** a full pipeline run.

```bash
VIDEO_ID=YOUTUBE_VIDEO_ID make release TAG=v1.0.0
```

Notes:
- `make release` fails unless your git working tree is clean (no uncommitted/untracked files).
- It tags and pushes `TAG` to `origin`.

## 2) Create The VM (one cheap always-on box)

Recommended:
- Compute Engine VM: `e2-small`
- OS: Ubuntu 22.04 LTS
- Disk: 30GB

Firewall ports (choose one approach):
- Direct access:
  - TCP `5678` (n8n UI)
  - TCP `8000` (runner API)
- Reverse proxy (recommended):
  - TCP `80` + `443` (Caddy)
  - Keep `5678` + `8000` closed to the public internet (use UFW + GCP firewall rules).

## 3) VM Bootstrap (Docker + UFW + app dirs)

SSH to the VM and run:

```bash
sudo apt-get update -y
sudo apt-get install -y git
git clone https://github.com/pacoroban1/youtubedevin-.git
cd youtubedevin-

# Optional: lock n8n/runner ports to your IP (recommended)
# export ALLOW_IP_CIDR="YOUR.PUBLIC.IP.ADDRESS/32"

sudo bash infra/gcp/setup_vm.sh
```

Then reconnect so the `autopilot` user picks up docker group membership:

```bash
exit
```

## 4) Create The Cloud .env (secrets live outside git)

On the VM:

```bash
sudo -u autopilot nano /opt/amharic-recap-autopilot/shared/.env
sudo chmod 600 /opt/amharic-recap-autopilot/shared/.env
```

Minimum required:
- `GEMINI_API_KEY`
- `N8N_USER` + `N8N_PASSWORD`

For true YouTube upload autopilot, also set:
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`
- `YOUTUBE_API_KEY`
- `YOUTUBE_PRIVACY_STATUS` (`public` | `unlisted` | `private`) (recommended: start with `unlisted`)

Tip: start from `.env.example`.

## 5) Promote A Tag To The VM (single command)

On your local machine (where `gcloud` is installed/authenticated):

```bash
export GCP_PROJECT="your-gcp-project-id"
export GCP_ZONE="us-central1-a"
export GCP_VM="your-vm-instance-name"

make promote TAG=v1.0.0
```

If you want to skip re-running the local gate before promotion:

```bash
SKIP_GATE=1 make promote TAG=v1.0.0
```

## 6) Verify (health check)

```bash
export GCP_PROJECT="your-gcp-project-id"
export GCP_ZONE="us-central1-a"
export GCP_VM="your-vm-instance-name"

make gcp-health
```

Also valid from your browser (if exposed):
- `http://<VM_EXTERNAL_IP>:5678` (n8n)
- `http://<VM_EXTERNAL_IP>:8000/health` (runner)

## 7) Rollback (single command)

Rollback to the **previous tag** recorded on the VM:

```bash
export GCP_PROJECT="your-gcp-project-id"
export GCP_ZONE="us-central1-a"
export GCP_VM="your-vm-instance-name"

make rollback
```

Rollback to an explicit tag:

```bash
make rollback TAG=v1.0.0
```

## 8) n8n Workflow Migration (daily + weekly)

1. Open n8n UI.
2. Workflows -> Import from File.
3. Import:
   - `n8n/workflows/autopilot_daily_full_pipeline.json`
   - `n8n/workflows/autopilot_weekly_full_pipeline.json`
4. Confirm HTTP nodes point to `http://runner:8000` (these exports already do).
5. Activate both workflows.

## 9) Optional HTTPS Reverse Proxy (Caddy)

This repo includes an optional Caddy service at `infra/gcp/docker-compose.caddy.yml`.

1. Add these to `/opt/amharic-recap-autopilot/shared/.env`:
   - `CADDY_SITE=yourdomain.com` (domain required for real public HTTPS)
   - `CADDY_ACME_EMAIL=you@example.com`
   - `CADDY_BASIC_AUTH_USER=admin`
   - `CADDY_BASIC_AUTH_HASH=...` (bcrypt hash)

Generate the bcrypt hash (run locally or on the VM):

```bash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'your_password'
```

2. Promote with Caddy enabled:

```bash
export ENABLE_CADDY=1
make promote TAG=v1.0.0
```

No-domain mode:
- Set `CADDY_SITE=:80` for HTTP only.
- Real TLS without a domain is not available via Let's Encrypt. (You can use self-signed/internal TLS, but browsers will warn unless you trust the CA.)
