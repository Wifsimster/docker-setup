# Equipe Dev IA — Rapport d'implementation

> Damien Battistella — 30 mars 2026
> **Statut : deploye, en cours de validation**

---

## 1. Objectif

Deployer une equipe d'agents IA developpeurs autonomes sur le homelab existant. Un agent CEO (Jarvis) orchestre des sous-agents specialises (Alice/Frontend, Bob/Backend, Charlie/DevOps) pour executer des taches de developpement en langage naturel depuis Discord.

---

## 2. Decisions d'architecture

| Decision | Choix | Raison |
|----------|-------|--------|
| Runtime agents | **Claude Code CLI natif** | Tous les outils deja integres (Read, Write, Edit, Bash, Git, Agent). Zero code a ecrire pour le tool-calling. |
| Orchestration | **Claude Code Agent tool** | Sous-agents avec worktrees isoles, parallelisme natif. Pas besoin de n8n ni LiteLLM. |
| Stockage repos | **NAS Unraid** (`/mnt/media/data/workspace/`) | VM a 75% disque (36 Go libres). NAS a 26 To. Montage NFS deja en place. |
| Repos geres | **Dynamique** | Tout repo present dans `/workspace/` est detecte. Aucune liste pre-configuree. |
| Autonomie | **Full auto** | Le CEO merge sans validation humaine. |
| Interface | **Discord `#dev`** + VS Code Remote SSH | Discord pour piloter, VS Code pour observer le code en temps reel. |
| Cout API | **ANTHROPIC_API_KEY** (meme cle que LiteLLM) | Migration vers Max Plan ($100/mois) possible plus tard via `claude auth login` dans le container. |
| Canal Discord | **`#dev` dedie** | Separe du conversationnel `#chat` (Jarvis homelab). |

---

## 3. Architecture deployee

```
┌───────────────────────────────────────────────────────────────┐
│  Discord                                                      │
│  ┌─────────┐  ┌─────────┐                                    │
│  │  #chat   │  │  #dev   │                                    │
│  └────┬─────┘  └────┬────┘                                    │
└───────┼──────────────┼────────────────────────────────────────┘
        │              │
        ▼              ▼
┌──────────────────────────────────────────┐
│  discord-bridge (Python, gateway)        │
│  Route par channel :                     │
│    #chat → POST n8n webhook (existant)   │
│    #dev  → POST dev-agents:8585/task     │
│           + reaction 🚀                  │
└───────┬──────────────┬───────────────────┘
        │              │
        ▼              ▼
┌──────────────┐  ┌────────────────────────────────────────────┐
│  n8n         │  │  dev-agents (HTTP :8585)                   │
│  Agent Chat  │  │                                            │
│  20 outils   │  │  POST /task → spawn claude CLI             │
│  Jarvis conv.│  │    cwd=/workspace (NAS NFS)                │
└──────────────┘  │    --dangerously-skip-permissions          │
                  │    --model claude-sonnet-4-6                │
                  │    --max-turns 50                           │
                  │                                            │
                  │  Claude Code CEO (Jarvis) :                │
                  │    ├── Read/Write/Edit (fichiers)           │
                  │    ├── Bash (npm, git, tests)               │
                  │    ├── Agent "Alice" (frontend, worktree)   │
                  │    ├── Agent "Bob" (backend, worktree)      │
                  │    └── Agent "Charlie" (devops, worktree)   │
                  │                                            │
                  │  Resultat → Discord REST API → #dev reply   │
                  │  Typing indicator toutes les 8s             │
                  └────────────────────────────────────────────┘
                                    │
                                    ▼
                  ┌────────────────────────────────────────────┐
                  │  /mnt/media/data/workspace/ (NAS Unraid)   │
                  │    ├── CLAUDE.md (personnalite CEO)         │
                  │    ├── <repo-a>/                            │
                  │    ├── <repo-b>/                            │
                  │    └── ...                                  │
                  └────────────────────────────────────────────┘
```

---

## 4. Composants deployes

### 4.1 Service `dev-agents` (nouveau)

| | |
|---|---|
| Container | `dev-agents` |
| Image | Custom build (Node.js 22 + Python 3.12 + Claude Code CLI + git) |
| Port | 8585 (HTTP, interne reseau `lan`) |
| RAM limit | 2 Go |
| Volumes | `/mnt/media/data/workspace:/workspace`, `~/.claude:/home/node/.claude` |
| Reseau | `lan` (externe) |

**`agent.py`** — Serveur HTTP aiohttp avec 2 endpoints :

| Endpoint | Methode | Role |
|----------|---------|------|
| `/task` | POST | Recoit une tache Discord, lance `claude` CLI en arriere-plan, repond 202 immediatement |
| `/health` | GET | Healthcheck |

**Fonctionnement interne :**
1. Recoit le payload `{channelId, content, author, messageId}` depuis discord-bridge
2. Verifie qu'aucune tache n'est en cours (`asyncio.Lock`)
3. Lance `claude -p "<prompt>" --output-format text --dangerously-skip-permissions --model claude-sonnet-4-6 --max-turns 50` avec `cwd=/workspace`
4. Envoie un typing indicator toutes les 8 secondes pendant l'execution
5. Quand termine, poste le resultat dans `#dev` via Discord REST API (`POST /channels/{id}/messages`)
6. Messages longs decoupes automatiquement en chunks de 1950 caracteres

**Dockerfile** — base `node:22-slim`, ajout de Python 3.12, git, openssh-client, Claude Code CLI (`@anthropic-ai/claude-code` via npm global), venv Python pour aiohttp.

### 4.2 Service `discord-bridge` (modifie)

**Changements dans `bot.py` :**

