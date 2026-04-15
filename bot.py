"""
Ostja Bot — isiklik ostuagent Telegramis
Taavi Tamkivi, 2026

Käivitamine:
    python bot.py

Nõuded:
    pip install python-telegram-bot httpx python-dotenv
"""

import asyncio
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from config import Config
from wolt import WoltAPI
from bolt import BoltFoodAPI
from orders import OrderManager

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

config = Config()
wolt = WoltAPI(config.WOLT_TOKEN, config.LAT, config.LON)
bolt = BoltFoodAPI(config.BOLT_TOKEN, config.LAT, config.LON)
orders = OrderManager()

# ─── Turvakontroll ────────────────────────────────────────────────────────────

def is_allowed(update: Update) -> bool:
    """Ainult lubatud kasutaja saab botti kasutada."""
    if config.ALLOWED_CHAT_ID == 0:
        return True  # Seadistamata — lubame kõik (arenda-faas)
    return update.effective_user.id == config.ALLOWED_CHAT_ID

# ─── Käsud ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update): return
    await update.message.reply_text(
        "👋 Tere! Olen *Ostja* — su isiklik ostuagent.\n\n"
        "Kirjuta mulle mida tahad, näiteks:\n"
        "• _telli mulle woltist burger alla 12€_\n"
        "• _otsi pitsat, wolt vs bolt_\n"
        "• _mis mul viimati tellitud?_\n"
        "• _palju ma sel kuul kulutasin?_\n\n"
        "Enne tellimist küsin alati kinnitust. ✅",
        parse_mode="Markdown"
    )

# ─── Asukoht ────────────────────────────────────────────────────────────

