# Reprise après sinistre

Runbook de restauration de l'infrastructure Docker en cas de panne majeure (crash serveur, corruption disque, etc.).

## Prérequis

- Serveur Debian avec Docker et Docker Compose installés
- Accès au NAS Unraid (montages NFS sous `/mnt/`)
- Accès au dépôt Git contenant les fichiers `compose.yml`
- **La passphrase borg** — sans elle le dépôt Hetzner est illisible (voir ci-dessous)

## 0. Où sont les sauvegardes

Trois niveaux, du plus proche au plus résistant :

| Niveau | Emplacement | Contenu | Fréquence |
|--------|-------------|---------|-----------|
| Local | `/opt/docker/pg-backup/backups` | 14 dumps PostgreSQL | quotidien 03:00 |
| Local | `/home/wifsimster/backups` | tarballs gramps + config HA | hebdo dimanche |
| LAN (NAS) | `/mnt/media/data/backups/` | `postgres/`, `gramps/`, `home-assistant/` | quotidien / hebdo |
| **Hors site** | dépôt borg Hetzner Storage Box | **tout ce qui compte** | quotidien 04:45 |

Le dépôt hors site contient deux familles d'archives, prunées indépendamment :

- `photos-*` (hebdo, dimanche 02:30) — `/mnt/media/photos` + `pg_dumpall` immich
- `data-*` (quotidien, 04:45) — dumps PostgreSQL (sauf immich, déjà dans
  `photos-*`), bases SQLite, `.env` de tous les services, documents Paperless,
  tarballs gramps/HA

**En cas d'incendie ou de vol, seul le niveau hors site subsiste.** Le serveur
et le NAS sont dans la même maison.

### ⚠️ Dépendance circulaire à surveiller — suivi : issue #37

La passphrase borg vit dans `/root/.borg-photos.env` et
`/root/borg-photos-key-paper.txt` — **sur ce serveur**. Elle est aussi dans
Vaultwarden, dont la sauvegarde est… dans le dépôt borg chiffré par cette même
passphrase.

Si le serveur disparaît sans qu'une copie de la passphrase existe **ailleurs**
(papier imprimé rangé hors du domicile, coffre bancaire, autre machine), le
dépôt Hetzner est définitivement illisible et toutes les sauvegardes hors site
sont perdues. C'est le seul maillon que l'automatisation ne peut pas couvrir.

### Restaurer depuis le dépôt hors site

```bash
# Les identifiants du dépôt sont dans /root/.borg-photos.env
set -a; source /root/.borg-photos.env; set +a
export BORG_RSH="ssh -i /root/.ssh/hetzner_borg -p 23 -o BatchMode=yes"
export BORG_REMOTE_PATH=borg-1.2

borg list                          # lister les archives disponibles
borg list ::data-YYYYMMDD-HHMM     # inspecter le contenu d'une archive

# Extraire (les chemins sont relatifs au répertoire courant)
mkdir -p /var/tmp/restore && cd /var/tmp/restore
borg extract ::data-YYYYMMDD-HHMM var/tmp/state-backup-staging   # SQLite + .env
borg extract ::data-YYYYMMDD-HHMM opt/docker/pg-backup/backups   # dumps PostgreSQL
borg extract ::data-YYYYMMDD-HHMM mnt/media/documents            # documents Paperless
```

## 1. Restaurer le système de base