- Ajout du routage `#dev` → `dev-agents` (fire-and-forget)
- Variables `CHANNEL_DEV` et `DEV_AGENTS_URL`
- Nouvelle fonction `forward_to_dev_agents()` : POST le payload vers `http://dev-agents:8585/task`, ajoute une reaction 🚀 pour confirmer la reception
- `#chat` continue de fonctionner exactement comme avant (n8n webhook, 120s timeout, message.reply)

**Changements dans `compose.yml` :**

- Ajout des env vars `CHANNEL_DEV` et `DEV_AGENTS_URL`

### 4.3 Canal Discord `#dev` (nouveau)

| | |
|---|---|
| Nom | `#dev` |
| ID | 1488138446311784478 |
| Serveur | beta (134048232257880064) |
| Topic | Equipe dev IA — Jarvis CEO + Alice/Bob/Charlie |
| Cree via | Discord REST API (`POST /guilds/{id}/channels`) |

### 4.4 Workspace NAS (nouveau)

| | |
|---|---|
| Chemin VM | `/mnt/media/data/workspace/` |
| Chemin NAS | `192.168.0.240:/mnt/user/media/data/workspace/` |
| Montage | NFS existant via `/mnt/media` |

**`CLAUDE.md`** — fichier d'instructions lu automatiquement par Claude Code a chaque execution. Definit :
- Personnalite CEO (strategique, decisif, autonome)
- Equipe sous-agents (Alice/Frontend, Bob/Backend, Charlie/DevOps)
- Regles de delegation (simple = CEO direct, complexe = sous-agents avec worktrees)
- Workflow git (branches feature, commits atomiques, merge apres review)
- Communication en francais

---

## 5. Flux de bout en bout

```
Utilisateur tape dans Discord #dev :
  "Ajoute une page /stats dans copro-pilot avec un bar chart des charges mensuelles"

1. discord-bridge recoit le message (gateway Discord)
2. Route #dev → POST http://dev-agents:8585/task
3. discord-bridge ajoute 🚀 au message (confirmation reception)

4. dev-agents recoit le payload
5. Verifie pas de tache en cours (lock)
6. Lance en background :
   claude -p "Ajoute une page /stats..." \
     --dangerously-skip-permissions \
     --model claude-sonnet-4-6 \
     --max-turns 50
   cwd=/workspace

7. Claude Code (CEO Jarvis) :
   - Lit CLAUDE.md → charge sa personnalite
   - ls /workspace → trouve copro-pilot/
   - Analyse le repo (package.json, src/, conventions)
   - Decompose la tache :
     - Agent "Bob" (worktree) → API endpoint GET /api/stats
     - Agent "Alice" (worktree) → Page React /stats + BarChart
   - Revoit les diffs
   - Merge dans main
   - git push

8. dev-agents capture stdout (resume en francais)
9. POST Discord REST API → reply dans #dev
10. Utilisateur voit la reponse dans Discord
```

---

## 6. Fichiers crees et modifies

### Nouveaux fichiers

| Fichier | Taille | Role |
|---------|--------|------|
| `dev-agents/agent.py` | 147 lignes | Serveur HTTP + runner Claude CLI |
| `dev-agents/Dockerfile` | 19 lignes | Image Node.js 22 + Python + Claude CLI |
| `dev-agents/compose.yml` | 33 lignes | Docker Compose service |
| `dev-agents/requirements.txt` | 1 ligne | `aiohttp==3.9.5` |
| `/mnt/media/data/workspace/CLAUDE.md` | 57 lignes | Personnalite CEO + regles equipe |
| `/opt/docker/dev-agents/.env` | 5 lignes | Secrets (bot token, API key, config) |

### Fichiers modifies

| Fichier | Changement |
|---------|-----------|
| `discord-bridge/bot.py` | Ajout routage `#dev` → dev-agents, fonction `forward_to_dev_agents()` |
| `discord-bridge/compose.yml` | Ajout `CHANNEL_DEV` et `DEV_AGENTS_URL` env vars |
| `/opt/docker/discord-bridge/.env` | Ajout `CHANNEL_DEV=1488138446311784478` et `DEV_AGENTS_URL=http://dev-agents:8585/task` |

---

## 7. Etat des containers

| Container | Statut | Port | Reseau |
|-----------|--------|------|--------|
| `dev-agents` | running | 8585 | lan |
| `discord-bridge` | running | — | lan |

---

## 8. Problemes rencontres et corrections

| Probleme | Cause | Correction |
|----------|-------|-----------|
| `unknown option '--cwd'` | Le CLI Claude Code n'a pas de flag `--cwd` | Utiliser `cwd=WORKSPACE` dans `asyncio.create_subprocess_exec()` au lieu d'un flag CLI |
| `CHANNEL_DEV=0` au demarrage | Le compose.yml deploye n'avait pas les nouvelles env vars | Copier le compose.yml mis a jour vers `/opt/docker/discord-bridge/` |

---

## 9. Prochaines etapes

- [ ] Valider le flux end-to-end : message `#dev` → Claude CLI → reponse Discord
- [ ] Cloner un premier repo dans `/mnt/media/data/workspace/` pour tester
- [ ] Configurer les credentials git dans le container (SSH key ou PAT pour push)
- [ ] Migrer vers Max Plan auth (`claude auth login` dans le container) pour eliminer les couts API
- [ ] Ajouter dev-agents dans Uptime Kuma (monitor HTTP sur `:8585/health`)
- [ ] Ajouter dev-agents dans Homepage (section IA)
- [ ] Affiner les personnalites des sous-agents selon les retours

---

*Rapport d'implementation — 30 mars 2026. Service `dev-agents` deploye avec Claude Code CLI natif, canal Discord `#dev` cree, discord-bridge mis a jour avec routage dual `#chat`/`#dev`.*
