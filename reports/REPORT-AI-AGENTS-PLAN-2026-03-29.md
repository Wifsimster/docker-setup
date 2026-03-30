# Agents IA Homelab — Rapport complet (v8)

> Stack autonome, observable, auto-hébergé sur Proxmox / Docker / UniFi
> Damien Battistella — Mars 2026
> **Mis à jour le 30 mars 2026 — Étapes 1, 2, 3, 4 et 6 déployées ✅**

---

## 1. Objectifs et contraintes

**But :** déployer une équipe d'agents IA autonomes sur le homelab existant, avec une maîtrise totale de chaque brique, un monitoring continu de l'état des agents, et un système de notifications push pour garder l'observabilité à tout moment.

**Contraintes :**
- Mise en place 100 % en autonomie, pas de SaaS obligatoire
- Tout en Docker sur Proxmox, pas de dépendance externe hors API LLM
- Observabilité complète : traces, coûts, erreurs, latence, état des agents
- Notifications et conversations centralisées sur Discord (mobile + desktop)
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

## 2. État actuel de l'infra — Mis à jour le 30 mars 2026

### Ressources système

| Métrique | Valeur |
|----------|--------|
| Disque total | 146 Go |
| Disque utilisé | 104 Go (75%) |
| Disque libre | 37 Go |
| RAM totale | 24 Gi |
| RAM utilisée | 15 Gi |
| RAM disponible | 9.8 Gi |
| Swap | 8 Gi |
| vCPU | 12 |

### Services Docker en production (35+ services, 70+ containers)

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

#### Stack IA (ajouté mars 2026) ✅

| Service | Image | Rôle |
|---------|-------|------|
| LiteLLM | `ghcr.io/berriai/litellm:main-stable` + PostgreSQL | Proxy LLM unifié (Haiku, Sonnet, qwen2.5:7b) |
| Open WebUI | `ghcr.io/open-webui/open-webui:main` | Interface chat IA (ai.battistella.ovh) |
| n8n | `n8nio/n8n:latest` + PostgreSQL | Orchestration 6 agents + workflows |
| Langfuse | `langfuse/langfuse:3` + worker + PostgreSQL + ClickHouse + MinIO + Redis | Observabilité LLM (traces, coûts) |
| Ollama | `ollama/ollama:latest` | LLM local qwen2.5:7b (CPU, 4.5 Go) |
| discord-bridge | Python discord.py (custom) | Bot Jarvis — écoute Discord → forward n8n |

### Infrastructure connexe

