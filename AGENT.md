# AGENT.md

Instructions pour les agents IA autonomes travaillant sur ce dépôt.

## Résumé du projet

Infrastructure Docker auto-hébergée pour un serveur domestique Debian. ~30 services orchestrés avec Docker Compose, exposés via Traefik avec HTTPS automatique. Dépôt de configuration uniquement — pas de code source, pas de build, pas de tests.

## Structure du dépôt

Chaque service a son propre répertoire contenant un `compose.yml`. Le répertoire `multimedia/` regroupe toute la pile média (Plex, Sonarr, Radarr, etc.) en un seul projet Compose.

Répertoires importants :
- `traefik/` — Proxy inverse, point d'entrée de toute l'infrastructure
- `multimedia/` — Pile multimédia unifiée (9 services)
- `homepage/config/` — Configuration du tableau de bord (contient des clés API)
- `immich-app/` — Gestion photo avec fichiers hwaccel

## Commandes essentielles

```bash
# Démarrer un service
cd <service-name> && docker compose up -d

# Arrêter un service
cd <service-name> && docker compose down

# Voir les logs d'un service
cd <service-name> && docker compose logs -f

# Mettre à jour les images
cd <service-name> && docker compose pull && docker compose up -d

# Créer le réseau partagé (une seule fois)
docker network create lan
```

## Conventions à respecter

### Structure d'un fichier compose.yml

```yaml
name: service-name

services:
  service:
    container_name: service-name
    image: registry/image:tag
    restart: unless-stopped
    environment:
      - TZ=Europe/Paris
      - PUID=1000
      - PGID=1000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.<name>.entrypoints=websecure"
      - "traefik.http.routers.<name>.rule=Host(`<name>.battistella.ovh`)"
      - "traefik.http.services.<name>.loadBalancer.server.port=<port>"
      - "com.centurylinklabs.watchtower.enable=true"
    networks:
      lan:

networks:
  lan:
    external: true
```

### Nommage

- Répertoires : minuscules, séparés par des tirets (`home-assistant`)
- Noms de conteneurs : identiques au nom du répertoire
- Domaines : `<service>.battistella.ovh`
- Exceptions : `proxy.` (Traefik), `indexer.` (Prowlarr), `cv.` (Resume), `blog.` (Blog)

### Secrets

- Ne jamais coder en dur des mots de passe ou clés API dans les compose.yml
- Utiliser des fichiers `.env` (automatiquement ignorés par git)
- Utiliser `${VARIABLE}` pour l'interpolation

### Bases de données

- PostgreSQL 16-alpine avec healthcheck `pg_isready`
- Redis/Valkey avec healthcheck `redis-cli ping`
- Utiliser `depends_on` avec `condition: service_healthy`
- Volumes nommés pour la persistance

### Réseau

- Tous les services utilisent le réseau Docker externe `lan`
- Exception : Plex utilise `network_mode: host`

## Workflow de développement

1. Modifier le `compose.yml` du service concerné
2. Appliquer avec `docker compose up -d`
3. Commiter le `compose.yml` modifié (seuls les compose.yml sont suivis par git)
4. Pas de pipeline CI/CD — le déploiement est manuel

## Notes importantes

- **Pas de Dockerfiles** — Tous les services utilisent des images pré-construites
- **Pas de build** — Aucune compilation. Les changements s'appliquent via `docker compose up -d`
- **Fichiers suivis par git** : uniquement `compose.yml`, `hwaccel.*.yml`, et `homepage/config/`
- **Le fichier `homepage/config/services.yaml` contient des clés API** — Ne pas exposer de secrets supplémentaires
- **Les chemins `/mnt/*` sont des montages NFS** depuis le NAS Unraid
- **Les hardlinks ne fonctionnent pas** entre partages NFS séparés
