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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
        await update.message.reply_text(
            f"😕 Ei leidnud tulemusi '{query}' kohta.\n"
            "Proovi täpsema nimetusega, nt: _'burger'_, _'pizza margherita'_, _'sushi'_",
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Bot töötab! Saada Telegramis /start")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
