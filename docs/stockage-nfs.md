# Stockage NFS — Architecture et montages Unraid

Ce document décrit l'architecture de stockage utilisée par la plateforme. Il couvre les montages NFS depuis le NAS Unraid et leurs limitations.

## Vue d'ensemble

```mermaid
graph LR
    NAS[(NAS Unraid)] -->|NFS| Serveur[Serveur Debian]
    Serveur --> Films[/mnt/movies]
    Serveur --> Series[/mnt/tv-shows]
    Serveur --> Musique[/mnt/musics]
    Serveur --> DL[/mnt/downloads]
    Serveur --> Docs[/mnt/documents]
    Serveur --> Photos[/mnt/photos]
```

Le NAS Unraid héberge tous les fichiers multimédia et documents. Le serveur Debian y accède via des **montages NFS** sous `/mnt/`.

## Points de montage

| Chemin | Contenu | Services utilisateurs |
|---|---|---|
| `/mnt/movies` | Films | Plex, Radarr, Bazarr |
| `/mnt/tv-shows` | Séries TV | Plex, Sonarr, Bazarr |
| `/mnt/musics` | Musique | Plex, Lidarr |
| `/mnt/downloads` | Téléchargements en cours | qBittorrent, Sonarr, Radarr, Lidarr |
| `/mnt/documents` | Documents numérisés | Paperless-ngx |

## Comment les services accèdent au stockage

Les montages NFS sont réalisés au **niveau de l'hôte**. Les conteneurs Docker les reçoivent via des volumes bind :

```yaml
volumes:
  - /mnt/movies:/data/movies
```

Les conteneurs ne gèrent pas le NFS directement. Si le montage NFS tombe, le conteneur perd l'accès aux fichiers.

## Permissions

Tous les services multimédia utilisent les mêmes identifiants :

- `PUID=1000` — ID utilisateur
- `PGID=1000` — ID groupe
- `UMASK=002` — Masque de permissions

Ces valeurs doivent correspondre aux permissions configurées sur le partage NFS du NAS Unraid.

## Limitation : pas de hardlinks

> **Point important**

Les **hardlinks ne fonctionnent pas** entre des partages NFS séparés. Chaque point de montage (`/mnt/movies`, `/mnt/downloads`, etc.) est un partage NFS distinct.

**Conséquence :** quand Sonarr ou Radarr « déplace » un fichier depuis `/mnt/downloads` vers `/mnt/movies`, il effectue en réalité une **copie suivie d'une suppression**. Cela :

- Double temporairement l'espace disque utilisé
- Prend plus de temps qu'un déplacement instantané
- Augmente le trafic réseau

**Solution envisagée :** consolider tous les partages NFS en un seul partage unique. Les hardlinks fonctionneraient alors et les déplacements seraient instantanés.

## Données locales

Certaines données ne sont **pas sur le NAS** et restent sur le serveur :

- **Configurations des services** — Répertoires relatifs (ex: `../plex/library`)
- **Bases de données** — Volumes Docker nommés (`pg_data`, `redis_data`)
- **Certificats TLS** — `traefik/acme/`
- **Fichiers temporaires** — `/transcode` pour Plex (tmpfs en RAM)
