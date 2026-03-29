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
- Proxmox VE 9.1.1 sur Debian 13 (trixie), kernel 6.17.2-1-pve
- AMD Ryzen 5 3600 (6c/12t), 46 Go RAM
- VM 100 (Unraid) : NAS, 10 Go RAM, 8x 4 To passthrough
- VM 101 (Docker) : Ubuntu 24.04, 25.4 Go RAM, 150 Go disque
- UniFi avec VLAN, SSID "Domotic" (2.4 GHz)
- NAS Unraid 26 To NFS (192.168.0.240)
- Services existants sur VM 101 : Home Assistant, Immich, Plex, qBittorrent, Uptime Kuma
- Pas de GPU dédié (RTX 2070 passthrough abandonné — IOMMU partagé)

---

## 2. Audit infra — Changements réalisés (29 mars 2026)

Avant de déployer, l'infra a été optimisée :

| Action | Avant | Après |
|--------|-------|-------|
| Snapshot `fresh-setup` VM 101 | 63 Go dans le thin pool | **Supprimé** |
| Disque VM 101 | 100 Go (98.4% plein) | **150 Go (66% plein)** |
| RAM VM 100 (Unraid) | 18.2 Go | **10 Go** (2 Go utilisés réels) |
| RAM hôte Proxmox libre | 1.5 Go | **11 Go** |
| Swap hôte | 6.1 Go utilisé | **890 Mo** |
| Thin pool `pve/data` | 78% | **72%** |

**Ressources disponibles pour le stack IA :**
- ~50 Go disque libre sur VM 101
- ~1.2 Go RAM nécessaire pour le stack minimal (dans les 25.4 Go de VM 101)
- 12 vCPU alloués à VM 101 (sur-commité, acceptable pour ce workload)

---

## 3. Architecture cible (révisée)

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
│  COUCHE OBSERVABILITÉ    │  Uptime Kuma (existant)              │
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
- Uptime Kuma déjà en place — pas à déployer

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

## 5. Les briques du stack — détail

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
2. **Agent monitoring infra** — cron → SSH sur les VMs → vérification disque/RAM/containers → alerte ntfy si seuil dépassé
3. **Agent veille techno** — cron hebdo → recherche web → synthèse Sonnet → envoi résumé par ntfy/email
4. **Agent domotique** — webhook Home Assistant → analyse Haiku → action HA → notification état
5. **Agent briefing matinal** — cron 7h → agrège météo + calendrier + emails prioritaires + état infra → envoie résumé ntfy

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
| `infra` | Uptime Kuma | Haute | Service down, disque plein, RAM critique |
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

## 6. Inventaire Docker — Stack IA

| Service | Port | Image | RAM estimée | Rôle |
|---------|------|-------|-------------|------|
| LiteLLM | 4000 | `litellm-database:main-stable` | ~200 Mo | Proxy LLM + coûts |
| Open WebUI | 3000 | `open-webui/open-webui:main` | ~300 Mo | Interface chat |
| n8n | 5678 | `n8nio/n8n:latest` | ~300 Mo | Orchestration agents |
| ntfy | 2586 | `binwiederhier/ntfy` | ~30 Mo | Notifications push |
| PostgreSQL | 5432 | `postgres:16` | ~200 Mo | Persistance globale |
| Redis | 6379 | `redis:7-alpine` | ~50 Mo | Cache + queue |

**Total : ~1.1 Go RAM**

### Services reportés (ajout futur)

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

### ~~Étape 0 — Préparer l'infra (FAIT ✅)~~

- [x] Supprimer le snapshot `fresh-setup` de VM 101
- [x] Agrandir disque VM 101 : 100 Go → 150 Go
- [x] Étendre le filesystem dans la VM
- [x] Réduire RAM Unraid : 18 Go → 10 Go
- [x] Vérifier : hôte Proxmox a 11 Go libres, swap < 1 Go

### Étape 1 — Stack minimal viable (1-2 jours)

> **Prérequis :** clé API Anthropic

1. Créer le réseau Docker dédié `ai-stack`
2. Déployer PostgreSQL 16 + Redis 7 (services partagés)
3. Déployer LiteLLM avec config Anthropic (Haiku + Sonnet)
4. Déployer Open WebUI pointant vers LiteLLM (`http://litellm:4000`)
5. Déployer n8n avec PostgreSQL
6. Déployer ntfy, créer les topics et l'auth
7. Ajouter les monitors dans Uptime Kuma (déjà en place)
8. **Test :** envoyer un message dans Open WebUI → vérifier le passage par LiteLLM → Anthropic
9. **Test :** envoyer une notification ntfy depuis curl → vérifier réception sur mobile

### Étape 2 — Sécurité + premiers agents (2-3 jours)

1. Déployer Caddy en reverse proxy devant Open WebUI + ntfy (TLS + auth)
2. Configurer WireGuard pour accès mobile sécurisé
3. Mettre en place un backup vzdump cron hebdomadaire vers NAS Unraid (192.168.0.240)
4. Créer le workflow n8n "agent triage email" : Gmail trigger → Haiku classification → routing → ntfy
5. Créer le workflow n8n "monitoring infra" : cron → SSH checks → ntfy
6. Connecter Uptime Kuma → ntfy pour les alertes down
7. Installer l'app ntfy sur le téléphone, souscrire aux topics
8. **Test :** envoyer un email test → vérifier triage + notification

### Étape 3 — Observabilité (quand 2-3 agents sont stables)

1. Déployer Langfuse + ClickHouse
2. Ajouter `success_callback: ["langfuse"]` dans LiteLLM
3. Créer un workflow n8n de surveillance des coûts → alerte ntfy si seuil dépassé
4. Créer l'agent briefing matinal (météo + calendrier + emails + état infra → ntfy)
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
| Proxy LLM unifié | LiteLLM | Multi-provider, cost tracking, fallback, MIT |
| Orchestration agents | n8n | GUI visuelle, 400+ intégrations, ReAct natif |
| Interface chat | Open WebUI | Référence du marché, PWA, function calling |
| Health monitoring | Uptime Kuma | Déjà en place, intégration ntfy native, MIT |
| Notifications push | ntfy | Auto-hébergé, 30 Mo RAM, app mobile, Apache 2.0 |
| LLM cloud | Anthropic (Haiku/Sonnet) | Meilleur tool-calling, 1M contexte, coût OK |
| **Reporté** | Ollama | Pas de GPU, CPU lent — à évaluer plus tard |
| **Reporté** | Dify | Lourd, redondant avec Open WebUI + n8n |
| **Reporté** | Langfuse | Phase 3, quand le volume d'agents le justifie |

---

*Rapport v2 — Mis à jour le 29 mars 2026 après audit et optimisation de l'infrastructure Proxmox.*
