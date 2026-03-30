# Equipe de Developpeurs IA — Rapport de conception

> Damien Battistella — 30 mars 2026
> **Statut : BROUILLON — en attente de validation**

---

## 1. Vision

Deployer une equipe d'agents IA developpeurs sur l'infrastructure homelab existante. Chaque agent a une personnalite, un role defini, et des competences specialisees. Un agent **CEO** orchestre l'ensemble : il recoit les objectifs, decompose en taches, delegue aux sous-agents, revoit leur travail, et valide les merges.

L'interface principale est **Discord `#chat`** (via Jarvis) — tu donnes un objectif en langage naturel, le CEO prend le relais.

---

## 2. Etat des lieux infra

### Ressources disponibles

| Metrique | Valeur | Commentaire |
|----------|--------|-------------|
| vCPU | 12 | AMD Ryzen 5 3600 (6c/12t) |
| RAM totale | 24 Gi | 9.9 Gi disponibles |
| Swap | 8 Gi | 4.7 Gi utilises |
| Disque | 146 Go total | 36 Go libres (75%) |
| GPU | Aucun | RTX 2070 passthrough abandonne |

### Dev tools deja en place

| Outil | Statut |
|-------|--------|
| VS Code Server (SSH Remote) | Installe, 1.5 Go (~/.vscode-server) |
| Cursor Server | Installe, 24 Mo (~/.cursor-server) — usage leger |
| Claude Code CLI | **Non installe** |
| Git | Installe |
| Docker + Compose | En production (68 containers) |
| GitHub Actions Runners x6 | Actifs (copro-pilot, personal-blog, toko, resume, wawptn, x-ai-weekly-bot) |
| n8n | En production (7 workflows) |
| LiteLLM | En production (Sonnet + Haiku + qwen2.5:7b) |
| Ollama | En production (qwen2.5:7b CPU) |

### Repos de travail

Les agents travaillent sur tous les repos presents dans `/mnt/media/data/workspace/`. Aucune liste pre-configuree — tu clones ce que tu veux, les agents le detectent automatiquement.

---

## 3. Architecture proposee

### 3.1 Vue d'ensemble

```
                    ┌─────────────────────────┐
                    │      Discord #dev        │
                    │  (ou #chat existant)     │
                    └──────────┬──────────────┘
                               │ objectif en langage naturel
                               ▼
                    ┌─────────────────────────┐
                    │    AGENT CEO "Jarvis"    │
                    │  Sonnet 4.6 (1M ctx)     │
                    │  Personnalite : CTO      │
                    │  strategique, decisif    │
                    └──────────┬──────────────┘
                               │ decomposition en taches
                    ┌──────────┼──────────────────┐
                    │          │                   │
                    ▼          ▼                   ▼
            ┌──────────┐ ┌──────────┐     ┌──────────────┐
            │ AGENT    │ │ AGENT    │     │ AGENT        │
            │ FRONTEND │ │ BACKEND  │     │ DEVOPS       │
            │ "Alice"  │ │ "Bob"    │     │ "Charlie"    │
            │ Sonnet   │ │ Sonnet   │     │ Haiku/Sonnet │
            └────┬─────┘ └────┬─────┘     └──────┬───────┘
                 │            │                   │
                 ▼            ▼                   ▼
            ┌──────────────────────────────────────────┐
            │         SANDBOXES (git worktrees)        │
            │  /workspace/<repo>/<agent>-<branch>      │
            │  Chaque agent travaille sur sa branche   │
            └──────────────────┬───────────────────────┘
                               │
                               ▼
            ┌──────────────────────────────────────────┐
            │       GIT (GitHub — source de verite)    │
            │  Push → PR → Review CEO → Merge          │
            └──────────────────────────────────────────┘
```

### 3.2 Options techniques pour le runtime des agents

#### Strategie evaluees

| Strategie | Principe | Verdict |
|-----------|----------|---------|
| **A) n8n + LiteLLM + API** | Meme architecture que Jarvis (#chat) — tool-calling manuel, require('http'), sandbox | **Mauvais pour du dev** — tout est a reconstruire, coute des tokens API |
| **B) Orchestrateur custom Python** | Script maison appelant l'API Anthropic, parse tool_calls | **Trop d'effort** — 3-6 mois de dev pour un resultat inferieur |
| **C) OpenHands (ex-OpenDevin)** | Framework open-source, sandbox Docker par agent | **Trop lourd** — ~2-3 Go RAM par agent, pas de multi-agents natif |
| **D) Claude Code natif** | CLI `claude` avec Agent tool, worktrees, outils natifs | **Recommande** — zero outil a construire, $0 (Max Plan) |

### 3.3 Strategie retenue : Claude Code natif (Option D)

