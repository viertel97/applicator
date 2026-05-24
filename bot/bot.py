import asyncio
import logging
import os

import httpx
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])
BOT_API_KEY = os.environ["BOT_API_KEY"]
API_URL = os.environ.get("API_URL", "http://api:8000")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_user.id != ALLOWED_USER_ID:
        return
    if update.message is None or not update.message.text:
        return

    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    if not text.startswith("http"):
        await update.message.reply_text("Send a job posting URL")
        return

    try:
        resp = httpx.post(
            f"{API_URL}/api/bot/applications",
            json={"url": text, "chat_id": chat_id},
            headers={"Authorization": f"Bearer {BOT_API_KEY}"},
            timeout=15.0,
        )
        if resp.status_code == 200:
            await update.message.reply_text(f"Queued: {text}")
        elif resp.status_code == 409:
            await update.message.reply_text(f"Already queued: {text}")
        else:
            await update.message.reply_text(f"Error {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        logger.exception("Failed to submit URL")
        await update.message.reply_text(f"Failed to reach API: {exc}")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot starting, draining backlog...")
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
