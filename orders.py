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
