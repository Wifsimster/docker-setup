# Stockage NFS — Architecture et montage Unraid

Ce document décrit l'architecture de stockage utilisée par la plateforme. Le NAS Unraid partage un **unique point de montage NFS** contenant tous les sous-répertoires médias.

## Vue d'ensemble

```mermaid
graph LR
    NAS[(NAS Unraid<br/>192.168.0.240)] -->|NFS unique| Serveur[Serveur Debian]
    Serveur --> Media[/mnt/media]
    Media --> Films[movies/]
    Media --> Series[tv-shows/]
    Media --> Musique[musics/]
    Media --> DL[downloads/]
    Media --> Docs[documents/]
    Media --> Photos[photos/]
    Media --> Data[data/]
```

## Point de montage unique

Un seul partage NFS est monté sur l'hôte :

```
192.168.0.240:/mnt/user/media /mnt/media nfs defaults,_netdev,nofail,x-systemd.mount-timeout=30s 0 0
```

> `nofail` : un NAS injoignable ne bloque pas le boot. `x-systemd.mount-timeout=30s` : abandon après 30 s si le NAS ne répond pas. Voir [Ordre de démarrage au boot](#ordre-de-démarrage-au-boot) pour la dépendance Docker → montage.

### Sous-répertoires

| Chemin | Contenu | Services utilisateurs |
|---|---|---|
| `/mnt/media/movies` | Films | Plex, Radarr |
| `/mnt/media/tv-shows` | Séries TV | Plex, Sonarr |
| `/mnt/media/musics` | Musique | Plex, Lidarr |
| `/mnt/media/downloads` | Téléchargements en cours | qBittorrent, Sonarr, Radarr, Lidarr |
| `/mnt/media/documents` | Documents numérisés | Paperless-ngx |
| `/mnt/media/photos` | Photos et vidéos | Immich |
| `/mnt/media/data` | Données diverses | — |

## Comment les services accèdent au stockage

Les montages NFS sont réalisés au **niveau de l'hôte**. Les conteneurs Docker les reçoivent via des volumes bind :

```yaml
volumes:
  - /mnt/media/movies:/data/movies
```

Les conteneurs ne gèrent pas le NFS directement. Si le montage NFS tombe, le conteneur perd l'accès aux fichiers.

## Permissions

Tous les services multimédia utilisent les mêmes identifiants :

- `PUID=1000` — ID utilisateur
- `PGID=1000` — ID groupe
- `UMASK=002` — Masque de permissions

Ces valeurs doivent correspondre aux permissions configurées sur le partage NFS du NAS Unraid.

## Hardlinks et déplacements instantanés

Le montage NFS unique permet les **hardlinks** entre tous les sous-répertoires. Quand Sonarr ou Radarr importe un fichier depuis `/mnt/media/downloads` vers `/mnt/media/movies`, il crée un **hardlink instantané** au lieu d'une copie.

Avantages :

- **Pas de duplication d'espace** — le fichier n'existe qu'une fois sur le disque
- **Import instantané** — pas de copie réseau
- **Seed continu** — le fichier reste disponible dans le répertoire de téléchargement pour le seeding

> Cela suit les recommandations des [TRaSH Guides](https://trash-guides.info/Hardlinks/How-to-setup-for/Unraid/) pour la configuration Unraid.

## Configuration Unraid

Sur Unraid, un partage unique `media` contient tous les sous-répertoires :

```
/mnt/user/media/
├── movies/
├── tv-shows/
├── musics/
├── downloads/
├── documents/
├── photos/
└── data/
```

Le partage est exporté via NFS dans les paramètres Unraid (Settings > NFS).

## Ordre de démarrage au boot

Au démarrage de l'hôte, **Docker doit attendre que `/mnt/media` soit monté** avant de restaurer les conteneurs. Sinon, tout conteneur qui bind-monte un sous-répertoire de `/mnt/media` échoue à l'étape de création du montage et **reste arrêté** — la restart policy ne le relance pas (elle ne s'applique qu'aux conteneurs déjà démarrés qui se terminent, pas à ceux qui échouent au montage → `RestartCount=0`).

### Symptôme

Après un reboot (typiquement une mise à jour kernel via `unattended-upgrades` qui redémarre l'hôte), une partie des conteneurs reste `Exited`. Dans les logs de `dockerd` :

```
failed to start container … error while creating mount source path
'/mnt/media/downloads': … no such device
'/mnt/media/musics':    … mkdir /mnt/media: file exists
```

Conteneurs concernés (tous ceux qui bind-montent `/mnt/media`) : **plex, sonarr, radarr, lidarr, metube, downtify, qbittorrent, immich_server** (`/photos`), **paperless-webserver** (`/paperless-inbox`), **n8n** (`/musics`).

### Cause

`docker.service` n'attend que `network-online.target`, **pas** le montage NFS. L'option `x-systemd.automount` (essayée en 2026-06) **aggrave** le problème : elle diffère le montage jusqu'au premier *accès*, et le démarrage de Docker ne compte pas comme cet accès.

### Correctif

**1. Montage NFS eager** (pas d'automount) dans `/etc/fstab` — voir la ligne en haut de ce document. Le montage est réalisé au boot, `nofail` garantit qu'un NAS mort ne bloque jamais le démarrage.

**2. Drop-in systemd** `/etc/systemd/system/docker.service.d/wait-for-media.conf` :

```ini
[Unit]
Wants=mnt-media.mount
After=mnt-media.mount
```

`Wants` (dépendance *souple*, pas `Requires`) : si le NAS est injoignable au boot, Docker démarre quand même — seuls les conteneurs médias attendent, au lieu de bloquer toute la stack.

Après modification : `sudo systemctl daemon-reload`. Vérifier avec `systemctl show docker.service -p After -p Wants | grep media`.

### Récupération manuelle (si le problème survient malgré tout)

Le NFS est monté (autofs le déclenche à l'accès), il suffit de relancer les conteneurs arrêtés :

```bash
docker start $(docker ps -aq --filter status=exited)
```

## Données locales

Certaines données ne sont **pas sur le NAS** et restent sur le serveur :

- **Configurations des services** — Répertoires relatifs (ex: `../plex/library`)
- **Bases de données** — Volumes Docker nommés (`pg_data`, `redis_data`)
- **Certificats TLS** — `traefik/acme/`
- **Fichiers temporaires** — `/transcode` pour Plex (tmpfs en RAM)
