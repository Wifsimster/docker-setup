# Agents IA Homelab — Rapport complet (v5)

> Stack autonome, observable, auto-hébergé sur Proxmox / Docker / UniFi
> Damien Battistella — Mars 2026
> **Mis à jour le 30 mars 2026 — Étapes 1, 2 et 3 déployées**

---

## 1. Objectifs et contraintes

**But :** déployer une équipe d'agents IA autonomes sur le homelab existant, avec une maîtrise totale de chaque brique, un monitoring continu de l'état des agents, et un système de notifications push pour garder l'observabilité à tout moment.

**Contraintes :**
- Mise en place 100 % en autonomie, pas de SaaS obligatoire
- Tout en Docker sur Proxmox, pas de dépendance externe hors API LLM
- Observabilité complète : traces, coûts, erreurs, latence, état des agents
- Notifications push en temps réel sur mobile (pas de dépendance Discord/Slack)
- Budget maîtrisé : seul coût variable = tokens API cloud

**Infra existante :**
- Proxmox VE sur Debian, kernel 6.x-pve
- AMD Ryzen 5 3600 (6c/12t), 24 Gi RAM allouée à la VM Docker
- VM Docker : Ubuntu 24.04, 12 vCPU, 24 Gi RAM, 146 Go disque
- UniFi avec VLAN, SSID "Domotic" (2.4 GHz)
- NAS Unraid 26 To NFS (192.168.0.240:/mnt/user/media) monté sur `/mnt/media`
- 29 services Docker déjà en production (voir section 2)
- Pas de GPU dédié (RTX 2070 passthrough abandonné — IOMMU partagé)

---

## 2. État actuel de l'infra — Audit du 29 mars 2026

### Ressources système

| Métrique | Valeur |
|----------|--------|
| Disque total | 146 Go |
| Disque utilisé | 74 Go (53%) |
| Disque libre | 66 Go |
| RAM totale | 24 Gi |
| RAM utilisée | 9.1 Gi |
| RAM disponible | 15 Gi |
| Swap | 8 Gi (0 utilisé) |
| vCPU | 12 |

### Services Docker existants (29 services)

#### Infrastructure & réseau

| Service | Image | Rôle |
|---------|-------|------|
| Traefik | `traefik` | Reverse proxy, TLS Let's Encrypt (OVH DNS) |
| Pi-hole | `pihole` | DNS ad-blocking (port 53) |
| UniFi | `unifi-network-application` | Contrôleur réseau UniFi |
| Portainer | `portainer-ce` | Interface Docker web |
| Dozzle | `amir20/dozzle` | Visualiseur de logs Docker |

#### Monitoring & maintenance

| Service | Image | Rôle |
|---------|-------|------|
| Uptime Kuma | `louislam/uptime-kuma:1` | Monitoring uptime des services |
| Beszel | `beszel` (hub + agent) | Monitoring système (CPU, RAM, disque) + alertes Discord |
| Watchtower | `containrrr/watchtower` | Auto-update images Docker (cron quotidien 06:00) |
| pg-backup | `postgres:16-alpine` + crond | Backup PostgreSQL quotidien (03:00), 5 bases, rétention 7 jours |
| Homepage | `gethomepage/homepage` | Dashboard avec widgets |

#### Multimédia

| Service | Image | Rôle |
|---------|-------|------|
| Plex | `plexinc/pms-docker` | Media server (mode host) |
| Sonarr | `linuxserver/sonarr` | Gestion séries TV |
| Radarr | `linuxserver/radarr` | Gestion films |
| Lidarr | `linuxserver/lidarr` | Gestion musique |
| Bazarr | `linuxserver/bazarr` | Sous-titres |
| Prowlarr | `linuxserver/prowlarr` | Indexeurs |
| qBittorrent | `ghcr.io/hotio/qbittorrent` | Téléchargement (VPN intégré) |
| Seerr | `seerr` | Requêtes média |
| Tautulli | `tautulli` | Statistiques Plex |
| Trotarr | `trotarr` | Gestion automatisée |

#### Domotique

| Service | Image | Rôle |
|---------|-------|------|
| Home Assistant | `homeassistant` | Hub domotique (mode host) |
| Mosquitto | `eclipse-mosquitto` | Broker MQTT |
| Matter Server | `matter-server` | Protocole Matter |

