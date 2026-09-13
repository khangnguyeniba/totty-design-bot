import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters, ConversationHandler
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
KIE_API_KEY = os.environ.get("KIE_API_KEY", "")

KIE_MODELS = {
    "gpt25": {
        "name": "GPT 2.5 Image",
        "model": "gpt-image-1",
        "desc": "Chất lượng cao nhất"
    },
    "seedream": {
        "name": "Seedream 5 Pro",
        "model": "seedream-3-0",
        "desc": "Nhanh, sáng tạo"
    },
    "nano": {
        "name": "Nano Banana Pro",
        "model": "nano-banana-pro",
        "desc": "Draft nhanh"
    }
}

TOTTY_STYLE = (
    "Style: Professional Vietnamese children's nutrition brand. "
    "Brand colors: Blue #0050b6, Teal #00bbb6, Orange #ff9d1b. "
    "Clean, modern, premium, warm and friendly. "
    "Square format 1:1. Brand name: TOTTY."
)

CHOOSE_MODEL, ENTER_PROMPT = range(2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Xin chào! Đây là *Totty Design Bot*\n\nGõ /design để tạo ảnh mới.",
        parse_mode="Markdown"
    )


async def design(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⭐ GPT 2.5 Image", callback_data="model_gpt25")],
        [InlineKeyboardButton("🚀 Seedream 5 Pro", callback_data="model_seedream")],
        [InlineKeyboardButton("⚡ Nano Banana Pro", callback_data="model_nano")],
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
        f"*Ví dụ:* `Khung ảnh sự kiện sinh nhật Boben Baby, logo Totty, tone xanh`",
        parse_mode="Markdown"
    )
    return ENTER_PROMPT


async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = update.message.text
    model_key = context.user_data.get("model", "gpt25")
    model_info = KIE_MODELS[model_key]

    msg = await update.message.reply_text(
        f"⏳ Đang tạo ảnh với *{model_info['name']}*...",
        parse_mode="Markdown"
    )

    full_prompt = f"{user_prompt}. {TOTTY_STYLE}"

    try:
        headers = {
            "Authorization": f"Bearer {KIE_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model_info["model"],
            "prompt": full_prompt,
            "n": 1,
            "size": "1024x1024"
        }

        response = requests.post(
            "https://api.kie.ai/v1/images/generations",
            headers=headers,
            json=payload,
            timeout=60
        )

        logger.info(f"KIE status: {response.status_code}")
        logger.info(f"KIE response: {response.text[:500]}")

        if response.status_code != 200:
            await update.message.reply_text(
                f"❌ Lỗi {response.status_code}: {response.text[:200]}"
            )
            await msg.delete()
            return ConversationHandler.END

        data = response.json()

        # Xử lý nhiều dạng response khác nhau của KIE
        image_url = None

        if isinstance(data, dict):
            # Dạng: {"data": [{"url": "..."}]}
            if "data" in data and isinstance(data["data"], list):
                first = data["data"][0]
                if isinstance(first, dict):
                    image_url = first.get("url") or first.get("b64_json")
                elif isinstance(first, str):
                    image_url = first

            # Dạng: {"url": "..."}
            elif "url" in data:
                image_url = data["url"]

            # Dạng: {"images": ["url1"]}
            elif "images" in data and isinstance(data["images"], list):
                image_url = data["images"][0]

            # Dạng: {"result": "url"}
            elif "result" in data:
                image_url = data["result"]

        elif isinstance(data, list):
            first = data[0]
            if isinstance(first, dict):
                image_url = first.get("url")
            elif isinstance(first, str):
                image_url = first

        if image_url:
            if image_url.startswith("http"):
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=image_url,
                    caption=f"✅ *{model_info['name']}*\n_{user_prompt}_\n\nGõ /design để tạo tiếp.",
                    parse_mode="Markdown"
                )
            else:
                # base64
                import base64
                img_bytes = base64.b64decode(image_url)
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=img_bytes,
                    caption=f"✅ *{model_info['name']}*\n_{user_prompt}_",
                    parse_mode="Markdown"
                )
        else:
            await update.message.reply_text(
                f"❌ Không parse được ảnh.\nResponse: {str(data)[:300]}"
            )

    except requests.Timeout:
        await update.message.reply_text("⏱ Timeout — thử lại sau 30 giây.")
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
