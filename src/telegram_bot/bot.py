"""Telegram bot main entry — registers handlers and starts long-polling.

Run: python -m src.telegram_bot
"""
import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from src.telegram_bot.config import load_config
from src.telegram_bot.worker import Worker

logger = logging.getLogger(__name__)


WELCOME = (
    "Bot ready. Send a Douyin/YouTube/TikTok link and I will dub it to Vietnamese, "
    "upload to YouTube + Facebook (PUBLIC), and report progress here.\n\n"
    "Commands:\n"
    "  /status — show queue + current job\n"
    "  /cancel — cancel current job (after current step finishes)\n"
    "  /help   — this message"
)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ctx.bot_data["whitelist_user_id"]:
        logger.warning(f"Rejected /start from non-whitelist user_id={update.effective_user.id}")
        return
    await update.message.reply_text(WELCOME)


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ctx.bot_data["whitelist_user_id"]:
        return
    worker: Worker = ctx.bot_data["worker"]
    await update.message.reply_text(worker.status_summary())


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ctx.bot_data["whitelist_user_id"]:
        return
    worker: Worker = ctx.bot_data["worker"]
    await update.message.reply_text(worker.cancel_current())


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ctx.bot_data["whitelist_user_id"]:
        logger.warning(f"Rejected message from non-whitelist user_id={user_id}")
        return
    text = (update.message.text or "").strip()
    if not _looks_like_url(text):
        await update.message.reply_text("Send a video URL (Douyin/YouTube/TikTok).")
        return
    worker: Worker = ctx.bot_data["worker"]
    await worker.enqueue(
        url=text,
        chat_id=update.effective_chat.id,
        message=update.message,
    )


def _looks_like_url(text: str) -> bool:
    return text.startswith(("http://", "https://"))


async def _on_startup(app: Application):
    """Spawn the worker task after the Application is running."""
    worker: Worker = app.bot_data["worker"]
    asyncio.create_task(worker.run())
    logger.info("Worker task spawned")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config()

    app = (
        Application.builder()
        .token(cfg.bot_token)
        .post_init(_on_startup)
        .build()
    )
    worker = Worker(bot=app.bot, claude_cwd=cfg.repo_root, work_dir_base=cfg.work_dir_base)
    app.bot_data["whitelist_user_id"] = cfg.whitelist_user_id
    app.bot_data["worker"] = worker

    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    logger.info(f"Bot starting, whitelist user_id={cfg.whitelist_user_id}")
    app.run_polling()
