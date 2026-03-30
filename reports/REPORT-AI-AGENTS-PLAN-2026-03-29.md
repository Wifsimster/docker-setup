# Agents IA Homelab — Rapport complet (v12)

> Stack autonome, observable, auto-hébergé sur Proxmox / Docker / UniFi
> Damien Battistella — Mars 2026
> **Mis à jour le 30 mars 2026 — Étapes 1, 2, 3, 4, 5 et 6 déployées ✅**

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
| Disque libre | 36 Go |
| RAM totale | 24 Gi |
| RAM utilisée | 15 Gi |
| RAM disponible | 9.7 Gi |
| Swap total | 8 Gi |
| Swap utilisé | 4.3 Gi |
| Images Docker | 68 Go (58 images, 56 actives) |
| Volumes Docker | 8.9 Go (40 volumes) |
| vCPU | 12 |

### Services Docker en production (43 services, 68 containers)

#### Infrastructure & réseau

| Service | Image | Rôle |
|---------|-------|------|
| Traefik | `traefik:v3.6` | Reverse proxy, TLS Let's Encrypt (OVH DNS) |
| Pi-hole | `pihole/pihole:latest` | DNS ad-blocking (port 53) |
| UniFi | `jacobalberty/unifi:v10.0` | Contrôleur réseau UniFi |
| Portainer | `portainer/portainer-ce:latest` | Interface Docker web |
| Dozzle | `amir20/dozzle:latest` | Visualiseur de logs Docker |

#### Monitoring & maintenance

| Service | Image | Rôle |
|---------|-------|------|
| Uptime Kuma | `louislam/uptime-kuma:latest` | Monitoring uptime des services |
| Beszel | `henrygd/beszel:latest` (hub + agent) | Monitoring système (CPU, RAM, disque) + alertes Discord |
| Watchtower | `containrrr/watchtower` | Auto-update images Docker (cron quotidien 06:00) |
| pg-backup | `postgres:16-alpine` + crond | Backup PostgreSQL quotidien (03:00), 5 bases, rétention 7 jours |
| Homepage | `gethomepage/homepage` | Dashboard avec widgets |

#### Multimédia

| Service | Image | Rôle |
|---------|-------|------|
| Plex | `lscr.io/linuxserver/plex:latest` | Media server (mode host) |
| Sonarr | `lscr.io/linuxserver/sonarr:latest` | Gestion séries TV |
| Radarr | `lscr.io/linuxserver/radarr:latest` | Gestion films |
| Lidarr | `lscr.io/linuxserver/lidarr:latest` | Gestion musique |
| Prowlarr | `lscr.io/linuxserver/prowlarr:latest` | Indexeurs |
| qBittorrent | `ghcr.io/hotio/qbittorrent:latest` | Téléchargement (VPN intégré) |
| Seerr | `ghcr.io/hotio/seerr:latest` | Requêtes média |
| Tautulli | `lscr.io/linuxserver/tautulli:latest` | Statistiques Plex |

#### Domotique

| Service | Image | Rôle |
|---------|-------|------|
| Home Assistant | `ghcr.io/home-assistant/home-assistant:stable` | Hub domotique (mode host) |
| Mosquitto | `eclipse-mosquitto:2` | Broker MQTT |
| Matter Server | `ghcr.io/home-assistant-libs/python-matter-server:stable` | Protocole Matter (healthcheck false-negative) |

#### Applications

| Service | Image | Rôle |
|---------|-------|------|
| Immich | `ghcr.io/immich-app/immich-server:v2` + ML + PostgreSQL + Valkey | Photos/vidéos avec ML |
| Paperless-NGX | `ghcr.io/paperless-ngx/paperless-ngx:latest` + PostgreSQL + Redis + Gotenberg + Tika | GED |
| Vaultwarden | `vaultwarden/server:latest` | Gestionnaire de mots de passe |
| Infisical | `infisical/infisical:latest-postgres` + PostgreSQL + Redis | Gestion des secrets |
| Wakapi | `ghcr.io/muety/wakapi:2.16.1` | Suivi temps de code |
| Stirling PDF | `docker.stirlingpdf.com/stirlingtools/stirling-pdf:latest` | Outils PDF |
| Gramps | `ghcr.io/gramps-project/grampsweb:latest` + Redis + Celery | Généalogie |
| Protonmail Bridge | `shenxn/protonmail-bridge:latest` | Bridge IMAP/SMTP ProtonMail |