- **Réseau Docker :** bridge externe `lan` partagé par tous les services
- **NFS :** `/mnt/media` → sous-dossiers `movies/`, `tv-shows/`, `downloads/`, `musics/`, `photos/`, `documents/`, `data/`
- **GitHub Actions :** 6 self-hosted runners dans `/opt/actions-runner/` (hardlinks)
- **Nettoyage automatique :** `/opt/docker/disk-cleanup.sh` chaque dimanche 03:00
- **Domaine :** `battistella.ovh` (Traefik + Let's Encrypt + OVH DNS challenge)
- **Bases PostgreSQL :** Immich, Paperless, Infisical, The-Box, Copro-Pilot, Toko, Wawptn, LiteLLM, n8n, Langfuse

---

## 3. Architecture cible du stack IA

```
┌─────────────────────────────────────────────────────────────────┐
│                   TÉLÉPHONE / DESKTOP                           │
│                    Discord app (bot Jarvis)                     │
│   #chat #media #maison #docs #infra #briefing #alerts #veille   │
└──────────────────────────┬──────────────────────────────────────┘
                           │ discord-bridge (Python)
                           │ → POST webhook n8n
┌──────▼──────────────────────────────────────────────────────────┐
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
- Ollama déployé avec `qwen2.5:7b` (4-bit, CPU) — pas de 14b (trop lent)
- Pas de Dify (trop lourd, redondant avec Open WebUI + n8n)
- Langfuse déployé en étape 3 (traces + coûts)
- Uptime Kuma et Beszel déjà en place — pas à déployer
- Traefik déjà en place comme reverse proxy (pas besoin de Caddy)
- pg-backup étendu aux nouvelles bases (LiteLLM, n8n, Langfuse)
- Réseau `lan` existant (pas besoin de créer un réseau `ai-stack`)
- **Discord comme interface conversationnelle** : bot Jarvis (discord-bridge) écoute #chat #media #maison #docs #infra → forward vers n8n webhook → Sonnet → réponse Discord
- n8n node discordTrigger absent → bridge Python discord.py (`discord-bridge` container) comme forwarder léger

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

1. **Agent triage email** — trigger Gmail → classification Haiku → routage par catégorie → résumé Discord `#chat`
2. **Agent monitoring infra** — cron 5 min → health checks services → alerte Discord `#alerts` si anomalie
3. **Agent veille techno** — cron lundi 8h → HN + Reddit + Lobsters → synthèse Sonnet → Discord `#veille`
4. **Agent domotique** — webhook Home Assistant → analyse Haiku → Discord `#maison`
5. **Agent briefing matinal** — cron 7h → météo + état infra → Discord `#briefing`
6. **Agent Chat Discord** — bot Jarvis écoute #chat #media #maison #docs #infra → Sonnet → réponse dans le channel source

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

### 5.4 Discord — Interface unique (notifications + conversations)

**Rôle :** interface centrale pour toutes les interactions avec les agents. Discord remplace ntfy pour les notifications — les agents postent directement dans les channels dédiés. ntfy est conservé en service mais n'est plus utilisé par les workflows IA.

| Channel | Source | Contenu |
|---------|--------|---------|
| `#chat` | Agent Chat (Sonnet) | Questions libres, conversation générale |
| `#media` | Agent Média | Sonarr/Radarr/Plex, requêtes contenu |
| `#maison` | Agent Maison | Home Assistant, domotique |
| `#docs` | Agent Documents | Paperless, Immich |
| `#infra` | Agent Infra + Monitoring | Beszel, Uptime Kuma, alertes infra |
| `#briefing` | Agent Briefing | Résumé matinal quotidien (cron 7h) |
| `#alerts` | Agent Monitoring | Alertes infra automatiques (cron 5 min) |
| `#veille` | Agent Veille Techno | Résumé hebdo actualités IA (lundi 8h) |

---

## 6. Inventaire Docker — Stack IA à ajouter

| Service | Port | Image | RAM estimée | Rôle |
|---------|------|-------|-------------|------|
| LiteLLM | 4000 | `litellm-database:main-stable` | ~200 Mo | Proxy LLM + coûts |
| Open WebUI | 3000 | `open-webui/open-webui:main` | ~300 Mo | Interface chat |
| n8n | 5678 | `n8nio/n8n:latest` | ~300 Mo | Orchestration agents |
| discord-bridge | — | Python discord.py (custom) | ~50 Mo | Bot Jarvis → forward n8n |
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
- [x] ~~ntfy~~ retiré — remplacé par Discord
- [x] Déployer n8n + PostgreSQL (`https://n8n.battistella.ovh`)
- [x] Ajouter les nouvelles bases dans pg-backup
- [x] Ajouter 4 monitors dans Uptime Kuma (LiteLLM, Open WebUI, n8n, ntfy)
- [x] Ajouter section "IA" dans Homepage (4 services)
- [x] Test : chat Open WebUI → LiteLLM → Anthropic ✅
- [x] Test : notification Discord → réception mobile ✅

### ~~Étape 2 — Premiers agents (FAIT ✅)~~

- [x] Agent Monitoring Infra : cron 5 min → health checks LiteLLM/OpenWebUI → Discord `#alerts`
- [x] Agent Triage Email : Gmail trigger → Haiku classification → Discord `#chat`
- [x] Agent Briefing Matinal : cron 7h → météo (Open-Meteo) + état infra → Discord `#briefing`
- [x] Agent Veille Techno : cron lundi 8h → HN + Reddit + Lobsters → Sonnet résumé → Discord `#veille`
- [x] Agent Domotique : webhook n8n → Haiku analyse → Discord `#maison`
- [x] Connecter Home Assistant → n8n via `rest_command` (porte/fenêtre ouverte, batterie faible)
- [x] Discord mobile configuré — bot Jarvis actif sur serveur beta ✅

### ~~Étape 3 — Observabilité avancée (FAIT ✅)~~

- [x] Déployer Langfuse v3 (web + worker + PostgreSQL + ClickHouse + Redis + MinIO)
- [x] Ajouter `success_callback: ["langfuse"]` et `failure_callback: ["langfuse"]` dans LiteLLM
- [x] Créer workflow n8n "Agent Suivi Coûts API" : cron 20h → LiteLLM spend API → Discord `#infra`
- [x] Ajouter Langfuse dans Uptime Kuma
- [x] Ajouter Langfuse dans Homepage section IA
- [x] Ajouter langfuse-db dans pg-backup

### ~~Étape 4 — Agents conversationnels via Discord (FAIT ✅)~~

> Déployé le 2026-03-30

> **Objectif final :** discuter avec des agents IA depuis Discord (mobile/desktop). Envoyer un message en langage naturel dans un channel, un agent le traite, interroge les services Docker existants, et répond dans le même channel. Discord remplace ntfy comme interface bidirectionnelle — ntfy reste pour les alertes push légères.

#### 4.1 Pourquoi Discord plutôt que ntfy

| Critère | Discord ✅ | ntfy ❌ |
|---------|-----------|---------|
| Webhooks natifs n8n | Oui (trigger natif) | Non (besoin forwarder SSE) |
| Historique conversation | Oui (dans le channel) | Non |
| Threading / channels | Oui | Non |
| Réponses formatées | Embeds, code blocks, boutons | Texte brut |
| UI mobile | App native excellente | App notifications only |
| Multi-channel par domaine | `#media`, `#maison`, etc. | Topics séparés sans UI |
| Infrastructure | 0 container supplémentaire | Forwarder SSE requis |

#### 4.2 Architecture conversationnelle

```
┌─────────────────────────────────────────────────────────────────┐
│  TÉLÉPHONE / DESKTOP — Discord app                              │
│  ► Message dans #media, #maison, #docs, #infra, #chat           │
│  ► Réponse de l'agent dans le même channel (avec historique)    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Discord Trigger (n8n natif)
┌──────────────────────────▼──────────────────────────────────────┐
│  n8n — Discord Trigger                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  1. Réception message (channel source = contexte)        │    │
│  │  2. Ignorer les messages du bot (éviter boucles)         │    │
│  │  3. Classification intention (Haiku) si #chat général    │    │
│  │  4. Routing vers agent spécialisé selon channel/intent   │    │
│  │  5. Exécution agent (Sonnet + appels API Docker)         │    │
│  │  6. Réponse formatée → Discord Send Message              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│              ┌────────────┼────────────┐                         │
│              ▼            ▼            ▼                          │
│     Services Docker  LiteLLM    Home Assistant                   │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.3 Channels Discord et agents associés

| Channel | Agent | Services interrogés | Exemples de commandes |
|---------|-------|---------------------|----------------------|
| `#chat` | Agent Général + Classifier | LiteLLM (Sonnet) → routing | Questions libres, aide rédaction, commandes mixtes |
| `#media` | Agent Média | Sonarr, Radarr, Plex, Tautulli, Seerr, qBittorrent | "Ajoute Breaking Bad", "Qui regarde Plex ?" |
| `#maison` | Agent Maison | Home Assistant | "Allume le salon", "Température ?", "Ferme le volet" |
| `#docs` | Agent Documents | Paperless-NGX, Immich | "Trouve ma facture Free de janvier" |
| `#infra` | Agent Infra | Beszel, Uptime Kuma, Portainer, Pi-hole | "État serveur ?", "Combien de DNS bloqués ?" |
| `#briefing` | Agent Briefing | Auto-post cron 7h | Résumé matinal quotidien |
| `#alerts` | Monitoring | Beszel, Uptime Kuma | Alertes infra automatiques |
| `#veille` | Agent Veille | Auto-post hebdo | Résumé actualités IA |

#### 4.4 Inventaire des APIs Docker accessibles par les agents

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

#### 4.5 Flux n8n — Agent Chat Discord

**Nom :** `Agent Chat Discord`
**Trigger :** n8n Discord Trigger (natif, écoute les messages des channels configurés)

```
Message Discord reçu
    │
    ▼
Ignorer si auteur = bot (éviter boucle)
    │
    ▼
Identifier le channel source
    │  → #media  : Agent Média directement
    │  → #maison : Agent Maison directement
    │  → #docs   : Agent Documents directement
    │  → #infra  : Agent Infra directement
    │  → #chat   : Classifier Haiku → routing
    │
    ▼
Exécuter l'agent spécialisé (Sonnet + tool-calling)
    │  → Appels HTTP aux APIs Docker internes
    │  → Contexte : 10 derniers messages du channel (Discord history API)
    │
    ▼
Formater la réponse (Discord Markdown, mobile-friendly)
    │
    ▼
Discord Send Message → channel source (ou thread si longue réponse)
```

#### 4.6 Gestion du contexte conversationnel

Discord fournit nativement l'historique de channel — l'agent peut récupérer les N derniers messages via l'API Discord pour construire le contexte multi-tours :

```
GET /channels/{channel_id}/messages?limit=10
→ injecter dans le prompt comme historique de conversation
```

Pas besoin de base de données supplémentaire. L'historique Discord EST la mémoire.

#### 4.7 Workflows Discord ✅

Tous les workflows n8n envoient exclusivement vers Discord (ntfy retiré) :

| Workflow | Channel Discord | Déclencheur |
|---------|----------------|-------------|
| Briefing Matinal | `#briefing` | Cron 7h |
| Veille Techno | `#veille` | Cron lundi 8h |
| Monitoring Infra | `#alerts` | Cron 5 min |
| Triage Email | `#chat` | Gmail trigger |
| Domotique | `#maison` | Webhook HA |
| Suivi Coûts | `#infra` | Cron 20h |

#### 4.8 Sécurité

- Discord bot token stocké dans n8n Credentials (jamais en clair)
- Bot limité au serveur Discord personnel uniquement
- API keys services (Sonarr, Radarr, HA token, etc.) dans n8n Credentials
- Actions destructives (restart container, supprimer document) → demander confirmation avant exécution (`@bot confirm`)
- Rate limiting Discord natif : 5 req/s par bot

#### 4.9 Prérequis Discord ✅

- [x] Serveur Discord existant (beta — ID: 134048232257880064)
- [x] Bot **Jarvis Wifsimster** créé (Application ID: 1488100441039568896)
  - Intents `MESSAGE_CONTENT` + `GUILD_MESSAGES` activés
  - Permissions : Administrator
- [x] Bot invité sur le serveur
- [x] Channels créés via script Python (API Discord) : `#chat`, `#media`, `#maison`, `#docs`, `#infra`, `#briefing`, `#alerts`, `#veille`

#### 4.10 Tâches de déploiement ✅

- [x] Credential "Discord Bot Homelab" créée dans n8n (ID: nZjeiz1Vi2ZaFIhZ)
- [x] Container `discord-bridge` déployé — bot Python discord.py, écoute 5 channels, forward vers n8n
- [x] Workflow `Agent Chat Discord` créé et actif dans n8n (webhook `/discord-chat`)
  - Routing par channel → system prompt spécialisé → Sonnet → réponse Discord
- [x] Workflows existants mis à jour pour poster aussi sur Discord :
  - Briefing Matinal → `#briefing`
  - Veille Techno → `#veille`
  - Monitoring Infra → `#alerts`
  - Suivi Coûts → `#infra`
  - Triage Email → `#chat`
  - Domotique → `#maison`
- [x] Test end-to-end validé : message Discord → Jarvis → n8n → Sonnet → réponse Discord

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
| Health monitoring | Uptime Kuma | **Déjà en place**, MIT |
| Monitoring système | Beszel | **Déjà en place**, CPU/RAM/disque + alertes |
| Auto-update | Watchtower | **Déjà en place**, cron quotidien |
| Backup PostgreSQL | pg-backup | **Déjà en place**, à étendre aux nouvelles bases |
| Notifications + conversations | Discord (bot Jarvis + channels) | discord-bridge Python, n8n webhook, 8 channels dédiés |
| LLM local | Ollama (qwen2.5:7b) | CPU, 4.5 Go RAM, 0 coût API, accessible via LiteLLM + Open WebUI |
| Accès services Docker | n8n + APIs REST | 20+ services exposent une API, n8n les orchestre |
| LLM cloud | Anthropic (Haiku/Sonnet) | Meilleur tool-calling, 1M contexte, coût OK |
| **Reporté** | Ollama | Pas de GPU, CPU lent — à évaluer plus tard |
| **Reporté** | Dify | Lourd, redondant avec Open WebUI + n8n |

---

*Rapport v10 — Mis à jour le 30 mars 2026. Étapes 1-4 et 6 déployées ✅. Stack IA complet : LiteLLM (Haiku + Sonnet + qwen2.5:7b) + Open WebUI + n8n (6 agents) + Langfuse + Ollama + Discord bot Jarvis (8 channels). ntfy supprimé. Interface unique Discord pour tout (notifications + conversations + agents). Seule étape optionnelle restante : Step 5 RAG.*
