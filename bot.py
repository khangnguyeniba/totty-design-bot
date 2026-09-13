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
    "gpt25": {
        "name": "GPT 2.5 Image",
        "model": "gpt-image-2-text-to-image",
        "desc": "Chất lượng cao nhất"
    },
    "seedream": {
        "name": "Seedream 5 Pro",
        "model": "seedream-3-0-text-to-image",
        "desc": "Nhanh, sáng tạo"
    },
    "nano": {
        "name": "Nano Banana Pro",
        "model": "nano-banana-2",
        "desc": "Draft nhanh"
    }
}

TOTTY_STYLE = (
    "Professional Vietnamese children's nutrition brand design. "
    "Brand colors: Blue #0050b6, Teal #00bbb6, Orange #ff9d1b. "
    "Clean, modern, premium, warm and friendly. "
    "Square format 1:1. Brand name: TOTTY. Tagline: Nuoi con that de."
)

CHOOSE_MODEL, ENTER_PROMPT = range(2)


def kie_headers():
    return {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json"
    }


def create_task(model_str, prompt):
    payload = {
        "model": model_str,
        "input": {
            "prompt": prompt,
            "nsfw_checker": False
        }
    }
    resp = requests.post(
        f"{KIE_BASE}/jobs/createTask",
        headers=kie_headers(),
        json=payload,
        timeout=30
    )
    logger.info(f"createTask status: {resp.status_code}, body: {resp.text[:300]}")
    data = resp.json()
    if data.get("code") == 200:
        return data["data"]["taskId"]
    raise Exception(f"createTask failed: {data.get('msg')} | {resp.text[:200]}")


def poll_task(task_id, max_wait=300):
    for _ in range(max_wait // 3):
        time.sleep(3)
        resp = requests.get(
            f"{KIE_BASE}/jobs/recordInfo",
            headers=kie_headers(),
            params={"taskId": task_id},
            timeout=30
        )
        data = resp.json()
        logger.info(f"poll state: {data.get('data', {}).get('state')} | taskId: {task_id}")
        if data.get("code") != 200:
            raise Exception(f"Poll error: {data.get('msg')}")
        record = data["data"]
        state = record.get("state")
        if state == "success":
            result_json = json.loads(record.get("resultJson", "{}"))
            urls = result_json.get("resultUrls", [])
            if urls:
                return urls[0]
            raise Exception("No resultUrls in response")
        elif state == "fail":
            raise Exception(f"Task failed: {record.get('failMsg', 'unknown')}")
    raise Exception("Timeout — ảnh mất quá 5 phút")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Xin chào! Đây là *Totty Design Bot*\n\nGõ /design để tạo ảnh mới.",
        parse_mode="Markdown"
    )


async def design(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⭐ GPT 2.5 Image — Chất lượng cao", callback_data="model_gpt25")],
        [InlineKeyboardButton("🚀 Seedream 5 Pro — Nhanh & sáng tạo", callback_data="model_seedream")],
        [InlineKeyboardButton("⚡ Nano Banana — Draft nhanh", callback_data="model_nano")],
    ]
    await update.message.reply_text(
        "🎨 *Chọn model tạo ảnh:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CHOOSE_MODEL


async def choose_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    model_key = query.data.replace("model_", "")
    context.user_data["model"] = model_key
    model_name = KIE_MODELS[model_key]["name"]
    await query.edit_message_text(
        f"✅ Đã chọn: *{model_name}*\n\n"
        f"Mô tả ảnh anh muốn tạo:\n\n"
        f"*Ví dụ:* `Khung ảnh sự kiện sinh nhật Boben Baby Thái Nguyên, logo Totty, tone xanh`",
        parse_mode="Markdown"
    )
    return ENTER_PROMPT


async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = update.message.text
    model_key = context.user_data.get("model", "gpt25")
    model_info = KIE_MODELS[model_key]

    msg = await update.message.reply_text(
        f"⏳ Đang tạo ảnh với *{model_info['name']}*...\nThường mất 30–90 giây.",
        parse_mode="Markdown"
    )

    full_prompt = f"{user_prompt}. {TOTTY_STYLE}"

    try:
        task_id = create_task(model_info["model"], full_prompt)
        logger.info(f"Task created: {task_id}")

        await msg.edit_text(
            f"⏳ Task đã tạo, đang chờ KIE render...\n`{task_id[:16]}...`",
            parse_mode="Markdown"
        )

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
    await update.message.reply_text("❌ Đã hủy. Gõ /design để bắt đầu lại.")
    return ConversationHandler.END


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("design", design)],
        states={
            CHOOSE_MODEL: [CallbackQueryHandler(choose_model, pattern="^model_")],
            ENTER_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_image)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    logger.info("Bot started...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
