import logging
import os
import httpx

log = logging.getLogger("operator.notify")

async def send_telegram(text: str):                            # /operator/notify.send_telegram
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        log.warning("Telegram notification skipped: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not configured")
        return

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
        r.raise_for_status()