Claude Code est deja utilise dans ce projet (ce rapport est genere avec). Tous les outils necessaires au dev sont **natifs** :

| Outil natif | Usage |
|-------------|-------|
| `Read`, `Write`, `Edit` | Lecture/ecriture/modification de fichiers |
| `Bash` | Terminal (npm, git, docker, tests, build) |
| `Glob`, `Grep` | Recherche dans le code |
| `Agent` | Spawn de sous-agents avec contexte isole |
| `Agent(isolation: "worktree")` | Sous-agent dans un worktree git isole |

**Seul morceau a construire :** un daemon qui recoit un message Discord `#dev` et lance un process `claude` CLI. Le reste est natif.

```
discord-bridge (existant, a etendre)
  → detecte message dans #dev
  → lance: claude --print --dangerously-skip-permissions \
           --system-prompt CEO_PERSONALITY \
           --cwd /mnt/media/data/workspace \
           "Objectif: <message utilisateur>"
  → capture la sortie
  → poste la reponse dans #dev
```

**n8n et LiteLLM ne sont PAS utilises** pour les agents dev. Ils restent en place pour Jarvis (`#chat` — bot conversationnel avec 20 outils). Les deux stacks sont independantes.

---

## 4. Les agents — personnalites et roles

### 4.1 CEO — "Jarvis" (existant, a enrichir)

| | |
|---|---|
| Modele | Sonnet 4.6 (1M contexte) |
| Role | CTO / Chef de projet technique |
| Personnalite | Strategique, direct, exigeant sur la qualite du code. Decompose les objectifs en taches atomiques. Revoit chaque PR avant merge. Ne code pas lui-meme — il delegue et valide. |
| Outils | Orchestration agents, git (merge/PR), Discord (communication), lecture de code (review) |
| Declencheur | Message Discord, cron (daily standup), webhook GitHub (PR review) |

### 4.2 Frontend — "Alice"

| | |
|---|---|
| Modele | Sonnet 4.6 |
| Role | Developpeur frontend senior |
| Personnalite | Perfectionniste sur l'UX et l'accessibilite. Bonne connaissance de React/Next.js, Tailwind, shadcn/ui. Propose des ameliorations visuelles. Teste toujours en mobile-first. |
| Competences | React, Next.js, TypeScript, CSS/Tailwind, composants UI, responsive design |
| Outils | Fichiers (Read/Write/Edit), terminal (npm, build, lint), git (commit, push), navigateur (screenshots optionnel) |

### 4.3 Backend — "Bob"

| | |
|---|---|
| Modele | Sonnet 4.6 |
| Role | Developpeur backend senior |
| Personnalite | Rigoureux, oriente performance et securite. Expert API REST, schemas de base de donnees, migrations. Privilegie la simplicite au cleverness. Documente les decisions d'architecture en commentaires. |
| Competences | Node.js, Python, PostgreSQL, Redis, API design, migrations, auth, validation |
| Outils | Fichiers, terminal (tests, migrations, linters), git, acces aux bases PostgreSQL en lecture |

### 4.4 DevOps — "Charlie"

| | |
|---|---|
| Modele | Haiku 4.5 (triage) / Sonnet 4.6 (execution) |
| Role | Ingenieur DevOps / SRE |
| Personnalite | Pragmatique, minimaliste. Specialiste Docker, CI/CD, monitoring. Alerte si une modification impacte l'infra. Optimise les Dockerfiles et les pipelines. |
| Competences | Docker, Docker Compose, GitHub Actions, Traefik, scripts bash, monitoring, PostgreSQL ops |
| Outils | Fichiers, terminal (docker, gh CLI, ssh), git, acces Docker socket (lecture seule) |

### 4.5 QA — "Diana" (optionnel, phase 2)

| | |
|---|---|
| Modele | Haiku 4.5 |
| Role | Testeur / Reviewer |
| Personnalite | Sceptique par defaut. Cherche les edge cases, les regressions, les failles de securite. Ne valide jamais sans avoir lu chaque ligne modifiee. |
| Competences | Tests unitaires, tests d'integration, code review, securite (OWASP), linting |
| Outils | Fichiers (Read), terminal (tests), git (diff, log), commentaires GitHub |

---

## 5. Workflow type

### 5.1 Cas d'usage : "Ajoute une page de stats dans Copro-Pilot"

