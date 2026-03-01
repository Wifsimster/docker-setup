# 🏠 Home Server Platform

> Plateforme auto-hébergée · ~30 services Docker · Debian · HTTPS automatique via `*.example.com`

Streaming multimédia, domotique, gestion documentaire, galerie photo et outils de productivité — accessible partout, 100% sous votre contrôle.

---

## 🎯 Ce que ça fait

| | Fonctionnalité | Description |
|---|---|---|
| 🎬 | **Streaming multimédia** | Films, séries, musique en streaming avec téléchargement automatisé |
| 📱 | **Demandes de contenu** | Les utilisateurs demandent, le système télécharge automatiquement |
| 🏡 | **Maison connectée** | Contrôle des appareils Matter, MQTT et Zigbee |
| 📸 | **Galerie photo IA** | Reconnaissance faciale et recherche intelligente |
| 📄 | **GED intelligente** | Numérisation OCR et classement automatique |
| 🔐 | **Sécurité** | Mots de passe, secrets, blocage pub DNS |
| 📊 | **Supervision 24/7** | Métriques, logs, alertes Discord, mises à jour auto |

---

## 🏗️ Architecture

```mermaid
graph TB
    Internet((🌐 Internet)) -->|HTTPS| Traefik[🔀 Traefik]
    Traefik --> Media[🎬 Média]
    Traefik --> Home[🏡 Domotique]
    Traefik --> Photos[📸 Photos & Docs]
    Traefik --> Apps[🌐 Apps web]
    Traefik --> Tools[🔧 Outils]
    Traefik --> Sec[🔐 Sécurité]
    Traefik --> Ops[📊 Supervision]

    NAS[(💾 NAS Unraid)] -.->|NFS| Media
    NAS -.->|NFS| Photos
```

---

## 🎬 Média & Divertissement

```mermaid
graph LR
    U[👤 Utilisateur] -->|Demande| Seerr
    Seerr -->|Séries| Sonarr
    Seerr -->|Films| Radarr
    Sonarr & Radarr & Lidarr --> Prowlarr
    Prowlarr --> qBit[qBittorrent + VPN 🔒]
    qBit --> Plex[🎬 Plex]
    Bazarr -.->|Sous-titres| Plex
    Tautulli -.->|Stats| Plex
    U -->|Regarde| Plex
```

| Service | Rôle | URL |
|---|---|---|
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/plex.svg" width="16"/> **Plex** | Streaming films, séries, musique | `plex.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/overseerr.svg" width="16"/> **Seerr** | Demande et découverte de contenu | `seerr.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/sonarr.svg" width="16"/> **Sonarr** | Gestion automatisée des séries | `sonarr.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/radarr.svg" width="16"/> **Radarr** | Gestion automatisée des films | `radarr.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/lidarr.svg" width="16"/> **Lidarr** | Gestion automatisée de la musique | `lidarr.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/bazarr.svg" width="16"/> **Bazarr** | Sous-titres automatiques | `bazarr.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/prowlarr.svg" width="16"/> **Prowlarr** | Gestion des indexeurs | `indexer.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/qbittorrent.svg" width="16"/> **qBittorrent** | Téléchargement (VPN intégré) | `qbittorrent.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/tautulli.svg" width="16"/> **Tautulli** | Statistiques Plex | `tautulli.example.com` |

---

## 🏡 Domotique

```mermaid
graph TB
    HA[🏡 Home Assistant] --> Matter[Matter Server]
    HA --> MQTT[🔌 Mosquitto MQTT]
    Matter --> D1([💡 Appareils Matter])
    MQTT --> D2([🌡️ Capteurs MQTT])
    HA --> D3([📡 Zigbee & autres])
```

| Service | Rôle | URL |
|---|---|---|
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/home-assistant.svg" width="16"/> **Home Assistant** | Hub domotique centralisé | `home-assistant.example.com` |
| 🔌 **Mosquitto** | Broker MQTT | _interne_ |
| 🔗 **Matter Server** | Protocole Matter | _interne_ |

---

## 📸 Photos & Documents

```mermaid
graph LR
    P([📸 Photos]) -->|Import| Immich
    Immich -->|🤖 IA| Reco[Reconnaissance faciale]
    D([📄 Documents]) -->|Scan| Paperless[Paperless-ngx]
    Paperless -->|OCR| Class[📁 Classement auto]
```

| Service | Rôle | URL |
|---|---|---|
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/immich.svg" width="16"/> **Immich** | Galerie photo avec IA | `immich.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/paperless-ngx.svg" width="16"/> **Paperless-ngx** | GED avec OCR | `paperless.example.com` |

---

## 🌐 Applications personnelles

| Service | Rôle | URL |
|---|---|---|
| ✍️ **Blog** | Blog personnel | `blog.example.com` |
| 📋 **CV en ligne** | Curriculum vitae interactif | `cv.example.com` |
| 🏢 **Copro-Pilot** | Gestion de copropriété | `copro-pilot.example.com` |
| 🎲 **The Box** | Collection de jeux | `the-box.example.com` |

---

## 🔧 Outils de productivité

| Service | Rôle | URL |
|---|---|---|
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/stirling-pdf.svg" width="16"/> **Stirling PDF** | Manipulation PDF | `stirling.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/memos.svg" width="16"/> **Memos** | Notes rapides | `memos.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/wakapi.svg" width="16"/> **Wakapi** | Suivi temps de dev | `wakapi.example.com` |
| 🌳 **Gramps Web** | Généalogie | `gramps.example.com` |

---

## 🔐 Sécurité

| Service | Rôle | URL |
|---|---|---|
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/vaultwarden.svg" width="16"/> **Vaultwarden** | Mots de passe (Bitwarden) | `vaultwarden.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/infisical.svg" width="16"/> **Infisical** | Secrets applicatifs | `infisical.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/pi-hole.svg" width="16"/> **Pi-hole** | Blocage pub DNS | `pihole.example.com` |

