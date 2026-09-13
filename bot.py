import os, logging, requests, time, json, io
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
UPLOAD_URL = "https://kieai.redpandaai.co/api/file-stream-upload"

MODELS = {
    "gpt_t2i":  {"name": "GPT 2.5 Flare", "model": "gpt-image-2-5-flare-text-to-image",   "i2i": False},
    "gpt_i2i":  {"name": "GPT 2.5 Flare", "model": "gpt-image-2-5-flare-image-to-image",   "i2i": True},
    "seed_i2i": {"name": "Seedream 5 Pro", "model": "seedream-5-0-pro-image-to-image",      "i2i": True},
    "nano_i2i": {"name": "Nano Banana Pro","model": "nano-banana-pro-image-to-image",        "i2i": True},
    "nano_t2i": {"name": "Nano Banana Pro","model": "nano-banana-pro",                      "i2i": False},
}

TOTTY_STYLE = (
    "Professional Vietnamese children's nutrition brand. "
    "Blue #0050b6, Teal #00bbb6, Orange #ff9d1b. "
    "Clean modern premium. Brand: TOTTY."
)

CHOOSE_TYPE, CHOOSE_MODEL, GET_IMAGE, GET_PROMPT = range(4)

def kie_headers():
    return {"Authorization": f"Bearer {KIE_API_KEY}", "Content-Type": "application/json"}

def upload_image(image_bytes, filename="photo.jpg"):
    r = requests.post(
        UPLOAD_URL,
        headers={"Authorization": f"Bearer {KIE_API_KEY}"},
        files={"file": (filename, image_bytes, "image/jpeg")},
        data={"uploadPath": "totty/uploads"},
        timeout=60
    )
    logger.info(f"upload: {r.status_code} {r.text[:200]}")
    d = r.json()
    if d.get("code") == 200:
        return d["data"].get("downloadUrl") or d["data"].get("fileUrl")
    raise Exception(f"Upload failed: {d.get('msg')}")

def create_task(model_str, prompt, input_urls=None):
    inp = {"prompt": prompt, "nsfw_checker": False, "aspect_ratio": "1:1"}
    if input_urls:
        inp["input_urls"] = input_urls
    payload = {"model": model_str, "input": inp}
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
            if urls: return urls[0]
            raise Exception("No resultUrls")
        elif state == "fail":
            raise Exception(f"Task failed: {d['data'].get('failMsg', 'unknown')}")
    raise Exception("Timeout sau 5 phút")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 *Totty Design Bot*\n\nGõ /design để tạo ảnh.", parse_mode="Markdown")

async def design(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("✏️ Text to Image — tạo ảnh từ mô tả", callback_data="type_t2i")],
        [InlineKeyboardButton("🖼 Image to Image — chỉnh sửa ảnh có sẵn", callback_data="type_i2i")],
    ]
    await update.message.reply_text(
        "🎨 *Anh muốn tạo ảnh theo cách nào?*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CHOOSE_TYPE

async def choose_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mode = query.data.replace("type_", "")
    context.user_data["mode"] = mode

    if mode == "t2i":
        keyboard = [
            [InlineKeyboardButton("⭐ GPT 2.5 Flare — chất lượng cao nhất", callback_data="model_gpt_t2i")],
            [InlineKeyboardButton("⚡ Nano Banana Pro — nhanh", callback_data="model_nano_t2i")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("⭐ GPT 2.5 Flare — giữ layout, chỉnh chi tiết", callback_data="model_gpt_i2i")],
            [InlineKeyboardButton("🎨 Seedream 5 Pro — sáng tạo mạnh hơn", callback_data="model_seed_i2i")],
            [InlineKeyboardButton("⚡ Nano Banana Pro — nhanh", callback_data="model_nano_i2i")],
        ]
    await query.edit_message_text(
        "🤖 *Chọn model:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CHOOSE_MODEL

async def choose_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    model_key = query.data.replace("model_", "")
    context.user_data["model_key"] = model_key
    mode = context.user_data["mode"]
    model_name = MODELS[model_key]["name"]

    if mode == "i2i":
        await query.edit_message_text(
            f"✅ *{model_name}* — Image to Image\n\n📸 Gửi ảnh gốc muốn chỉnh sửa:",
            parse_mode="Markdown"
        )
        return GET_IMAGE
    else:
        await query.edit_message_text(
            f"✅ *{model_name}* — Text to Image\n\nMô tả ảnh muốn tạo:\n\n"
            f"*Ví dụ:* `Khung ảnh sinh nhật Boben Baby, tone xanh Totty, có logo`",
            parse_mode="Markdown"
        )
        return GET_PROMPT

async def get_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("⚠️ Vui lòng gửi ảnh (không phải file).")
        return GET_IMAGE
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()
    msg = await update.message.reply_text("⏳ Đang upload ảnh lên KIE...")
    try:
        url = upload_image(bytes(image_bytes))
        context.user_data["input_url"] = url
        await msg.edit_text(
            "✅ Ảnh đã upload!\n\nBây giờ mô tả chỉnh sửa muốn thực hiện:\n\n"
            "*Ví dụ:* `Thêm khung xanh Totty, logo TOTTY góc phải, tiêu đề sinh nhật Boben Baby`",
            parse_mode="Markdown"
        )
        return GET_PROMPT
    except Exception as e:
        await msg.edit_text(f"❌ Upload thất bại: {str(e)}")
        return ConversationHandler.END

async def get_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = update.message.text
    model_key = context.user_data.get("model_key", "gpt_t2i")
    model_info = MODELS[model_key]
    input_url = context.user_data.get("input_url")

    msg = await update.message.reply_text(
        f"⏳ Đang tạo ảnh với *{model_info['name']}*...\nThường mất 30–90 giây.",
        parse_mode="Markdown"
    )
    try:
        full_prompt = f"{user_prompt}. {TOTTY_STYLE}"
        input_urls = [input_url] if input_url else None
        task_id = create_task(model_info["model"], full_prompt, input_urls)
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
    context.user_data.clear()
    await msg.delete()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Đã hủy. Gõ /design để bắt đầu lại.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("design", design)],
        states={
            CHOOSE_TYPE:  [CallbackQueryHandler(choose_type,  pattern="^type_")],
            CHOOSE_MODEL: [CallbackQueryHandler(choose_model, pattern="^model_")],
            GET_IMAGE:    [MessageHandler(filters.PHOTO, get_image)],
            GET_PROMPT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_prompt)],
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
