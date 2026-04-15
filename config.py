import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
    ALLOWED_CHAT_ID = int(os.getenv("ALLOWED_CHAT_ID", "0"))  # Ainult sinu chat ID

    # Asukoht (Tallinn vaikimisi — muuda .env-is)
    LAT = float(os.getenv("LAT", "59.4370"))
    LON = float(os.getenv("LON", "24.7536"))
    CITY = os.getenv("CITY", "tallinn")

    # Wolt
    WOLT_TOKEN = os.getenv("WOLT_TOKEN", "")  # Valikuline — ainult tellimiseks

    # Bolt Food
    BOLT_TOKEN = os.getenv("BOLT_TOKEN", "")  # Valikuline — ainult tellimiseks
    BOLT_REFRESH_TOKEN = os.getenv("BOLT_REFRESH_TOKEN", "")

    # Seaded
    MAX_RESULTS = 3  # Mitu tulemust näidata
    CONFIRM_TIMEOUT = 300  # Sekundid — kui ei vasta 5 minutiga, tühistatakse
