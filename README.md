# World Cup Prediction Game

Production-ready prediction platform powered by **official FIFA World Cup 2026** tournament data.

## Features

- **Real tournament data** — Official 48 teams, 12 groups, 72 fixtures with UTC kickoffs and stadiums
- **FIFA knockout rules** — 495 third-place scenario lookup (Annex C), official R32–Final bracket mapping
- **Per-user simulation** — Independent group standings and knockout paths for scoring
- **Configurable tournaments** — JSON seed system supports future World Cup, Euro, Copa América formats
- **Admin import system** — Transactional reseed, validation, bracket preview

## Quick Start

```bash
docker compose up --build
```

Open http://localhost

> **VPS production:** use `docker-compose.prod.yml` (no Docker Nginx). See [deploy/DEPLOY.md](deploy/DEPLOY.md).

**Admin:** `admin` / `admin123`

## Production (VPS + domain)

See **[deploy/DEPLOY.md](deploy/DEPLOY.md)** for hosting behind existing Nginx with HTTPS on **https://worldcupytu.org**.

Quick start on the VPS:

```bash
cp .env.production.example .env.production   # edit secrets
bash deploy/scripts/deploy-app.sh
sudo bash deploy/scripts/install-nginx-site.sh
sudo CERTBOT_EMAIL=you@example.com bash deploy/scripts/enable-ssl.sh
```


## Seed Architecture

```
backend/app/seeds/tournaments/worldcup_2026/
├── tournament.json          # Tournament metadata & format config
├── groups.json              # Group definitions
├── teams.json               # 48 official teams with flags
├── matches.json             # 72 group fixtures (official order)
├── stadiums.json            # 16 host venues
├── knockout_rules.json      # R32–Final mappings & feeders
└── third_place_scenarios.json  # 495 FIFA Annex C scenarios
```

Import via admin (`POST /api/admin/import-tournament`) or automatic on first boot.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/tournament/active` | Active tournament info |
| `GET /api/tournament/groups` | Groups with teams & flags |
| `GET /api/matches?stage=group&group=A&matchday=1` | Fixtures with kickoffs |
| `POST /api/simulation/preview-bracket` | Preview knockout from group preds |
| `POST /api/admin/import-tournament` | Import/reseed tournament |
| `GET /api/admin/tournament/validate` | Validate seed consistency |
| `GET /api/admin/tournament/preview-bracket` | Preview real R32 from results |

## Database Schema

New tournament entities (preserves existing auth/scoring):

- `tournaments` — Multi-tournament support
- `groups` — Group stage definitions
- `stadiums` — Venue data
- `teams` — Linked to tournament + group, flag codes
- `matches` — `kickoff_time_utc`, `match_number`, `matchday`, `stadium_id`

## Tests

```bash
docker exec worldcup-backend-1 pytest tests/ -v
```

Covers: standings, best-3rd qualification, 495-scenario lookup, R32 generation, scoring.

## Tech Stack

FastAPI · PostgreSQL · SQLAlchemy · Next.js 14 · TailwindCSS · Docker Compose · Nginx

## Official Data Sources

Team groups and fixtures based on the FIFA World Cup 2026 draw (December 2025). Knockout third-place scenarios from FIFA Competition Regulations Annex C.