```bash
# Cloner le dépôt
git clone <url-du-depot> /opt/docker
cd /opt/docker

# Créer le réseau Docker partagé
docker network create lan

# Restaurer les fichiers .env pour chaque service.
# Ils sont volontairement gitignorés, donc ABSENTS du dépôt cloné ci-dessus.
# Ils sont en revanche dans chaque archive data-* du dépôt borg :
#   configs.tar.gz contient tous les /opt/docker/*/.env et compose.yml
tar -xzf /var/tmp/restore/var/tmp/state-backup-staging/configs.tar.gz -C /opt/docker
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

# Racontine
docker exec -i racontine-db pg_restore \
  -U racontine -d racontine --clean --if-exists \
  < pg-backup/backups/racontine_YYYY-MM-DD_HHMMSS.dump

# Umami
docker exec -i umami-db pg_restore \
  -U umami -d umami --clean --if-exists \
  < pg-backup/backups/umami_YYYY-MM-DD_HHMMSS.dump

# Ghostfolio (nom de base avec tiret)
docker exec -i ghostfolio-postgres pg_restore \
  -U ghostfolio -d ghostfolio-db --clean --if-exists \
  < pg-backup/backups/ghostfolio-db_YYYY-MM-DD_HHMMSS.dump

# Koe / Toko / WAWPTN / Yamtrack — même schéma :
#   docker exec -i <conteneur> pg_restore -U <user> -d <base> --clean --if-exists < <dump>
```

> **Langfuse a été supprimé le 2026-08-05** (boucle de redémarrages OOM) ; ses
> anciens dumps ne sont plus produits.

### 4.2 bis Restaurer les bases SQLite

`pg_restore` ne les voit pas. Elles sont dans `data-*/var/tmp/state-backup-staging/sqlite/`.
**Arrêter le service avant de remplacer le fichier**, et supprimer les `-wal`/`-shm`
résiduels, sinon SQLite rejouera un journal qui ne correspond plus à la base.

```bash
SQL=/var/tmp/restore/var/tmp/state-backup-staging/sqlite

# Vaultwarden — le plus critique
cd /opt/docker/vaultwarden && docker compose down
rm -f data/db.sqlite3-wal data/db.sqlite3-shm
cp $SQL/vaultwarden.sqlite3 data/db.sqlite3
cp $SQL/vaultwarden-rsa_key.pem data/rsa_key.pem   # sans lui, toutes les sessions cassent
tar -xzf $SQL/vaultwarden-attachments.tar.gz -C data/
chown -R 1000:1000 data && docker compose up -d

# Home Assistant — réseau Zigbee (ZHA)
cd /opt/docker/home-assistant && docker compose down
rm -f config/zigbee.db-wal config/zigbee.db-shm
cp $SQL/zigbee.sqlite3 config/zigbee.db
docker compose up -d
# Sans cette base, il faut ré-appairer tous les équipements Zigbee un par un.

# Solopilot (CRM, factures, compta)
cd /opt/docker/solopilot && docker compose down
docker run --rm -v solopilot_bot-data:/d -v $SQL:/s alpine \
  sh -c 'rm -f /d/bot.db-wal /d/bot.db-shm && cp /s/solopilot.sqlite3 /d/bot.db'
docker compose up -d

# Birthday invitation (RSVP)
cd /opt/docker/birthday-invitation && docker compose down
docker run --rm -v birthday-invitation_birthday_db:/d -v $SQL:/s alpine \
  sh -c 'rm -f /d/rsvp.db-wal /d/rsvp.db-shm && cp /s/birthday.sqlite3 /d/rsvp.db'
docker compose up -d

# Orbite — le conteneur tourne en uid 65532 : le fichier restauré doit lui appartenir
cd /opt/docker/orbite && docker compose down
docker run --rm -v orbite-data:/d -v $SQL:/s alpine \
  sh -c 'rm -f /d/orbite.sqlite-wal /d/orbite.sqlite-shm && cp /s/orbite.sqlite3 /d/orbite.sqlite && chown 65532:65532 /d/orbite.sqlite && chmod 600 /d/orbite.sqlite'
docker compose up -d
```

Vérifier chaque base restaurée avant de redémarrer le service :

