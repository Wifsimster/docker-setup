# AGENTS.md

Guide for AI coding agents working with this repository. It applies to any coding agent (Claude Code, Codex, Copilot...); `CLAUDE.md` only imports this file.

## Project Overview

Self-hosted Docker infrastructure for a personal home server (Debian). ~36 services (~65 containers) orchestrated with Docker Compose, exposed via Traefik reverse proxy with automatic HTTPS (Let's Encrypt / OVH DNS challenge). Media stored on an Unraid NAS via NFS mounts.

**This is a configuration-only repository** — no application source code, no build system, no tests, no CI/CD. All changes are Docker Compose files and supporting config.

## Repository Structure

Chaque service a son propre répertoire contenant un `compose.yml`. Le répertoire `multimedia/` regroupe toute la pile média (Plex, Sonarr, Radarr, etc.) en un seul projet Compose.

```
docker-setup/
├── AGENTS.md                  # This file
├── CLAUDE.md                  # Imports AGENTS.md (Claude Code entry point)
├── README.md                  # Infrastructure documentation
├── .gitignore                 # Tracks only compose.yml, hwaccel.*.yml, CLAUDE.md and AGENTS.md
├── photos-backup.sh           # Weekly offsite borg backup of the Immich library (Hetzner)
├── state-backup.sh            # Daily offsite borg backup of everything except photos
├── borg-check.sh              # Monthly integrity check of the Hetzner borg repo
├── ha-config-backup.sh        # Weekly Home Assistant config backup to the NAS
├── gramps-backup.sh           # Weekly Gramps Web data backup to the NAS
├── disk-cleanup.sh            # Disk space cleanup (cron)
├── disk-guard.sh              # Hourly guard: runs disk-cleanup.sh above a usage threshold
├── traefik/compose.yml        # Core: reverse proxy, TLS, Let's Encrypt (OVH DNS) — point d'entrée de toute l'infrastructure
├── multimedia/                # Unified media stack (single compose project)
│   ├── compose.yml            # Plex, Sonarr, Radarr, Lidarr, Prowlarr,
│   │                          # qBittorrent (VPN), Seerr, Cleanuparr (Bazarr et Tautulli retirés)
│   └── README.md
├── home-assistant/compose.yml # Home Assistant + Mosquitto MQTT + Matter Server
├── immich-app/                # Photo/video management with ML
│   ├── compose.yml
│   ├── hwaccel.ml.yml         # ML hardware acceleration profiles
│   └── hwaccel.transcoding.yml
├── paperless-ngx/compose.yml  # Document management (+ Postgres, Redis, Gotenberg, Tika)
├── homepage/                  # Dashboard
│   ├── compose.yml
│   ├── .env                   # API keys for widgets (HOMEPAGE_VAR_*, gitignored)
│   └── config/                # Dashboard widget configs (services.yaml — gitignored, uses env substitution)
├── vaultwarden/compose.yml    # Password manager
├── infisical/compose.yml      # Secrets management (+ Postgres, Redis)
├── portainer/compose.yml      # Docker UI
├── dozzle/compose.yml         # Docker log viewer
├── beszel/compose.yml         # System monitoring — Beszel hub + agent (+ Discord alerting)
├── uptime-kuma/compose.yml    # Uptime monitoring
├── watchtower/compose.yml     # Auto-updates (daily at 06:00)
├── pihole/compose.yml         # DNS ad-blocking
├── gramps/compose.yml         # Genealogy (+ Redis, Celery worker)
├── stirling/compose.yml       # PDF tools
├── personal-blog/compose.yml  # Blog (wifsimster/wifsimster-blog) + GoatCounter analytics
├── resume/compose.yml         # Online resume (wifsimster/resume)
├── birthday-invitation/compose.yml
├── copro-pilot/compose.yml    # Co-ownership app (+ Postgres)
├── the-box/compose.yml        # Game management app (+ Postgres, Redis)
├── unifi/compose.yml          # Network controller
├── tinyauth/compose.yml       # tinyauth (steveiliop56/tinyauth:v5)
├── ntfy/compose.yml           # ntfy (binwiederhier/ntfy)
├── n8n/compose.yml            # n8n (+ Postgres)
├── litellm/compose.yml        # LiteLLM (berriai/litellm) (+ Postgres)
├── langfuse/compose.yml       # Langfuse web + worker (+ Postgres, ClickHouse, MinIO, Redis)
├── digest/compose.yml         # Static site (nginx:alpine)
├── discord-bridge/compose.yml # Built locally (build: .)
├── seaweedfs/compose.yml      # SeaweedFS (chrislusf/seaweedfs)
├── ghostfolio/compose.yml     # Ghostfolio (+ Postgres, Redis)
├── downtify/compose.yml       # henriquesebastiao/downtify
├── metube/compose.yml         # alexta69/metube
├── koe/compose.yml            # wifsimster/koe-server (+ Postgres)
├── racontine/compose.yml      # wifsimster/racontine-server + racontine-web (+ Postgres)
├── solopilot/compose.yml      # wifsimster/solopilot
├── toko/compose.yml           # wifsimster/toko (+ Postgres)
├── wawptn/compose.yml         # wifsimster/wawptn (+ Postgres)
├── tribu/compose.yml          # tribu + tribu-api (local builds)
├── umami/compose.yml          # Umami (+ Postgres)
├── yamtrack/compose.yml       # Yamtrack (+ Postgres, Redis)
├── tileserver/compose.yml     # maptiler/tileserver-gl
└── pg-backup/                 # Daily PostgreSQL backups
    ├── compose.yml            # postgres:17-alpine + crond
    ├── backup.sh              # Dump script (14 databases, 7-day retention)
    ├── crontab                # Schedule: daily at 03:00
    └── .env                   # DB credentials (gitignored)
```

## Commandes essentielles

Run these from `/opt/docker/<service-name>/` (see "Compose working directories" below).

```bash
# Démarrer un service
cd /opt/docker/<service-name> && docker compose up -d

# Arrêter un service
cd /opt/docker/<service-name> && docker compose down

# Voir les logs d'un service
cd /opt/docker/<service-name> && docker compose logs -f

# Mettre à jour les images
cd /opt/docker/<service-name> && docker compose pull && docker compose up -d

# Créer le réseau partagé (une seule fois)
docker network create lan
```

## Key Conventions

### Compose File Structure

Every service follows this pattern:

```yaml
name: service-name            # Top-level project name

services:
  service:
    container_name: service-name
    image: registry/image:tag
    restart: unless-stopped
    environment:
      - TZ=Europe/Paris
      - PUID=1000
      - PGID=1000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.<name>.entrypoints=websecure"
      - "traefik.http.routers.<name>.rule=Host(`<name>.battistella.ovh`)"
      - "traefik.http.services.<name>.loadBalancer.server.port=<port>"
      - "com.centurylinklabs.watchtower.enable=true"
    networks:
      lan:

networks:
  lan:
    external: true
```

### Naming

- **Directories**: lowercase, hyphen-separated (`home-assistant`, `paperless-ngx`)
- **Container names**: match the service/directory name
- **Domain pattern**: `<service>.battistella.ovh` (exceptions: `proxy.` for Traefik, `indexer.` for Prowlarr, `cv.` for Resume, `blog.` for Personal-blog)
- **Internal DNS**: `.internal` suffix for inter-container communication (e.g., `qbittorrent.internal`)

### Networking

- All services use the shared external Docker bridge network named `lan`
- Network is created manually: `docker network create lan`
- Exception: Plex uses `network_mode: host` (for DLNA discovery) and is routed via Traefik file provider instead of labels

### Environment Variables

- Sensitive values go in `.env` files (gitignored) next to each `compose.yml`
- Common variables: `TZ=Europe/Paris`, `PUID=1000`, `PGID=1000`
- Domain variable: `DOMAIN=battistella.ovh` (used in Traefik labels via interpolation)

### Databases

- PostgreSQL 16-Alpine for services needing relational storage (Paperless, Immich, The-box, Copro-Pilot, Infisical)
- Redis/Valkey for caching and task queues (Paperless, Immich, Gramps, The-box, Infisical)
- Healthchecks: `pg_isready` for Postgres, `redis-cli ping` for Redis
- Services use `depends_on` with `condition: service_healthy` for DB readiness

### Volumes

- Config data: relative paths from compose file (e.g., `./data` in `vaultwarden/compose.yml`, `./config` in `stirling/compose.yml`)
- Named Docker volumes: for databases and internal state (`pg_data`, `redis_data`)
- NFS mounts: single host-level mount at `/mnt/media` with subdirectories (`movies/`, `tv-shows/`, `downloads/`, `musics/`, `photos/`, `documents/`, `data/`)

### Restart Policies

- Standard: `restart: unless-stopped`
- Critical infrastructure: `restart: always` or `restart: on-failure:N` (rare)

## Git Tracking

The `.gitignore` uses an inverted pattern — it ignores everything, then whitelists:

```
*
!.gitignore
!*/
!**/compose.yml
!**/hwaccel.*.yml
```

`homepage/config/services.yaml` is **not tracked** — it contains `{{HOMEPAGE_VAR_*}}` template variables that Homepage resolves from environment variables at runtime. The actual secrets live in `homepage/.env` (gitignored). The `env_file` directive in `homepage/compose.yml` injects them into the container.

Runtime data, logs, certificates, `.env` files, and service-generated configs are all excluded.

## Workflow de développement

1. Modifier le `compose.yml` du service concerné
2. Appliquer avec `docker compose up -d` (depuis `/opt/docker/<service>/`)
3. Commiter le `compose.yml` modifié
4. Pas de pipeline CI/CD — le déploiement est manuel

## Common Tasks

### Adding a New Service

1. Create a directory: `mkdir <service-name>`
2. Create `<service-name>/compose.yml` following the conventions above
3. Include Traefik labels if the service needs external access
4. Include the Watchtower label for auto-updates
5. Add the service to the `lan` network
6. Create a `.env` file for secrets (will be gitignored automatically)
7. Update `README.md` stack table
8. Optionally add to `homepage/config/services.yaml` for dashboard visibility

### Modifying Traefik Labels

Labels follow a strict pattern. The router name in all labels must be consistent:
```yaml
- "traefik.http.routers.ROUTERNAME.entrypoints=websecure"
- "traefik.http.routers.ROUTERNAME.rule=Host(`subdomain.battistella.ovh`)"
- "traefik.http.services.ROUTERNAME.loadBalancer.server.port=PORT"
```

### Adding a Service with a Database

Follow the pattern in `paperless-ngx/compose.yml` or `the-box/compose.yml`:
- Add a `db` service (postgres:16-alpine) with healthcheck
- Add a `redis` service if caching is needed
- Use `depends_on` with health conditions
- Use named volumes for data persistence

## Important Notes

- **Pre-built images, except three stacks that build locally**: Almost every service uses a pre-built image. The exceptions build their own image: `discord-bridge` (`build: .`, `discord-bridge/Dockerfile`), `paperless-ngx`'s `protonmail-bridge` (`build: ./protonmail-bridge`), and `tribu` + `tribu-api` (built from `/home/wifsimster/tribu-src`, outside this repo). Do not create new Dockerfiles: use a pre-built image.
- **Build step only for those services**: For image-based services, changes take effect via `docker compose up -d`. For the local builds above, rebuild with `docker compose up -d --build`.
- **Secrets in `.env`**: Never hardcode passwords, API keys, or tokens in compose files. Use `${VARIABLE}` interpolation from `.env` files.
- **Image tags**: Most services use `:latest`. The multimedia stack (LinuxServer images) and some others may pin specific versions.
- **NFS storage**: All media is stored under a single NFS mount `/mnt/media` from Unraid (`192.168.0.240:/mnt/user/media`). Hardlinks work across all subdirectories.
- **Les hardlinks ne fonctionnent pas** entre partages NFS séparés
- **Domain**: The domain `battistella.ovh` is used throughout. Use `${DOMAIN}` variable where possible.
- **Homepage config**: `homepage/config/services.yaml` is gitignored and uses `{{HOMEPAGE_VAR_*}}` env substitution for secrets. Add new API keys to `homepage/.env` as `HOMEPAGE_VAR_<NAME>=<value>`, then reference them in `services.yaml` as `{{HOMEPAGE_VAR_<NAME>}}`.
- **Compose working directories**: Live compose projects with `.env` files are under `/opt/docker/<service>/`. The repo at `/home/wifsimster/docker-setup/` tracks only the compose files (gitignored `.env`). Always run `docker compose` from `/opt/docker/<service>/` to get the secrets, not from the repo clone.
- **matter-server healthcheck**: The `matter-server` container reports `unhealthy` because `nc` is missing from its image. This is a false negative — the service runs correctly. `homeassistant` must be started manually with `docker start homeassistant` if it fails on `depends_on` health check.

## GitHub Actions Runners

6 self-hosted runners are installed in `/opt/actions-runner/`, one per repo. They share a single set of binaries via **hardlinks** to save ~3.5 Go of disk space.

### Architecture

```
/opt/actions-runner/
├── copro-pilot/          # Binary source (bin.2.x.x/ and externals.2.x.x/ are real files)
├── personal-blog/        # bin/ and externals/ are hardlinks → copro-pilot/bin.2.x.x/
├── toko/                 # idem
├── resume/               # idem
├── wawptn/               # idem
└── x-ai-weekly-bot/      # idem
```

> **Do not use symlinks** for `bin/` and `externals/`. The runner resolves the real path and looks for `.runner`/`.credentials` in the symlink source directory, breaking independent registration. Use `cp -al` (hardlinks) instead.

### Re-registering a runner

```bash
# Get a registration token
TOKEN=$(gh api -X POST repos/Wifsimster/<repo>/actions/runners/registration-token -q '.token')

cd /opt/actions-runner/<dir>
sudo -u deploy ./svc.sh stop && sudo -u deploy ./svc.sh uninstall
rm -f .runner .credentials .credentials_rsaparams .runner_migrated .service .env .path
sudo -u deploy ./config.sh --url https://github.com/Wifsimster/<repo> --token $TOKEN \
  --name docker-server --labels self-hosted,linux,x64,docker --work _work --replace --unattended
./svc.sh install deploy && ./svc.sh start
```

### After a runner auto-update (new bin.2.x.x version)

Recreate hardlinks for secondary runners and delete the old version:

```bash
NEW="bin.2.334.0"   # adjust version
NEW_EXT="externals.2.334.0"

for d in personal-blog toko resume wawptn x-ai-weekly-bot; do
  rm -rf /opt/actions-runner/${d}/bin /opt/actions-runner/${d}/externals
  cp -al /opt/actions-runner/copro-pilot/${NEW} /opt/actions-runner/${d}/bin
  cp -al /opt/actions-runner/copro-pilot/${NEW_EXT} /opt/actions-runner/${d}/externals
done

# Once stable, delete old version from all runners
OLD="bin.2.333.0"
for d in copro-pilot personal-blog toko resume wawptn x-ai-weekly-bot; do
  rm -rf /opt/actions-runner/${d}/${OLD} /opt/actions-runner/${d}/externals${OLD#bin}
done
```

## Disk Space Management

### Current state (2026-03-29)
- Primary partition: 97 Go total, ~74 Go used (81%), ~19 Go free
- Docker images: ~43 Go (all active, cannot prune without stopping services)
- `/var/lib/containerd`: ~32 Go (shared layers with Docker/moby namespace)

### Automated cleanup

`/opt/docker/disk-cleanup.sh` runs every **Sunday at 03:00** (root crontab). It handles:
- Docker prune (dangling images, stopped containers, orphan volumes)
- Container log truncation (>50 Mo)
- Systemd journal vacuum (14 days / 500 Mo)
- APT cache clean
- Old rotated log files (>30 days)
- Runner `_work/_update` deduplication
- Old runner binary versions cleanup
- Aggressive mode if disk >90%

Logs: `/var/log/disk-cleanup.log`

### Manual cleanup triggers

```bash
# Quick Docker cleanup
sudo docker system prune --force

# Full cleanup script
sudo /opt/docker/disk-cleanup.sh

# Check disk usage breakdown
sudo docker system df
sudo du -sh /opt/actions-runner/*/ /var/lib/docker/ /var/log/
```