```
Toi (Discord #dev):
  "Ajoute une page /stats dans copro-pilot qui affiche le nombre de
   charges par mois en bar chart"

CEO (Jarvis):
  1. Analyse le repo copro-pilot (structure, stack, conventions)
  2. Decompose :
     - Tache 1 (Bob): API endpoint GET /api/stats/charges-monthly
     - Tache 2 (Alice): Page /stats avec composant BarChart (recharts)
     - Tache 3 (Charlie): Verifier que le build Docker passe
  3. Delegue en parallele (Bob + Alice sur des branches separees)

Bob (branche feat/stats-api):
  - Lit le schema Prisma existant
  - Cree l'endpoint API avec aggregation par mois
  - Ecrit un test
  - Commit + push

Alice (branche feat/stats-page):
  - Lit les composants existants pour les conventions UI
  - Cree la page /stats avec recharts BarChart
  - Fetch l'API de Bob
  - Commit + push

CEO (review):
  - Lit les diffs des 2 branches
  - Verifie la coherence (types partages, noms de routes)
  - Merge Bob → main, puis Alice → main (ou rebase)
  - Delegue a Charlie pour le build check

Charlie:
  - `docker compose build` pour verifier
  - Si OK → CEO repond sur Discord "Done ✅, PR #42 merged"
  - Si KO → remonte l'erreur au CEO qui redelegue
```

### 5.2 Standup quotidien (cron 9h)

```
CEO (automatique, chaque matin):
  - Liste les PRs ouvertes
  - Resume l'activite de la veille (commits, merges)
  - Identifie les taches bloquees
  - Poste le resume dans Discord #dev
```

---

## 6. Infrastructure necessaire

### 6.1 Composants a deployer

| Composant | Type | RAM estimee | Disque | Priorite |
|-----------|------|-------------|--------|----------|
| Claude Code CLI | npm global | ~200 Mo par session | 500 Mo | P0 |
| Workspace repos | Git clones | ~100 Mo par repo | ~2 Go (7 repos) | P0 |
| Orchestrateur CEO | Service Node.js ou Python | ~300 Mo | 100 Mo | P0 |
| code-server (optionnel) | Container Docker | ~500 Mo | 500 Mo | P2 |
| Gitea (optionnel) | Container Docker | ~256 Mo | 500 Mo | P3 |

**Impact RAM total : ~1-2 Go supplementaires** (les agents utilisent l'API Claude, pas de LLM local pour le coding).

### 6.2 Stockage des repos

**Repos sur le NAS Unraid** via le montage NFS existant `/mnt/media`. Pas de nouveau share — on utilise le sous-dossier `data/`.

```
/mnt/media/data/workspace/          # NFS Unraid (192.168.0.240:/mnt/user/media)
├── <repo-a>/                       # git clone depuis GitHub (ou autre)
│   └── worktrees/                  # branches des agents
│       ├── alice-feat-xxx/
│       └── bob-feat-yyy/
├── <repo-b>/
└── ...                             # tu ajoutes ce que tu veux, quand tu veux
```

**Fonctionnement :** les agents scannent `/mnt/media/data/workspace/` et travaillent sur tous les repos presents. Tu y clones un repo → les agents y ont acces. Tu le supprimes → ils l'ignorent. Aucune config a mettre a jour.

**Pourquoi sur le NAS :**
- La VM Docker est a 75% (36 Go libres) — pas de place pour des repos + node_modules
- Le NAS Unraid a 26 To disponibles
- Le montage NFS est deja en place (`/mnt/media`), zero config supplementaire
- La latence NFS (~2-5x vs SSD local) est negligeable : le bottleneck est l'API Claude (2-10s par appel), pas le disque

Les repos GitHub restent la **source de verite**. Les agents `git push` vers GitHub, les runners CI/CD existants deploient automatiquement.

### 6.3 Securite

| Risque | Mitigation |
|--------|-----------|
| Agent execute du code malveillant | Sandbox : pas de `sudo`, user dedie `agent` sans privileges root |
| Agent supprime des fichiers critiques | Worktrees isoles, jamais de write sur `main` direct |
| Agent push du code bugged en prod | Branche protegee `main` — merge uniquement par le CEO apres review |
| Agent accede aux secrets .env | User `agent` n'a pas acces a `/opt/docker/*/env` |
| Cout API explose | Rate limit dans LiteLLM, budget max/jour configurable |
| Agent boucle indefiniment | Timeout par tache (10 min), max 3 retries |

---

## 7. Integration avec l'existant

### 7.1 Discord

Deux approches possibles :

**A) Enrichir le canal `#chat` existant (simple)**
- Jarvis/CEO repond deja dans `#chat`
- Ajouter les commandes dev : "cree une feature...", "review la PR #12..."
- Les agents postent leur avancement dans le meme canal

**B) Canal dedie `#dev` (recommande)**
- Separer le dev du conversationnel quotidien
- Le CEO poste les standups, les reviews, les merges
- Thread par tache pour garder le contexte

