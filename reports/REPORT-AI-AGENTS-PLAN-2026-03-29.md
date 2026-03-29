# Agents IA Homelab — Rapport complet

> Stack autonome, observable, auto-hébergé sur Proxmox / Docker / UniFi
> Damien Battistella — Mars 2026

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
- Proxmox VE + VMs Docker (Ubuntu)
- UniFi avec VLAN, SSID "Domotic" (2.4 GHz)
- NAS 26 To NFS (192.168.0.240)
- Home Assistant, Immich, Plex, qBittorrent
- Pas de GPU dédié (RTX 2070 passthrough abandonné — IOMMU partagé)

---

## 2. Architecture cible

```
┌─────────────────────────────────────────────────────────────────┐
│                        TON TÉLÉPHONE                            │
│                    ntfy app (push natif)                         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ push
┌──────────────────────────▼──────────────────────────────────────┐
│  COUCHE NOTIFICATION     │  ntfy (self-hosted, port 2586)       │
│                          │  Topics: agents, infra, domotique    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP POST
┌──────────────────────────▼──────────────────────────────────────┐
│  COUCHE OBSERVABILITÉ    │  Langfuse (port 3001)                │
│                          │  Traces, coûts, latence, erreurs     │
│                          │  Uptime Kuma (port 3002)             │
│                          │  Health checks tous les services     │
└──────────────────────────┬──────────────────────────────────────┘
                           │ callbacks
┌──────────────────────────▼──────────────────────────────────────┐
│  COUCHE ORCHESTRATION    │  n8n (port 5678) — agents + workflows│
│                          │  Dify (port 5001) — RAG + apps IA    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ /chat/completions
┌──────────────────────────▼──────────────────────────────────────┐
│  COUCHE PROXY LLM        │  LiteLLM (port 4000)                │
│                          │  → Anthropic API (Haiku/Sonnet)      │
│                          │  → Ollama local (qwen2.5)            │
│                          │  → OpenAI fallback                   │
│                          │  Cost tracking + routing + retry     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│  COUCHE INTERFACE        │  Open WebUI (port 3000)              │
│                          │  Chat quotidien, RAG docs, PWA mobile│
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Tarifs API LLM (mars 2026)

| Modèle | Input/MTok | Output/MTok | Contexte | Rôle dans le stack |
|--------|-----------|------------|----------|-------------------|
| Claude Haiku 4.5 | $1 | $5 | 200K | Triage, classification, tri email |
| Claude Sonnet 4.6 | $3 | $15 | 1M | Raisonnement, tool-calling, agents |
| Claude Opus 4.6 | $5 | $25 | 1M | Tâches flagship (optionnel) |
| Ollama qwen2.5:14b | 0 | 0 | 128K | Tâches privées, offline, embeddings |
| GPT-4o (fallback) | $5 | $15 | 128K | Backup via LiteLLM |

**Optimisations intégrées à LiteLLM :** prompt caching (−90 % input), batch API (−50 %), routage automatique Haiku/Sonnet selon la complexité.

---

## 4. Les briques du stack — détail

### 4.1 LiteLLM — Proxy LLM unifié

**Rôle :** point d'entrée unique pour TOUS les appels LLM. Chaque service (n8n, Dify, Open WebUI) pointe vers `http://litellm:4000` au lieu d'appeler directement Anthropic/OpenAI. Ça permet de changer de modèle, ajouter du fallback, et tracker les coûts sans toucher aux agents.

| | |
|---|---|
| Image Docker | `docker.litellm.ai/berriai/litellm-database:main-stable` |
| Port | 4000 |
| Dépendances | PostgreSQL (tracking coûts), Redis (optionnel, cache) |
| Licence | MIT |
| Observabilité | Callback natif vers Langfuse, suivi coûts par clé virtuelle |

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
  - model_name: local
    litellm_params:
      model: ollama/qwen2.5:14b
      api_base: http://ollama:11434

litellm_settings:
  success_callback: ["langfuse"]  # ← traces auto vers Langfuse

general_settings:
  master_key: sk-ton-master-key
  database_url: postgresql://litellm:pass@postgres:5432/litellm