> 🔒 Les secrets (`.env`) ne sont jamais commités. Homepage utilise `{{HOMEPAGE_VAR_*}}` pour la substitution d'environnement.

---

## 📊 Supervision & Opérations

```mermaid
graph LR
    Homepage[📊 Homepage] -->|Dashboard| S([Services])
    Beszel[📈 Beszel] -->|Métriques| Srv([Serveur])
    Beszel -->|⚠️ Alertes| Discord([💬 Discord])
    Watchtower[🔄 Watchtower] -->|MAJ 6h| S
    Watchtower -->|📢 Notif| Discord
    UptimeKuma[⏱️ Uptime Kuma] -->|Ping| S
    PgBackup[💾 pg-backup] -->|Dump 3h| DB[(🐘 PostgreSQL x5)]
```

| Service | Rôle | URL |
|---|---|---|
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/homepage.svg" width="16"/> **Homepage** | Tableau de bord | `homepage.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/beszel.svg" width="16"/> **Beszel** | Métriques système + alertes Discord | `beszel.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/uptime-kuma.svg" width="16"/> **Uptime Kuma** | Surveillance disponibilité | `uptime.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/portainer.svg" width="16"/> **Portainer** | Gestion Docker | `portainer.example.com` |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/dozzle.svg" width="16"/> **Dozzle** | Logs temps réel | `dozzle.example.com` |
| 🔄 **Watchtower** | MAJ auto quotidiennes + alertes Discord | _arrière-plan_ |
| 💾 **pg-backup** | Backup PostgreSQL (5 bases, rétention 7j) | _arrière-plan_ |
| <img src="https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/svg/unifi.svg" width="16"/> **Unifi** | Contrôleur réseau | `unifi.example.com` |

---

## 🚀 Déploiement

```mermaid
graph LR
    Dev[👨‍💻 Dev] -->|compose.yml| Git[📦 Git]
    Dev -->|docker compose up -d| Server[🖥️ Serveur]
    Watchtower[🔄 Watchtower] -->|MAJ 6h| Server
    LE[🔒 Let's Encrypt] -.->|TLS| Traefik[🔀 Traefik]
    OVH -.->|DNS Challenge| LE
```

> Pas de CI/CD — déploiement manuel `docker compose up -d`. Watchtower met à jour les images quotidiennement.

---

## ⚙️ Stack technique

| Composant | Technologie |
|---|---|
| 🐳 Orchestration | Docker + Docker Compose |
| 🔀 Proxy inverse | Traefik v3.6 (Let's Encrypt / OVH DNS) |
| 🐘 Bases de données | PostgreSQL 16, Redis / Valkey |
| 💾 Sauvegarde | pg-backup — dump quotidien 3h, rétention 7j |
| 📁 Stockage | NAS Unraid via NFS |
| 📊 Supervision | Beszel, Uptime Kuma, Dozzle, Portainer, Homepage |
| 🔒 Sécurité | `no-new-privileges`, réseaux internes isolés |
| 🌐 Domaine | `example.com` (sous-domaine par service) |

---

## 💾 Backup PostgreSQL

| Base | Conteneur source |
|---|---|
| 📄 Paperless | `paperless-db` |
| 📸 Immich | `immich_postgres` |
| 🎲 The Box | `the-box-postgres` |
| 🏢 Copro-Pilot | `copro-pilot-postgres` |
| 🔐 Infisical | `infisical-db` |

> ⏰ Dump quotidien à 3h · Format `pg_dump -Fc` · Rétention 7 jours · Restauration via `pg_restore`

---

## 🗺️ Feuille de route

### 🔴 Haute priorité

- **Stockage NAS unifié** — Consolider les montages NFS (hardlinks + déplacements instantanés)
- **Sauvegardes off-site** — Réplication vers S3 / Backblaze B2 / second NAS
- **Tests de restauration** — Validation mensuelle de l'intégrité des backups

### 🟡 Moyenne priorité

- **Secrets centralisés** — Migration `.env` → Infisical (rotation auto)
- **Monitoring TLS** — Alerte avant expiration des certificats
- **Sauvegardes Redis** — Ajouter Redis (Immich, Paperless) au plan de backup

### 🟢 Basse priorité

- **Images versionnées** — Tags fixes sur les services critiques
- **Read-only rootfs** — `read_only: true` sur les conteneurs stateless

### ✅ Terminé

- ~~Rate limiting Vaultwarden~~ · ~~Uptime Kuma~~ · ~~Alertes Beszel → Discord~~
- ~~Healthchecks universels~~ · ~~Limites mémoire~~ · ~~Rotation des logs~~
- ~~Domaine variable~~ · ~~Nettoyage labels Traefik~~ · ~~Sécurité conteneurs~~
- ~~Isolation réseau~~ · ~~Alertes backup Discord~~ · ~~Documentation DR~~

---

## 📚 Documentation

| Document | Description |
|---|---|
| 📖 [Stack Multimédia](multimedia/README.md) | Architecture de la pile multimédia |
| 🔀 [Traefik](docs/traefik.md) | Proxy inverse, TLS, middlewares |
| 💾 [Stockage NFS](docs/stockage-nfs.md) | Montages Unraid, limitations |
| ➕ [Ajout d'un service](docs/ajout-service.md) | Guide pas à pas |
| 🐘 [Bases de données](docs/bases-de-donnees.md) | PostgreSQL, Redis, healthchecks |
| 🚨 [Reprise après sinistre](docs/reprise-sinistre.md) | Runbook de restauration |
| 🤖 [CLAUDE.md](CLAUDE.md) | Guide pour assistants IA |