#### Projets personnels

| Service | Image | Rôle |
|---------|-------|------|
| Personal Blog | `wifsimster/wifsimster-blog:latest` | Blog (blog.battistella.ovh) |
| Resume | `wifsimster/resume:latest` | CV en ligne (cv.battistella.ovh) |
| Copro-Pilot | `ghcr.io/wifsimster/copro-pilot:latest` + PostgreSQL | App copropriété |
| The-Box | `wifsimster/the-box:latest` + PostgreSQL + Redis | App jeux |
| Wawptn | `ghcr.io/wifsimster/wawptn:latest` + PostgreSQL + wawptn-discord | Stats de jeu (3 containers) |
| Toko | `ghcr.io/wifsimster/toko:latest` + PostgreSQL | App TDAH |
| Birthday Invitation | `wifsimster/birthday-invitation:latest` | App RSVP |
| X-AI-Weekly-Bot | `ghcr.io/wifsimster/x-ai-weekly-bot:latest` | Bot X/Twitter IA |

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
- **Bases PostgreSQL :** Immich, Paperless, Infisical, The-Box, Copro-Pilot, Toko, Wawptn, LiteLLM, n8n, Langfuse (10 instances PostgreSQL)

---

## 3. Architecture cible du stack IA

```
┌─────────────────────────────────────────────────────────────────┐
│                   TÉLÉPHONE / DESKTOP                           │
│                    Discord app (bot Jarvis)                     │
│                       #chat (canal unique)                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ discord-bridge (Python discord.py)
                           │ → POST webhook n8n (payload JSON)
┌──────────────────────────▼──────────────────────────────────────┐
│  n8n — Agent Chat Discord (webhook /discord-chat)               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  1. Filter & Route (ignore bots, identifie channel)      │    │
│  │  2. HTTP Request → LiteLLM (Sonnet + 20 outils)          │    │
│  │  3. Code node : Parse réponse, exécute tool calls        │    │
│  │     (require('http') → Docker services internes)         │    │
│  │  4. Si tool calls : second appel LiteLLM avec résultats  │    │
│  │  5. Respond to Webhook → JSON {reply, channelId}         │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────┬───────────────┬───────────────┬──────────────────────┘
           │               │               │
           ▼               ▼               ▼
┌──────────────┐ ┌─────────────────┐ ┌────────────────────────┐
│ PROXY LLM    │ │ SERVICES DOCKER │ │ OBSERVABILITÉ          │
│ LiteLLM 4000 │ │ Sonarr, Radarr  │ │ Langfuse (traces)      │
│ → Sonnet 4.6 │ │ Tautulli        │ │ Uptime Kuma            │
│ → Haiku 4.5  │ │ Home Assistant  │ │ Beszel (CPU/RAM)       │
│ Cost tracking│ │ Paperless-NGX   │ └────────────────────────┘
└──────────────┘ │ Beszel, Uptime K│ ┌────────────────────────┐
                 └─────────────────┘ │ INTERFACE WEB          │
                                     │ Open WebUI (port 3000) │
                                     │ Chat, PWA mobile       │
                                     └────────────────────────┘
```

**Changements vs plan initial :**
- Ollama déployé avec `qwen2.5:7b` (4-bit, CPU) — pas de 14b (trop lent)
- Pas de Dify (trop lourd, redondant avec Open WebUI + n8n)
- Langfuse déployé en étape 3 (traces + coûts)
- Uptime Kuma et Beszel déjà en place — pas à déployer
- Traefik déjà en place comme reverse proxy (pas besoin de Caddy)
- pg-backup étendu aux nouvelles bases (LiteLLM, n8n, Langfuse)
- Réseau `lan` existant (pas besoin de créer un réseau `ai-stack`)
- **Discord canal unique `#chat`** : bot Jarvis (discord-bridge) écoute uniquement `#chat`, forward vers n8n → agent unifié avec 20 outils (Sonnet + tool-calling) → réponse via `message.reply()`
- n8n node discordTrigger absent → bridge Python discord.py (`discord-bridge` container) comme forwarder léger
- **Tool-calling réel** : n8n Code nodes exécutent les appels HTTP aux services Docker via `require('http')` (fetch indisponible dans le sandbox n8n), puis envoient les résultats à Sonnet pour formulation finale
- **NODE_FUNCTION_ALLOW_BUILTIN=\*** ajouté à n8n pour autoriser les modules Node.js natifs dans les Code nodes

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