```

**Pourquoi c'est critique :** sans LiteLLM, chaque service a sa propre config API, ses propres clés, et tu perds la vue consolidée des coûts. Avec LiteLLM, tu as UN dashboard de dépenses, UN point de fallback, et UN endroit pour changer de modèle.

### 4.2 n8n — Orchestration des agents

**Rôle :** c'est le cerveau opérationnel. Chaque agent est un workflow visuel qui combine un LLM (via LiteLLM), des outils (HTTP, SSH, DB, Home Assistant), et de la mémoire. Le pattern ReAct (raisonnement → action → observation → boucle) est natif.

| | |
|---|---|
| Image Docker | `n8nio/n8n:latest` |
| Port | 5678 |
| Dépendances | PostgreSQL (persistance workflows), Redis (queue mode) |
| Licence | Fair-code (Apache 2.0 + restrictions commerciales) |
| Intégrations | 400+ connecteurs natifs |
| Ressources | 4 cores / 8 Go pour ~50-100 workflows concurrents |

**Agents concrets à déployer :**

1. **Agent triage email** — trigger Gmail → classification Haiku → routage par catégorie → notification ntfy si urgent
2. **Agent monitoring infra** — cron → SSH sur les VMs → vérification disque/RAM/containers → alerte ntfy si seuil dépassé
3. **Agent veille techno** — cron hebdo → recherche web → synthèse Sonnet → envoi résumé par ntfy/email
4. **Agent domotique** — webhook Home Assistant → analyse Haiku → action HA → notification état
5. **Agent briefing matinal** — cron 7h → agrège météo + calendrier + emails prioritaires + état infra → envoie résumé ntfy

**Lien avec l'observabilité :** chaque workflow n8n peut envoyer ses résultats et erreurs vers ntfy (node HTTP Request) et ses traces LLM passent automatiquement par LiteLLM → Langfuse.

### 4.3 Dify — RAG et apps IA

**Rôle :** complément de n8n pour les cas RAG-heavy. Tu uploades ta documentation (Hexagone, Hexaflux, notes perso, PDF techniques), Dify la chunke, l'indexe, et expose un assistant conversationnel qui répond en citant les sources.

| | |
|---|---|
| Image Docker | `langgenius/dify` (Docker Compose multi-services) |
| Port | 5001 |
| Dépendances | PostgreSQL, Redis, Weaviate (vector DB incluse) |
| Licence | Apache 2.0 |
| Modèles | 100+ providers, dont Ollama et Anthropic via LiteLLM |

**Cas d'usage prioritaires :**
- Assistant documentation Hexagone Web (les docs PO que tu génères)
- Base de connaissances HL7/Hexaflux pour les tickets support
- Assistant property management (documents locatifs, ALUR, charges)

### 4.4 Open WebUI — Interface chat

**Rôle :** interface quotidienne de chat, connectée à LiteLLM comme backend OpenAI-compatible. Tu accèdes à tous tes modèles (cloud et local) depuis un seul endroit, avec RAG, function calling, et historique.

| | |
|---|---|
| Image Docker | `ghcr.io/open-webui/open-webui:main` |
| Port | 3000 |
| Licence | Propriétaire (usage libre, pas MIT) |
| GitHub | 129K+ étoiles, 290M+ téléchargements |

**Points clés :**
- PWA installable sur mobile → accès chat IA depuis n'importe où
- Model Builder → créer des "personnages" agents avec system prompts dédiés
- Python tools natifs → écrire des fonctions custom (appeler Home Assistant, chercher dans tes docs)
- Pipelines → ajouter du rate limiting, logging, filtres sans toucher au code

---

## 5. Observabilité — la partie critique

### 5.1 Langfuse — Tracing et coûts des agents

**Rôle :** Langfuse capture chaque appel LLM, chaque étape d'agent, chaque tool call, avec le coût en tokens, la latence, et les entrées/sorties. C'est ton "debugger en production" pour les agents.

| | |
|---|---|
| Image Docker | `langfuse/langfuse` (web + worker) |
| Port | 3001 |
| Dépendances | PostgreSQL, ClickHouse, Redis |
| Licence | MIT (core open-source) |
| GitHub | 21K+ étoiles |
| Intégrations | LiteLLM (callback natif), LangChain, CrewAI, n8n |

**Ce que tu vois dans Langfuse :**
- Chaque trace complète d'un agent : prompt système → requête → tool calls → réponse finale
- Coût par trace, par modèle, par jour, par agent
- Latence P50/P95 de chaque étape
- Taux d'erreurs et types d'erreurs
- Sessions utilisateur (pour débugger des conversations multi-tours)

**Intégration avec LiteLLM :** une seule ligne dans la config LiteLLM (`success_callback: ["langfuse"]`) et toutes les traces de tous les services passent automatiquement dans Langfuse. Pas de code à modifier dans n8n ou Dify.

**Déploiement :**
```bash
git clone https://github.com/langfuse/langfuse.git
cd langfuse
docker compose up -d
# Accessible sur http://localhost:3001
# Créer un compte → organisation → projet → récupérer les clés API
```

### 5.2 Uptime Kuma — Health checks des services

**Rôle :** monitorer que chaque brique du stack est up. Dashboard visuel avec historique d'uptime et alertes vers ntfy en cas de panne.

| | |
|---|---|
| Image Docker | `louislam/uptime-kuma:1` |
| Port | 3002 |
| Licence | MIT |
| Alertes | ntfy natif, + Slack, email, webhook |

**Monitors à configurer :**

| Endpoint | Service |
|----------|---------|
| `http://litellm:4000/health` | Proxy LLM |
| `http://n8n:5678/healthz` | Orchestrateur agents |
| `http://open-webui:8080` | Interface chat |
| `http://dify:5001` | Plateforme RAG |
| `http://ollama:11434/api/tags` | Inference locale |
| `http://langfuse:3001` | Observabilité |
| `http://qdrant:6333/collections` | Vector DB |
| TCP `postgres:5432` | Base de données |
| TCP `redis:6379` | Cache |

