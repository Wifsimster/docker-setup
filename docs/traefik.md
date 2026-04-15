# Traefik — Proxy inverse et certificats TLS

Ce document explique le fonctionnement de Traefik, le point d'entrée unique de toute l'infrastructure. Il couvre le routage, les certificats HTTPS et les middlewares de sécurité.

## Rôle de Traefik

Traefik est le **proxy inverse** de la plateforme. Il remplit trois fonctions :

- **Router** chaque sous-domaine `*.battistella.ovh` vers le bon conteneur
- **Générer et renouveler** les certificats TLS via Let's Encrypt
- **Appliquer** des règles de sécurité HTTP (headers HSTS, XSS, etc.)

## Comment ça fonctionne

```mermaid
graph LR
    Internet((Internet)) -->|Port 80/443| Traefik[Traefik v3.6]
    Traefik -->|Labels Docker| Conteneurs([~65 conteneurs])
    Traefik -->|Provider fichier| Plex[Plex - host network]
    LetsEncrypt[Let's Encrypt] -.->|Certificats TLS| Traefik
    OVH[OVH DNS] -.->|Challenge DNS| LetsEncrypt
```

Traefik découvre automatiquement les services via les **labels Docker**. Chaque conteneur déclare son sous-domaine et son port. Traefik crée le routage sans configuration manuelle. Exception : Plex utilise le réseau hôte, donc son routage passe par un fichier de configuration statique.

## Points d'entrée

| Point d'entrée | Port | Rôle |
|---|---|---|
| `web` | 80 | HTTP — redirige vers HTTPS |
| `websecure` | 443 | HTTPS — point d'entrée principal |

Toutes les requêtes HTTP sont automatiquement redirigées vers HTTPS.

## Certificats TLS

Les certificats sont obtenus via **Let's Encrypt** avec le **challenge DNS OVH** :

- Le challenge DNS ne nécessite pas d'ouvrir le port 80 pour la validation
- Les certificats couvrent chaque sous-domaine individuellement
- Le renouvellement est automatique
- Les certificats sont stockés dans `traefik/acme/letsencrypt.json`

> **Détail technique**

Les variables OVH nécessaires sont dans le fichier `.env` de Traefik :
- `OVH_APPLICATION_KEY`
- `OVH_APPLICATION_SECRET`
- `OVH_CONSUMER_KEY`
- `OVH_ENDPOINT`

## Labels Docker

Chaque service déclare son routage via des labels. Le nom du routeur doit être **cohérent** dans tous les labels :

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.ROUTEUR.entrypoints=websecure"
  - "traefik.http.routers.ROUTEUR.rule=Host(`sous-domaine.battistella.ovh`)"
  - "traefik.http.services.ROUTEUR.loadBalancer.server.port=PORT"
```

## Provider fichier

Pour les services qui n'utilisent pas le réseau Docker `lan` (comme Plex en mode hôte), le routage se fait via des fichiers YAML dans `traefik/config/`.

Le fichier `traefik/config/plex.yml` définit le routage vers Plex sur le port 32400 de l'hôte.

## Middlewares de sécurité

Traefik applique des **headers de sécurité** sur le dashboard :

| Header | Fonction |
|---|---|
| **HSTS** | Force HTTPS pendant 1 an avec sous-domaines |
| **X-XSS-Protection** | Protection contre les attaques XSS |
| **X-Content-Type-Options** | Empêche le sniffing de type MIME |

## ForwardAuth — Authentification

Certaines applications n'ont pas d'authentification intégrée (ex. Homepage). Elles sont protégées par un middleware **forwardAuth** qui délègue la vérification de session à [Tinyauth](../tinyauth/compose.yml).

```mermaid
sequenceDiagram
    participant U as 📱 Navigateur
    participant T as 🔀 Traefik
    participant TA as 🔐 Tinyauth
    participant S as 🏠 Service (Homepage)
    U->>T: GET homepage.battistella.ovh
    T->>TA: forwardAuth http://tinyauth:3000/api/auth/traefik
    TA-->>T: 307 → tinyauth.battistella.ovh/login
    T-->>U: 307 (redirection)
    U->>TA: Formulaire login (HTML + TOTP)
    TA-->>U: Cookie de session `.battistella.ovh`
    U->>T: GET homepage.battistella.ovh (avec cookie)
    T->>TA: forwardAuth (cookie)
    TA-->>T: 200 OK
    T->>S: Requête proxy
    S-->>U: Réponse
```

Le cookie est scopé sur `.battistella.ovh`, ce qui permet de réutiliser la même session pour d'autres services protégés par le même middleware. Tinyauth détecte les navigateurs via l'en-tête `User-Agent` et renvoie un 307 vers `/login` ; les clients non-navigateur reçoivent un 401 avec l'en-tête `x-tinyauth-location`.

**Services actuellement protégés :**

| Service | Middleware |
|---|---|
| Homepage | `tinyauth@docker` |

**Déclaration du middleware** (labels du conteneur `tinyauth`) :

```yaml
- "traefik.http.middlewares.tinyauth.forwardauth.address=http://tinyauth:3000/api/auth/traefik"
```

**Utilisation sur un service** :

```yaml
- "traefik.http.routers.<service>.middlewares=tinyauth@docker"
```

> 🎯 Tinyauth est une **solution intermédiaire**. Une migration vers **Authelia SSO** est prévue pour centraliser l'authentification sur l'ensemble des services internes avec WebAuthn, ACLs par service et session unique — voir [#30](https://github.com/Wifsimster/docker-setup/issues/30).

## Timeouts étendus

Les timeouts de lecture et écriture sont configurés à **600 secondes**. Cela permet l'upload de fichiers volumineux, notamment les vidéos vers Immich.

## Tableau de bord

Le dashboard Traefik est accessible sur `proxy.battistella.ovh`. Il offre une vue d'ensemble de tous les routeurs, services et middlewares actifs.

## Logs

Traefik journalise en format JSON :

- **Logs d'accès** : requêtes avec codes d'erreur 400-599 uniquement
- **Logs applicatifs** : niveau WARN minimum
- Stockés dans `traefik/logs/`
