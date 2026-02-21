# Multimedia Stack

Docker Compose stack for managing media acquisition, organization, and streaming.

## Services

| Service | Image | Port | URL | Description |
|---|---|---|---|---|
| **Plex** | `lscr.io/linuxserver/plex` | 32400 | `plex.battistella.ovh` | Media server for streaming movies, TV shows, and music |
| **Sonarr** | `lscr.io/linuxserver/sonarr` | 8989 | `sonarr.battistella.ovh` | TV show PVR and manager |
| **Radarr** | `lscr.io/linuxserver/radarr` | 7878 | `radarr.battistella.ovh` | Movie PVR and manager |
| **Lidarr** | `lscr.io/linuxserver/lidarr` | 8686 | `lidarr.battistella.ovh` | Music PVR and manager |
| **Bazarr** | `lscr.io/linuxserver/bazarr` | 6767 | `bazarr.battistella.ovh` | Subtitle manager for Sonarr and Radarr |
| **Prowlarr** | `lscr.io/linuxserver/prowlarr` | 9696 | `indexer.battistella.ovh` | Indexer manager for Sonarr, Radarr, and Lidarr |
| **qBittorrent** | `ghcr.io/hotio/qbittorrent` | 8080 | `qbittorrent.battistella.ovh` | BitTorrent client with built-in VPN (ProtonVPN) |
| **Seerr** | `ghcr.io/hotio/seerr` | 5055 | `seerr.battistella.ovh` | Media request and discovery manager |
| **Tautulli** | `lscr.io/linuxserver/tautulli` | 8181 | `tautulli.battistella.ovh` | Plex monitoring, analytics, and notifications |

## Architecture

```
                   ┌─────────────┐
                   │   Traefik   │
                   │ (reverse    │
                   │  proxy)     │
                   └──────┬──────┘
                          │
        ┌─────────────────┼─────────────────────┐
        │    lan network   │                     │
        │                  │                     │
   ┌────┴────┐  ┌─────────┴──────┐  ┌───────────┴──┐
   │ Seerr   │  │   *arr suite   │  │  qBittorrent │
   │ (request│  │ Sonarr, Radarr │  │  (VPN/WG)    │
   │ manager)│  │ Lidarr, Bazarr │  └───────┬──────┘
   └─────────┘  │ Prowlarr       │          │
                └───────┬────────┘    /mnt/downloads
                        │
                  ┌─────┴──────┐
                  │    Plex    │ ← host network
                  │  Tautulli  │   (port 32400)
                  └────────────┘
                        │
              /mnt/movies  /mnt/tv-shows  /mnt/musics
```

## Prerequisites