### 5.3 ntfy — Notifications push auto-hébergées

**Rôle :** service de notifications pub/sub ultra-léger. Tout ce qui peut faire un `curl` peut envoyer une notification. App mobile Android/iOS pour les recevoir en push.

| | |
|---|---|
| Image Docker | `binwiederhier/ntfy` |
| Port | 2586 |
| RAM | ~20-50 Mo |
| Licence | Apache 2.0 + GPL |
| Apps | Android, iOS, Web PWA |

**Topics à créer :**

| Topic | Source | Priorité | Contenu |
|-------|--------|----------|---------|
| `agents` | n8n workflows | Normale | Résultats des agents, tâches terminées |
| `infra` | Uptime Kuma | Haute | Service down, disque plein, RAM critique |
| `domotique` | Home Assistant + n8n | Normale | Événements domotiques IA |
| `briefing` | Agent briefing n8n | Basse | Résumé matinal quotidien |
| `costs` | LiteLLM / Langfuse | Normale | Alerte si budget API dépassé |
| `urgent` | Tous | Urgente | Alertes critiques cross-système |

**Pourquoi ntfy et pas Discord/Slack :**
- 100 % auto-hébergé, zéro dépendance externe
- Push natif Android sans Firebase (polling mode)
- iOS via upstream ntfy.sh ou PWA
- Intégration native avec Uptime Kuma, Home Assistant, n8n
- Un simple `curl -d "message" http://ntfy:2586/topic` suffit
- Priorités, tags, pièces jointes, actions dans les notifications

**Config Docker :**
```yaml
ntfy:
  image: binwiederhier/ntfy:latest
  container_name: ntfy
  restart: unless-stopped
  command: serve
  ports:
    - "2586:80"
  environment:
    - TZ=Europe/Paris
    - NTFY_AUTH_DEFAULT_ACCESS=deny-all
    - NTFY_AUTH_FILE=/var/lib/ntfy/auth.db
    - NTFY_BEHIND_PROXY=true
    - NTFY_BASE_URL=https://ntfy.tondomaine.com
  volumes:
    - ntfy-cache:/var/cache/ntfy
    - ntfy-auth:/var/lib/ntfy
```

---

## 6. Boucle d'observabilité complète

Voici comment les données circulent pour une vision permanente de l'état du système :

```
Agent n8n fait un appel LLM
  → passe par LiteLLM (port 4000)
    → LiteLLM route vers Anthropic/Ollama
    → LiteLLM log le coût dans PostgreSQL
    → LiteLLM envoie la trace à Langfuse (callback)
  → n8n reçoit la réponse, exécute les tools
  → n8n envoie le résultat par ntfy (topic "agents")
  → si erreur → n8n envoie alerte ntfy (topic "urgent")

En parallèle :
  Uptime Kuma ping tous les services toutes les 60s
    → si down → notification ntfy (topic "infra")
    → dashboard historique accessible sur :3002

  Langfuse agrège toutes les traces
    → dashboard coûts/latence/erreurs sur :3001
    → workflow n8n en cron qui query le spend Langfuse
      → si spend > seuil → notification ntfy (topic "costs")
```

---

## 7. Inventaire Docker complet

| Service | Port | Image | RAM estimée | Rôle |
|---------|------|-------|-------------|------|
| Ollama | 11434 | `ollama/ollama` | 8-16 Go | Inference locale |
| LiteLLM | 4000 | `litellm-database:main-stable` | ~200 Mo | Proxy LLM + coûts |
| Open WebUI | 3000 | `open-webui/open-webui:main` | ~300 Mo | Interface chat |
| n8n | 5678 | `n8nio/n8n:latest` | ~300 Mo | Orchestration agents |
| Dify | 5001 | `langgenius/dify` (multi) | ~1 Go | RAG + apps IA |
| Langfuse | 3001 | `langfuse/langfuse` | ~500 Mo | Observabilité LLM |
| Uptime Kuma | 3002 | `louislam/uptime-kuma:1` | ~100 Mo | Health monitoring |
| ntfy | 2586 | `binwiederhier/ntfy` | ~30 Mo | Notifications push |
| Qdrant | 6333 | `qdrant/qdrant` | ~200 Mo | Vector DB |
| PostgreSQL | 5432 | `postgres:16` | ~200 Mo | Persistance globale |
| Redis | 6379 | `redis:7-alpine` | ~50 Mo | Cache + mémoire |

