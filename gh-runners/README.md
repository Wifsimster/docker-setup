# gh-runners — runners GitHub Actions éphémères (CI des repos privés)

Conception, choix et risques : [ADR 0001](../docs/adr/0001-runners-github-ephemeres.md).

| Conteneur | Rôle |
|---|---|
| `gh-runners-broker` | seul à lire le PAT ; renouvelle toutes les 30 min un token d'enregistrement par repo **privé** |
| `gh-runners-<repo>` | runner éphémère, label `homelab-ci`, un job puis redémarrage propre |
| `gh-runners-<repo>-dind` | démon Docker isolé du runner (builds, `services:`) |

Repos : `copro-pilot`, `orbite`, `battistella-pro`. Les runners systemd de
`/opt/actions-runner/` (déploiements, label `self-hosted`) ne changent pas.

## Prérequis (humain)

1. **PAT fine-grained** (Settings → Developer settings → Fine-grained tokens) :
   - Resource owner : `Wifsimster`, expiration 90 jours maximum ;
   - Repository access : *Only select repositories* → copro-pilot, orbite,
     battistella-pro (aucun repo public) ;
   - Permissions : **Administration : Read and write** (Metadata : read est
     ajouté d'office). Aucune autre permission.
2. **Réglage de chaque repo** : Settings → Actions → General → *Fork pull
   request workflows in private repositories* : laisser décoché.

## Application (nécessite l'OK explicite de l'humain)

Sur la VM, une fois la PR mergée :

```bash
cd /opt/docker && git pull --ff-only
cd /opt/docker/gh-runners
cp -n .env.example .env                       # -n : n'écrase jamais un .env existant
sudo install -d -m 711 -o root -g root secrets     # 711 : compose doit pouvoir traverser
sudo install -m 600 -o root -g root /dev/null secrets/github_pat.new
sudoedit secrets/github_pat.new               # coller le PAT, une seule ligne
sudo mv -n secrets/github_pat.new secrets/github_pat
docker compose pull
docker compose up -d --wait
```

Vérification :

```bash
docker compose ps                              # 7 conteneurs, dind « healthy »
docker compose logs broker | tail              # « token renouvelé » ×3, aucun token affiché
docker compose logs copro-pilot | grep -E "Listening for Jobs|Error"
gh api repos/Wifsimster/copro-pilot/actions/runners -q '.runners[] | "\(.name) \(.status) \([.labels[].name])"'
```

Il faut ensuite merger les PR `ci/self-hosted-runners` des repos applicatifs.
Avant cela, aucun job ne cible `homelab-ci`.

## Retour arrière

```bash
cd /opt/docker/gh-runners && docker compose down          # garde volumes et cache
# nettoyage complet, optionnel :
docker compose down -v && sudo rm -f secrets/github_pat
```

Ensuite : revert des PR `ci/self-hosted-runners` (retour à `ubuntu-latest`),
puis révocation du PAT sur GitHub. Les runners éphémères se désenregistrent à
l'arrêt. Sinon, GitHub supprime les runners éphémères hors ligne au bout d'un
jour. Les runners systemd et les déploiements ne sont pas touchés.

## Mise à jour du runner (au moins une fois par mois)

```bash
docker pull myoung34/github-runner:ubuntu-noble
docker image inspect myoung34/github-runner:ubuntu-noble --format '{{index .RepoDigests 0}}'
```

Reporter le digest dans `compose.yml` (`x-runner-image`) via une PR, puis
`docker compose up -d` sur la VM. Même démarche pour `docker:29-dind`. Pour
revenir en arrière : remettre l'ancien digest et relancer `docker compose up -d`.

## Ajouter ou retirer un repo

Dupliquer ou retirer le trio `<repo>-dind` / `<repo>`, les volumes
`token-|dind-|work-<repo>` et le réseau `10.230.<n>.0/24`. Mettre à jour
`BROKER_REPOS` et le montage `/tokens/<repo>` du broker. Le PAT doit couvrir le
repo, et ce repo doit être **privé**.

## Option : couper l'accès au LAN depuis les runners

Non appliqué par défaut, car c'est une modification du pare-feu de l'hôte :

```bash
sudo iptables -I DOCKER-USER -s 10.230.0.0/16 -d 192.168.0.0/16 -m conntrack ! --ctstate ESTABLISHED,RELATED -j DROP
# retour arrière :
sudo iptables -D DOCKER-USER -s 10.230.0.0/16 -d 192.168.0.0/16 -m conntrack ! --ctstate ESTABLISHED,RELATED -j DROP
```

Les DinD utilisent les DNS publics (`1.1.1.1`, `9.9.9.9`) et ne dépendent donc
pas de Pi-hole. La règle n'est pas persistante après un redémarrage de la VM.
