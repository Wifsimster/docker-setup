# Agents IA Homelab — Rapport complet (v2)

> Stack autonome, observable, auto-hébergé sur Proxmox / Docker / UniFi
> Damien Battistella — Mars 2026
> **Mis à jour le 29 mars 2026 — Plan révisé après audit infra réel**

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
│                    ntfy app (push natif)                         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ push
┌──────────────────────────▼──────────────────────────────────────┐
│  COUCHE NOTIFICATION     │  ntfy (self-hosted, port 2586)       │
│                          │  Topics: agents, infra, domotique    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP POST
┌──────────────────────────▼──────────────────────────────────────┐
│  COUCHE OBSERVABILITÉ    │  Uptime Kuma (existant)              │
│                          │  Beszel (existant)                   │
│                          │  Health checks tous les services     │
│                          │  Langfuse (Phase 3, plus tard)       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ callbacks
┌──────────────────────────▼──────────────────────────────────────┐
│  COUCHE ORCHESTRATION    │  n8n (port 5678) — agents + workflows│
└──────────────────────────┬──────────────────────────────────────┘
                           │ /chat/completions
┌──────────────────────────▼──────────────────────────────────────┐
│  COUCHE PROXY LLM        │  LiteLLM (port 4000)                │
│                          │  → Anthropic API (Haiku/Sonnet)      │
│                          │  → OpenAI fallback                   │
│                          │  Cost tracking + routing + retry     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│  COUCHE INTERFACE        │  Open WebUI (port 3000)              │
│                          │  Chat quotidien, RAG docs, PWA mobile│
└─────────────────────────────────────────────────────────────────┘
```

**Changements vs plan initial :**
- Pas d'Ollama (pas de GPU, CPU trop lent pour 14b)
- Pas de Dify (trop lourd, redondant avec Open WebUI + n8n)
- Langfuse reporté en Phase 3
- Uptime Kuma et Beszel déjà en place — pas à déployer
- Traefik déjà en place comme reverse proxy (pas besoin de Caddy)
- pg-backup déjà en place pour les sauvegardes PostgreSQL
- Réseau `lan` existant (pas besoin de créer un réseau `ai-stack`)

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

### Étape 1 — Stack minimal viable (1-2 jours)

> **Prérequis :** clé API Anthropic

1. Déployer PostgreSQL 16 dédié IA (port 5433, base `litellm` + base `n8n`)
2. Déployer LiteLLM avec config Anthropic (Haiku + Sonnet), Traefik labels, réseau `lan`
3. Déployer Open WebUI pointant vers LiteLLM (`http://litellm:4000`), Traefik labels
4. Déployer ntfy, créer les topics et l'auth, Traefik labels
5. Déployer n8n avec la base PostgreSQL IA
6. Ajouter les nouvelles bases dans pg-backup (`backup.sh` existant)
7. Ajouter les monitors dans Uptime Kuma (health endpoints)
8. **Test :** envoyer un message dans Open WebUI → vérifier le passage par LiteLLM → Anthropic
9. **Test :** envoyer une notification ntfy depuis curl → vérifier réception sur mobile

### Étape 2 — Premiers agents (2-3 jours)

1. Créer le workflow n8n "agent triage email" : Gmail trigger → Haiku classification → routing → ntfy
2. Créer le workflow n8n "monitoring infra" : cron → Beszel API → seuils → ntfy
3. Connecter Uptime Kuma → ntfy pour les alertes down
4. Installer l'app ntfy sur le téléphone, souscrire aux topics
5. **Test :** envoyer un email test → vérifier triage + notification

### Étape 3 — Observabilité avancée (quand 2-3 agents sont stables)

1. Déployer Langfuse + ClickHouse
2. Ajouter `success_callback: ["langfuse"]` dans LiteLLM
3. Créer un workflow n8n de surveillance des coûts → alerte ntfy si seuil dépassé
4. Créer l'agent briefing matinal (météo + calendrier + emails + état infra via Beszel → ntfy)
5. Connecter n8n à Home Assistant pour les agents domotiques

### Étape 4 — RAG et agents avancés (optionnel)

> Conditionnel : seulement si Open WebUI RAG ne suffit pas

1. Déployer Dify + Qdrant
2. Uploader la documentation Hexagone/Hexaflux
3. Assistant property management (documents locatifs, ALUR, charges)

### Étape 5 — LLM local (optionnel, conditionnel)

> Seulement si besoin offline/privé confirmé

1. Déployer Ollama avec `qwen2.5:7b` (pas 14b — trop lent en CPU)
2. Ajouter le modèle local dans LiteLLM
3. Cas d'usage : embeddings locaux, tâches privées, fallback offline

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
| LLM cloud | Anthropic (Haiku/Sonnet) | Meilleur tool-calling, 1M contexte, coût OK |
| **Reporté** | Ollama | Pas de GPU, CPU lent — à évaluer plus tard |
| **Reporté** | Dify | Lourd, redondant avec Open WebUI + n8n |
| **Reporté** | Langfuse | Phase 3, quand le volume d'agents le justifie |

---

*Rapport v2 — Mis à jour le 29 mars 2026 après audit complet de l'infrastructure Docker (29 services en production).*
