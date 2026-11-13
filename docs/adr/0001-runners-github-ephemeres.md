# ADR 0001 — Runners GitHub Actions éphémères pour la CI des repos privés

- Statut : proposé (non appliqué)
- Date : 2026-10-23
- Stack : [`gh-runners/`](../../gh-runners/)

## Contexte

Le quota de minutes GitHub Actions du compte Wifsimster est épuisé depuis le
19/10/2026 : la CI des repos privés (copro-pilot, orbite, battistella-pro) ne
démarre plus. Les repos publics ne consomment pas de minutes. play-my-house n'a
aucun workflow et n'est donc pas concerné.

La VM Docker héberge déjà 15 runners **persistants** en service systemd
(`/opt/actions-runner/<repo>`, utilisateur `deploy`, membre du groupe `docker`,
nom `docker-server`, v2.337/2.338). Ils servent aux jobs de déploiement
(`runs-on: self-hosted`) et ont, via le socket Docker de l'hôte, un accès root de
fait à toute la production. Y faire tourner la CI (code de PR, `npm install`,
builds) serait trop risqué : pas d'isolation, pas de limites, état persistant.

Ressources de la VM au 23/10 : 12 vCPU, 19 Gio de RAM (≈ 9 Gio disponibles),
swap de 8 Gio **déjà plein**, charge ≈ 1,5, 119 Go libres sur `/`.

## Décision

1. **Runners éphémères en conteneur**, image `myoung34/github-runner:ubuntu-noble`
   épinglée par digest (runner 2.338.1, Ubuntu 24.04).
   - Écartée : `ghcr.io/actions/actions-runner`, l'image officielle. Elle vise
     ARC/Kubernetes : pas de git, de Docker CLI ni de logique d'enregistrement.
     Il faudrait maintenir notre propre image, ce que `AGENTS.md` déconseille.
   - Retenue : myoung34 fournit `--ephemeral`, `--no-default-labels`,
     `--disableupdate`, git, Docker CLI, buildx, sudo, jq et curl. C'est une
     image tierce : on l'épingle par digest et on ne la met pas à jour
     automatiquement (Watchtower désactivé).
2. **Un runner par repo.** GitHub ne permet pas de runner au niveau d'un compte
   personnel (seulement repo, organisation ou entreprise). Un runner par repo
   isole aussi les repos entre eux (volumes, cache Docker, token) et limite la
   charge : un repo exécute un job à la fois.
3. **Label unique `homelab-ci`, sans les labels par défaut** (`--no-default-labels`).
   Les jobs de déploiement existants ciblent `self-hosted` : sans ce label, ils
   ne peuvent pas atterrir sur un runner de CI, et la CI (`runs-on: homelab-ci`)
   ne peut pas atterrir sur un runner de déploiement. Cette séparation ne dépend
   pas des labels des runners systemd, que nous ne pouvons pas lire sans le rôle
   admin.
4. **Docker isolé : un DinD par runner**, jamais le socket de l'hôte.
   Le runner partage le netns de son DinD (`network_mode: service:<repo>-dind`) :
   les ports des conteneurs `services:` (ex. Postgres de l'e2e) sont joignables
   sur `localhost`, et le démon n'écoute que sur `127.0.0.1:2375`. Le workspace
   `/_work` est un volume monté au même chemin dans les deux conteneurs.
   - Le DinD est `privileged`. Rootless DinD exige aussi `--privileged` et
     complique les droits sur le workspace partagé : ce n'est pas un gain réel
     ici. Sysbox supprimerait ce privilège mais demande un runtime sur l'hôte
     (piste future).
   - Cache : images de moins de 72 h et cache BuildKit récent conservés dans le
     volume `dind-<repo>`. Le reste est purgé avant chaque job, ainsi que les
     conteneurs, volumes et réseaux restants (`runner-entrypoint.sh`).
     `disk-cleanup.sh` ne touche pas ces volumes nommés : ils sont déjà purgés
     par le runner.
5. **Limites** (plafonds, pas réservations), swap interdit (`memswap_limit` égal
   à la limite mémoire), `cpu_shares: 256` (priorité 4× plus basse que la prod
   en cas de contention), `oom_score_adj: 800` (tués avant la prod), 4096 pids.

   | Repo | runner | dind | total |
   |---|---|---|---|
   | copro-pilot | 2 CPU / 2,5 Gio | 2,5 CPU / 2,5 Gio | 5 Gio |
   | orbite | 2 CPU / 1,5 Gio | 2 CPU / 2 Gio | 3,5 Gio |
   | battistella-pro | 1 CPU / 1 Gio | 1 CPU / 1 Gio | 2 Gio |

   Le pire cas (trois jobs lourds simultanés, 10,5 Gio) dépasse la RAM
   disponible. En pratique, les jobs lourds sont rares et courts (CI copro-pilot
   5 à 13 min, orbite 2 min). Si la pression mémoire monte, les runners sont tués
   en premier. Il est recommandé de traiter d'abord le swap plein (hors périmètre).
6. **Sécurité**
   - **Repos privés uniquement** : le broker vérifie `private == true` avant
     chaque émission de token. Un repo devenu public ne reçoit plus de token, et
     son runner s'arrête au redémarrage suivant.
   - **PR de forks** : le réglage GitHub « Run workflows from fork pull requests »
     reste désactivé sur ces repos privés (c'est le défaut). Les workflows
     ajoutent en plus une garde `head.repo.full_name == github.repository`.
   - **Secrets** : le PAT est un secret Compose (fichier hors du repo, monté en
     lecture seule dans `/run/secrets`), visible **uniquement** par le broker
     (`read_only`, `cap_drop: ALL`). Chaque runner ne monte, en lecture seule,
     que le token d'enregistrement de son repo (valide 1 h). Un job compromis
     peut au pire enregistrer un runner sur **son** repo pendant une heure, pas
     modifier les autres repos.
   - **Réseau** : un réseau bridge par repo (`10.230.<n>.0/24`), sans `lan` ni
     réseau backend d'une autre stack. Les runners sortent vers Internet
     (GitHub, npm, ghcr). L'accès au LAN (`192.168.0.0/24`) reste possible comme
     pour tout conteneur : un filtrage `DOCKER-USER` est proposé en option dans
     le README.
   - **Risque résiduel assumé** : un job a les droits root dans un DinD
     privilégié, donc une évasion vers l'hôte est possible. Ce niveau de
     confiance est déjà celui des runners systemd actuels (groupe `docker`).
     L'acceptation repose sur les repos privés, un seul propriétaire et aucune
     PR de fork.
7. **Mise à jour** : `DISABLE_AUTO_UPDATE`. GitHub refuse les jobs aux runners
   trop anciens (environ 30 jours après une nouvelle version). Il faut donc
   monter le digest au moins une fois par mois (procédure dans le README).

## Conséquences

- La CI ne consomme plus de minutes GitHub. Les artefacts et le cache
  `actions/cache` restent stockés chez GitHub (quota de stockage, pas de minutes).
- Les jobs d'un même repo s'exécutent en série : une PR copro-pilot prend plus de
  temps de bout en bout, d'où les ajustements de `ci.yml` (e2e et Lighthouse
  uniquement sur `main` ou à la demande, `paths-ignore` docs).
- Une panne de la VM bloque la CI de ces repos, comme elle bloque déjà leurs
  déploiements.
- Retour arrière : arrêter la stack (`docker compose down`) et revenir sur les
  PR des repos applicatifs (`runs-on: ubuntu-latest`). Voir le README.
