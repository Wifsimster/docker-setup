# CLAUDE.md

Guide for AI assistants working with this repository.

## Project Overview

Self-hosted Docker infrastructure for a personal home server (Debian). ~30 services orchestrated with Docker Compose, exposed via Traefik reverse proxy with automatic HTTPS (Let's Encrypt / OVH DNS challenge). Media stored on an Unraid NAS via NFS mounts.

**This is a configuration-only repository** — no application source code, no build system, no tests, no CI/CD. All changes are Docker Compose files and supporting config.

## Repository Structure

```
docker-setup/
├── CLAUDE.md                  # This file
├── README.md                  # Infrastructure documentation
├── .gitignore                 # Tracks only compose.yml, hwaccel.*.yml, and CLAUDE.md
├── traefik/compose.yml        # Core: reverse proxy, TLS, Let's Encrypt (OVH DNS)
├── multimedia/                # Unified media stack (single compose project)
│   ├── compose.yml            # Plex, Sonarr, Radarr, Lidarr, Bazarr, Prowlarr,
│   │                          # qBittorrent (VPN), Seerr, Tautulli, Trotarr
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
├── netdata/compose.yml        # System monitoring (+ Discord alerting)
├── uptime-kuma/compose.yml    # Uptime monitoring
├── watchtower/compose.yml     # Auto-updates (daily at 06:00)
├── pihole/compose.yml         # DNS ad-blocking
├── gramps/compose.yml         # Genealogy (+ Redis, Celery worker)
├── memos/compose.yml          # Note-taking
├── wakapi/compose.yml         # Coding time tracking
├── stirling/compose.yml       # PDF tools
├── personal-blog/compose.yml  # Blog (wifsimster/wifsimster-blog)
├── resume/compose.yml         # Online resume (wifsimster/resume)
├── birthday-invitation/compose.yml
├── copro-pilot/compose.yml    # Co-ownership app (+ Postgres)
├── the-box/compose.yml        # Game management app (+ Postgres, Redis)
├── techney/compose.yml        # Tech documentation site
├── unifi/compose.yml          # Network controller
└── pg-backup/                 # Daily PostgreSQL backups
    ├── compose.yml            # postgres:16-alpine + crond
    ├── backup.sh              # Dump script (5 databases, 7-day retention)
    ├── crontab                # Schedule: daily at 03:00
    └── .env                   # DB credentials (gitignored)
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

- Config data: relative paths from compose file (e.g., `../bazarr/data`, `../plex/library`)
- Named Docker volumes: for databases and internal state (`pg_data`, `redis_data`)
- NFS mounts: host-level mounts under `/mnt/` (`/mnt/movies`, `/mnt/tv-shows`, `/mnt/downloads`, etc.)

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

- **No Dockerfiles**: All services use pre-built images. Do not create Dockerfiles.
- **No build step**: There is nothing to compile or build. Changes take effect via `docker compose up -d`.
- **Secrets in `.env`**: Never hardcode passwords, API keys, or tokens in compose files. Use `${VARIABLE}` interpolation from `.env` files.
- **Image tags**: Most services use `:latest`. The multimedia stack (LinuxServer images) and some others may pin specific versions.
- **NFS storage**: Media paths (`/mnt/*`) are NFS mounts from Unraid. Hardlinks don't work across separate NFS shares (see README TODO).
- **Domain**: The domain `battistella.ovh` is used throughout. Use `${DOMAIN}` variable where possible.
- **Homepage config**: `homepage/config/services.yaml` is gitignored and uses `{{HOMEPAGE_VAR_*}}` env substitution for secrets. Add new API keys to `homepage/.env` as `HOMEPAGE_VAR_<NAME>=<value>`, then reference them in `services.yaml` as `{{HOMEPAGE_VAR_<NAME>}}`.
