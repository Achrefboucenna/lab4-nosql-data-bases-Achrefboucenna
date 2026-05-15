"""
Ex3 — Cache-Aside avec TTL (5 pts)
ShopFast — Pattern Cache-Aside, mesure hit/miss, invalidation
"""

import redis
import json
import time
import random

r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

CACHE_TTL = 300        # 5 minutes par défaut
STATS_KEY  = "cache:stats"   # Hash pour stocker hit/miss


# ─────────────────────────────────────────────
# Simulation de la base de données PostgreSQL
# ─────────────────────────────────────────────

FAKE_DB = {
    "p001": {"id": "p001", "name": "Samsung A54",      "price": 45000, "stock": 150, "category": "electronics"},
    "p002": {"id": "p002", "name": "Nike Air Max",     "price": 12000, "stock": 80,  "category": "shoes"},
    "p003": {"id": "p003", "name": "Livre Python",     "price": 2500,  "stock": 200, "category": "books"},
    "p004": {"id": "p004", "name": "Huile d'olive Bio","price": 800,   "stock": 500, "category": "food"},
}

def db_get_product(product_id: str) -> dict | None:
    """Simule une requête DB lente (50-150ms)."""
    time.sleep(random.uniform(0.05, 0.15))   # latence simulée
    return FAKE_DB.get(product_id)

def db_update_product(product_id: str, data: dict) -> bool:
    """Simule une mise à jour en DB."""
    if product_id in FAKE_DB:
        FAKE_DB[product_id].update(data)
        return True
    return False


# ─────────────────────────────────────────────
# Helpers statistiques
# ─────────────────────────────────────────────

def _record_hit():
    r.hincrby(STATS_KEY, "hits",   1)
    r.hincrby(STATS_KEY, "total",  1)

def _record_miss():
    r.hincrby(STATS_KEY, "misses", 1)
    r.hincrby(STATS_KEY, "total",  1)

def get_cache_stats() -> dict:
    """Retourne les statistiques de cache."""
    raw = r.hgetall(STATS_KEY)
    hits   = int(raw.get("hits",   0))
    misses = int(raw.get("misses", 0))
    total  = int(raw.get("total",  0))
    hit_rate = round(hits / total * 100, 2) if total > 0 else 0
    return {"hits": hits, "misses": misses, "total": total, "hit_rate": f"{hit_rate}%"}

def reset_cache_stats():
    r.delete(STATS_KEY)


# ─────────────────────────────────────────────
# Cache-Aside : lecture
# ─────────────────────────────────────────────

def get_product_cached(product_id: str, ttl: int = CACHE_TTL) -> dict | None:
    """
    Pattern Cache-Aside :
    1. Chercher dans Redis
    2. HIT  → retourner directement
    3. MISS → interroger DB → stocker dans Redis avec TTL → retourner
    """
    cache_key = f"cache:product:{product_id}"

    # ── Étape 1 : Lecture cache
    cached = r.get(cache_key)
    if cached:
        _record_hit()
        return json.loads(cached)

    # ── Étape 2 : MISS → DB
    _record_miss()
    product = db_get_product(product_id)
    if product is None:
        return None

    # ── Étape 3 : Stocker dans Redis
    r.setex(cache_key, ttl, json.dumps(product))
    return product


# ─────────────────────────────────────────────
# Invalidation du cache
# ─────────────────────────────────────────────

def invalidate_product_cache(product_id: str) -> bool:
    """Supprime le cache d'un produit (write-through / invalidation)."""
    cache_key = f"cache:product:{product_id}"
    return bool(r.delete(cache_key))


def update_product_and_invalidate(product_id: str, new_data: dict) -> bool:
    """
    Met à jour la DB PUIS invalide le cache.
    Garantit la cohérence cache ↔ DB.
    """
    success = db_update_product(product_id, new_data)
    if success:
        invalidate_product_cache(product_id)
    return success


# ─────────────────────────────────────────────
# Mesure de performance : hit vs miss
# ─────────────────────────────────────────────

def benchmark_cache(product_id: str = "p001", nb_requests: int = 20):
    """
    Compare le temps de réponse avec et sans cache.
    """
    reset_cache_stats()
    invalidate_product_cache(product_id)  # partir d'un cache vide

    latencies = []

    for i in range(nb_requests):
        start = time.time()
        get_product_cached(product_id)
        elapsed = (time.time() - start) * 1000   # ms
        latencies.append(elapsed)

    stats = get_cache_stats()
    avg_all   = sum(latencies) / len(latencies)
    avg_miss  = latencies[0]                       # premier appel = MISS
    avg_hits  = sum(latencies[1:]) / (len(latencies) - 1)

    print("=" * 50)
    print(f"  Requêtes totales : {nb_requests}")
    print(f"  Cache hits       : {stats['hits']}  ({stats['hit_rate']})")
    print(f"  Cache misses     : {stats['misses']}")
    print(f"  Latence MISS     : {avg_miss:.1f} ms")
    print(f"  Latence HIT moy. : {avg_hits:.2f} ms")
    print(f"  Gain moyen       : {avg_miss / avg_hits:.0f}x plus rapide")
    print("=" * 50)
    return stats


# ─────────────────────────────────────────────
# Demo / test manuel
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # Test basique
    print("1er appel (MISS) :", get_product_cached("p001"))
    print("2e  appel (HIT)  :", get_product_cached("p001"))
    print("Stats :", get_cache_stats())

    # Mise à jour + invalidation
    print("\n--- Mise à jour du prix ---")
    update_product_and_invalidate("p001", {"price": 42000})
    print("Après invalidation (MISS + rechargement) :", get_product_cached("p001"))

    # Benchmark
    print("\n--- Benchmark (20 requêtes) ---")
    benchmark_cache("p002", nb_requests=20)
