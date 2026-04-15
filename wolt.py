import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

WOLT_BASE = "https://restaurant-api.wolt.com"
WOLT_AUTH = "https://authentication.wolt.com"

class WoltAPI:
    def __init__(self, token: str, lat: float, lon: float):
        self.token = token
        self.lat = lat
        self.lon = lon
        self.headers = {
            "User-Agent": "Wolt/3.0 (iPhone; iOS 16.0)",
            "Accept": "application/json",
            "Accept-Language": "et",
            "w-wolt-session-id": "demo-session",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    async def search(self, query: str) -> list[dict]:
        """Otsi Woltist restorane ja toite."""
        url = f"{WOLT_BASE}/v1/search"
        params = {
            "q": query,
            "lat": self.lat,
            "lon": self.lon,
            "limit": 10,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=self.headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                return self._parse_search(data, query)
        except Exception as e:
            logger.error(f"Wolti otsing ebaõnnestus: {e}")
            return []

    def _parse_search(self, data: dict, query: str) -> list[dict]:
        results = []
        sections = data.get("sections", [])
        for section in sections:
            items = section.get("items", [])
            for item in items:
                venue = item.get("venue", {})
                if not venue:
                    continue
                results.append({
                    "platform": "wolt",
                    "name": venue.get("name", {}).get("et") or venue.get("name", {}).get("en", ""),
                    "slug": venue.get("slug", ""),
                    "rating": venue.get("rating", {}).get("score", 0),
                    "delivery_time": venue.get("estimate", 30),
                    "delivery_price": venue.get("delivery_price_int", 0) / 100,
                    "description": venue.get("short_description", {}).get("et") or venue.get("short_description", {}).get("en", ""),
                    "url": f"https://wolt.com/et/est/{self._city_slug(venue)}/restaurant/{venue.get('slug', '')}",
                })
                if len(results) >= 5:
                    break
            if len(results) >= 5:
                break
        return results[:3]

    def _city_slug(self, venue: dict) -> str:
        city = venue.get("city", "tallinn").lower()
        return city if city else "tallinn"

    async def search_items(self, query: str) -> list[dict]:
        """Otsi konkreetseid toite (mitte restorane)."""
        url = f"{WOLT_BASE}/v1/search"
        params = {
            "q": query,
            "lat": self.lat,
            "lon": self.lon,
            "limit": 20,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=self.headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                return self._parse_items(data)
        except Exception as e:
            logger.error(f"Wolti toiduotsing ebaõnnestus: {e}")
            return []

    def _parse_items(self, data: dict) -> list[dict]:
        results = []
        sections = data.get("sections", [])
        for section in sections:
            items = section.get("items", [])
            for item in items:
                item_data = item.get("item", {})
                if not item_data:
                    continue
                price = item_data.get("base_price", 0) / 100
                if price <= 0:
                    continue
                results.append({
                    "platform": "wolt",
                    "item_name": item_data.get("name", {}).get("et") or item_data.get("name", {}).get("en", ""),
                    "venue_name": item_data.get("venue_name", ""),
                    "price": price,
                    "delivery_time": item_data.get("estimate", 30),
                    "item_id": item_data.get("id", ""),
                    "venue_slug": item_data.get("venue_slug", ""),
                    "url": f"https://wolt.com/et/est/tallinn/restaurant/{item_data.get('venue_slug', '')}",
                    "image": item_data.get("image", {}).get("url", ""),
                })
                if len(results) >= 5:
                    break
            if len(results) >= 5:
                break
        return results[:3]

    async def get_delivery_address(self) -> Optional[str]:
        """Saab kasutaja salvestatud tarne-aadressi (vajab tokenit)."""
        if not self.token:
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{WOLT_BASE}/v1/users/me/addresses",
                    headers=self.headers
                )
                if resp.status_code == 200:
                    addrs = resp.json()
                    if addrs:
                        return addrs[0].get("formatted_address", "")
        except Exception as e:
            logger.error(f"Aadressi päring ebaõnnestus: {e}")
        return None

    async def place_order(self, venue_slug: str, item_id: str, address: dict) -> dict:
        """
        Esita tellimus Woltis.
        NB: See nõuab kehtivat WOLT_TOKEN-it .env failis.
        Tagastab {'success': bool, 'order_id': str, 'message': str}
        """
        if not self.token:
            return {
                "success": False,
                "message": "❌ Wolt token puudub. Lisa WOLT_TOKEN .env faili.\nVt README.md jaotist 'Wolt tokeni hankimine'."
            }

        # Loo ostukorv
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # Loo cart
                cart_resp = await client.post(
                    f"{WOLT_BASE}/v1/order_xp/cart",
                    headers=self.headers,
                    json={
                        "venue_id": venue_slug,
                        "items": [{"item_id": item_id, "count": 1}],
                    }
                )
                if cart_resp.status_code not in (200, 201):
                    return {"success": False, "message": f"Ostukorvi loomine ebaõnnestus: {cart_resp.status_code}"}

                cart_id = cart_resp.json().get("id")

                # Esita tellimus
                order_resp = await client.post(
                    f"{WOLT_BASE}/v1/order_xp/order",
                    headers=self.headers,
                    json={
                        "cart_id": cart_id,
                        "delivery_address": address,
                    }
                )
                if order_resp.status_code in (200, 201):
                    order = order_resp.json()
                    return {
                        "success": True,
                        "order_id": order.get("id", "N/A"),
                        "message": f"✅ Tellimus esitatud! ID: {order.get('id', 'N/A')}"
                    }
                else:
                    return {"success": False, "message": f"Tellimuse esitamine ebaõnnestus: {order_resp.status_code}\n{order_resp.text[:200]}"}

        except Exception as e:
            logger.error(f"Wolti tellimus ebaõnnestus: {e}")
            return {"success": False, "message": f"Viga: {str(e)}"}
