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
192.168.0.240:/mnt/user/media /mnt/media nfs defaults,_netdev 0 0
```

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

## Données locales

Certaines données ne sont **pas sur le NAS** et restent sur le serveur :

- **Configurations des services** — Répertoires relatifs (ex: `../plex/library`)
- **Bases de données** — Volumes Docker nommés (`pg_data`, `redis_data`)
- **Certificats TLS** — `traefik/acme/`
- **Fichiers temporaires** — `/transcode` pour Plex (tmpfs en RAM)
