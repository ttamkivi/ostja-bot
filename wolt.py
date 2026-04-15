import httpx
import logging
import json
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Wolt kasutab neid avalikke endpointe (reverse-engineered veebilehelt)
WOLT_SEARCH = "https://restaurant-api.wolt.com/v1/search"
WOLT_CONSUMER = "https://consumer-api.wolt.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
    "Referer": "https://wolt.com/",
    "Origin": "https://wolt.com",
}


class WoltAPI:
    def __init__(self, token: str, lat: float, lon: float):
        self.token = token
        self.lat = lat
        self.lon = lon
        self.headers = HEADERS.copy()
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    async def search(self, query: str) -> list[dict]:
        return await self.search_items(query)

    async def search_items(self, query: str) -> list[dict]:
        """Otsi Woltist toite/restorane Google otsingu kaudu kui Wolti API ei tööta."""

        # Meetod 1: Wolti ametlik veebileht JSON päring
        results = await self._search_via_web(query)
        if results:
            return results

        # Meetod 2: Wolti avaliku discovery API
        results = await self._search_via_discovery(query)
        if results:
            return results

        # Meetod 3: Fallback — manuaalne link
        return self._fallback_results(query)

    async def _search_via_web(self, query: str) -> list[dict]:
        """Proovi Wolti erinevaid search endpointe."""
        endpoints = [
            f"https://restaurant-api.wolt.com/v1/search?q={query}&lat={self.lat}&lon={self.lon}&limit=5",
            f"https://restaurant-api.wolt.com/v1/search?q={query}&lat={self.lat}&lon={self.lon}&language=et",
        ]
        for url in endpoints:
            try:
                async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                    resp = await client.get(url, headers=self.headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        if "sections" in data:
                            parsed = self._parse_search_data(data, query)
                            if parsed:
                                return parsed
            except Exception as e:
                logger.debug(f"Endpoint {url} ebaõnnestus: {e}")
        return []

    async def _search_via_discovery(self, query: str) -> list[dict]:
        """Proovi Wolti discovery/pages endpointe."""
        try:
            url = f"https://restaurant-api.wolt.com/v1/pages/delivery"
            params = {"lat": self.lat, "lon": self.lon}
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(url, headers=self.headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    # Otsi query-le vastavaid kohti
                    results = []
                    sections = data.get("sections", [])
                    for section in sections:
                        items = section.get("items", [])
                        for item in items:
                            venue = item.get("venue", {})
                            name = venue.get("name", {})
                            if isinstance(name, dict):
                                name_str = name.get("et") or name.get("en", "")
                            else:
                                name_str = str(name)
                            if query.lower() in name_str.lower():
                                results.append({
                                    "platform": "wolt",
                                    "item_name": name_str,
                                    "venue_name": name_str,
                                    "price": 0,
                                    "delivery_time": venue.get("estimate", 30),
                                    "venue_slug": venue.get("slug", ""),
                                    "item_id": "",
                                    "url": f"https://wolt.com/et/est/tallinn/restaurant/{venue.get('slug', '')}",
                                })
                    return results[:3]
        except Exception as e:
            logger.debug(f"Discovery API ebaõnnestus: {e}")
        return []

    def _parse_search_data(self, data: dict, query: str) -> list[dict]:
        results = []
        sections = data.get("sections", [])
        for section in sections:
            items = section.get("items", [])
            for item in items:
                # Proovi venue struktuuri
                venue = item.get("venue", {})
                item_data = item.get("item", {})

                if item_data:
                    name = item_data.get("name", {})
                    if isinstance(name, dict):
                        name_str = name.get("et") or name.get("en", "")
                    else:
                        name_str = str(name)
                    price = item_data.get("base_price", 0) / 100
                    results.append({
                        "platform": "wolt",
                        "item_name": name_str,
                        "venue_name": item_data.get("venue_name", ""),
                        "price": price,
                        "delivery_time": item_data.get("estimate", 30),
                        "venue_slug": item_data.get("venue_slug", ""),
                        "item_id": item_data.get("id", ""),
                        "url": f"https://wolt.com/et/est/tallinn/restaurant/{item_data.get('venue_slug', '')}",
                    })
                elif venue:
                    name = venue.get("name", {})
                    if isinstance(name, dict):
                        name_str = name.get("et") or name.get("en", "")
                    else:
                        name_str = str(name)
                    results.append({
                        "platform": "wolt",
                        "item_name": name_str,
                        "venue_name": name_str,
                        "price": venue.get("delivery_price_int", 0) / 100,
                        "delivery_time": venue.get("estimate", 30),
                        "venue_slug": venue.get("slug", ""),
                        "item_id": "",
                        "url": f"https://wolt.com/et/est/tallinn/restaurant/{venue.get('slug', '')}",
                    })

                if len(results) >= 3:
                    break
            if len(results) >= 3:
                break
        return results

    def _fallback_results(self, query: str) -> list[dict]:
        """Kui API ei tööta — tagasta Wolti otsingulink."""
        import urllib.parse
        encoded = urllib.parse.quote(query)
        return [{
            "platform": "wolt",
            "item_name": f"🔍 Otsi '{query}' Woltist",
            "venue_name": "Wolt",
            "price": 0,
            "delivery_time": "?",
            "venue_slug": "",
            "item_id": "",
            "url": f"https://wolt.com/et/est/tallinn?q={encoded}",
            "is_fallback": True,
        }]

    async def place_order(self, venue_slug: str, item_id: str, address: dict) -> dict:
        if not self.token:
            import urllib.parse
            url = f"https://wolt.com/et/est/tallinn/restaurant/{venue_slug}"
            return {
                "success": False,
                "message": (
                    "⚠️ Wolt token puudub — automaatne tellimus pole võimalik.\n\n"
                    f"📱 Telli käsitsi: {url}\n\n"
                    "Tokeni lisamiseks vt README → 'Wolt tokeni hankimine'"
                )
            }
        # Token olemas — proovi päris tellimust
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                cart_resp = await client.post(
                    "https://restaurant-api.wolt.com/v1/order_xp/cart",
                    headers=self.headers,
                    json={"venue_id": venue_slug, "items": [{"item_id": item_id, "count": 1}]}
                )
                if cart_resp.status_code not in (200, 201):
                    return {"success": False, "message": f"Ostukorvi viga: {cart_resp.status_code}"}
                cart_id = cart_resp.json().get("id")
                order_resp = await client.post(
                    "https://restaurant-api.wolt.com/v1/order_xp/order",
                    headers=self.headers,
                    json={"cart_id": cart_id, "delivery_address": address}
                )
                if order_resp.status_code in (200, 201):
                    order = order_resp.json()
                    return {"success": True, "order_id": order.get("id"), "message": f"✅ Tellimus esitatud! ID: {order.get('id')}"}
                return {"success": False, "message": f"Tellimuse viga: {order_resp.status_code}"}
        except Exception as e:
            return {"success": False, "message": f"Viga: {e}"}
