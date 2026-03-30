# Reprise après sinistre

Runbook de restauration de l'infrastructure Docker en cas de panne majeure (crash serveur, corruption disque, etc.).

## Prérequis

- Serveur Debian avec Docker et Docker Compose installés
- Accès au NAS Unraid (montages NFS sous `/mnt/`)
- Accès au dépôt Git contenant les fichiers `compose.yml`
- Dumps PostgreSQL (`pg-backup/backups/*.dump`)
- Fichiers `.env` de chaque service (stockés séparément, **non versionnés**)

## 1. Restaurer le système de base

```bash
# Cloner le dépôt
git clone <url-du-depot> /opt/docker
cd /opt/docker

# Créer le réseau Docker partagé
docker network create lan

# Restaurer les fichiers .env pour chaque service
# (depuis votre stockage sécurisé de secrets)
```

## 2. Restaurer les montages NFS

Vérifier que les montages Unraid sont opérationnels dans `/etc/fstab` :

```bash
# Montage NFS unique attendu
mount | grep /mnt/media

# Point de montage unique :
# /mnt/media → NAS Unraid (192.168.0.240:/mnt/user/media)
#   ├── movies/      → Films (Radarr/Plex)
#   ├── tv-shows/    → Séries TV (Sonarr/Plex)
#   ├── musics/      → Musique (Lidarr/Plex)
#   ├── downloads/   → Téléchargements (qBittorrent)
#   ├── documents/   → Données Paperless
#   ├── photos/      → Photos (Immich)
#   └── data/        → Données diverses
```

## 3. Démarrer l'infrastructure critique

Ordre de démarrage recommandé :

```bash
# 1. Reverse proxy (requis pour l'accès web)
cd /opt/docker/traefik && docker compose up -d

# 2. DNS (résolution locale)
cd /opt/docker/pihole && docker compose up -d

# 3. Monitoring (pour surveiller la restauration)
cd /opt/docker/beszel && docker compose up -d
cd /opt/docker/uptime-kuma && docker compose up -d
cd /opt/docker/dozzle && docker compose up -d
```

## 4. Restaurer les bases de données PostgreSQL

### 4.1 Démarrer uniquement les conteneurs de base de données

```bash
# Pour chaque service avec base de données :
cd /opt/docker/paperless-ngx && docker compose up -d db
cd /opt/docker/immich-app && docker compose up -d database
cd /opt/docker/the-box && docker compose up -d postgres
cd /opt/docker/copro-pilot && docker compose up -d postgres
cd /opt/docker/infisical && docker compose up -d db
cd /opt/docker/n8n && docker compose up -d db
cd /opt/docker/litellm && docker compose up -d db
cd /opt/docker/langfuse && docker compose up -d db
cd /opt/docker/toko && docker compose up -d postgres
cd /opt/docker/wawptn && docker compose up -d postgres
```

Attendre que les healthchecks passent :

```bash
docker ps --filter "health=healthy" --format "{{.Names}}" | grep -E "postgres|db"
```

### 4.2 Restaurer les dumps

Les dumps sont au format custom (`pg_dump -Fc`), stockés dans `pg-backup/backups/`.

```bash
# Paperless
docker exec -i paperless-db pg_restore \
  -U paperless -d paperless --clean --if-exists \
  < pg-backup/backups/paperless_YYYY-MM-DD_HHMMSS.dump

# Immich
docker exec -i immich_postgres pg_restore \
  -U postgres -d immich --clean --if-exists \
  < pg-backup/backups/immich_YYYY-MM-DD_HHMMSS.dump

# The Box
docker exec -i the-box-postgres pg_restore \
  -U thebox -d thebox --clean --if-exists \
  < pg-backup/backups/thebox_YYYY-MM-DD_HHMMSS.dump

# Copro-Pilot
docker exec -i copro-pilot-postgres pg_restore \
  -U copro_pilot -d copro_pilot --clean --if-exists \
  < pg-backup/backups/copro_pilot_YYYY-MM-DD_HHMMSS.dump

# Infisical
docker exec -i infisical-db pg_restore \
  -U infisical -d infisical --clean --if-exists \
  < pg-backup/backups/infisical_YYYY-MM-DD_HHMMSS.dump

# LiteLLM
docker exec -i litellm-db pg_restore \
  -U litellm -d litellm --clean --if-exists \
  < pg-backup/backups/litellm_YYYY-MM-DD_HHMMSS.dump

# n8n
docker exec -i n8n-db pg_restore \
  -U n8n -d n8n --clean --if-exists \
  < pg-backup/backups/n8n_YYYY-MM-DD_HHMMSS.dump

# Langfuse
docker exec -i langfuse-db pg_restore \
  -U langfuse -d langfuse --clean --if-exists \
  < pg-backup/backups/langfuse_YYYY-MM-DD_HHMMSS.dump
```