async def cmd_asukoht(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Küsib kasutajalt asukohta GPS või salvestatud aadressidest."""
    if not is_allowed(update): return

    addresses = orders.get_all_addresses()
    active = orders.get_active_address()

    # Näita salvestatud aadressid inline nuppudena
    keyboard = []
    for addr in addresses:
        label = addr["label"]
        marker = " ✅" if addr["is_active"] else ""
        keyboard.append([InlineKeyboardButton(f"{label}{marker}", callback_data=f"addr_select_{addr['id']}" )])

    keyboard.append([InlineKeyboardButton("📍 Saada praegune asukoht (GPS)", callback_data="addr_gps")])
    keyboard.append([InlineKeyboardButton("➕ Lisa käsitsi", callback_data="addr_manual")])
    if addresses:
        keyboard.append([InlineKeyboardButton("🗑 Kustuta aadress", callback_data="addr_delete_menu")])

    current = f"\n\n📍 *Praegu aktiivne:* {active['label']} ({active['address_text'] or f"{active['lat']:.4f}, {active['lon']:.4f}"})" if active else "\n\n⚠️ Aktiivne aadress puudub — kasutan Tallinn (Viru) vaikimisi."

    await update.message.reply_text(
        f"🏠 *Tarneaadress*{current}\n\nVali aadress või saada GPS:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kasutaja saatis GPS asukoha."""
    if not is_allowed(update): return
    loc = update.message.location
    lat, lon = loc.latitude, loc.longitude

    # Pöördgeokodeeri aadress
    address_text = await _reverse_geocode(lat, lon)
    label = address_text.split(",")[0] if address_text else f"{lat:.4f}, {lon:.4f}"

    # Salvesta ja aktiveeri
    addr_id = orders.save_address(label, lat, lon, address_text)
    orders.set_active_address(addr_id)

    # Uuenda boti sätetes koordinaadid
    config.LAT = lat
    config.LON = lon
    wolt.lat = lat
    wolt.lon = lon
    bolt.lat = lat
    bolt.lon = lon

    await update.message.reply_text(
        f"✅ *Asukoht salvestatud!*\n\n📍 {address_text or f'{lat:.4f}, {lon:.4f}'}\n\nKõik järgmised otsingud ja tarned kasutavad seda aadressi.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

async def _reverse_geocode(lat: float, lon: float) -> str:
    """Geokodeeri koordinaadid aadressiks (Nominatim / OpenStreetMap)."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": lat, "lon": lon, "format": "json", "accept-language": "et"},
                headers={"User-Agent": "OstjaBot/1.0"}
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("display_name", "")[:80]
    except Exception:
        pass
    return ""

async def handle_addr_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline nupu vajutused aadresside haldamiseks."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "addr_gps":
        # Palu kasutajal saata GPS — muuda nupp hallikas et vältida topelt vajutust
        await query.edit_message_reply_markup(reply_markup=None)
        gps_btn = KeyboardButton("📍 Saada minu asukoht", request_location=True)
        markup = ReplyKeyboardMarkup([[gps_btn]], one_time_keyboard=True, resize_keyboard=True)
        await query.message.reply_text(
            "📱 Vajuta alumist nuppu et saata GPS asukoht:",
            reply_markup=markup
        )

    elif data.startswith("addr_select_"):
        addr_id = int(data.split("_")[-1])
        addr = next((a for a in orders.get_all_addresses() if a["id"] == addr_id), None)
        if addr:
            orders.set_active_address(addr_id)
            config.LAT = addr["lat"]
            config.LON = addr["lon"]
            wolt.lat = addr["lat"]
            wolt.lon = addr["lon"]
            bolt.lat = addr["lat"]
            bolt.lon = addr["lon"]
            coord_str = addr['address_text'] or f"{addr['lat']:.4f}, {addr['lon']:.4f}"
            await query.edit_message_text(
                f"✅ *Aktiivne aadress:* {addr['label']}\n📍 {coord_str}",
                parse_mode="Markdown"
            )

    elif data == "addr_manual":
        context.user_data["awaiting_address"] = True
        await query.message.reply_text(
            "✏️ Kirjuta aadress tekstina (nt: *Kadaka tee 42, Tallinn*)",
            parse_mode="Markdown"
        )

    elif data == "addr_delete_menu":
        addresses = orders.get_all_addresses()
        keyboard = [[InlineKeyboardButton(f"🗑 {a['label']}", callback_data=f"addr_del_{a['id']}")] for a in addresses]
        keyboard.append([InlineKeyboardButton("← Tagasi", callback_data="addr_back")])
        await query.edit_message_text("Vali kustutatav aadress:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("addr_del_"):
        addr_id = int(data.split("_")[-1])
        orders.delete_address(addr_id)
        await query.edit_message_text("✅ Aadress kustutatud.")

    elif data == "addr_back":
        await cmd_asukoht_edit(query)

async def cmd_asukoht_edit(query):
    """Uuenda asukoha menüü (callback versioon)."""
    addresses = orders.get_all_addresses()
    active = orders.get_active_address()
    keyboard = []
    for addr in addresses:
        marker = " ✅" if addr["is_active"] else ""
        keyboard.append([InlineKeyboardButton(f"{addr['label']}{marker}", callback_data=f"addr_select_{addr['id']}" )])
    keyboard.append([InlineKeyboardButton("📍 GPS asukoht", callback_data="addr_gps")])
    keyboard.append([InlineKeyboardButton("➕ Lisa käsitsi", callback_data="addr_manual")])
    current = f"\n\n*Aktiivne:* {active['label']}" if active else ""
    await query.edit_message_text(
        f"🏠 *Tarneaadress*{current}\n\nVali:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_manual_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kasutaja sisestas käsitsi aadressi tekstina."""
    if not context.user_data.get("awaiting_address"):
        return False
    context.user_data["awaiting_address"] = False
    address_text = update.message.text.strip()

    # Geokodeeri tekst koordinaatideks
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": address_text, "format": "json", "limit": 1, "accept-language": "et"},
                headers={"User-Agent": "OstjaBot/1.0"}
            )
            results = resp.json()
            if results:
                lat = float(results[0]["lat"])
                lon = float(results[0]["lon"])
                display = results[0].get("display_name", address_text)[:80]
                label = address_text.split(",")[0]
                addr_id = orders.save_address(label, lat, lon, display)
                orders.set_active_address(addr_id)
                config.LAT = lat
                config.LON = lon
                wolt.lat = lat
                wolt.lon = lon
                bolt.lat = lat
                bolt.lon = lon
                await update.message.reply_text(
                    f"✅ *Aadress salvestatud!*\n📍 {display}",
                    parse_mode="Markdown"
                )
                return True
            else:
                await update.message.reply_text(
                    f"❌ Ei leidnud aadressi '{address_text}'. Proovi täpsemalt, nt: *Kadaka tee 42, Tallinn*",
                    parse_mode="Markdown"
                )
                return True
    except Exception as e:
        await update.message.reply_text(f"❌ Geokodeerimise viga: {e}")
        return True

async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update): return
    history = orders.get_history(10)
    if not history:
        await update.message.reply_text("📭 Tellimuste ajalugu on tühi.")
        return
    lines = ["📋 *Viimased tellimused:*\n"]
    for o in history:
        platform = "🟡 Wolt" if o["platform"] == "wolt" else "🟢 Bolt"
        date = o["created_at"][:10]
        lines.append(f"{platform} — {o['item_name']} @ {o['venue_name']} — *{o['price']:.2f}€* ({date})")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_spend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update): return
    spend = orders.get_monthly_spend()
    if not spend:
        await update.message.reply_text("📊 Sel kuul pole veel tellimusi.")
        return
    total = sum(v["total"] for v in spend.values())
    lines = ["💶 *Kulutused sel kuul:*\n"]
    for platform, data in spend.items():
        name = "Wolt" if platform == "wolt" else "Bolt Food"
        lines.append(f"{name}: {data['total']:.2f}€ ({data['count']} tellimust)")
    lines.append(f"\n*Kokku: {total:.2f}€*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update): return
    orders.clear_pending(update.effective_user.id)
    await update.message.reply_text("❌ Tühistatud. Ootel tellimus eemaldatud.")

# ─── Peamine sõnumi käsitleja ──────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update): return

    # Kontrolli kas ootame käsitsi aadressi
    if context.user_data.get("awaiting_address"):
        handled = await handle_manual_address(update, context)
        if handled:
            return

    text = update.message.text.strip().lower()
    user_id = update.effective_user.id

    # Kinnitus-vastused
    if text in ("jah", "yes", "y", "jep", "ok", "telli"):
        await handle_confirm(update, context)
        return
    if text in ("ei", "no", "n", "tühista", "cancel"):
        orders.clear_pending(user_id)
        await update.message.reply_text("❌ Tühistatud.")
        return

    # Numbriline valik (1, 2, 3)
    if re.match(r"^[123]$", text):
        await handle_number_choice(update, context, int(text))
        return

    # Asukoha käsitlus tekstina
    if any(w in text for w in ("asukoht", "asun", "kus ma", "muuda asukoht", "tarneaadress", "aadress")):
        await cmd_asukoht(update, context)
        return

    # Ajalugu ja kulud
    if any(w in text for w in ("viimati", "ajalugu", "history", "tellimused")):
        await cmd_history(update, context)
        return
    if any(w in text for w in ("kulutasin", "kulus", "kulud", "spend", "palju")):
        await cmd_spend(update, context)
        return

    # Võrdlus (wolt vs bolt)
    if any(p in text for p in ("vs", "versus", "või", "odavam", "võrdle", "wolt vs", "bolt vs")):
        await handle_compare(update, context, update.message.text)
        return

    # Bolt-spetsiifiline päring
    if "bolt" in text and "wolt" not in text:
        await handle_search(update, context, update.message.text, platform="bolt")
        return

    # Wolt-spetsiifiline päring
    if "wolt" in text:
        await handle_search(update, context, update.message.text, platform="wolt")
        return

    # Üldine otsing (proovib Woltist)
    await handle_search(update, context, update.message.text, platform="wolt")

# ─── Otsing ───────────────────────────────────────────────────────────────────

def extract_query(text: str) -> str:
    """Võtab kasutajasisendist otsitava märksõna välja."""
    # Eemalda tavalised ostufraaside algused
    patterns = [
        r"telli mulle\s+(woltist|boltist|wolt|bolt|wolt food|bolt food)?\s*",
        r"otsi\s+(woltist|boltist|wolt|bolt)?\s*",
        r"tahan\s+(woltist|boltist|wolt|bolt)?\s*",
        r"anna mulle\s+",
        r"(woltist|boltist|wolt food|bolt food|wolt|bolt)\s+",
    ]
    result = text
    for p in patterns:
        result = re.sub(p, "", result, flags=re.IGNORECASE).strip()
    return result if result else text

def extract_max_price(text: str) -> float | None:
    """Otsib hinnalimiiti tekstist (nt 'alla 12€' → 12.0)."""
    m = re.search(r"alla\s*(\d+(?:[.,]\d+)?)\s*€?", text, re.IGNORECASE)
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.search(r"max\s*(\d+(?:[.,]\d+)?)\s*€?", text, re.IGNORECASE)
    if m:
        return float(m.group(1).replace(",", "."))
    return None

async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, platform: str = "wolt"):
    query = extract_query(text)
    max_price = extract_max_price(text)

    await update.message.reply_text(f"🔍 Otsin {'Woltist' if platform == 'wolt' else 'Bolt Food-ist'}: _{query}_...", parse_mode="Markdown")

    if platform == "wolt":
        results = await wolt.search_items(query)
        if not results:
            results = await wolt.search(query)
    else:
        results = await bolt.search(query)

    if not results:
        import urllib.parse
        encoded = urllib.parse.quote(query)
        p = "Wolt" if platform == "wolt" else "Bolt Food"
        url = f"https://wolt.com/et/est/tallinn?q={encoded}" if platform == "wolt" else f"https://food.bolt.eu/et-ee/tallinn?q={encoded}"
        await update.message.reply_text(
            f"😕 Ei leidnud '{query}' kohta automaatselt tulemusi.\n\n"
            f"📱 Otsi käsitsi {p}-ist:\n{url}",
            parse_mode="Markdown"
        )
        return

    # Filtreeri hinna järgi
    if max_price:
        filtered = [r for r in results if r.get("price", 999) <= max_price]
        results = filtered if filtered else results  # kui kõik on kallimad, näita ikkagi

    # Kuva tulemused
    lines = [f"{'🟡 Wolt' if platform == 'wolt' else '🟢 Bolt Food'} — *{query}* ({len(results)} tulemust):\n"]
    for i, r in enumerate(results, 1):
        item_name = r.get("item_name") or r.get("name", "")
        venue = r.get("venue_name") or r.get("name", "")
        price = r.get("price", 0)
        delivery = r.get("delivery_time", "?")
        lines.append(f"{i}️⃣ *{item_name}* @ {venue}\n   💶 {price:.2f}€ · 🕐 ~{delivery} min")

    lines.append("\nVasta *1*, *2* või *3* tellimiseks, või *ei* tühistamiseks.")

    # Salvesta tulemused ootele
    orders.set_pending(update.effective_user.id, {
        "platform": platform,
        "query": query,
        "results": results,
        "selected": None,
    })

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── Võrdlus ──────────────────────────────────────────────────────────────────