**Agents concrets déployés :**

1. **Agent triage email** — trigger Gmail → classification Haiku → résumé Discord `#chat`
2. **Agent monitoring infra** — cron 5 min → health checks services → alerte Discord `#chat` si anomalie
3. **Agent veille techno** — cron lundi 8h → HN + Reddit + Lobsters → synthèse Sonnet → Discord `#chat`
4. **Agent domotique** — webhook Home Assistant → analyse Haiku → Discord `#chat`
5. **Agent briefing matinal** — cron 7h → météo + état infra → Discord `#chat`
6. **Agent suivi coûts** — cron 20h → LiteLLM spend API → Discord `#chat`
7. **Agent Chat Discord** ✅ bot Jarvis écoute `#chat` → Sonnet avec 20 outils (tool-calling) → réponse inline dans `#chat`

**Workflows n8n :** tous les 7 workflows envoient vers `#chat` via HTTP Request → Discord Bot API (plus aucun canal dédié).

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

**Rôle :** interface centrale pour toutes les interactions avec les agents. Discord remplace ntfy pour les notifications — tous les agents postent dans **`#chat`**, canal unique. ntfy est conservé en service mais n'est plus utilisé par les workflows IA.

| Channel | Source | Contenu |
|---------|--------|---------|
| `#chat` | Tous les agents + bot Jarvis | Conversations, alertes, briefings, notifications — tout converge ici |

**Architecture simplifiée :** un canal unique `#chat` remplace l'architecture initiale à 8 canaux. L'agent unifié (Sonnet + 20 outils) répond à toutes les questions depuis ce canal. Les notifications automatiques (briefing, monitoring, triage email, veille, coûts) arrivent aussi dans `#chat`.

---

## 6. Inventaire Docker — Stack IA déployée ✅

| Service | Port | Image | Rôle |
|---------|------|-------|------|
| LiteLLM | 4000 | `ghcr.io/berriai/litellm:main-stable` + PostgreSQL | Proxy LLM unifié (Haiku, Sonnet, qwen2.5:7b) |
| Open WebUI | 8080 | `ghcr.io/open-webui/open-webui:main` | Interface chat IA (ai.battistella.ovh) |
| n8n | 5678 | `n8nio/n8n:latest` + PostgreSQL | Orchestration 6 agents + workflows |
| Ollama | 11434 | `ollama/ollama:latest` | LLM local qwen2.5:7b (CPU, ~4.5 Go) |
| Langfuse | — | `langfuse/langfuse:3` + worker + PostgreSQL + ClickHouse + MinIO + Redis | Observabilité LLM (traces, coûts) |
| discord-bridge | — | Python discord.py (custom build) | Bot Jarvis — écoute Discord → forward n8n webhook |

### Services optionnels non déployés

| Service | RAM | Condition d'ajout |
|---------|-----|-------------------|
| Dify + Qdrant | ~3 Go | Si Open WebUI RAG insuffisant pour les docs Hexagone/Hexaflux |

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

> **Objectif final :** discuter avec des agents IA depuis Discord (mobile/desktop). Envoyer un message en langage naturel dans `#chat`, l'agent le traite, interroge les services Docker existants via tool-calling, et répond dans le même canal. Discord est l'interface unique — notifications push, conversations et alertes.

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
│  ► Message dans #chat                                           │
│  ► Réponse de Jarvis dans #chat (message.reply)                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │ discord-bridge (Python, typing indicator)
                           │ POST {channelId, content, author, messageId, guildId}
