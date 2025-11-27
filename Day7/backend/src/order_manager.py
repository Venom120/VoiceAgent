import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
CATALOG_PATH = BASE_DIR / "data" / "catalog.json"
DB_PATH = BASE_DIR / "data" / "sqlite.db"
ORDERS_DIR = BASE_DIR / "orders"


def _ensure_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            customer_name TEXT,
            customer_address TEXT,
            total REAL,
            status TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            item_id TEXT,
            item_name TEXT,
            unit_price REAL,
            quantity INTEGER,
            FOREIGN KEY(order_id) REFERENCES orders(id)
        )
        """
    )
    # Pending carts table to persist in-progress carts (session_key -> cart JSON)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_carts (
            session_key TEXT PRIMARY KEY,
            cart_json TEXT,
            updated TEXT
        )
        """
    )
    conn.commit()
    conn.close()


class Catalog:
    def __init__(self, catalog_path: Optional[Path] = None):
        self.path = Path(catalog_path) if catalog_path else CATALOG_PATH
        self._load()

    def _load(self):
        with open(self.path, "r") as f:
            self.items = json.load(f)
        self.by_id = {it["id"]: it for it in self.items}

    def find_by_name(self, name: str) -> Optional[Dict]:
        def _normalize(s: str) -> str:
            return "".join(ch for ch in s.lower().strip() if ch.isalnum() or ch.isspace())

        name_norm = _normalize(name)
        # exact id
        if name in self.by_id:
            return self.by_id[name]
        # try normalized id match
        for _id, it in self.by_id.items():
            if _normalize(_id) == name_norm:
                return it

        # exact name (normalized)
        for it in self.items:
            if _normalize(it["name"]) == name_norm:
                return it

        # contains match (normalized) - covers 'tomato' in 'tomato (1)'
        for it in self.items:
            if name_norm in _normalize(it["name"]):
                return it

        # tag match
        for it in self.items:
            if any(name_norm == _normalize(t) for t in it.get("tags", [])):
                return it

        # try simple plural/singular variations: strip trailing 's'
        if name_norm.endswith("s"):
            singular = name_norm[:-1]
            for it in self.items:
                if singular == _normalize(it["name"]) or singular in _normalize(it["name"]):
                    return it

        return None

    def get(self, item_id: str) -> Optional[Dict]:
        return self.by_id.get(item_id)

    def list_items(self) -> List[Dict]:
        return self.items

    def get_details(self, name_or_id: str) -> Optional[Dict]:
        """Return a normalized details dict for an item by id or name.

        This includes optional fields like brand, size, weight, unit and description
        if they are present in the catalog entry.
        """
        it = self.find_by_name(name_or_id)
        if not it:
            return None
        return {
            "id": it.get("id"),
            "name": it.get("name"),
            "price": float(it.get("price", 0)),
            "brand": it.get("brand"),
            "size": it.get("size"),
            "weight": it.get("weight"),
            # catalog historically used "units" key; prefer that then "unit"
            "unit": it.get("unit") or it.get("units"),
            "description": it.get("description"),
            "tags": it.get("tags", []),
        }

    def categories(self) -> List[str]:
        """Return a sorted list of unique categories present in the catalog."""
        cats = {it.get("category", "").strip() for it in self.items if it.get("category")}
        return sorted([c for c in cats if c])

    def items_by_category(self, category: str) -> List[Dict]:
        """Return a list of items (normalized) that belong to the given category.

        Comparison is case-insensitive. Each item contains id,name,price,brand,size,unit,tags.
        """
        if not category:
            return []
        cat_l = category.lower().strip()
        out = []
        for it in self.items:
            if it.get("category", "").lower().strip() == cat_l:
                out.append({
                    "id": it.get("id"),
                    "name": it.get("name"),
                    "price": float(it.get("price", 0)),
                    "brand": it.get("brand"),
                    "size": it.get("size"),
                    "unit": it.get("unit") or it.get("units"),
                    "tags": it.get("tags", []),
                })
        return out

    # Simple alias mapping to help match user-friendly category names to catalog categories
    CATEGORY_ALIASES = {
        "fruits": "Produce",
        "fruit": "Produce",
        "produce": "Produce",
        "dairy": "Groceries",
        "dairy & eggs": "Groceries",
        "dairy and eggs": "Groceries",
        "meat & seafood": "Meat",
        "meat and seafood": "Meat",
        "pantry": "Groceries",
        "beverages": "Groceries",
        "snacks": "Snacks",
        "frozen": "Frozen",
        "household": "Household",
        "personal care": "Personal Care",
    }

    def resolve_category(self, user_input: str) -> Optional[str]:
        """Try to resolve a user-provided category/alias to a canonical catalog category.

        Returns the canonical category name if found, otherwise None.
        """
        if not user_input:
            return None
        u = user_input.lower().strip()
        # direct exact match (case-insensitive)
        for c in self.categories():
            if c.lower() == u:
                return c
        # alias map
        if u in self.CATEGORY_ALIASES:
            candidate = self.CATEGORY_ALIASES[u]
            # ensure alias maps to an existing catalog category
            if candidate in self.categories():
                return candidate
        # substring match against categories
        for c in self.categories():
            if u in c.lower() or c.lower() in u:
                return c
        return None


