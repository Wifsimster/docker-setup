# Stripe — Abonnements

Trois services facturent des abonnements via Stripe. Tous pointent sur le même compte Stripe **live** depuis le 2026-04-29.

| Service | Compte | Domaine webhook | Endpoint |
|---|---|---|---|
| copro-pilot | `acct_1SFA9OK2G0vOIqPa` (live) | `copro-pilot.battistella.ovh` | `/api/subscription/webhook` |
| toko | `acct_1SFA9OK2G0vOIqPa` (live) | `toko.battistella.ovh` | `/api/webhooks/stripe` |
| wawptn | `acct_1SFA9OK2G0vOIqPa` (live) | `wawptn.battistella.ovh` | `/api/subscription/webhook` |

> Avant le 2026-04-29, les services utilisaient un compte de test distinct (`acct_1SFA9VGcsiDYgDIf`, profil CLI `environnement de test new business`). Les webhooks de test correspondants ont été désactivés (status `disabled`) — récupérables via le dashboard ou `stripe webhook_endpoints update <id> -d disabled=false`.

## Variables d'environnement

Chaque service expose les variables suivantes dans son `.env` (jamais commité) :

```bash
STRIPE_SECRET_KEY=rk_live_...        # Clé restreinte (CLI Stripe, expire 2026-07-27)
STRIPE_WEBHOOK_SECRET=whsec_...      # Unique par endpoint webhook
STRIPE_PRICE_ID=price_...            # toko, wawptn (un seul prix)
# copro-pilot : 7 prix (Essentiel, Pro, Pro Extra ×2, Entreprise, Entreprise Extra ×2)
```

## Événements webhook abonnés

| Événement | copro-pilot | toko | wawptn |
|---|:-:|:-:|:-:|
| `checkout.session.completed` | ✅ | ✅ | ✅ |
| `customer.subscription.created` | — | ✅ | — |
| `customer.subscription.updated` | ✅ | ✅ | ✅ |
| `customer.subscription.deleted` | ✅ | ✅ | ✅ |
| `invoice.payment_succeeded` | — | ✅ | — |
| `invoice.payment_failed` | ✅ | ✅ | ✅ |

## Gestion des clés

**État actuel (2026-04-29)** : les trois services partagent la clé restreinte du CLI Stripe (`rk_live_…P60W`). Elle expire le **2026-07-27**.

**Cible** : une clé restreinte par service, sans date d'expiration, scopée au minimum :
- `Customers` RW
- `Subscriptions` RW
- `Checkout Sessions` RW
- `Prices` read
- `Products` read

Création : Dashboard → Developers → API keys → Create restricted key (mode live).

## Vérifier un endpoint webhook

```bash
# Lister les endpoints live
stripe --api-key=$KEY webhook_endpoints list

# Détails d'un endpoint
stripe --api-key=$KEY webhook_endpoints retrieve we_...
```

Le secret `whsec_…` n'est retourné qu'à la création — conservé dans le `.env` du service correspondant.

## Backups de migration

Les `.env` pré-migration sont conservés à titre de référence (gitignorés) :

```
/opt/docker/copro-pilot/.env.test.bak.20260428
/opt/docker/toko/.env.test.bak.20260428
/opt/docker/wawptn/.env.test.bak.20260428
```

À supprimer une fois un paiement live de bout en bout validé.