**Total sans Ollama : ~3 Go RAM.** Avec Ollama + qwen2.5:14b : +10-16 Go.

---

## 8. Budget mensuel

| Poste | Coût/mois | Notes |
|-------|----------|-------|
| Infrastructure Proxmox | 0 € | Déjà en place |
| Tous les logiciels | 0 € | Open-source, self-hosted |
| Anthropic API (modéré) | 8–20 € | ~500 appels Sonnet + triage Haiku |
| Anthropic API (intensif) | 30–50 € | Multi-agents actifs, RAG, automatisations |
| OpenAI fallback | 0–5 € | Optionnel |
| **TOTAL** | **8–55 €/mois** | **Seul coût = tokens API** |

---

## 9. Plan de déploiement

### Phase 1 — Fondations (1-2 jours)

1. Créer une VM dédiée "ai-stack" sur Proxmox (ou réutiliser la VM Docker existante)
2. Déployer PostgreSQL + Redis (services partagés)
3. Déployer Ollama, pull `qwen2.5:14b`
4. Déployer LiteLLM avec config Anthropic + Ollama
5. Déployer Open WebUI pointant vers LiteLLM
6. **Test :** envoyer un message dans Open WebUI → vérifier le passage par LiteLLM → Anthropic

### Phase 2 — Observabilité (1 jour)

1. Déployer Langfuse, créer le projet, récupérer les clés API
2. Ajouter `success_callback: ["langfuse"]` dans LiteLLM
3. Déployer Uptime Kuma, configurer les monitors pour chaque service
4. Déployer ntfy, créer les topics et l'utilisateur auth
5. Connecter Uptime Kuma → ntfy pour les alertes
6. Installer l'app ntfy sur le téléphone, souscrire aux topics
7. **Test :** arrêter un container → vérifier l'alerte ntfy → relancer

### Phase 3 — Premier agent (2-3 jours)

1. Déployer n8n avec PostgreSQL
2. Créer le workflow "agent triage email" : Gmail trigger → Haiku classification → routing
3. Ajouter des notifications ntfy en fin de workflow (succès + erreurs)
4. Créer le workflow "monitoring infra" : cron → SSH → check disk/RAM → ntfy
5. **Test :** envoyer un email test → vérifier triage + notification + trace Langfuse

### Phase 4 — RAG et agents avancés (1 semaine)

1. Déployer Dify + Qdrant
2. Uploader la documentation Hexagone/Hexaflux dans Dify
3. Créer l'agent briefing matinal dans n8n (multi-sources → résumé → ntfy)
4. Connecter n8n à Home Assistant pour les agents domotiques
5. Créer un workflow de surveillance des coûts (query Langfuse → alerte ntfy si seuil)

### Phase 5 — Consolidation (continu)

- Affiner les system prompts selon les retours
- Ajouter des agents selon les besoins (veille, gestion locative, etc.)
- Monitorer les coûts dans Langfuse et optimiser le routing Haiku/Sonnet
- Documenter chaque workflow pour pouvoir reconstruire en cas de rebuild

---

## 10. Résumé des choix

| Besoin | Solution | Pourquoi |
|--------|----------|----------|
| Proxy LLM unifié | LiteLLM | Multi-provider, cost tracking, fallback, MIT |
| Orchestration agents | n8n | GUI visuelle, 400+ intégrations, ReAct natif |
| RAG documentaire | Dify | Pipeline RAG complet, no-code, Apache 2.0 |
| Interface chat | Open WebUI | Référence du marché, PWA, function calling |
| Tracing/coûts agents | Langfuse | Open-source, callback LiteLLM natif, MIT |
| Health monitoring | Uptime Kuma | Léger, intégration ntfy native, MIT |
| Notifications push | ntfy | Auto-hébergé, 30 Mo RAM, app mobile, Apache 2.0 |
| Vector DB | Qdrant | Léger, API REST, adapté homelab |
| LLM cloud | Anthropic (Haiku/Sonnet) | Meilleur tool-calling, 1M contexte, coût OK |
| LLM local | Ollama (qwen2.5) | Gratuit, privé, suffisant pour triage |

*Rapport mis à jour le 29 mars 2026 — Tarifs et versions en vigueur à cette date.*
