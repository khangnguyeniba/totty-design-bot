import os
import logging
import requests
import time
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters, ConversationHandler
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
KIE_API_KEY = os.environ.get("KIE_API_KEY", "")
KIE_BASE = "https://api.kie.ai/api/v1"

KIE_MODELS = {
    "gpt25": {"name": "GPT 2.5 Image", "model": "gpt-image-2-text-to-image"},
    "seedream": {"name": "Seedream 5 Pro", "model": "seedream-3-0-text-to-image"},
    "nano": {"name": "Nano Banana", "model": "nano-banana-2"},
}

TOTTY_STYLE = (
    "Professional Vietnamese children's nutrition brand. "
    "Brand colors: Blue #0050b6, Teal #00bbb6, Orange #ff9d1b. "
    "Clean, modern, premium, warm. Square 1:1. Brand: TOTTY."
)

CHOOSE_MODEL, ENTER_PROMPT = range(2)


def kie_headers():
    return {"Authorization": f"Bearer {KIE_API_KEY}", "Content-Type": "application/json"}


def create_task(model_str, prompt):
    payload = {"model": model_str, "input": {"prompt": prompt, "nsfw_checker": False}}
    r = requests.post(f"{KIE_BASE}/jobs/createTask", headers=kie_headers(), json=payload, timeout=30)
    logger.info(f"createTask {r.status_code}: {r.text[:300]}")
    d = r.json()
    if d.get("code") == 200:
        return d["data"]["taskId"]
    raise Exception(f"createTask failed: {d.get('msg')} | {r.text[:200]}")


def poll_task(task_id, max_wait=300):
    for _ in range(max_wait // 3):
        time.sleep(3)
        r = requests.get(f"{KIE_BASE}/jobs/recordInfo", headers=kie_headers(), params={"taskId": task_id}, timeout=30)
        d = r.json()
        state = d.get("data", {}).get("state", "")
        logger.info(f"poll {task_id[:8]}: {state}")
        if d.get("code") != 200:
            raise Exception(f"Poll error: {d.get('msg')}")
        if state == "success":
            result = json.loads(d["data"].get("resultJson", "{}"))
            urls = result.get("resultUrls", [])
            if urls:
                return urls[0]
            raise Exception("No resultUrls")
        elif state == "fail":
            raise Exception(f"Task failed: {d['data'].get('failMsg', 'unknown')}")
    raise Exception("Timeout sau 5 phút")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 *Totty Design Bot*\n\nGõ /design để tạo ảnh.", parse_mode="Markdown")


async def design(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⭐ GPT 2.5 Image", callback_data="model_gpt25")],
        [InlineKeyboardButton("🚀 Seedream 5 Pro", callback_data="model_seedream")],
        [InlineKeyboardButton("⚡ Nano Banana", callback_data="model_nano")],
    ]
    await update.message.reply_text("🎨 *Chọn model:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return CHOOSE_MODEL


async def choose_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    model_key = query.data.replace("model_", "")
    context.user_data["model"] = model_key
    await query.edit_message_text(
        f"✅ *{KIE_MODELS[model_key]['name']}*\n\nMô tả ảnh muốn tạo:",
        parse_mode="Markdown"
    )
    return ENTER_PROMPT


async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = update.message.text
    model_key = context.user_data.get("model", "gpt25")
    model_info = KIE_MODELS[model_key]
    msg = await update.message.reply_text(f"⏳ Đang tạo ảnh với *{model_info['name']}*...", parse_mode="Markdown")
    try:
        task_id = create_task(model_info["model"], f"{user_prompt}. {TOTTY_STYLE}")
        await msg.edit_text(f"⏳ Đang render... `{task_id[:12]}...`", parse_mode="Markdown")
        image_url = poll_task(task_id)
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=image_url,
            caption=f"✅ *{model_info['name']}*\n_{user_prompt}_\n\nGõ /design để tạo tiếp.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Lỗi: {str(e)}")
    await msg.delete()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Đã hủy. Gõ /design để bắt đầu lại.")
    return ConversationHandler.END


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("design", design)],
        states={
            CHOOSE_MODEL: [CallbackQueryHandler(choose_model, pattern="^model_")],
            ENTER_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_image)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    logger.info("Bot started...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
