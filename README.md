# Home Server Platform

A self-hosted personal cloud running ~30 services on a Debian home server, providing media streaming, smart home control, document management, photo storage, and more — all accessible via `*.battistella.ovh` with automatic HTTPS.

## Platform Overview

```mermaid
graph TB
    Internet((Internet)) -->|HTTPS| Traefik[Traefik Reverse Proxy]
    Traefik --> Media[Media & Entertainment]
    Traefik --> Home[Smart Home]
    Traefik --> Docs[Photos & Documents]
    Traefik --> Apps[Web Applications]
    Traefik --> Tools[Productivity Tools]
    Traefik --> Sec[Security]
    Traefik --> Ops[Operations]

    NAS[(Unraid NAS)] -.->|NFS| Media
    NAS -.->|NFS| Docs

    style Internet fill:#f9f,stroke:#333
    style Traefik fill:#2196F3,color:#fff,stroke:#333
    style NAS fill:#FF9800,color:#fff,stroke:#333
    style Media fill:#E91E63,color:#fff
    style Home fill:#4CAF50,color:#fff
    style Docs fill:#9C27B0,color:#fff
    style Apps fill:#00BCD4,color:#fff
    style Tools fill:#FFC107,color:#000
    style Sec fill:#F44336,color:#fff
    style Ops fill:#607D8B,color:#fff
```

## Media & Entertainment

Stream movies, TV shows, and music. Discover and request new content. Everything is automated — from search to download to subtitles.

```mermaid
graph LR
    User([User]) -->|Request content| Seerr
    Seerr -->|TV shows| Sonarr
    Seerr -->|Movies| Radarr
    Sonarr --> Prowlarr[Prowlarr<br>Indexer]
    Radarr --> Prowlarr
    Lidarr[Lidarr<br>Music] --> Prowlarr
    Prowlarr -->|Search| qBit[qBittorrent<br>+ VPN]
    qBit -->|Downloaded| Sonarr
    qBit -->|Downloaded| Radarr
    qBit -->|Downloaded| Lidarr
    Sonarr -->|Organized| Plex
    Radarr -->|Organized| Plex
    Lidarr -->|Organized| Plex
    Bazarr -.->|Subtitles| Sonarr
    Bazarr -.->|Subtitles| Radarr
    Tautulli -.->|Analytics| Plex
    User -->|Watch| Plex

    style User fill:#fff,stroke:#333
    style Plex fill:#E5A00D,color:#000
    style Seerr fill:#2196F3,color:#fff
    style qBit fill:#F44336,color:#fff
```

| Service | What it does | URL |
|---|---|---|
| **Plex** | Stream movies, TV shows, and music | `plex.battistella.ovh` |
| **Seerr** | Request and discover new content | `seerr.battistella.ovh` |
| **Sonarr** | Automate TV show acquisition | `sonarr.battistella.ovh` |
| **Radarr** | Automate movie acquisition | `radarr.battistella.ovh` |
| **Lidarr** | Automate music acquisition | `lidarr.battistella.ovh` |
| **Bazarr** | Automatic subtitle downloads | `bazarr.battistella.ovh` |
| **Prowlarr** | Manage search indexers | `indexer.battistella.ovh` |
| **qBittorrent** | Download client (VPN-protected) | `qbittorrent.battistella.ovh` |
| **Tautulli** | Plex usage analytics and stats | `tautulli.battistella.ovh` |

## Smart Home

Control and automate home devices through a central hub supporting Matter, MQTT, Zigbee, and more.

```mermaid
graph TB
    HA[Home Assistant] --> Matter[Matter Server]
    HA --> MQTT[Mosquitto MQTT]
    Matter --> Devices1([Matter Devices])
    MQTT --> Devices2([MQTT Devices])
    HA --> Devices3([Zigbee / Other])

    style HA fill:#18BCF2,color:#fff
    style Matter fill:#4CAF50,color:#fff
    style MQTT fill:#8BC34A,color:#fff
```

| Service | What it does | URL |
|---|---|---|
| **Home Assistant** | Smart home hub and automation | `home-assistant.battistella.ovh` |
| **Mosquitto** | MQTT message broker for IoT devices | _internal_ |
| **Matter Server** | Matter protocol support | _internal_ |

## Photos & Documents

Store and organize photos with AI-powered search and face recognition. Manage paperwork with OCR and automated sorting.

