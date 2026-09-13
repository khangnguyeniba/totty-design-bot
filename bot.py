import os
import logging
import requests
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters, ConversationHandler
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "PASTE_TOKEN_HERE")
KIE_API_KEY = os.environ.get("KIE_API_KEY", "PASTE_KIE_KEY_HERE")

KIE_MODELS = {
    "gpt25": {
        "name": "GPT 2.5 Image",
        "model": "gpt-image-1",
        "desc": "Chất lượng cao nhất, tốt cho event frame"
    },
    "seedream": {
        "name": "Seedream 5 Pro",
        "model": "seedream-3-0",
        "desc": "Nhanh, phù hợp thiết kế sáng tạo"
    },
    "nano": {
        "name": "Nano Banana Pro",
        "model": "nano-banana-pro",
        "desc": "Draft nhanh, tiết kiệm quota"
    }
}

TOTTY_STYLE = """
Style: Professional Vietnamese children's nutrition brand.
Brand colors: Blue #0050b6, Teal #00bbb6, Orange #ff9d1b.
Clean, modern, premium, warm and friendly tone.
Square format 1:1. Vietnamese text where needed.
Brand name: TOTTY. Tagline: Nuôi con thật dễ.
"""

CHOOSE_MODEL, ENTER_PROMPT = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Xin chào! Đây là *Totty Design Bot*\n\n"
        "Tôi sẽ giúp anh tạo ảnh thiết kế cho nhãn hàng Totty.\n\n"
        "Gõ /design để bắt đầu tạo ảnh mới.",
        parse_mode="Markdown"
    )

async def design(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⭐ GPT 2.5 Image — Chất lượng cao", callback_data="model_gpt25")],
        [InlineKeyboardButton("🚀 Seedream 5 Pro — Nhanh & sáng tạo", callback_data="model_seedream")],
        [InlineKeyboardButton("⚡ Nano Banana Pro — Draft nhanh", callback_data="model_nano")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎨 *Chọn model tạo ảnh:*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return CHOOSE_MODEL

async def choose_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    model_key = query.data.replace("model_", "")
    context.user_data["model"] = model_key
    model_info = KIE_MODELS[model_key]
    await query.edit_message_text(
        f"✅ Đã chọn: *{model_info['name']}*\n\n"
        f"Bây giờ mô tả ảnh anh muốn tạo:\n\n"
        f"*Ví dụ:*\n"
        f"• `Khung ảnh sự kiện sinh nhật shop Boben Baby Thái Nguyên, có logo Totty`\n"
        f"• `Banner quảng cáo Totty Immu Jelly cho mùa tựu trường`\n"
        f"• `Ảnh product shot Sữa chua Hy Lạp sấy Totty trên nền trắng`",
        parse_mode="Markdown"
    )
    return ENTER_PROMPT

async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = update.message.text
    model_key = context.user_data.get("model", "gpt25")
    model_info = KIE_MODELS[model_key]

    msg = await update.message.reply_text(
        f"⏳ Đang tạo ảnh với *{model_info['name']}*...\nThường mất 15–30 giây.",
        parse_mode="Markdown"
    )

    full_prompt = f"{user_prompt}\n\n{TOTTY_STYLE}"

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
        data = response.json()

        if response.status_code == 200 and data.get("data"):
            image_url = data["data"][0].get("url") or data["data"][0].get("b64_json")
            if image_url and image_url.startswith("http"):
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=image_url,
                    caption=f"✅ *{model_info['name']}*\nPrompt: _{user_prompt}_\n\nGõ /design để tạo ảnh mới.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Không lấy được URL ảnh. Thử lại hoặc đổi model.")
        else:
            error_msg = data.get("error", {}).get("message", str(data))
            await update.message.reply_text(f"❌ Lỗi API: {error_msg}")

    except requests.Timeout:
        await update.message.reply_text("⏱ Timeout — server KIE đang bận. Thử lại sau 30 giây.")
    except Exception as e:
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
