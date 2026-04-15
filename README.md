# 🛒 Ostja Bot

Sinu isiklik Telegrami ostuagent. Kirjuta mida tahad, bot otsib parima variandi Woltist või Bolt Food-ist ja esitab tellimuse sinu kinnituse järel.

---

## Kiirstart (10 minutit)

### 1. Ava Terminal, mine projekti kausta

```bash
cd ~/dev/ostja-bot
```

### 2. Paigalda sõltuvused

```bash
pip install -r requirements.txt
```

### 3. Loo seadistusfail

```bash
cp .env.example .env
```

Ava `.env` tekstiredaktoris ja täida:

```
TELEGRAM_TOKEN=...     ← hangi @BotFather käest (vt allpool)
ALLOWED_CHAT_ID=...    ← hangi @userinfobot käest
```

### 4. Käivita bot

```bash
python bot.py
```

Bot töötab nüüd. Ava Telegram, otsi oma botti (see nimi, mille BotFather-is andsid) ja kirjuta `/start`.

---

## Telegram tokeni hankimine (@BotFather)

1. Ava Telegram → otsi `@BotFather`
2. Kirjuta `/newbot`
3. Anna botile nimi (nt `OstjaBot`)
4. Anna kasutajanimi (nt `taavi_ostja_bot`) — peab lõppema `bot`-iga
5. BotFather saadab sulle tokeni kujul `123456:ABCdef...`
6. Kopeeri see `.env` faili `TELEGRAM_TOKEN=` järele

## Sinu Telegrami ID hankimine

1. Ava Telegram → otsi `@userinfobot`
2. Kirjuta `/start`
3. Bot vastab sinu ID-ga (number, nt `123456789`)
4. Kopeeri `.env` faili `ALLOWED_CHAT_ID=` järele

---

## Kasutamine

### Toidutellimus

```
telli mulle woltist burger alla 12€
```
Bot vastab 3 variandiga. Vasta `1`, `2` või `3` valimiseks, siis `jah` tellimiseks.

### Hinnav võrdlus

```
mis on odavam, wolt või bolt, pizza margherita?
```
Bot võrdleb mõlemat ja soovitab odavamat.

### Bolt Food spetsiifiliselt

```
telli boltist sushi
```

### Ajalugu ja kulud

```
mis mul viimati tellitud?
palju ma sel kuul kulutasin?
```

### Tühistamine

```
ei
```
või käsk `/tyhista`

---

## Wolt tokeni hankimine (automaatne tellimine)

Ilma tokenita töötab otsing ja võrdlus, aga bot ei saa automaatselt tellida — ta näitab linki manuaalseks tellimiseks.

Tokeni hankimiseks:

1. Ava Terminal ja käivita:
```bash
python get_wolt_token.py
```
2. Sisesta oma telefoninumber (nt +37256789000)
3. Sisesta SMS-kood
4. Token kuvatakse ekraanil
5. Kopeeri `.env` faili `WOLT_TOKEN=` järele

**NB:** Wolt sessioon aegub mõne nädala pärast. Kui bot ütleb "token on aegunud", korda ülaltoodud sammu.

---

## Bolt tokeni hankimine

Sarnane protsess. Käivita:
```bash
python get_bolt_token.py
```
Järgi juhiseid.

---

## Piirangud (mida bot praegu EI tee)

- ❌ Selver — tuleb v2-s (brauseri automatiseerimine)
- ❌ Amazon — tuleb v2-s
- ❌ Apple Pay otsene kasutamine — bot kasutab su Wolt/Bolt kontol olevat kaarti
- ⚠️ Wolt/Bolt mitteametlik API — sessioon aegub, tuleb aeg-ajalt uuendada
- ⚠️ Wolt/Bolt ToS — isiklik kasutus, kasutad omal riisikol

---

## Probleemid

**Bot ei vasta:**
- Kontrolli, et `python bot.py` töötab terminalis
- Kontrolli, et `TELEGRAM_TOKEN` on õige

**"Token puudub" viga:**
- Otsing töötab, aga tellimus mitte — hangi token (vt ülal)

**Wolt ei leia tulemusi:**
- Proovi inglise keeles: `burger`, `pizza`, `sushi`
- Kontrolli, et `LAT`/`LON` on õige (Tallinn: 59.4370, 24.7536)

---

## Failid

```
ostja-bot/
├── bot.py          ← Peamine fail, käivita see
├── wolt.py         ← Wolti integratsioon
├── bolt.py         ← Bolt Food integratsioon
├── orders.py       ← Tellimuste salvestamine
├── config.py       ← Seadistuste laadimine
├── .env            ← Sinu isiklikud andmed (EI lähe GitHubi)
├── .env.example    ← Mall .env loomiseks
├── requirements.txt
└── orders.db       ← Loodud automaatselt, SQLite andmebaas
```