class Cart:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.items: Dict[str, int] = {}  # item_id -> qty

    def add(self, name_or_id: str, qty: int = 1) -> Tuple[bool, str]:
        it = self.catalog.find_by_name(name_or_id)
        if not it:
            return False, f"Item '{name_or_id}' not found in catalog"
        item_id = it["id"]
        self.items[item_id] = self.items.get(item_id, 0) + max(1, int(qty))
        return True, f"Added {qty} x {it['name']}"

    def remove(self, name_or_id: str) -> Tuple[bool, str]:
        it = self.catalog.find_by_name(name_or_id)
        if not it:
            return False, f"Item '{name_or_id}' not found"
        item_id = it["id"]
        if item_id in self.items:
            del self.items[item_id]
            return True, f"Removed {it['name']} from cart"
        return False, f"{it['name']} not in cart"

    def update(self, name_or_id: str, qty: int) -> Tuple[bool, str]:
        it = self.catalog.find_by_name(name_or_id)
        if not it:
            return False, f"Item '{name_or_id}' not found"
        item_id = it["id"]
        if qty <= 0:
            return self.remove(item_id)
        self.items[item_id] = int(qty)
        return True, f"Updated {it['name']} to {qty}"

    def list(self) -> List[Dict]:
        out = []
        for item_id, qty in self.items.items():
            it = self.catalog.get(item_id)
            if not it:
                continue
            out.append({
                "id": item_id,
                "name": it["name"],
                "unit_price": float(it["price"]),
                "quantity": qty,
                "line_total": round(float(it["price"]) * qty, 2),
            })
        return out

    def total(self) -> float:
        return round(sum(it["line_total"] for it in self.list()), 2)


