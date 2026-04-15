import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "orders.db"

class OrderManager:
    def __init__(self):
        self._init_db()
        self._pending: dict = {}  # chat_id -> pending order

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    venue_name TEXT,
                    item_name TEXT,
                    price REAL,
                    order_id TEXT,
                    status TEXT DEFAULT 'ordered',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    raw JSON
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS addresses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lon REAL NOT NULL,
                    address_text TEXT,
                    is_active INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def set_pending(self, chat_id: int, order: dict):
        """Salvesta ootel tellimus (ootab kinnitust)."""
        order["created_at"] = datetime.now().isoformat()
        self._pending[chat_id] = order

    def get_pending(self, chat_id: int) -> dict | None:
        """Saab ootel tellimuse."""
        return self._pending.get(chat_id)

    def clear_pending(self, chat_id: int):
        """Kustuta ootel tellimus."""
        self._pending.pop(chat_id, None)

    def save_order(self, platform: str, venue_name: str, item_name: str,
                   price: float, order_id: str, raw: dict = None):
        """Salvesta edukalt esitatud tellimus."""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO orders (platform, venue_name, item_name, price, order_id, raw) VALUES (?,?,?,?,?,?)",
                (platform, venue_name, item_name, price, order_id, json.dumps(raw or {}))
            )
            conn.commit()

    def get_history(self, limit: int = 5) -> list[dict]:
        """Saab viimased tellimused."""
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT platform, venue_name, item_name, price, status, created_at FROM orders ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [
            {
                "platform": r[0], "venue_name": r[1], "item_name": r[2],
                "price": r[3], "status": r[4], "created_at": r[5]
            }
            for r in rows
        ]

    # ─── Aadressid ────────────────────────────────────────────────────────────

    def save_address(self, label: str, lat: float, lon: float, address_text: str = "") -> int:
        """Salvesta uus aadress. Tagastab id."""
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "INSERT INTO addresses (label, lat, lon, address_text) VALUES (?,?,?,?)",
                (label, lat, lon, address_text)
            )
            conn.commit()
            return cur.lastrowid

    def set_active_address(self, address_id: int):
        """Seab aktiivse tarneaadressi."""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE addresses SET is_active = 0")
            conn.execute("UPDATE addresses SET is_active = 1 WHERE id = ?", (address_id,))
            conn.commit()

    def get_active_address(self) -> dict | None:
        """Saab aktiivse tarneaadressi."""
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT id, label, lat, lon, address_text FROM addresses WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row:
            return {"id": row[0], "label": row[1], "lat": row[2], "lon": row[3], "address_text": row[4]}
        return None

    def get_all_addresses(self) -> list[dict]:
        """Kõik salvestatud aadressid."""
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT id, label, lat, lon, address_text, is_active FROM addresses ORDER BY id DESC"
            ).fetchall()
        return [
            {"id": r[0], "label": r[1], "lat": r[2], "lon": r[3], "address_text": r[4], "is_active": bool(r[5])}
            for r in rows
        ]

    def delete_address(self, address_id: int):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM addresses WHERE id = ?", (address_id,))
            conn.commit()

    def get_monthly_spend(self) -> dict:
        """Kulutused sel kuul, jagatud platvormi kaupa."""
        month = datetime.now().strftime("%Y-%m")
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT platform, SUM(price), COUNT(*) FROM orders WHERE created_at LIKE ? AND status='ordered' GROUP BY platform",
                (f"{month}%",)
            ).fetchall()
        result = {}
        for r in rows:
            result[r[0]] = {"total": round(r[1], 2), "count": r[2]}
        return result