async def handle_compare(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    query = extract_query(text)
    query = re.sub(r"\s*(vs|versus|või|wolt|bolt|odavam|võrdle)\s*", " ", query, flags=re.IGNORECASE).strip()

    await update.message.reply_text(f"🔍 Võrdlen Wolt vs Bolt Food: _{query}_...", parse_mode="Markdown")

    wolt_results, bolt_results = await asyncio.gather(
        wolt.search_items(query),
        bolt.search(query)
    )

    lines = [f"⚖️ *Võrdlus: {query}*\n"]

    if wolt_results:
        best_w = wolt_results[0]
        lines.append(f"🟡 *Wolt:* {best_w.get('item_name') or best_w.get('name', '')} @ {best_w.get('venue_name', '')}")
        lines.append(f"   💶 {best_w.get('price', 0):.2f}€ · 🕐 ~{best_w.get('delivery_time', '?')} min")
    else:
        lines.append("🟡 *Wolt:* tulemusi ei leitud")

    lines.append("")

    if bolt_results:
        best_b = bolt_results[0]
        lines.append(f"🟢 *Bolt Food:* {best_b.get('item_name') or best_b.get('name', '')}")
        lines.append(f"   💶 {best_b.get('price', 0):.2f}€ · 🕐 ~{best_b.get('delivery_time', '?')} min")
    else:
        lines.append("🟢 *Bolt Food:* tulemusi ei leitud")

    # Soovitus
    if wolt_results and bolt_results:
        wp = wolt_results[0].get("price", 999)
        bp = bolt_results[0].get("price", 999)
        if wp < bp:
            lines.append(f"\n💡 *Wolt on odavam* ({bp - wp:.2f}€ vahe). Tellen Woltist? (jah/ei)")
            orders.set_pending(update.effective_user.id, {
                "platform": "wolt", "query": query,
                "results": wolt_results, "selected": 0
            })
        else:
            lines.append(f"\n💡 *Bolt on odavam* ({wp - bp:.2f}€ vahe). Tellen Boltist? (jah/ei)")
            orders.set_pending(update.effective_user.id, {
                "platform": "bolt", "query": query,
                "results": bolt_results, "selected": 0
            })
    elif wolt_results:
        lines.append("\nTellen Woltist? (jah/ei)")
        orders.set_pending(update.effective_user.id, {
            "platform": "wolt", "query": query,
            "results": wolt_results, "selected": 0
        })

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── Numbriline valik ─────────────────────────────────────────────────────────

async def handle_number_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, number: int):
    user_id = update.effective_user.id
    pending = orders.get_pending(user_id)

    if not pending:
        await update.message.reply_text("❓ Pole aktiivseid otsinguid. Kirjuta mida soovid tellida.")
        return

    results = pending.get("results", [])
    idx = number - 1

    if idx >= len(results):
        await update.message.reply_text(f"❓ Valik {number} pole saadaval. Vali 1–{len(results)}.")
        return

    selected = results[idx]
    pending["selected"] = idx
    orders.set_pending(user_id, pending)

    platform = "Wolt" if pending["platform"] == "wolt" else "Bolt Food"
    item_name = selected.get("item_name") or selected.get("name", "")
    venue = selected.get("venue_name") or selected.get("name", "")
    price = selected.get("price", 0)
    delivery = selected.get("delivery_time", "?")

    await update.message.reply_text(
        f"{'🟡' if pending['platform'] == 'wolt' else '🟢'} *{platform}* — kinnita tellimus:\n\n"
        f"🍽 {item_name} @ {venue}\n"
        f"💶 {price:.2f}€ · 🕐 ~{delivery} min\n\n"
        "Tarne sinu tavaaadressile.\n\n"
        "Tellen? Vasta *jah* või *ei*",
        parse_mode="Markdown"
    )