class OrderManager:
    def __init__(self, db_path: Optional[Path] = None):
        _ensure_db()

    def list_orders(self, limit: int = 50) -> List[Dict]:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute("SELECT id, timestamp, customer_name, customer_address, total, status FROM orders ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        conn.close()
        out = []
        for r in rows:
            out.append({
                "order_id": r[0],
                "timestamp": r[1],
                "customer_name": r[2],
                "customer_address": r[3],
                "total": r[4],
                "status": r[5],
            })
        return out

    def get_order(self, order_id: int) -> Optional[Dict]:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute("SELECT id, timestamp, customer_name, customer_address, total, status FROM orders WHERE id = ?", (order_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return None
        cur.execute("SELECT item_id, item_name, unit_price, quantity FROM order_items WHERE order_id = ?", (order_id,))
        items = [
            {"id": r[0], "name": r[1], "unit_price": r[2], "quantity": r[3], "line_total": round(r[2] * r[3], 2)}
            for r in cur.fetchall()
        ]
        conn.close()
        return {
            "order_id": row[0],
            "timestamp": row[1],
            "customer_name": row[2],
            "customer_address": row[3],
            "total": row[4],
            "status": row[5],
            "items": items,
        }

    def _write_order_json(self, order_id: int) -> Optional[str]:
        order = self.get_order(order_id)
        if not order:
            return None
        ORDERS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = ORDERS_DIR / f"order_{order_id}.json"
        with open(out_path, "w") as f:
            json.dump(order, f, indent=2)
        return str(out_path)

    def set_status(self, order_id: int, status: str) -> bool:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        changed = cur.rowcount
        conn.commit()
        conn.close()
        if changed:
            self._write_order_json(order_id)
            return True
        return False

    ORDER_STATUSES = ["received", "confirmed", "being_prepared", "out_for_delivery", "delivered"]

    def advance_status(self, order_id: int) -> Optional[str]:
        ord = self.get_order(order_id)
        if not ord:
            return None
        try:
            idx = self.ORDER_STATUSES.index(ord["status"])
        except ValueError:
            # unknown status, set to first
            new = self.ORDER_STATUSES[0]
            self.set_status(order_id, new)
            return new
        if idx + 1 < len(self.ORDER_STATUSES):
            new = self.ORDER_STATUSES[idx + 1]
            self.set_status(order_id, new)
            return new
        # already final
        return ord["status"]

    def place_order(self, cart: Cart, customer_name: str = "", customer_address: str = "") -> Dict:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        timestamp = datetime.utcnow().isoformat() + "Z"
        total = cart.total()
        status = "received"
        cur.execute(
            "INSERT INTO orders (timestamp, customer_name, customer_address, total, status) VALUES (?,?,?,?,?)",
            (timestamp, customer_name, customer_address, total, status),
        )
        order_id = cur.lastrowid
        for item in cart.list():
            cur.execute(
                "INSERT INTO order_items (order_id, item_id, item_name, unit_price, quantity) VALUES (?,?,?,?,?)",
                (order_id, item["id"], item["name"], item["unit_price"], item["quantity"]),
            )
        conn.commit()
        conn.close()

        # Save order JSON as well for easy inspection
        ORDERS_DIR.mkdir(parents=True, exist_ok=True)
        order_obj = {
            "order_id": order_id,
            "timestamp": timestamp,
            "customer_name": customer_name,
            "customer_address": customer_address,
            "status": status,
            "total": total,
            "items": cart.list(),
        }
        out_path = ORDERS_DIR / f"order_{order_id}.json"
        with open(out_path, "w") as f:
            json.dump(order_obj, f, indent=2)

        return {"order_id": order_id, "path": str(out_path), "order": order_obj}


# Simple recipe mappings for "ingredients for X"
RECIPES = {
    "peanut butter sandwich": [
        ("bread_whole_wheat", 2),
        ("peanut_butter", 1)
    ],
    "pasta for two": [
        ("pasta_spaghetti", 1),
        ("marinara_sauce", 1)
    ],
    "grilled cheese": [
        ("bread_whole_wheat", 2),
        ("cheddar_sliced", 2),
        ("butter_unsalted", 1)
    ]
}

def ingredients_for(dish: str, servings: int = 1) -> List[Tuple[str, int]]:
    key = dish.lower().strip()
    if key in RECIPES:
        return [(item_id, max(1, qty * servings)) for item_id, qty in RECIPES[key]]
    # fallback: try to match tags in catalog
    cat = Catalog()
    parts = []
    for it in cat.list_items():
        if key in " ".join(it.get("tags", [])).lower():
            parts.append((it["id"], 1 * servings))
    return parts


def save_pending_cart(session_key: str, cart_list: List[Dict]):
    """Persist the current cart snapshot for a session_key as JSON."""
    _ensure_db()
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    payload = json.dumps(cart_list)
    updated = datetime.utcnow().isoformat() + "Z"
    cur.execute(
        "INSERT INTO pending_carts (session_key, cart_json, updated) VALUES (?,?,?)"
        "ON CONFLICT(session_key) DO UPDATE SET cart_json=excluded.cart_json, updated=excluded.updated",
        (session_key, payload, updated),
    )
    conn.commit()
    conn.close()


def load_pending_cart(session_key: str) -> Optional[List[Dict]]:
    _ensure_db()
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT cart_json FROM pending_carts WHERE session_key = ?", (session_key,))
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def delete_pending_cart(session_key: str):
    _ensure_db()
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("DELETE FROM pending_carts WHERE session_key = ?", (session_key,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    print("Order manager module. Use through import or the demo agent.")