#### Applications

| Service | Image | Rôle |
|---------|-------|------|
| Immich | `immich` + PostgreSQL + Valkey | Photos/vidéos avec ML |
| Paperless-NGX | `paperless-ngx` + PostgreSQL + Redis + Gotenberg + Tika | GED |
| Vaultwarden | `vaultwarden/server` | Gestionnaire de mots de passe |
| Infisical | `infisical` + PostgreSQL + Redis | Gestion des secrets |
| Memos | `memos` | Prise de notes |
| Wakapi | `wakapi` | Suivi temps de code |
| Stirling | `stirling-pdf` | Outils PDF |
| Gramps | `gramps-web` + Redis + Celery | Généalogie |

#### Projets personnels

| Service | Image | Rôle |
|---------|-------|------|
| Personal Blog | `wifsimster/wifsimster-blog` | Blog (blog.battistella.ovh) |
| Resume | `wifsimster/resume` | CV en ligne (cv.battistella.ovh) |
| Copro-Pilot | `wifsimster/copro-pilot` + PostgreSQL | App copropriété |
| The-Box | `wifsimster/the-box` + PostgreSQL + Redis | App jeux |
| Wawptn | `wifsimster/wawptn` + PostgreSQL + Discord bot | Stats de jeu |
| Toko | `wifsimster/toko` + PostgreSQL | Suivi achievements |
| Birthday Invitation | `birthday-invitation` | App RSVP |
| X-AI-Weekly-Bot | `x-ai-weekly-bot` | Bot X/Twitter IA |

### Infrastructure connexe

