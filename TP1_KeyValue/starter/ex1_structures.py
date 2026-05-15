"""
Ex1 — Structures de données Redis (4 pts)
ShopFast — Gestion des produits, paniers, historique, catégories
"""

import redis
import json

r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)


# ─────────────────────────────────────────────
# 1. Stockage produit avec Hash
# ─────────────────────────────────────────────

def store_product(product_id: str, product_data: dict) -> bool:
    """
    Stocke un produit dans un Hash Redis.
    Clé : product:{product_id}
    """
    key = f"product:{product_id}"
    r.hset(key, mapping=product_data)
    r.expire(key, 3600)  # TTL 1 heure
    return True


def get_product(product_id: str) -> dict:
    """Récupère un produit depuis Redis."""
    key = f"product:{product_id}"
    data = r.hgetall(key)
    return data if data else {}


def update_product_price(product_id: str, new_price: float) -> bool:
    """Met à jour uniquement le prix d'un produit."""
    key = f"product:{product_id}"
    if not r.exists(key):
        return False
    r.hset(key, "price", str(new_price))
    return True


# ─────────────────────────────────────────────
# 2. Gestion du panier (Hash)
# ─────────────────────────────────────────────

def add_to_cart(user_id: str, product_id: str, quantity: int) -> int:
    """
    Ajoute ou met à jour un article dans le panier.
    Clé : cart:{user_id}  |  field : product_id  |  value : quantity
    """
    key = f"cart:{user_id}"
    current = int(r.hget(key, product_id) or 0)
    new_qty = current + quantity
    r.hset(key, product_id, new_qty)
    r.expire(key, 86400)  # TTL 24h
    return new_qty


def remove_from_cart(user_id: str, product_id: str) -> bool:
    """Retire un article du panier."""
    key = f"cart:{user_id}"
    return bool(r.hdel(key, product_id))


def get_cart(user_id: str) -> dict:
    """Retourne le contenu complet du panier."""
    key = f"cart:{user_id}"
    return r.hgetall(key)


def clear_cart(user_id: str) -> bool:
    """Vide le panier."""
    return bool(r.delete(f"cart:{user_id}"))


# ─────────────────────────────────────────────
# 3. Historique de navigation (List)
# ─────────────────────────────────────────────

HISTORY_MAX = 10  # garder les 10 derniers produits visités


def add_to_history(user_id: str, product_id: str) -> None:
    """
    Ajoute un produit à l'historique de navigation.
    LPUSH + LTRIM pour conserver uniquement les N derniers.
    """
    key = f"history:{user_id}"
    r.lpush(key, product_id)
    r.ltrim(key, 0, HISTORY_MAX - 1)
    r.expire(key, 604800)  # TTL 7 jours


def get_history(user_id: str, limit: int = HISTORY_MAX) -> list:
    """Retourne l'historique de navigation (du plus récent au plus ancien)."""
    key = f"history:{user_id}"
    return r.lrange(key, 0, limit - 1)


# ─────────────────────────────────────────────
# 4. Produits par catégorie (Set)
# ─────────────────────────────────────────────

def add_product_to_category(category: str, product_id: str) -> int:
    """Ajoute un produit dans la catégorie."""
    key = f"category:{category}"
    return r.sadd(key, product_id)


def get_products_by_category(category: str) -> set:
    """Retourne tous les produits d'une catégorie."""
    key = f"category:{category}"
    return r.smembers(key)


def get_products_in_multiple_categories(categories: list) -> set:
    """
    Retourne les produits présents dans TOUTES les catégories (intersection).
    Utile pour les filtres multi-critères.
    """
    keys = [f"category:{c}" for c in categories]
    if not keys:
        return set()
    return r.sinter(*keys)


def remove_product_from_category(category: str, product_id: str) -> int:
    """Retire un produit d'une catégorie."""
    key = f"category:{category}"
    return r.srem(key, product_id)


# ─────────────────────────────────────────────
# Demo / test manuel
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # Produit
    store_product("p001", {
        "name": "Smartphone Samsung A54",
        "price": "45000",
        "stock": "150",
        "category": "electronics"
    })
    print("Produit:", get_product("p001"))

    update_product_price("p001", 43000)
    print("Nouveau prix:", r.hget("product:p001", "price"))

    # Panier
    add_to_cart("u001", "p001", 2)
    add_to_cart("u001", "p002", 1)
    print("Panier u001:", get_cart("u001"))
    remove_from_cart("u001", "p002")
    print("Panier après suppression:", get_cart("u001"))

    # Historique
    for pid in ["p003", "p002", "p001", "p004"]:
        add_to_history("u001", pid)
    print("Historique:", get_history("u001"))

    # Catégories
    for pid in ["p001", "p002", "p003"]:
        add_product_to_category("electronics", pid)
    add_product_to_category("promo", "p001")
    add_product_to_category("promo", "p002")

    print("Electronics:", get_products_by_category("electronics"))
    print("Electronics ∩ Promo:", get_products_in_multiple_categories(["electronics", "promo"]))