┌──────────────────────────▼──────────────────────────────────────┐
│  n8n — Webhook /discord-chat                                    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  1. Filter & Route — ignorer bots, vérifier channelId    │    │
│  │  2. Build requestBody — messages + 20 outils définis     │    │
│  │  3. HTTP Request → LiteLLM (claude-sonnet-4-6)           │    │
│  │  4. Code node "Extract Reply" :                          │    │
│  │     - Parse JSON response                                │    │
│  │     - Si tool_calls → exécute via require('http')        │    │
│  │     - Agrège tool_results, met needsSecondCall=true      │    │
│  │  5. Si needsSecondCall → HTTP Request LiteLLM (round 2)  │    │
│  │  6. Extract Final Reply → formule réponse finale         │    │
│  │  7. Respond to Webhook → {reply, channelId}              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│              ┌──────────────────────────────┐                   │
│              ▼                              ▼                    │
│     LiteLLM :4000                 Services Docker internes      │
│     (Sonnet 4.6)                  Sonarr, Radarr, Tautulli      │
│                                   Home Assistant, Paperless      │
│                                   Beszel, Uptime Kuma            │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼ JSON {reply, channelId}
┌──────────────────────────────────────────────────────────────────┐
│  discord-bridge — bot.py                                         │
│  await message.reply(data["reply"], mention_author=False)        │
└──────────────────────────────────────────────────────────────────┘
```

#### 4.3 Canal Discord et agent unifié

**Un seul canal `#chat`, un seul agent avec 20 outils.** L'agent Sonnet choisit lui-même les outils à appeler selon la question posée.

| Canal | Agent | Services disponibles | Exemples de commandes |
|-------|-------|---------------------|----------------------|
| `#chat` | Agent Jarvis (Sonnet 4.6 + 20 outils) | Sonarr, Radarr, Tautulli, Home Assistant, Paperless, Beszel, Uptime Kuma | "Quelles séries arrivent ?", "Température salon ?", "État serveur ?", "Qui a détecté le portail ?" |

**20 outils disponibles :**

| Catégorie | Outils |
|-----------|--------|
| Multimédia | `sonarr_series`, `sonarr_calendar`, `sonarr_queue`, `radarr_movies`, `radarr_queue`, `tautulli_activity`, `tautulli_history`, `tautulli_stats` |
| Domotique | `ha_states`, `ha_entity`, `ha_service`, `ha_history`, `ha_detection_history` |
| Infrastructure | `beszel_systems`, `beszel_records`, `uptime_kuma_monitors` |
| Documents | `paperless_documents`, `paperless_search` |
| Général | `get_date_time` |

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
**Trigger :** n8n Webhook (POST `/discord-chat`) — discord-bridge envoie le payload JSON

```
discord-bridge POST → n8n webhook /discord-chat
    │ {channelId, channelName, content, author, messageId, guildId}
    ▼
Filter & Route
    │  → ignore si auteur.bot = true (éviter boucle)
    │  → vérifie channelId = 1488101544753893396 (#chat)
    │
    ▼
Build requestBody (Code node)
    │  → messages: [{role: "user", content: message.content}]
    │  → tools: [20 outils définis avec JSON Schema]
    │  → model: "sonnet", max_tokens: 1024
    │
    ▼
HTTP Request → LiteLLM :4000/chat/completions
    │  → Authorization: Bearer <LITELLM_MASTER_KEY>
    │
    ▼
Extract Reply (Code node)
    │  → Parse response.choices[0].message
    │  → Si tool_calls présents :
    │      pour chaque tool_call :
    │        → require('http') + parseUrl() → GET service Docker interne
    │        → stocker {tool_call_id, name, content: résultat}
    │  → Si tool_calls : needsSecondCall = true
    │  → Si text : reply = content, needsSecondCall = false
    │
    ▼
Needs Second Call? (Switch node)
    │  → true  : HTTP Request LiteLLM (round 2 avec tool_results)
    │  → false : Respond to Webhook directement
    │
    ▼
Extract Final Reply (Code node)
    │  → Parse réponse LiteLLM (text seulement après tool_results)
    │
    ▼
Respond to Webhook
    │  → respondWith: 'text'
    │  → body: JSON.stringify({reply: ..., channelId: ...})
    │
    ▼
discord-bridge reçoit {reply, channelId}
    │
    ▼
message.reply(reply, mention_author=False)
```

#### 4.6 Gestion du contexte conversationnel