### 7.2 GitHub Actions

Les runners existants continuent de fonctionner normalement. Le flux est :
1. Agent push sur une branche feature
2. GitHub Actions execute les tests/build (runner existant)
3. CEO lit le resultat CI et decide du merge

### 7.3 n8n

n8n peut servir de declencheur supplementaire :
- Webhook GitHub (PR opened) → notifier le CEO pour review
- Cron 9h → standup automatique
- Webhook Discord → deleguer au CEO

---

## 8. Estimation des couts

### Cout : $0 supplementaire (Max Plan)

Les agents dev utilisent le **Claude Code SDK** qui tourne sous l'abonnement Max Plan existant. Pas de cout API Anthropic supplementaire.

| Poste | Cout |
|-------|------|
| Abonnement Max Plan (deja en place) | $100/mois |
| Agents dev (Claude Code SDK) | **$0** (inclus dans Max Plan) |
| Jarvis/n8n conversationnel (API via LiteLLM) | ~$8-20/mois (inchange) |

**Risque :** rate limiting si plusieurs agents travaillent en parallele intensivement. Mitigation : le CEO serialise les taches non-urgentes et parallelise uniquement quand necessaire.

> **Note :** Le Max Plan couvre Claude Code CLI + SDK. Les outils natifs (Read, Write, Edit, Bash, Git, Agent) sont tous inclus — pas besoin de reconstruire les tool calls manuellement comme dans n8n.

---

## 9. Plan de deploiement

### Phase 1 — Fondations (1-2 jours)

- [ ] Installer Claude Code CLI sur la VM (`npm install -g @anthropic-ai/claude-code`)
- [ ] Creer le user `agent` avec acces limite
- [ ] Cloner les 7 repos dans `/workspace/`
- [ ] Configurer les credentials GitHub (SSH key ou PAT pour le user agent)
- [ ] Tester Claude Code CLI manuellement sur un repo

### Phase 2 — Premier agent solo (1-2 jours)

- [ ] Ecrire le system prompt du CEO
- [ ] Creer un script orchestrateur minimal (Node.js/Python)
- [ ] Tester : "Ajoute un composant Button dans copro-pilot"
- [ ] Valider le flux : Discord → CEO → Agent → git push → PR

### Phase 3 — Equipe multi-agents (3-5 jours)

- [ ] Ajouter Alice (frontend) et Bob (backend) avec personnalites
- [ ] Implementer la delegation parallele (CEO → sous-agents)
- [ ] Implementer la review automatique (CEO lit les diffs)
- [ ] Ajouter le standup cron

### Phase 4 — Production (continu)

- [ ] Ajouter Charlie (DevOps) et Diana (QA)
- [ ] Affiner les personnalites selon les resultats
- [ ] Dashboard couts dans Langfuse
- [ ] Canal Discord `#dev` dedie

---

## 10. Questions ouvertes

Avant de demarrer, j'ai besoin de tes retours sur ces points :

### Q1 — Scope des repos
Les agents doivent travailler sur **lesquels** de tes repos ? Tous les 7 ? Seulement certains ?

Les stacks que je vois :
- copro-pilot, toko, wawptn, resume, personal-blog → probablement Next.js/TypeScript
- x-ai-weekly-bot → Python
- docker-setup → YAML/config

### Q2 — Autonomie vs controle ✅
**Full auto.** Le CEO merge sans validation humaine. Les agents sont autonomes de bout en bout.

### Q3 — Interface de pilotage ✅
**Discord + VS Code.** Discord pour piloter les agents (objectifs, suivi). VS Code Remote SSH pour voir le code en temps reel et intervenir si besoin.

### Q4 — Git : GitHub vs local
- **A) GitHub reste la source de verite** — les agents push sur GitHub, les PRs sont sur GitHub
- **B) Gitea local** — miroir local + push vers GitHub (plus rapide, fonctionne offline)

Je recommande A pour commencer (plus simple, tes runners CI sont deja configures sur GitHub).

### Q5 — Priorite des projets
Sur quel repo veux-tu tester en premier ? Je recommande un repo petit et actif pour valider le flux avant de generaliser.

### Q6 — Budget API confortable ?
Avec Sonnet 4.6, le coding multi-agents va couter significativement plus que l'usage conversationnel actuel (~$8-20/mois). Es-tu OK avec un budget de $50-100/mois pour le dev IA, ou faut-il optimiser (Haiku pour le triage, Sonnet seulement pour le coding) ?

### Q7 — Canal Discord ✅
**Canal `#dev` dedie.** Les agents developpeurs postent dans `#dev`, separe du conversationnel `#chat`.

---

*Rapport v1 — 30 mars 2026. En attente de validation avant implementation.*
