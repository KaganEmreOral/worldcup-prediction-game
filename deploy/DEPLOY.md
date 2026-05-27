# Production deployment — worldcupytu.org

Host the World Cup Prediction Game on a VPS that **already runs Nginx** for another site. This guide adds a **separate vhost** only for `worldcupytu.org` and does **not** modify `default.conf` or other sites.

## Architecture

```
Internet :443 / :80
    ↓
Host Nginx (/etc/nginx/sites-available/worldcupytu.org)
    ├─ /api/*  → 127.0.0.1:8000 (FastAPI)
    └─ /*      → 127.0.0.1:3000 (Next.js)
    ↓
docker compose -f docker-compose.prod.yml
    ├─ backend  (127.0.0.1:8000)
    ├─ frontend (127.0.0.1:3000)
    └─ db       (internal only)
```

The **Docker Nginx container** from `docker-compose.yml` is **not used** in production (it would conflict with host Nginx on port 80).

---

## 1. Prerequisites on VPS

- DNS **A records** for `worldcupytu.org` and `www.worldcupytu.org` → VPS IP
- Docker + Docker Compose plugin installed
- Host **Nginx** already serving your other website
- Ports **80** and **443** open in firewall (see below)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
bash deploy/scripts/check-firewall.sh
```

---

## 2. Production environment

```bash
cd /path/to/worldcup
cp .env.production.example .env.production
nano .env.production
```

Generate a secret key:

```bash
openssl rand -hex 32
```

Set at minimum:

| Variable | Example |
|----------|---------|
| `SECRET_KEY` | output of `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | strong random password |
| `ADMIN_PASSWORD` | strong admin password |
| `ENABLE_TESTING_TOOLS` | `false` |
| `NEXT_PUBLIC_API_URL` | `https://worldcupytu.org/api` |
| `CORS_ORIGINS` | `https://worldcupytu.org,https://www.worldcupytu.org` |

---

## 3. Start Docker (production)

```bash
bash deploy/scripts/deploy-app.sh
```

This runs:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

Verify locally on the VPS:

```bash
curl -s http://127.0.0.1:8000/api/health
curl -sI http://127.0.0.1:3000/
```

**If the old dev stack used Docker Nginx on port 80**, stop it first:

```bash
docker compose stop nginx
# or: docker compose down
```

---

## 4. Install Nginx site (HTTP only — Phase 1)

Does **not** edit other files in `sites-enabled/`.

```bash
sudo bash deploy/scripts/install-nginx-site.sh
```

Files installed:

| Path | Purpose |
|------|---------|
| `/etc/nginx/sites-available/worldcupytu.org` | Site vhost |
| `/etc/nginx/sites-enabled/worldcupytu.org` | Symlink |
| `/etc/nginx/snippets/worldcup-proxy.conf` | Shared proxy headers |
| `/etc/nginx/conf.d/worldcup-limits.conf` | Rate limit zones |

Test public HTTP:

```bash
curl -sI http://worldcupytu.org/api/health
curl -sI http://worldcupytu.org/
```

Confirm your **existing website** still works.

---

## 5. Enable HTTPS (Let's Encrypt — Phase 2)

```bash
sudo CERTBOT_EMAIL=you@example.com bash deploy/scripts/enable-ssl.sh
```

This will:

1. Install `certbot` if missing  
2. Issue certs via webroot (`/var/www/certbot`)  
3. Replace the site config with `deploy/nginx/worldcupytu.org.conf` (HTTPS + redirect)  
4. Reload Nginx  

Certificates: `/etc/letsencrypt/live/worldcupytu.org/`

Renewal (usually automatic):

```bash
sudo certbot renew --dry-run
```

---

## 6. Validation checklist

```bash
curl -s https://worldcupytu.org/api/health
curl -sI https://worldcupytu.org/
```

In a browser:

- [ ] Homepage loads over HTTPS  
- [ ] Register / login work  
- [ ] Admin panel (`admin` user) works  
- [ ] API calls go to `https://worldcupytu.org/api/...`  
- [ ] Existing unrelated site still works  
- [ ] Mobile layout OK  

---

## 7. Updates / redeploy

```bash
git pull
bash deploy/scripts/deploy-app.sh
```

Nginx reload only if configs changed:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## 8. Optional: fail2ban

Nginx logs for this site:

- `/var/log/nginx/worldcupytu.org.access.log`
- `/var/log/nginx/worldcupytu.org.error.log`

Point a fail2ban jail at repeated `401`/`429` on `/api/auth/` if desired.

---

## File reference

| File | Role |
|------|------|
| `docker-compose.prod.yml` | Production stack, `restart: unless-stopped`, localhost ports |
| `frontend/Dockerfile.prod` | Next.js production build |
| `.env.production.example` | Template for secrets |
| `deploy/nginx/worldcupytu.org.http-only.conf` | Phase 1 HTTP |
| `deploy/nginx/worldcupytu.org.conf` | Phase 2 HTTPS |
| `deploy/scripts/install-nginx-site.sh` | Safe Nginx install |
| `deploy/scripts/enable-ssl.sh` | Certbot + HTTPS |
| `deploy/scripts/deploy-app.sh` | Docker prod up |

## Public URL

**https://worldcupytu.org** (www redirects to apex)