- Docker and Docker Compose
- An external Docker network named `lan` (`docker network create lan`)
- Traefik reverse proxy with:
  - Docker provider on the `lan` network
  - File provider for Plex routing (see [Plex & Traefik](#plex--traefik))
- Mount points: `/mnt/downloads`, `/mnt/movies`, `/mnt/tv-shows`, `/mnt/musics`
- A WireGuard config file for ProtonVPN in `./wireguard/wg0.conf`

## Quick Start

1. Copy the example environment file and edit it:
   ```bash
   cp .env.example .env
   nano .env
   ```

2. Place your WireGuard configuration at `./wireguard/wg0.conf`.

3. Start the stack:
   ```bash
   docker compose up -d
   ```

## Environment Variables

### Common

| Variable | Description | Default |
|---|---|---|
| `TZ` | Timezone | `Europe/Paris` |
| `PUID` | User ID for file permissions | `1000` |
| `PGID` | Group ID for file permissions | `1000` |
| `DOMAIN` | Base domain for Traefik routing | `battistella.ovh` |

### Media Paths

| Variable | Description | Default |
|---|---|---|
| `DOWNLOADS_LOCATION` | Download client output directory | `/mnt/downloads` |
| `TV_SHOWS_LOCATION` | TV shows library | `/mnt/tv-shows` |
| `MOVIES_LOCATION` | Movies library | `/mnt/movies` |
| `MUSIC_LOCATION` | Music library | `/mnt/musics` |

### Service Config Paths

Each service stores persistent data in a config directory relative to the compose file:

| Variable | Default |
|---|---|
| `BAZARR_CONFIG_PATH` | `../bazarr/data` |
| `LIDARR_CONFIG_PATH` | `../lidarr/config` |
| `SEERR_CONFIG_PATH` | `../overseerr/data` |
| `PLEX_CONFIG_PATH` | `../plex/library` |
| `PROWLARR_CONFIG_PATH` | `../prowlarr/data` |
| `RADARR_CONFIG_PATH` | `../radarr/data` |
| `SONARR_CONFIG_PATH` | `../sonarr/data` |
| `TAUTULLI_CONFIG_PATH` | `../tautulli/config` |
| `CONFIG_LOCATION` (qBittorrent) | `../qbittorrent/data` |

### qBittorrent / VPN

| Variable | Description | Default |
|---|---|---|
| `WEBUI_PORTS` | WebUI listen ports | `8080/tcp` |
| `LIBTORRENT` | libtorrent version | `v1` |
| `BT_PORT` | BitTorrent listen port (host) | `6881` |
| `VPN_ENABLED` | Enable WireGuard VPN | `true` |
| `VPN_CONF` | WireGuard config name | `wg0` |
| `VPN_PROVIDER` | VPN provider | `proton` |
| `VPN_LAN_NETWORK` | Local network CIDR (for bypass) | `192.168.1.0/24` |
| `VPN_AUTO_PORT_FORWARD` | Auto port forwarding | `true` |

### Plex

| Variable | Description | Default |
|---|---|---|
| `PLEX_VERSION` | Plex version type | `docker` |
| `PLEX_CLAIM` | Plex claim token (from plex.tv/claim) | — |

## Plex & Traefik

Plex runs with `network_mode: host` for DLNA and local discovery support. Because of this, Traefik cannot route to it via Docker labels. Instead, Plex is exposed through Traefik's **file provider**.

The route is defined in `traefik/config/plex.yml`:

```yaml
http:
  routers:
    plex:
      entryPoints:
        - websecure
      rule: "Host(`plex.battistella.ovh`)"
      service: plex
      tls:
        certResolver: letsencrypt

  services:
    plex:
      loadBalancer:
        servers:
          - url: "http://<HOST_IP>:32400"
```

Replace `<HOST_IP>` with the server's LAN IP address.

## Volume Mappings

Container paths follow official image documentation:

| Service | Config | Media / Data |
|---|---|---|
| Bazarr | `/config` | `/tv`, `/movies` |
| Lidarr | `/config` | `/music`, `/downloads` |
| Seerr | `/config` | — |
| Plex | `/config` | `/tv`, `/movies`, `/musics` |
| Prowlarr | `/config` | — |
| qBittorrent | `/config` | `/data/downloads` |
| Radarr | `/config` | `/movies`, `/downloads` |
| Sonarr | `/config` | `/tv`, `/downloads` |
| Tautulli | `/config` | `/logs` (Plex logs, read-only) |

## Networking

- All services (except Plex) are attached to the external `lan` Docker network, shared with Traefik.
- Plex uses `network_mode: host` for full host network access (required for DLNA discovery).
- qBittorrent routes all traffic through a WireGuard VPN tunnel (ProtonVPN). It has `NET_ADMIN` capability and a TUN device for VPN connectivity.

## Hardware Transcoding

Plex is configured with `/dev/dri` device passthrough for Intel QuickSync / VAAPI hardware transcoding. Ensure the `PUID` user has access to the render group on the host:

```bash
sudo usermod -aG render <username>
```

## Auto-Updates

All services have the Watchtower label `com.centurylinklabs.watchtower.enable=true` for automatic image updates.

## Useful Commands

```bash
# Start all services
docker compose up -d

# Restart a single service
docker compose restart sonarr

# View logs
docker compose logs -f radarr

# Pull latest images
docker compose pull

# Rebuild and restart
docker compose up -d --pull always
```
