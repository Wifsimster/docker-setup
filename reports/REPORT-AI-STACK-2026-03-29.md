# Agents IA Homelab — Audit VM & Faisabilité

**Date :** 2026-03-29
**Scope :** Audit de la VM Docker existante pour le déploiement du stack agents IA

---

## 1. Caractéristiques de la VM "docker" (192.168.0.237)

| Ressource | Valeur |
|-----------|--------|
| **Hostname** | docker |
| **OS** | Ubuntu 24.04.4 LTS (Noble Numbat) |
| **CPU** | AMD Ryzen 5 3600 6-Core (12 threads) |
| **RAM totale** | 24 Go (26 040 Mo) |
| **RAM disponible** | ~14 Go |
| **Swap** | 8 Go (non utilisé) |
| **Disque principal** | 100 Go LVM (`/dev/mapper/ubuntu--vg-ubuntu--lv`) |
| **Disque utilisé** | 74 Go (81%) |
| **Disque libre** | 18 Go |
| **NFS** | 26 To NAS Unraid (192.168.0.240:/mnt/user/media → /mnt/media) |
| **Docker** | v29.2.1 |
| **Réseau** | 192.168.0.237/24, réseau Docker bridge `lan` |
| **GPU** | Aucun (virtio VGA uniquement) |

### Services déjà en production (~30 containers)

Traefik, Home Assistant, Mosquitto MQTT, Plex, Sonarr, Radarr, Lidarr, Bazarr, Prowlarr, qBittorrent, Seerr, Tautulli, Trotarr, Immich, Paperless-NGX, Homepage, Vaultwarden, Infisical, Portainer, Dozzle, Beszel, Uptime Kuma, Watchtower, Pi-hole, Gramps, Memos, Wakapi, Stirling PDF, Personal Blog, Resume, Copro-Pilot, The Box, UniFi Controller, pg-backup.

PostgreSQL (x5 instances) et Redis/Valkey (x4 instances) déjà actifs.

---

## 2. Besoins du stack IA

### RAM estimée

| Service | RAM |
|---------|-----|
| LiteLLM + PostgreSQL dédié | ~400 Mo |
| n8n | ~300 Mo |
| Langfuse (web + worker + ClickHouse) | ~500 Mo |
| ntfy | ~30 Mo |
| Open WebUI | ~300 Mo |
| Dify (multi-containers) | ~1 Go |
| Qdrant | ~200 Mo |
| **Total sans Ollama** | **~2.8 Go** |
| Ollama + qwen2.5:14b | +10-16 Go |
| **Total avec Ollama 14b** | **~13-19 Go** |

### Disque estimé

| Besoin | Espace |
|--------|--------|
| Images Docker (tous services IA) | ~5-8 Go |
| Données PostgreSQL / ClickHouse | ~2-5 Go |
| Modèle Ollama qwen2.5:14b | ~9-10 Go |
| Qdrant (données vectorielles) | ~1 Go |
| Langfuse traces (croissance) | ~1-5 Go/mois |
| **Total minimal (sans Ollama)** | **~10-18 Go** |
| **Total avec Ollama** | **~20-28 Go** |

---

## 3. Analyse de faisabilité — VM actuelle

| Critère | Status | Détail |
|---------|--------|--------|
| **CPU** | OK | 12 threads suffisants pour orchestration + API cloud |
| **RAM sans Ollama** | OK | 14 Go dispo − 2.8 Go = ~11 Go de marge |
| **RAM avec Ollama 14b** | BLOQUANT | 14 Go dispo − 13-19 Go = swap permanent, crash probable |
| **Disque** | BLOQUANT | 18 Go libres pour ~20+ Go de besoin |
| **Réseau** | OK | Réseau `lan` existant, NAS accessible |
| **GPU** | N/A | Pas de GPU passthrough, Ollama CPU-only (lent mais fonctionnel) |

### Risques identifiés

1. **Disk full** — Le pull des images Docker seul (~5-8 Go) + données = risque de saturation disque à 100%, impactant TOUS les 30 services existants
2. **Contention RAM** — Même sans Ollama, ajouter 2.8 Go de services réduit les marges pour les pics de charge des services existants (Immich ML, Plex transcoding)
3. **PostgreSQL** — 5 instances PG déjà actives, le stack IA en ajoute 2-3 de plus (Langfuse, n8n, Dify). Envisager la mutualisation
4. **Redis** — 4 instances Redis déjà actives, +2-3 de plus

---

## 4. Options de déploiement

### Option A — Étendre la VM actuelle (minimum viable)

- Étendre le disque Proxmox à **200 Go** minimum
- Pas d'Ollama (API cloud uniquement via LiteLLM)
- Mutualiser PostgreSQL/Redis existants si possible
- **Avantage :** simple, rapide
- **Risque :** contention avec les services existants

```bash
# Après extension disque dans Proxmox
sudo lvextend -l +100%FREE /dev/mapper/ubuntu--vg-ubuntu--lv
sudo resize2fs /dev/mapper/ubuntu--vg-ubuntu--lv
```

### Option B — VM dédiée "ai-stack" (recommandé)

Créer une nouvelle VM sur Proxmox dédiée au stack IA :

| Ressource | Sans Ollama | Avec Ollama qwen2.5:14b | Avec Ollama qwen2.5:3b |
|-----------|-------------|--------------------------|-------------------------|
| CPU | 4 cores | 8 cores | 6 cores |
| RAM | 16 Go | 40-48 Go | 24 Go |
| Disque | 100 Go | 200 Go | 150 Go |

- **Avantage :** isolation totale, pas de risque pour les services existants
- **Inconvénient :** consomme des ressources Proxmox supplémentaires

### Option C — Compromis : VM dédiée légère + modèle local léger

- VM dédiée : **8 cores / 24 Go RAM / 150 Go disque**
- Ollama avec `qwen2.5:3b` (~3-4 Go RAM) au lieu de 14b
- Suffisant pour triage/classification locale, Sonnet/Haiku pour le raisonnement

---

## 5. Éléments déjà en place (réutilisables)

| Service | Status | Action |
|---------|--------|--------|
| Uptime Kuma | Déjà déployé | Ajouter les monitors IA |
| PostgreSQL | 5 instances actives | Potentiellement mutualisable |
| Redis | 4 instances actives | Potentiellement mutualisable |
| Traefik | Actif | Ajouter les routes pour les nouveaux services |
| Watchtower | Actif | Auto-update des nouveaux containers |
| Beszel | Actif | Monitoring système déjà en place |

---

## 6. Prochaine étape

Vérifier les ressources disponibles sur l'hôte Proxmox (RAM totale, CPU, stockage) pour dimensionner soit l'extension de la VM actuelle, soit la création d'une VM dédiée.