# ─── Kinnitus ja tellimuse esitamine ──────────────────────────────────────────

async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pending = orders.get_pending(user_id)

    if not pending:
        await update.message.reply_text("❓ Pole ootel tellimust. Kirjuta mida soovid.")
        return

    results = pending.get("results", [])
    selected_idx = pending.get("selected")

    # Kui valik pole tehtud — vali automaatselt esimene
    if selected_idx is None:
        if len(results) > 1:
            await update.message.reply_text(
                "❓ Vali esmalt number (1, 2 või 3) — mitu varianti on saadaval."
            )
            return
        selected_idx = 0
        pending["selected"] = 0

    if selected_idx >= len(results):
        await update.message.reply_text("❓ Viga valikus. Alusta uuesti.")
        orders.clear_pending(user_id)
        return

    selected = results[selected_idx]
    platform = pending["platform"]

    await update.message.reply_text("⏳ Esitan tellimust...")

    # Esita tellimus
    if platform == "wolt":
        result = await wolt.place_order(
            venue_slug=selected.get("venue_slug", ""),
            item_id=selected.get("item_id", ""),
            address={"lat": config.LAT, "lon": config.LON}
        )
    else:
        result = await bolt.place_order(
            restaurant_id=selected.get("id", ""),
            item_ids=[selected.get("item_id", "")],
            address={"lat": config.LAT, "lng": config.LON}
        )

    if result["success"]:
        # Salvesta tellimus
        orders.save_order(
            platform=platform,
            venue_name=selected.get("venue_name") or selected.get("name", ""),
            item_name=selected.get("item_name") or selected.get("name", ""),
            price=selected.get("price", 0),
            order_id=result.get("order_id", ""),
            raw=selected
        )
        orders.clear_pending(user_id)
        await update.message.reply_text(result["message"])
    else:
        # Tellimus ebaõnnestus — näita linki manuaalseks tellimiseks
        url = selected.get("url", "")
        orders.clear_pending(user_id)
        await update.message.reply_text(
            f"{result['message']}\n\n"
            f"📱 Telli käsitsi: {url}" if url else result["message"]
        )

# ─── Käivitus ─────────────────────────────────────────────────────────────────

def main():
    if not config.TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN puudub .env failist!")
        print("   Lisa see ja käivita uuesti.")
        return

    print("🤖 Ostja bot käivitub...")
    print(f"   Asukoht: {config.LAT}, {config.LON} ({config.CITY})")
    print(f"   Wolt token: {'✅ olemas' if config.WOLT_TOKEN else '⚠️ puudub (ainult otsing töötab)'}")
    print(f"   Bolt token: {'✅ olemas' if config.BOLT_TOKEN else '⚠️ puudub (ainult otsing töötab)'}")

    app = Application.builder().token(config.TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ajalugu", cmd_history))
    app.add_handler(CommandHandler("kulud", cmd_spend))
    app.add_handler(CommandHandler("tyhista", cmd_cancel))
    app.add_handler(CommandHandler("asukoht", cmd_asukoht))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(CallbackQueryHandler(handle_addr_callback, pattern="^addr_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Bot töötab! Saada Telegramis /start")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