```bash
sqlite3 <fichier> "PRAGMA integrity_check;"   # doit répondre exactement "ok"
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

## Couverture des sauvegardes

### Couvert automatiquement

| Donnée | Sauvegardé par | Où |
|--------|----------------|-----|
| 14 bases PostgreSQL | `pg-backup` (quotidien) | local + NAS + hors site |
| Vaultwarden (base, clé RSA, pièces jointes) | `state-backup.sh` | hors site |
| Solopilot, zigbee.db, RSVP birthday, Orbite | `state-backup.sh` | hors site |
| Fichiers `.env` de tous les services | `state-backup.sh` (`configs.tar.gz`) | hors site |
| Documents Paperless | `state-backup.sh` | NAS + hors site |
| Photos Immich (388 Go) | `photos-backup.sh` (hebdo) | hors site |
| Config Home Assistant | `ha-config-backup.sh` (hebdo) | NAS + hors site |
| Gramps | `gramps-backup.sh` (hebdo) | NAS + hors site |

### Non couvert — et pourquoi c'est acceptable

| Donnée | Emplacement | Action |
|--------|-------------|--------|
| Passphrase borg | `/root/.borg-photos.env` | ⚠️ **Doit exister hors du domicile** (voir §0) |
| Config Traefik `acme.json` | `traefik/` | Regénéré automatiquement (Let's Encrypt) |
| Données Redis | Volumes Docker | Cache et files d'attente, perte acceptable |
| Historique recorder HA | `home-assistant_v2.db` | Volontairement exclu (~760 Mo de courbes) |
| Miniatures / transcodes Immich | `thumbs/`, `encoded-video/` | 44 Go regénérés par Immich après restauration |
| Films / séries / musique | `/mnt/media` | Volumétrie non sauvegardable, re-téléchargeable |
| Bibliothèque Plex | Volume Docker | Reconstruite par scan (métadonnées perdues) |

## Vérifier que les sauvegardes fonctionnent vraiment

Une sauvegarde jamais relue n'est qu'une hypothèse. Trois contrôles :

```bash
# 1. Fraîcheur — quand chaque job a-t-il tourné pour la dernière fois ?
tail -3 /var/log/state-backup.log /var/log/photos-backup.log \
        /var/log/ha-config-backup.log /var/log/gramps-backup.log

# 2. Intégrité du dépôt (automatique le 1er de chaque mois, alerte Discord)
/opt/docker/borg-check.sh

# 3. Exercice de restauration — à refaire au moins une fois par an.
#    Extraire une archive récente et vérifier le contenu SANS rien écraser :
mkdir -p /var/tmp/drill && cd /var/tmp/drill
set -a; source /root/.borg-photos.env; set +a
export BORG_RSH="ssh -i /root/.ssh/hetzner_borg -p 23 -o BatchMode=yes"
export BORG_REMOTE_PATH=borg-1.2
borg extract "::$(borg list --short --glob-archives 'data-*' | tail -1)" \
     var/tmp/state-backup-staging
sqlite3 var/tmp/state-backup-staging/sqlite/vaultwarden.sqlite3 \
     "PRAGMA integrity_check; SELECT COUNT(*) FROM ciphers;"
# Comparer au vault en production : les compteurs doivent correspondre.
sqlite3 var/tmp/state-backup-staging/sqlite/orbite.sqlite3 \
     "PRAGMA integrity_check; SELECT COUNT(*) FROM person;"
rm -rf /var/tmp/drill
```

Dernier exercice réalisé : **2026-09-02** — vaultwarden (452 entrées, identique
à la production), zigbee (24 équipements), solopilot et birthday tous à
`integrity_check = ok` ; 13 dumps PostgreSQL validés au `pg_restore --list`.

## Contacts et escalade

- **Alertes Discord** (salon #backups) : `photos-backup`, `state-backup` et
  `borg-check` notifient succès ET échec ; `pg-backup` notifie uniquement les
  échecs. `state-backup` alerte aussi si aucun dump PostgreSQL n'a moins de
  26 h — c'est le garde-fou qui détecte un `crond` mort dans le conteneur
  `pg-backup`, cas qu'aucune alerte d'échec ne peut signaler.
- **Uptime Kuma** : Surveillance de disponibilité avec alertes configurées
- **Beszel** : Alertes système (CPU, RAM, disque) vers Discord