> **Note :** Remplacer `YYYY-MM-DD_HHMMSS` par le timestamp du dump le plus récent.

### 4.3 Vérifier la restauration

```bash
# Vérifier que chaque base contient des données
docker exec paperless-db psql -U paperless -d paperless -c "SELECT count(*) FROM documents_document;" 2>/dev/null
docker exec immich_postgres psql -U postgres -d immich -c "SELECT count(*) FROM assets;" 2>/dev/null
```

## 5. Démarrer tous les services

```bash
# Services avec base de données (déjà partiellement démarrés)
cd /opt/docker/paperless-ngx && docker compose up -d
cd /opt/docker/immich-app && docker compose up -d
cd /opt/docker/the-box && docker compose up -d
cd /opt/docker/copro-pilot && docker compose up -d
cd /opt/docker/infisical && docker compose up -d
cd /opt/docker/n8n && docker compose up -d
cd /opt/docker/litellm && docker compose up -d
cd /opt/docker/langfuse && docker compose up -d
cd /opt/docker/toko && docker compose up -d
cd /opt/docker/wawptn && docker compose up -d

# Stack multimédia
cd /opt/docker/multimedia && docker compose up -d

# Stack IA
cd /opt/docker/ollama && docker compose up -d
cd /opt/docker/open-webui && docker compose up -d
cd /opt/docker/discord-bridge && docker compose up -d

# Autres services
for svc in home-assistant vaultwarden gramps wakapi stirling \
           personal-blog resume homepage portainer watchtower \
           unifi birthday-invitation pg-backup ntfy \
           x-ai-weekly-bot dev-agents; do
  cd /opt/docker/$svc && docker compose up -d
  cd /opt/docker
done
```

## 6. Vérifications post-restauration

### Services web

Vérifier que chaque service répond via Traefik :

```bash
# Liste des sous-domaines à tester
for sub in paperless immich the-box copro-pilot infisical \
           gramps wakapi plex sonarr radarr homepage \
           vaultwarden dozzle portainer beszel uptime stirling \
           n8n litellm langfuse ai toko wawptn; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://${sub}.${DOMAIN}")
  echo "${sub}: ${STATUS}"
done
```

### Certificats TLS

```bash
# Vérifier que le fichier ACME existe
ls -la /opt/docker/traefik/acme.json

# Vérifier un certificat
echo | openssl s_client -servername paperless.${DOMAIN} -connect ${DOMAIN}:443 2>/dev/null | openssl x509 -noout -dates
```

### Sauvegardes

```bash
# Vérifier que le cron de backup tourne
docker exec pg-backup crontab -l

# Lancer un backup test
docker exec pg-backup sh /backup.sh
```

## Données non sauvegardées

Les éléments suivants ne sont **pas** couverts par les sauvegardes automatiques et doivent être restaurés manuellement :

| Donnée | Emplacement | Action |
|--------|-------------|--------|
| Fichiers `.env` | Chaque dossier service | Restaurer depuis stockage sécurisé |
| Config Traefik `acme.json` | `traefik/` | Sera regénéré automatiquement (Let's Encrypt) |
| Données Redis | Volumes Docker | Pertes acceptables (cache, files d'attente) |
| Médias Immich | Volume `UPLOAD_LOCATION` | Restaurer depuis NAS/backup externe |
| Médias Paperless | Volume `paperless_media` | Restaurer depuis NAS (`/mnt/documents`) |
| Config Home Assistant | Volume monté | Restaurer depuis backup HA intégré |
| Données Vaultwarden | Volume Docker | **Critique** — restaurer depuis backup externe |
| Bibliothèque Plex | Volume Docker | Reconstruit par scan (métadonnées perdues) |

## Contacts et escalade

- **Alertes Discord** : Les échecs de backup sont notifiés automatiquement via webhook
- **Uptime Kuma** : Surveillance de disponibilité avec alertes configurées
- **Beszel** : Alertes système (CPU, RAM, disque) vers Discord
