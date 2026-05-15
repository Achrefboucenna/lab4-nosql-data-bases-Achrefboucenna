# RAPPORT — TP1 : Redis Cache E-commerce (ShopFast)

## 1. Comparaison de performance : Cache Hit vs Miss

| Métrique | Cache MISS | Cache HIT |
|----------|-----------|-----------|
| Latence moyenne | ~80–150 ms | < 1 ms |
| Gain de performance | — | **~100×** plus rapide |
| Source des données | PostgreSQL (simulé) | Redis (RAM) |

**Interprétation :** Le premier appel (MISS) interroge la base de données avec une latence simulée de 50–150 ms. Tous les appels suivants (HIT) sont servis depuis la RAM Redis en < 1 ms. Sur 20 requêtes, le taux de cache hit atteint **95 %** dès la deuxième requête.

---

## 2. Justification des choix de modélisation

### Ex1 — Structures de données

| Donnée | Structure Redis | Justification |
|--------|----------------|---------------|
| Produit | **Hash** | Lecture/écriture de champs individuels sans désérialiser tout l'objet |
| Panier | **Hash** | `product_id → quantity` : accès O(1) par produit, mise à jour partielle |
| Historique navigation | **List** + LTRIM | Ordre chronologique naturel, fenêtre glissante sur les 10 derniers |
| Produits par catégorie | **Set** | Unicité garantie, intersection multi-catégories en O(N) |

### Ex4 — Leaderboard

Le **Sorted Set** est la structure idéale pour les classements :
- `ZADD` pour incrémenter les ventes : O(log N)
- `ZREVRANGE` pour le top N : O(log N + N)
- `ZREVRANK` pour le rang d'un produit : O(log N)

Aucune autre structure ne permet ces trois opérations avec cette efficacité.

### Ex5 — Pipeline vs Transactions

- **Pipeline** : regroupe N commandes en 1 seul aller-retour réseau → gain ~10–50× pour les bulk operations
- **MULTI/EXEC + WATCH** : garantit l'atomicité (décrémentation stock + création commande). Le `WATCH` implémente l'optimistic locking : si le stock est modifié entre `WATCH` et `EXEC`, la transaction échoue proprement et est réessayée.

---

## 3. Réponses aux questions de réflexion

### Q1 — Que se passe-t-il si Redis redémarre ?

Par défaut, Redis est une base **in-memory** : un redémarrage entraîne la **perte totale du cache**. Conséquences :
- Toutes les clés (sessions, paniers, cache produits) disparaissent
- Le taux de cache hit tombe à 0 % temporairement → pic de charge sur PostgreSQL

**Solutions :**
- **RDB (snapshotting)** : sauvegarde périodique sur disque (tolérance à la perte de quelques minutes de données)
- **AOF (Append-Only File)** : journalisation de chaque opération (durabilité quasi-totale, légère perte de performance)
- **Architecture hybride** : Redis comme cache pur avec reconstrution automatique depuis la DB au redémarrage

Pour les **sessions**, il faut utiliser AOF ou une persistance Redis dédiée, car la perte des sessions entraîne la déconnexion de tous les utilisateurs.

---

### Q2 — Comment gérer la cohérence cache/DB en cas d'accès concurrent ?

Plusieurs problèmes peuvent survenir :

| Problème | Description | Solution |
|----------|-------------|----------|
| **Cache Stampede** | Plusieurs requêtes simultanées sur un MISS → surcharge DB | Mutex distribué (`SET NX EX`) ou probabilistic early expiration |
| **Stale Read** | Lecture d'une valeur obsolète | Invalidation immédiate à chaque écriture DB (pattern **write-through**) |
| **Race condition** | Deux processus modifient stock simultanément | `WATCH` + `MULTI/EXEC` (optimistic locking) ou `INCR`/`DECR` atomiques |

Notre implémentation `update_product_and_invalidate()` (Ex3) applique la règle :
> **Écrire en DB PUIS invalider le cache** (jamais l'inverse)

---

### Q3 — Quand un TTL trop court est-il problématique ?

Un TTL trop court provoque :

1. **Taux de hit bas** → beaucoup de MISS → surcharge de la base de données
2. **Thundering herd** : si de nombreuses clés expirent simultanément, toutes les requêtes frappent la DB en même temps
3. **Dégradation de l'expérience** : les pages produits redeviennent lentes (3-4s) au lieu du gain Redis

**Exemple concret :** un TTL de 5 secondes sur les fiches produits signifie que chaque fiche est rechargée depuis la DB 12 fois par minute, annulant l'intérêt du cache pour les produits populaires.

**Recommandations pour ShopFast :**

| Données | TTL recommandé | Raison |
|---------|---------------|--------|
| Fiche produit | 5–10 minutes | Changements peu fréquents |
| Prix | 1–2 minutes | Peut changer rapidement |
| Session | 30 min (glissant) | Confort utilisateur |
| Panier | 24h | Persistance inter-sessions |
| Leaderboard | Pas de TTL | Mis à jour en temps réel via ZINCRBY |

---

## 4. Bonus — Rate Limiting

Implémenté avec un **Sliding Window Counter** (Sorted Set de timestamps) :
- Avantage sur le Fixed Window : pas d'effet de bord aux frontières des fenêtres
- Complexité : O(log N) par requête
- Limites configurées par action : search (100/min), checkout (5/10min), API (200/h)