```mermaid
graph LR
    Photos([Photos]) -->|Upload| Immich
    Immich -->|ML| Recognition[Face Recognition<br>& Smart Search]
    Documents([Documents]) -->|Scan / Import| Paperless[Paperless-ngx]
    Paperless -->|OCR| Classified[Auto-classified<br>& Searchable]
    Email([ProtonMail]) -.->|Import| Paperless

    style Immich fill:#9C27B0,color:#fff
    style Paperless fill:#4CAF50,color:#fff
    style Recognition fill:#E1BEE7
    style Classified fill:#C8E6C9
```

| Service | What it does | URL |
|---|---|---|
| **Immich** | Photo & video management with AI | `immich.battistella.ovh` |
| **Paperless-ngx** | Document management with OCR | `paperless.battistella.ovh` |

## Web Applications

Custom-built web apps for personal use.

| Service | What it does | URL |
|---|---|---|
| **Personal Blog** | Blog | `blog.battistella.ovh` |
| **Resume** | Online CV | `cv.battistella.ovh` |
| **Copro-Pilot** | Co-ownership management | `copro-pilot.battistella.ovh` |
| **The Box** | Game collection manager | `the-box.battistella.ovh` |
| **Techney** | Tech documentation site | `techney.battistella.ovh` |
| **Birthday Invitation** | Event invitations with RSVP | `leo-birthday.battistella.ovh` |

## Productivity Tools

| Service | What it does | URL |
|---|---|---|
| **Stirling PDF** | PDF manipulation tools (merge, split, convert…) | `stirling.battistella.ovh` |
| **Memos** | Quick notes and snippets | `memos.battistella.ovh` |
| **Wakapi** | Coding time tracking | `wakapi.battistella.ovh` |
| **Gramps Web** | Genealogy and family tree | `gramps.battistella.ovh` |

## Security

| Service | What it does | URL |
|---|---|---|
| **Vaultwarden** | Password manager (Bitwarden-compatible) | `vaultwarden.battistella.ovh` |
| **Infisical** | Secrets and environment variable management | `infisical.battistella.ovh` |
| **Pi-hole** | Network-wide DNS ad-blocking | `pihole.battistella.ovh` |

## Operations & Monitoring

```mermaid
graph LR
    Homepage[Homepage<br>Dashboard] -->|Overview| Services([All Services])
    Watchtower -->|Daily auto-updates| Services
    Watchtower -->|Notifications| Discord([Discord])
    Portainer -->|Container management| Services
    Dozzle -->|Live logs| Services
    Netdata -->|System metrics| Server([Server Health])
    Unifi -->|Network management| Network([WiFi & Network])

    style Homepage fill:#2196F3,color:#fff
    style Watchtower fill:#4CAF50,color:#fff
    style Discord fill:#5865F2,color:#fff
```

| Service | What it does | URL |
|---|---|---|
| **Homepage** | Central dashboard for all services | `homepage.battistella.ovh` |
| **Portainer** | Docker container management UI | `portainer.battistella.ovh` |
| **Dozzle** | Real-time container log viewer | `dozzle.battistella.ovh` |
| **Netdata** | Server performance monitoring | `netdata.battistella.ovh` |
| **Watchtower** | Automatic daily container updates (→ Discord alerts) | _background_ |
| **Unifi** | Network controller (WiFi, switches) | _local access_ |

## How It All Connects

```mermaid
graph TB
    subgraph External
        Internet((Internet))
        LetsEncrypt[Let's Encrypt]
        OVH[OVH DNS]
    end

    subgraph Server [Debian Home Server]
        Traefik[Traefik<br>Reverse Proxy]
        subgraph Services [~30 Containers]
            S1[Media Stack]
            S2[Smart Home]
            S3[Photos & Docs]
            S4[Web Apps]
            S5[Tools]
            S6[Monitoring]
        end
    end

    subgraph Storage [Unraid NAS]
        Movies[(Movies)]
        TV[(TV Shows)]
        Music[(Music)]
        Photos[(Photos)]
        Docs[(Documents)]
    end

    Internet -->|HTTPS| Traefik
    LetsEncrypt -.->|TLS Certs| Traefik
    OVH -.->|DNS Challenge| LetsEncrypt
    Traefik --> Services
    Storage -.->|NFS| Services

    style Internet fill:#f9f,stroke:#333
    style Traefik fill:#2196F3,color:#fff
    style Server fill:#E3F2FD,stroke:#2196F3
    style Storage fill:#FFF3E0,stroke:#FF9800
    style Services fill:#E8EAF6,stroke:#3F51B5
```

## Roadmap

- **Unified NAS storage** — Consolidate NFS mounts into a single share to enable hardlinks and instant file moves (faster imports, no temporary disk usage doubling)