Contexte limité à 1 tour (le message entrant) — pas d'historique multi-tours pour l'instant.
L'historique Discord visible dans le channel constitue la mémoire de facto pour l'utilisateur.

Ajout futur possible : `GET /channels/{channel_id}/messages?limit=10` → injecter dans le prompt.

#### 4.7 Workflows Discord ✅

Tous les workflows n8n envoient exclusivement vers Discord `#chat` via **HTTP Request → Discord Bot API** (plus de node Discord natif — il était cassé en n8n 2.13.4) :

```
POST https://discord.com/api/v10/channels/{CHANNEL_CHAT}/messages
Authorization: Bot {DISCORD_BOT_TOKEN}
{"content": "..."}
```

| Workflow | Canal Discord | Déclencheur |
|---------|--------------|-------------|
| Briefing Matinal | `#chat` | Cron 7h |
| Veille Techno | `#chat` | Cron lundi 8h |
| Monitoring Infra | `#chat` | Cron 5 min |
| Triage Email | `#chat` | Gmail trigger |
| Domotique | `#chat` | Webhook HA |
| Suivi Coûts | `#chat` | Cron 20h |
| Agent Chat Discord | `#chat` | Webhook (discord-bridge) |

#### 4.8 Sécurité

- Discord bot token stocké dans les env vars du container `discord-bridge` (`.env` gitignorée)
- Bot token aussi présent dans les Code nodes n8n pour l'envoi Discord — à migrer vers n8n Credentials si besoin
- Bot limité au serveur Discord personnel uniquement
- API keys services (Sonarr, Radarr, Tautulli, HA token, Paperless token) hardcodées dans les Code nodes (architecture actuelle — acceptable pour usage personnel)
- Actions destructives : `ha_service` peut contrôler les équipements HA → requiert Intents activés

#### 4.9 Prérequis Discord ✅

- [x] Serveur Discord existant (beta — ID: 134048232257880064)
- [x] Bot **Jarvis Wifsimster** créé (Application ID: 1488100441039568896)
  - Intents `MESSAGE_CONTENT` + `GUILD_MESSAGES` activés
  - Permissions : Administrator
- [x] Bot invité sur le serveur
- [x] Canal actif : `#chat` (ID: 1488101544753893396) — canal unique

#### 4.10 Tâches de déploiement ✅

- [x] Container `discord-bridge` déployé — bot Python discord.py, écoute `#chat` uniquement, forward vers n8n
  - `CHANNEL_CHAT` comme seule variable d'env canal (suppression de `CHANNEL_MEDIA`, `CHANNEL_MAISON`, `CHANNEL_DOCS`, `CHANNEL_INFRA`)
  - Timeout 120s, typing indicator, `message.reply()` avec JSON response
- [x] Workflow `Agent Chat Discord` actif dans n8n (webhook `/discord-chat`)
  - Agent unifié : Sonnet 4.6 + 20 outils — toutes catégories (media, domotique, infra, docs)
  - Tool-calling via Code nodes + `require('http')` + manual URL parser (contournement sandbox)
- [x] `NODE_FUNCTION_ALLOW_BUILTIN=*` ajouté à n8n (compose.yml) pour modules Node.js natifs
- [x] Tous les workflows existants mis à jour pour poster vers `#chat` :
  - Briefing Matinal → `#chat`
  - Veille Techno → `#chat`
  - Monitoring Infra → `#chat`
  - Suivi Coûts → `#chat`
  - Triage Email → `#chat`
  - Domotique → `#chat`
- [x] Test end-to-end validé : message Discord → Jarvis (typing) → n8n → Sonnet → tool call → service Docker → réponse Discord

#### 4.11 APIs Docker connectées — état réel

