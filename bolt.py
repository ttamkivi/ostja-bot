import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

BOLT_BASE = "https://food-api.bolt.eu"

class BoltFoodAPI:
    def __init__(self, token: str, lat: float, lon: float):
        self.token = token
        self.lat = lat
        self.lon = lon
        self.headers = {
            "User-Agent": "Bolt Food/1.0 (iPhone; iOS 16.0)",
            "Accept": "application/json",
            "Accept-Language": "et",
            "X-Bolt-Market": "EE",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    async def search(self, query: str) -> list[dict]:
        """Otsi Bolt Food-ist restorane ja toite."""
        url = f"{BOLT_BASE}/v1/restaurants/search"
        params = {
            "q": query,
            "lat": self.lat,
            "lng": self.lon,
            "limit": 10,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=self.headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    return self._parse_search(data)
                else:
                    # Proovime alternatiivset endpoint-i
                    return await self._search_v2(query)
        except Exception as e:
            logger.error(f"Bolt Food otsing ebaõnnestus: {e}")
            return await self._search_v2(query)

    async def _search_v2(self, query: str) -> list[dict]:
        """Alternatiivne Bolt Food otsinguendpoint."""
        url = f"{BOLT_BASE}/v2/restaurants"
        params = {
            "lat": self.lat,
            "lng": self.lon,
            "search": query,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=self.headers, params=params)
                if resp.status_code == 200:
                    return self._parse_search(resp.json())
        except Exception as e:
            logger.error(f"Bolt Food v2 otsing ebaõnnestus: {e}")
        return []

    def _parse_search(self, data: dict) -> list[dict]:
        results = []

        # Proovime erinevaid struktuurivõimalusi
        items = (
            data.get("data", {}).get("restaurants", [])
            or data.get("restaurants", [])
            or data.get("results", [])
            or []
        )

        for item in items:
            name = item.get("name", "") or item.get("title", "")
            if not name:
                continue

            delivery = item.get("delivery", {}) or {}
            results.append({
                "platform": "bolt",
                "name": name,
                "id": str(item.get("id", "")),
                "rating": item.get("rating", 0),
                "delivery_time": delivery.get("eta_seconds", 1800) // 60,
                "delivery_price": delivery.get("fee", {}).get("cents", 0) / 100,
                "description": item.get("description", ""),
                "url": f"https://food.bolt.eu/et/restaurant/{item.get('id', '')}",
            })
            if len(results) >= 5:
                break

        return results[:3]

    async def place_order(self, restaurant_id: str, item_ids: list[str], address: dict) -> dict:
        """
        Esita tellimus Bolt Food kaudu.
        Vajab kehtivat BOLT_TOKEN-it .env failis.
        """
        if not self.token:
            return {
                "success": False,
                "message": "❌ Bolt token puudub. Lisa BOLT_TOKEN .env faili.\nVt README.md jaotist 'Bolt tokeni hankimine'."
            }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # Loo ostukorv
                cart_resp = await client.post(
                    f"{BOLT_BASE}/v1/cart",
                    headers=self.headers,
                    json={
                        "restaurant_id": restaurant_id,
                        "items": [{"id": iid, "quantity": 1} for iid in item_ids],
                        "delivery_address": address,
                    }
                )

                if cart_resp.status_code not in (200, 201):
                    return {"success": False, "message": f"Ostukorvi loomine ebaõnnestus: {cart_resp.status_code}"}

                cart_data = cart_resp.json()
                order_id = cart_data.get("data", {}).get("order_id") or cart_data.get("order_id")

                if order_id:
                    # Kinnita tellimus
                    confirm_resp = await client.post(
                        f"{BOLT_BASE}/v1/order/{order_id}/confirm",
                        headers=self.headers,
                        json={}
                    )
                    if confirm_resp.status_code in (200, 201):
                        return {
                            "success": True,
                            "order_id": order_id,
                            "message": f"✅ Bolt tellimus esitatud! ID: {order_id}"
                        }

                return {"success": False, "message": "Tellimuse kinnitamine ebaõnnestus"}

        except Exception as e:
            logger.error(f"Bolt tellimus ebaõnnestus: {e}")
            return {"success": False, "message": f"Viga: {str(e)}"}