- **Réseau Docker :** bridge externe `lan` partagé par tous les services
- **NFS :** `/mnt/media` → sous-dossiers `movies/`, `tv-shows/`, `downloads/`, `musics/`, `photos/`, `documents/`, `data/`
- **GitHub Actions :** 6 self-hosted runners dans `/opt/actions-runner/` (hardlinks)
- **Nettoyage automatique :** `/opt/docker/disk-cleanup.sh` chaque dimanche 03:00
- **Domaine :** `battistella.ovh` (Traefik + Let's Encrypt + OVH DNS challenge)
- **Bases PostgreSQL existantes :** Immich, Paperless, Infisical, The-Box, Copro-Pilot, Toko, Wawptn

---

## 3. Architecture cible du stack IA

```
┌─────────────────────────────────────────────────────────────────┐
│                        TÉLÉPHONE                                │
│            ntfy app (push natif + envoi messages)                │
│            "Ajoute ce film" → topic chat → réponse agent        │
└──────────────────────────┬──────────┬──────────────────────────┘
                   publish │          │ push réponse
┌──────────────────────────▼──────────▼──────────────────────────┐
│  COUCHE CONVERSATION     │  ntfy (self-hosted, port 2586)       │
│  (bidirectionnelle)      │  Topics: chat, media, home, docs,    │
│                          │  infra, agents, briefing, costs,     │
│                          │  urgent, domotique                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │ webhook + HTTP POST
┌──────────────────────────▼──────────────────────────────────────┐
│  COUCHE OBSERVABILITÉ    │  Uptime Kuma (existant)              │
│                          │  Beszel (existant)                   │
│                          │  Langfuse (traces + coûts)           │
└──────────────────────────┬──────────────────────────────────────┘
                           │ callbacks
┌──────────────────────────▼──────────────────────────────────────┐
│  COUCHE ORCHESTRATION    │  n8n (port 5678) — agents + workflows│
│                          │  Agent Chat (classifier + routing)   │
│                          │  Agents spécialisés (media, home,    │
│                          │  docs, infra, notes, général)        │
└──────────┬───────────────┼───────────────┬──────────────────────┘
           │               │               │
           ▼               ▼               ▼
┌──────────────┐ ┌─────────────────┐ ┌────────────────────────┐
│ PROXY LLM    │ │ SERVICES DOCKER │ │ INTERFACE WEB          │
│ LiteLLM 4000 │ │ Sonarr, Radarr  │ │ Open WebUI (port 3000) │
│ → Haiku      │ │ Plex, Tautulli  │ │ Chat, RAG, PWA mobile  │
│ → Sonnet     │ │ Home Assistant  │ └────────────────────────┘
│ → fallback   │ │ Paperless, Immich│
│ Cost tracking│ │ Beszel, Portainer│
└──────────────┘ │ Memos, Pi-hole  │
                 └─────────────────┘
```

**Changements vs plan initial :**
- Pas d'Ollama (pas de GPU, CPU trop lent pour 14b)
- Pas de Dify (trop lourd, redondant avec Open WebUI + n8n)
- Langfuse déployé en étape 3 (traces + coûts)
- Uptime Kuma et Beszel déjà en place — pas à déployer
- Traefik déjà en place comme reverse proxy (pas besoin de Caddy)
- pg-backup déjà en place pour les sauvegardes PostgreSQL
- Réseau `lan` existant (pas besoin de créer un réseau `ai-stack`)
- **ntfy devient bidirectionnel** : pas juste des notifications push, mais une interface de conversation avec les agents via topics

---

## 4. Tarifs API LLM (mars 2026)

| Modèle | Input/MTok | Output/MTok | Contexte | Rôle dans le stack |
|--------|-----------|------------|----------|-------------------|
| Claude Haiku 4.5 | $1 | $5 | 200K | Triage, classification, tri email |
| Claude Sonnet 4.6 | $3 | $15 | 1M | Raisonnement, tool-calling, agents |
| Claude Opus 4.6 | $5 | $25 | 1M | Tâches flagship (optionnel) |
| GPT-4o (fallback) | $5 | $15 | 128K | Backup via LiteLLM |

**Optimisations intégrées à LiteLLM :** prompt caching (−90 % input), batch API (−50 %), routage automatique Haiku/Sonnet selon la complexité.

---

## 5. Les briques à déployer — détail

### 5.1 LiteLLM — Proxy LLM unifié

**Rôle :** point d'entrée unique pour TOUS les appels LLM. Chaque service (n8n, Open WebUI) pointe vers `http://litellm:4000` au lieu d'appeler directement Anthropic/OpenAI. Ça permet de changer de modèle, ajouter du fallback, et tracker les coûts sans toucher aux agents.

| | |
|---|---|
| Image Docker | `docker.litellm.ai/berriai/litellm-database:main-stable` |
| Port | 4000 |
| Dépendances | PostgreSQL (tracking coûts), Redis (optionnel, cache) |
| Licence | MIT |

**Config clé :**
```yaml
model_list:
  - model_name: sonnet
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: haiku
    litellm_params:
      model: anthropic/claude-haiku-4-5
      api_key: os.environ/ANTHROPIC_API_KEY

litellm_settings:
  drop_params: true

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/DATABASE_URL
```

**Pourquoi c'est critique :** sans LiteLLM, chaque service a sa propre config API, ses propres clés, et tu perds la vue consolidée des coûts. Avec LiteLLM, tu as UN dashboard de dépenses, UN point de fallback, et UN endroit pour changer de modèle.

**Intégration infra existante :**
- Exposé via Traefik (`litellm.battistella.ovh`)
- PostgreSQL dédié ou base dans un PostgreSQL existant
- Rejoint le réseau `lan`
- Labels Watchtower pour auto-update

### 5.2 n8n — Orchestration des agents

**Rôle :** cerveau opérationnel. Chaque agent est un workflow visuel qui combine un LLM (via LiteLLM), des outils (HTTP, SSH, DB, Home Assistant), et de la mémoire. Le pattern ReAct (raisonnement → action → observation → boucle) est natif.

| | |
|---|---|
| Image Docker | `n8nio/n8n:latest` |
| Port | 5678 |
| Dépendances | PostgreSQL (persistance workflows) |
| Licence | Fair-code (Apache 2.0 + restrictions commerciales) |
| Intégrations | 400+ connecteurs natifs |

**Agents concrets à déployer :**

1. **Agent triage email** — trigger Gmail → classification Haiku → routage par catégorie → notification ntfy si urgent
2. **Agent monitoring infra** — cron → query Beszel API → vérification seuils disque/RAM/containers → alerte ntfy si dépassé
3. **Agent veille techno** — cron hebdo → recherche web → synthèse Sonnet → envoi résumé par ntfy/email
4. **Agent domotique** — webhook Home Assistant → analyse Haiku → action HA → notification état
5. **Agent briefing matinal** — cron 7h → agrège météo + calendrier + emails prioritaires + état infra via Beszel → envoie résumé ntfy

### 5.3 Open WebUI — Interface chat

**Rôle :** interface quotidienne de chat, connectée à LiteLLM comme backend OpenAI-compatible. Accès à tous les modèles cloud depuis un seul endroit, avec RAG, function calling, et historique.

| | |
|---|---|
| Image Docker | `ghcr.io/open-webui/open-webui:main` |
| Port | 3000 |
| Licence | Propriétaire (usage libre) |

**Points clés :**
- PWA installable sur mobile → accès chat IA depuis n'importe où
- Model Builder → créer des "personnages" agents avec system prompts dédiés
- Python tools natifs → écrire des fonctions custom
- Pipelines → rate limiting, logging, filtres
- Exposé via Traefik (`chat.battistella.ovh` ou `ai.battistella.ovh`)

### 5.4 ntfy — Notifications push auto-hébergées

**Rôle :** service de notifications pub/sub ultra-léger. Tout ce qui peut faire un `curl` peut envoyer une notification. App mobile Android/iOS pour les recevoir en push.

| | |
|---|---|
| Image Docker | `binwiederhier/ntfy` |
| Port | 2586 |
| RAM | ~30 Mo |
| Licence | Apache 2.0 + GPL |

**Topics à créer :**

| Topic | Source | Priorité | Contenu |
|-------|--------|----------|---------|
| `agents` | n8n workflows | Normale | Résultats des agents, tâches terminées |
| `infra` | Uptime Kuma + Beszel | Haute | Service down, disque plein, RAM critique |
| `domotique` | Home Assistant + n8n | Normale | Événements domotiques IA |
| `briefing` | Agent briefing n8n | Basse | Résumé matinal quotidien |
| `costs` | LiteLLM | Normale | Alerte si budget API dépassé |
| `urgent` | Tous | Urgente | Alertes critiques cross-système |

**Config Docker :**
```yaml
ntfy:
  image: binwiederhier/ntfy:latest
  container_name: ntfy
  restart: unless-stopped
  command: serve
  environment:
    - TZ=Europe/Paris
    - NTFY_AUTH_DEFAULT_ACCESS=deny-all
    - NTFY_AUTH_FILE=/var/lib/ntfy/auth.db
    - NTFY_BEHIND_PROXY=true
    - NTFY_BASE_URL=https://ntfy.battistella.ovh
  volumes:
    - ntfy-cache:/var/cache/ntfy
    - ntfy-auth:/var/lib/ntfy
  labels:
    - "traefik.enable=true"
    - "traefik.http.routers.ntfy.entrypoints=websecure"
    - "traefik.http.routers.ntfy.rule=Host(`ntfy.battistella.ovh`)"
    - "traefik.http.services.ntfy.loadBalancer.server.port=80"
    - "com.centurylinklabs.watchtower.enable=true"
  networks:
    lan:
```

---

## 6. Inventaire Docker — Stack IA à ajouter

| Service | Port | Image | RAM estimée | Rôle |
|---------|------|-------|-------------|------|
| LiteLLM | 4000 | `litellm-database:main-stable` | ~200 Mo | Proxy LLM + coûts |
| Open WebUI | 3000 | `open-webui/open-webui:main` | ~300 Mo | Interface chat |
| n8n | 5678 | `n8nio/n8n:latest` | ~300 Mo | Orchestration agents |
| ntfy | 2586 | `binwiederhier/ntfy` | ~30 Mo | Notifications push |
| PostgreSQL (IA) | 5433 | `postgres:16-alpine` | ~200 Mo | Persistance LiteLLM + n8n |

**Total à ajouter : ~1 Go RAM** (sur 15 Gi disponibles)

**Pas besoin de déployer (déjà en place) :**
- Traefik (reverse proxy + TLS)
- Uptime Kuma (health monitoring)
- Beszel (monitoring système)
- Watchtower (auto-update)
- pg-backup (backups PostgreSQL — à configurer pour les nouvelles bases)

### Services reportés (ajout futur conditionnel)

| Service | RAM | Condition d'ajout |
|---------|-----|-------------------|
| Langfuse + ClickHouse | ~1.5 Go | Phase 3, quand 2-3 agents sont stables |
| Ollama (qwen2.5:7b) | ~5 Go | Si besoin offline/privé confirmé, accepter la lenteur CPU |
| Dify + Qdrant | ~3 Go | Si Open WebUI RAG insuffisant pour les docs |

---

## 7. Budget mensuel

| Poste | Coût/mois | Notes |
|-------|----------|-------|
| Infrastructure Proxmox | 0 € | Déjà en place |
| Tous les logiciels | 0 € | Open-source, self-hosted |
| Anthropic API (modéré) | 8–20 € | ~500 appels Sonnet + triage Haiku |
| Anthropic API (intensif) | 30–50 € | Multi-agents actifs, RAG, automatisations |
| OpenAI fallback | 0–5 € | Optionnel |
| **TOTAL** | **8–55 €/mois** | **Seul coût = tokens API** |

---

## 8. Plan de déploiement

### ~~Étape 0 — Auditer l'infra (FAIT ✅)~~

- [x] Inventorier les 29 services Docker existants
- [x] Vérifier les ressources disponibles (15 Gi RAM libre, 66 Go disque libre)
- [x] Confirmer Traefik, Uptime Kuma, Beszel, pg-backup déjà en place
- [x] Identifier le réseau `lan` comme réseau cible (pas besoin de `ai-stack`)

### ~~Étape 1 — Stack minimal viable (FAIT ✅)~~

- [x] Déployer LiteLLM + PostgreSQL avec config Anthropic (Haiku + Sonnet)
- [x] Déployer Open WebUI pointant vers LiteLLM (`https://ai.battistella.ovh`)
- [x] Déployer ntfy, créer admin + 6 topics (infra, agents, domotique, briefing, costs, urgent)
- [x] Déployer n8n + PostgreSQL (`https://n8n.battistella.ovh`)
- [x] Ajouter les nouvelles bases dans pg-backup
- [x] Ajouter 4 monitors dans Uptime Kuma (LiteLLM, Open WebUI, n8n, ntfy)
- [x] Connecter les 33 monitors Uptime Kuma → ntfy topic `infra`
- [x] Ajouter section "IA" dans Homepage (4 services)
- [x] Test : chat Open WebUI → LiteLLM → Anthropic ✅
- [x] Test : notification ntfy → réception mobile ✅

### ~~Étape 2 — Premiers agents (FAIT ✅)~~

- [x] Agent Monitoring Infra : cron 5 min → health checks LiteLLM/OpenWebUI/ntfy → ntfy `infra`
- [x] Agent Triage Email : Gmail trigger → Haiku classification → ntfy `urgent`/`agents`
- [x] Agent Briefing Matinal : cron 7h → météo (Open-Meteo) + état infra → ntfy `briefing`
- [x] Agent Veille Techno : cron lundi 8h → HN + Reddit + Lobsters → Sonnet résumé → ntfy `agents`
- [x] Agent Domotique : webhook n8n → Haiku analyse → ntfy `domotique`
- [x] Connecter Home Assistant → n8n via `rest_command` (porte/fenêtre ouverte, batterie faible)
- [x] Installer ntfy sur mobile, souscrire aux 6 topics ✅

### ~~Étape 3 — Observabilité avancée (FAIT ✅)~~

- [x] Déployer Langfuse v3 (web + worker + PostgreSQL + ClickHouse + Redis + MinIO)
- [x] Ajouter `success_callback: ["langfuse"]` et `failure_callback: ["langfuse"]` dans LiteLLM
- [x] Créer workflow n8n "Agent Suivi Coûts API" : cron 20h → LiteLLM spend API → ntfy `costs`/`urgent`
- [x] Ajouter Langfuse dans Uptime Kuma + ntfy
- [x] Ajouter Langfuse dans Homepage section IA
- [x] Ajouter langfuse-db dans pg-backup

### Étape 4 — Agents conversationnels via ntfy

> **Objectif final :** pouvoir discuter avec des agents IA depuis le téléphone via ntfy. Envoyer un message en langage naturel sur un topic, un agent le traite, interroge les services Docker existants, et répond sur le même topic.

#### 4.1 Architecture conversationnelle

```
┌─────────────────────────────────────────────────────────────────┐
│  TÉLÉPHONE — ntfy app                                           │
│  ► Envoyer un message sur topic `chat`                          │
│  ► Recevoir la réponse de l'agent sur le même topic             │
└──────────────────────────┬──────────┬──────────────────────────┘
                   publish │          │ push réponse
┌──────────────────────────▼──────────▼──────────────────────────┐
│  ntfy (self-hosted)                                             │
│  Topic `chat` — bidirectionnel (user ↔ agent)                   │
│  Topics spécialisés : `media`, `home`, `docs`, `infra`          │
└──────────────────────────┬──────────────────────────────────────┘
                           │ webhook POST sur message reçu
┌──────────────────────────▼──────────────────────────────────────┐
│  n8n — Webhook Trigger                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  1. Réception message utilisateur                        │    │
│  │  2. Classification intention (Haiku) → routing           │    │
│  │  3. Exécution agent spécialisé (Sonnet + tools)          │    │
│  │  4. Appel API services Docker concernés                  │    │
│  │  5. Réponse formatée → POST ntfy                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│              ┌────────────┼────────────┐                         │
│              ▼            ▼            ▼                          │
│     Services Docker  LiteLLM    Home Assistant                   │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.2 Inventaire des APIs Docker accessibles par les agents

Tous les services sont joignables depuis n8n via le réseau Docker `lan` (DNS interne).

**Multimédia**

| Service | URL interne | API | Cas d'usage agent |
|---------|-------------|-----|-------------------|
| Plex | `http://plex:32400` | REST | "Qu'est-ce qui tourne sur Plex ?", stats sessions |
| Sonarr | `http://sonarr:8989/api/v3/` | REST + API key | "Quelles séries arrivent cette semaine ?", ajouter une série |
| Radarr | `http://radarr:7878/api/v3/` | REST + API key | "Ajoute ce film", "Combien de films en attente ?" |
| Lidarr | `http://lidarr:8686/api/v1/` | REST + API key | "Ajoute cet artiste", état des téléchargements |
| Prowlarr | `http://prowlarr:9696/api/v1/` | REST + API key | Recherche indexeurs |
| Seerr | `http://seerr:5055/api/v1/` | REST + API key | "Demande ce film/série", liste des requêtes |
| qBittorrent | `http://qbittorrent:8080/api/v2/` | REST + session | "Quels torrents en cours ?", vitesse, pause/resume |
| Tautulli | `http://tautulli:8181/api/v2/` | REST + API key | "Qui regarde quoi ?", historique, stats |

**Domotique**

| Service | URL interne | API | Cas d'usage agent |
|---------|-------------|-----|-------------------|
| Home Assistant | `http://homeassistant:8123/api/` | REST + Bearer token | "Allume le salon", "Quelle température ?", états capteurs |
| Mosquitto | `mqtt://mosquitto:1883` | MQTT | Pub/sub événements IoT |

**Documents & Photos**

| Service | URL interne | API | Cas d'usage agent |
|---------|-------------|-----|-------------------|
| Immich | `http://immich_server:2283/api/` | REST + API key | "Combien de photos ce mois ?", recherche, albums |
| Paperless-NGX | `http://paperless-webserver:8000/api/` | REST + token | "Trouve ma facture EDF", recherche documents, tags |

**Infrastructure & Monitoring**

| Service | URL interne | API | Cas d'usage agent |
|---------|-------------|-----|-------------------|
| Uptime Kuma | `http://uptime-kuma:3001/api/` | REST | "Quel service est down ?", statut monitors |
| Beszel | `http://beszel:8090/api/` | REST | "Combien de RAM libre ?", état CPU/disque |
| Pi-hole | `http://pihole:80/admin/api.php` | REST + API key | "Combien de requêtes bloquées ?", stats DNS |
| Portainer | `http://portainer:9000/api/` | REST + JWT | "Liste les containers", restart service |

**Notes & Outils**

| Service | URL interne | API | Cas d'usage agent |
|---------|-------------|-----|-------------------|
| Memos | `http://memos:5230/api/v1/` | REST | "Note ça", "Quelles notes récentes ?", créer/lister memos |

**Stack IA**

| Service | URL interne | API | Cas d'usage agent |
|---------|-------------|-----|-------------------|
| LiteLLM | `http://litellm:4000/v1/` | OpenAI-compatible | Chat completions, coûts, modèles |
| Langfuse | `http://langfuse-web:3000/api/` | REST | Traces, coûts, scores |

#### 4.3 Workflow n8n — Agent Conversationnel (nouveau)

**Nom :** `Agent Chat ntfy`
**Trigger :** Webhook déclenché par ntfy sur réception de message topic `chat`

**Flux :**

```
ntfy message reçu (webhook)
    │
    ▼
Extraire texte + metadata (topic source, user)
    │
    ▼
Classifier l'intention avec Haiku
    │  → media : Sonarr/Radarr/Plex/Tautulli
    │  → home  : Home Assistant
    │  → docs  : Paperless-NGX/Immich
    │  → infra : Beszel/Uptime Kuma/Portainer
    │  → notes : Memos
    │  → general : question libre → Sonnet
    │
    ▼
Exécuter l'agent spécialisé (Sonnet + tool-calling)
    │  → Appels HTTP aux APIs Docker internes
    │  → Agrégation des résultats
    │
    ▼
Formater la réponse (concise, mobile-friendly)
    │
    ▼
POST réponse sur ntfy topic `chat`
```

**Configuration ntfy requise :**
- Activer les webhooks sortants sur le topic `chat` → `https://n8n.battistella.ovh/webhook/ntfy-chat`
- Créer un token d'accès read/write pour le topic `chat` côté n8n
- Optionnel : topics spécialisés (`media`, `home`, `docs`, `infra`) pour des conversations thématiques

#### 4.4 Agents spécialisés à créer

| Agent | Topic ntfy | Services interrogés | Exemples de commandes |
|-------|-----------|---------------------|----------------------|
| **Agent Média** | `chat` / `media` | Sonarr, Radarr, Plex, Tautulli, Seerr, qBittorrent | "Ajoute Breaking Bad", "Quels films sortent cette semaine ?", "Qui regarde Plex ?" |
| **Agent Maison** | `chat` / `home` | Home Assistant, Mosquitto | "Allume la lumière du salon", "Température extérieure ?", "Ferme le volet" |
| **Agent Documents** | `chat` / `docs` | Paperless-NGX, Immich | "Trouve ma facture Free de janvier", "Combien de photos cette semaine ?" |
| **Agent Infra** | `chat` / `infra` | Beszel, Uptime Kuma, Portainer, Pi-hole | "État du serveur ?", "Redémarre Plex", "Combien de requêtes DNS bloquées ?" |
| **Agent Notes** | `chat` / `notes` | Memos | "Note : appeler plombier demain", "Quelles notes cette semaine ?" |
| **Agent Général** | `chat` | LiteLLM (Sonnet) | Questions libres, résumés, aide rédaction |

#### 4.5 Gestion du contexte conversationnel

Pour garder une mémoire de conversation (multi-tours) :
- **Option A — n8n + code node :** stocker les N derniers messages par user dans une variable n8n ou Redis (léger, rapide)
- **Option B — PostgreSQL :** table `chat_history(id, user, topic, role, content, timestamp)` dans la base n8n, fenêtre glissante de 10 messages
- **Option C — Memos comme mémoire :** chaque échange est sauvé comme memo tagué `#chat`, l'agent peut relire le contexte récent

**Recommandation :** Option B (PostgreSQL) — la base n8n-db existe déjà, pas de service supplémentaire.

#### 4.6 Sécurité

- ntfy auth `deny-all` déjà en place → seuls les users avec token peuvent publier
- n8n webhook protégé par un secret header (`X-Webhook-Secret`)
- Les API keys des services (Sonarr, Radarr, HA token, etc.) stockées dans n8n Credentials
- Rate limiting côté n8n : max 10 messages/minute par user pour éviter les abus de tokens
- Actions destructives (restart container, supprimer document) → demander confirmation avant exécution

#### 4.7 Tâches de déploiement

- [ ] Créer le topic `chat` dans ntfy avec accès read/write pour l'user mobile
- [ ] Configurer ntfy pour envoyer un webhook à n8n sur chaque message reçu sur `chat`
- [ ] Créer le workflow n8n "Agent Chat ntfy" avec le webhook trigger
- [ ] Implémenter le classifier d'intention (Haiku) avec routing vers sous-workflows
- [ ] Créer les credentials n8n pour chaque service (API keys Sonarr, Radarr, HA token, etc.)
- [ ] Implémenter l'agent Média (Sonarr + Radarr + Plex + Tautulli)
- [ ] Implémenter l'agent Maison (Home Assistant REST API)
- [ ] Implémenter l'agent Documents (Paperless-NGX + Immich)
- [ ] Implémenter l'agent Infra (Beszel + Uptime Kuma + Portainer)
- [ ] Implémenter l'agent Notes (Memos)
- [ ] Ajouter la table `chat_history` dans n8n-db pour le contexte multi-tours
- [ ] Tester le flux complet : message ntfy → agent → réponse ntfy
- [ ] Ajouter le monitor "Agent Chat" dans Uptime Kuma
- [ ] Documenter les commandes disponibles par agent

### Étape 5 — RAG et agents avancés (optionnel)

> Conditionnel : seulement si Open WebUI RAG ne suffit pas

1. Déployer Dify + Qdrant
2. Uploader la documentation Hexagone/Hexaflux
3. Assistant property management (documents locatifs, ALUR, charges)

### ~~Étape 6 — LLM local (FAIT ✅)~~

> Déployé le 2026-03-30

1. ~~Déployer Ollama avec `qwen2.5:7b` (pas 14b — trop lent en CPU)~~ → `/opt/docker/ollama/`
2. ~~Ajouter le modèle local dans LiteLLM~~ → `ollama/qwen2.5:7b` disponible via LiteLLM proxy
3. Cas d'usage : embeddings locaux, tâches privées, fallback offline — modèle accessible dans Open WebUI

### Phase continue — Consolidation

- Affiner les system prompts selon les retours
- Ajouter des agents selon les besoins (veille techno, gestion locative, etc.)
- Monitorer les coûts dans LiteLLM/Langfuse et optimiser le routing Haiku/Sonnet
- Documenter chaque workflow pour pouvoir reconstruire en cas de rebuild

---

## 9. Résumé des choix

| Besoin | Solution | Pourquoi |
|--------|----------|----------|
| Reverse proxy + TLS | Traefik | **Déjà en place**, Let's Encrypt + OVH DNS |
| Proxy LLM unifié | LiteLLM | Multi-provider, cost tracking, fallback, MIT |
| Orchestration agents | n8n | GUI visuelle, 400+ intégrations, ReAct natif |
| Interface chat | Open WebUI | Référence du marché, PWA, function calling |
| Health monitoring | Uptime Kuma | **Déjà en place**, intégration ntfy native, MIT |
| Monitoring système | Beszel | **Déjà en place**, CPU/RAM/disque + alertes |
| Auto-update | Watchtower | **Déjà en place**, cron quotidien |
| Backup PostgreSQL | pg-backup | **Déjà en place**, à étendre aux nouvelles bases |
| Notifications push | ntfy | Auto-hébergé, 30 Mo RAM, app mobile, Apache 2.0 |
| Interface conversationnelle | ntfy (bidirectionnel) | Pas besoin d'app custom, ntfy = chat mobile natif |
| Accès services Docker | n8n + APIs REST | 20+ services exposent une API, n8n les orchestre |
| LLM cloud | Anthropic (Haiku/Sonnet) | Meilleur tool-calling, 1M contexte, coût OK |
| **Reporté** | Ollama | Pas de GPU, CPU lent — à évaluer plus tard |
| **Reporté** | Dify | Lourd, redondant avec Open WebUI + n8n |

---

*Rapport v5 — Mis à jour le 30 mars 2026. Étapes 1-3 déployées. Étape 4 planifiée : agents conversationnels via ntfy avec accès aux 20+ services Docker existants.*
