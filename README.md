# Docker Infrastructure

Self-hosted services running on a home server, orchestrated with Docker Compose and exposed via Traefik reverse proxy with automatic HTTPS (Let's Encrypt / OVH DNS challenge).

**Host:** Debian-based server  
**Domain:** `*.example.com`  
**Storage:** Unraid NAS via NFS mounts under `/mnt/`

## Architecture

```
Internet
   │
   ▼
[ Traefik ] ─── HTTPS *.example.com
   │
   ├── lan (Docker bridge network, shared by most services)
   │
   ├── Multimedia stack (single compose)
   │     qBittorrent (VPN) → Prowlarr → Radarr / Sonarr / Lidarr → Plex
   │     + Bazarr, Seerr, Tautulli, Trotarr
   │
   ├── Home Automation
   │     Home Assistant, Matter Server, Mosquitto (MQTT)
   │
   ├── Productivity / Tools
   │     Paperless-ngx, Stirling PDF, Memos, Wakapi, Gramps Web
   │
   ├── Web Apps
   │     Personal Blog, Resume, Birthday Invitation, Copro-Pilot, The Box
   │
   └── Infrastructure
         Portainer, Pi-hole (DNS), Watchtower, Dozzle, Netdata, Homepage
         Infisical (secrets), Vaultwarden (passwords), Unifi (network)
```

## Stacks

Each directory contains a `compose.yml` and optionally a `.env` file (gitignored).

| Stack | Description | Traefik |
|---|---|:---:|
| **traefik** | Reverse proxy, TLS termination, Let's Encrypt via OVH DNS | -- |
| **multimedia** | Unified media stack (see below) | Yes |
| **home-assistant** | Home automation + Matter + Mosquitto MQTT | Yes |
| **immich-app** | Photo/video management with ML | Yes |
| **paperless-ngx** | Document management & OCR | Yes |
| **pihole** | DNS ad-blocking | Yes |
| **vaultwarden** | Bitwarden-compatible password manager | Yes |
| **infisical** | Secrets management | Yes |
| **portainer** | Docker management UI | Yes |
| **dozzle** | Real-time Docker log viewer | Yes |
| **netdata** | System monitoring | Yes |
| **watchtower** | Automatic container updates | -- |
| **homepage** | Dashboard | Yes |
| **gramps** | Genealogy web app | Yes |
| **memos** | Note-taking | Yes |
| **wakapi** | Coding time tracking | Yes |
| **stirling** | PDF tools | Yes |
| **personal-blog** | Blog | Yes |
| **resume** | Online resume | Yes |
| **birthday-invitation** | Event invitation app | Yes |
| **copro-pilot** | Co-ownership management app (+ Postgres) | Yes |
| **the-box** | Web app (+ Postgres, Redis) | Yes |
| **techney** | Tech-related web app | Yes |
| **unifi** | Unifi network controller | Yes |

### Multimedia Stack

The multimedia stack is a single compose project grouping all media-related services. NFS-mounted storage from the Unraid NAS is used for media and downloads.

**Services:** qBittorrent (with WireGuard VPN), Prowlarr, Radarr, Sonarr, Lidarr, Bazarr, Seerr (Overseerr), Plex, Tautulli, Trotarr

**Volume convention:** All containers follow the `/data/` path convention per [Servarr Docker Guide](https://wiki.servarr.com/docker-guide) and [TRaSH Guides](https://trash-guides.info/Hardlinks/How-to-setup-for/Docker/):

| Container | Internal paths |
|---|---|
| qBittorrent | `/data/downloads` |
| Radarr | `/data/movies`, `/data/downloads` |
| Sonarr | `/data/tv`, `/data/downloads` |
| Lidarr | `/data/music`, `/data/downloads` |
| Bazarr | `/data/tv`, `/data/movies` |
| Plex | `/data/tv`, `/data/movies`, `/data/music` |

## Storage

Media is stored on an Unraid NAS and mounted via NFS:

| Host mount | NFS share | Purpose |
|---|---|---|
| `/mnt/downloads` | `/mnt/user/downloads` | Torrent downloads |
| `/mnt/movies` | `/mnt/user/movies` | Movie library |
| `/mnt/tv-shows` | `/mnt/user/tv-shows` | TV show library |
| `/mnt/musics` | `/mnt/user/musics` | Music library |
| `/mnt/photos` | `/mnt/user/photos` | Photo library (Immich) |
| `/mnt/documents` | `/mnt/user/documents` | Documents (Paperless) |
| `/mnt/data` | `/mnt/user/data` | General data |

## TODO: Enable Hardlinks & Atomic Moves on Unraid

Currently, each media type (downloads, movies, tv-shows, music) is exported as a **separate NFS share** from Unraid. This means hardlinks and atomic moves between downloads and media libraries **do not work** -- files are copied + deleted instead, which is slower and doubles disk usage temporarily.

### Why it matters

- **Hardlinks** allow a file to exist in both the download client directory and the media library without using extra disk space
- **Atomic moves** (instant file moves on the same filesystem) eliminate the slow copy+delete cycle
- Both require the source and destination to be on the **same filesystem**

### How to fix

1. **On Unraid:** Create a unified share structure under a single parent, for example `/mnt/user/data/`:
   ```
   /mnt/user/data/
   ├── torrents/
   │   ├── movies/
   │   ├── tv/
   │   └── music/
   └── media/
       ├── movies/
       ├── tv/
       └── music/
   ```

2. **On Unraid:** Export a single NFS share: `/mnt/user/data`

3. **On Docker host:** Replace individual NFS mounts with one:
   ```
   <NAS_IP>:/mnt/user/data  /mnt/data  nfs4  defaults,_netdev  0  0
   ```

4. **In `.env`:** Update paths to use the unified mount:
   ```env
   DOWNLOADS_LOCATION=/mnt/data/torrents
   TV_SHOWS_LOCATION=/mnt/data/media/tv
   MOVIES_LOCATION=/mnt/data/media/movies
   MUSIC_LOCATION=/mnt/data/media/music
   ```

5. **In qBittorrent UI:** Set download path to `/data/torrents`

6. **In Radarr/Sonarr/Lidarr UI:** Root folders become `/data/media/movies`, `/data/media/tv`, `/data/media/music`

### References

- [Servarr Docker Guide](https://wiki.servarr.com/docker-guide)
- [TRaSH Guides - Hardlinks & Atomic Moves](https://trash-guides.info/Hardlinks/Hardlinks-and-Instant-Moves/)
- [TRaSH Guides - Docker Setup](https://trash-guides.info/Hardlinks/How-to-setup-for/Docker/)

## Networking

- Most services join the `lan` external Docker bridge network
- Traefik discovers services via Docker labels
- Plex uses `network_mode: host` for DLNA/discovery
- qBittorrent routes traffic through a WireGuard VPN with `NET_ADMIN` capability
- Inter-container DNS uses the `.internal` suffix (e.g., `qbittorrent.internal`)

## Git

The `.gitignore` tracks only compose files and hardware acceleration configs. All runtime data, configs, secrets, and `.env` files are excluded.

```gitignore
*
!.gitignore
!*/
!**/compose.yml
!**/hwaccel.*.yml
```