| Service | URL interne | Clé/Token | Outils exposés | Statut |
|---------|-------------|-----------|----------------|--------|
| Sonarr | `http://sonarr:8989/api/v3` | API key | `sonarr_series`, `sonarr_calendar`, `sonarr_queue` | ✅ |
| Radarr | `http://radarr:7878/api/v3` | API key | `radarr_movies`, `radarr_queue` | ✅ |
| Tautulli | `http://tautulli:8181/api/v2` | API key (`dae7a941...`) | `tautulli_activity`, `tautulli_history`, `tautulli_stats` | ✅ |
| Home Assistant | `http://homeassistant:8123/api` | Long-lived token (JWT) | `ha_states`, `ha_entity`, `ha_service`, `ha_history`, `ha_detection_history` | ✅ |
| Paperless-NGX | `http://paperless-webserver:8000/api` | Token API (user `jarvis`) | `paperless_documents`, `paperless_search` | ✅ (0 docs) |
| Beszel | `http://beszel:8090/api` | Admin credentials | `beszel_systems`, `beszel_records` | ✅ |
| Uptime Kuma | `http://uptime-kuma:3001` | — | `uptime_kuma_monitors` | ✅ |

**Home Assistant — caméras de détection :**
- `portail` → `camera.lts_ipc_f42feux_g3s_portail`
- `atelier/bullet` → `camera.lts_ipc_f22feux_g5_bullet_atelier`
- `allée/garage` → `camera.lts_ipc_f22feux_g5_bullet_allee_garage`

Outil `ha_detection_history` : retourne le nombre de détections et les timestamps des N dernières heures par caméra et type de mouvement.

### ~~Étape 5 — Canal unique + tool-calling réel (FAIT ✅)~~

> Déployé le 2026-03-30

- [x] Simplification architecture Discord : 8 canaux → `#chat` uniquement
- [x] discord-bridge mis à jour : écoute uniquement `CHANNEL_CHAT` (suppression des 4 autres canaux)
- [x] Agent Chat Discord refactorisé : agent unifié avec 20 outils (Sonnet 4.6)
  - Tool-calling via Code nodes n8n + `require('http')` (pas de fetch dans le sandbox)
  - Manual URL parser regex (contournement `url.parse()` deprecated)
  - Second appel LiteLLM avec `tool_results` pour formulation finale
- [x] `NODE_FUNCTION_ALLOW_BUILTIN=*` ajouté à n8n compose.yml
- [x] Tous les workflows (6) mis à jour pour envoyer vers `#chat` via Discord Bot API HTTP
- [x] APIs connectées : Sonarr, Radarr, Tautulli, Home Assistant (avec token JWT), Paperless-NGX, Beszel, Uptime Kuma
- [x] Home Assistant : détection caméras (portail, atelier, allée/garage) via history API
- [x] Paperless-NGX : user `jarvis` créé via Django shell, token API récupéré

### Étape 6 — RAG et agents avancés (optionnel)

> Conditionnel : seulement si Open WebUI RAG ne suffit pas

1. Déployer Dify + Qdrant
2. Uploader la documentation Hexagone/Hexaflux
3. Assistant property management (documents locatifs, ALUR, charges)

### ~~Étape 7 — LLM local (FAIT ✅)~~

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
| Notifications + conversations | Discord (bot Jarvis + `#chat`) | discord-bridge Python, n8n webhook, canal unique `#chat`, agent unifié 20 outils |
| LLM local | Ollama (qwen2.5:7b) | CPU, 4.5 Go RAM, 0 coût API, accessible via LiteLLM + Open WebUI |
| Accès services Docker | n8n + APIs REST | 20+ services exposent une API, n8n les orchestre |
| LLM cloud | Anthropic (Haiku/Sonnet) | Meilleur tool-calling, 1M contexte, coût OK |
| **Reporté** | Ollama | Pas de GPU, CPU lent — à évaluer plus tard |
| **Reporté** | Dify | Lourd, redondant avec Open WebUI + n8n |

---

*Rapport v12 — Mis à jour le 30 mars 2026. Étapes 1-5 et 7 déployées ✅. Stack IA complet : LiteLLM (Haiku + Sonnet + qwen2.5:7b) + Open WebUI + n8n (7 workflows) + Langfuse + Ollama + Discord bot Jarvis. ntfy supprimé. Interface unique Discord `#chat` pour tout (notifications + conversations + agents). Agent unifié Sonnet 4.6 avec 20 outils (Sonarr, Radarr, Tautulli, Home Assistant, Paperless, Beszel, Uptime Kuma). Tool-calling réel via `require('http')` dans Code nodes n8n. Seule étape optionnelle restante : Étape 6 RAG.*
