#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║         🎨 POLLINATIONS AI - TELEGRAM IMAGE BOT 🎨           ║
║              Powered by Pollinations.ai API                  ║
╚══════════════════════════════════════════════════════════════╝
"""

import logging
import urllib.parse
import urllib.request
import io
import json
import random
import os
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputMediaPhoto,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode, ChatAction

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
BOT_TOKEN   = os.environ.get("BOT_TOKEN", "8638701994:AAF1rFHvzaRX8t6eBMA5TSYZUnZ5gi_pGdk")
GEMINI_KEY  = os.environ.get("GEMINI_KEY", "AIzaSyDBeRwDVbQvKY0mI7KeDED4M48JJ2HK4DY")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
PORT        = int(os.environ.get("PORT", 8080))

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  CONSTANTS / STATES
# ─────────────────────────────────────────────
WAITING_PROMPT      = 1
WAITING_EDIT_PROMPT = 2
WAITING_BATCH_COUNT = 3

# Pollinations models
MODELS = {
    "imagen-3":       "🖼️ Imagen 3 (Default)",
    "imagen-3-fast":  "⚡ Imagen 3 Fast",
}

# Style presets
STYLE_PRESETS = {
    "realistic":      "ultra realistic, 8k, photographic, detailed",
    "anime":          "anime style, manga, vibrant colors, Studio Ghibli",
    "digital_art":    "digital art, concept art, artstation trending",
    "oil_painting":   "oil painting, classical art, textured canvas",
    "watercolor":     "watercolor painting, soft colors, artistic",
    "cyberpunk":      "cyberpunk, neon lights, futuristic city, dark",
    "fantasy":        "fantasy art, magical, ethereal, mystical",
    "minimalist":     "minimalist, clean lines, simple, modern design",
    "portrait":       "professional portrait, studio lighting, sharp focus",
    "landscape":      "epic landscape, golden hour, cinematic, wide angle",
    "cartoon":        "cartoon style, colorful, fun, Disney-like",
    "sketch":         "pencil sketch, hand drawn, detailed linework",
}

# Aspect ratios
ASPECT_RATIOS = {
    "square":     (1024, 1024, "Square 1:1"),
    "portrait":   (768,  1024, "Portrait 2:3"),
    "landscape":  (1024, 768,  "Landscape 4:3"),
    "wide":       (1280, 720,  "Widescreen 16:9"),
    "tall":       (720,  1280, "Tall 9:16"),
    "banner":     (1500, 500,  "Banner 3:1"),
}

# Default user settings
DEFAULT_SETTINGS = {
    "model":       "imagen-3",
    "style":       None,
    "ratio":       "square",
    "enhance":     True,
    "seed":        None,
    "nsfw":        False,
}

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def get_user_settings(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "settings" not in context.user_data:
        context.user_data["settings"] = DEFAULT_SETTINGS.copy()
    return context.user_data["settings"]

def get_history(context: ContextTypes.DEFAULT_TYPE) -> list:
    if "history" not in context.user_data:
        context.user_data["history"] = []
    return context.user_data["history"]

async def generate_image_gemini(prompt: str, settings: dict):
    """Gemini API দিয়ে image generate করে bytes আর seed return করে"""
    import asyncio, base64, json as _json

    style   = settings.get("style")
    seed    = settings.get("seed") or random.randint(1, 999999)

    full_prompt = prompt
    if style and style in STYLE_PRESETS:
        full_prompt = f"{prompt}, {STYLE_PRESETS[style]}"

    # Gemini imagen-3.0-generate-002 endpoint
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"imagen-3.0-generate-002:predict?key={GEMINI_KEY}"
    )

    ratio_key = settings.get("ratio", "square")
    ratio_map = {
        "square":    "1:1",
        "portrait":  "3:4",
        "landscape": "4:3",
        "wide":      "16:9",
        "tall":      "9:16",
        "banner":    "4:1",
    }
    aspect = ratio_map.get(ratio_key, "1:1")

    payload = _json.dumps({
        "instances": [{"prompt": full_prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": aspect,
            "safetyFilterLevel": "block_few",
            "personGeneration": "allow_adult",
        }
    }).encode()

    def _call():
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()

    loop = asyncio.get_event_loop()
    raw  = await loop.run_in_executor(None, _call)
    data = _json.loads(raw)

    b64 = data["predictions"][0]["bytesBase64Encoded"]
    image_bytes = base64.b64decode(b64)
    return image_bytes, seed

def settings_text(settings: dict) -> str:
    ratio_key  = settings.get("ratio", "square")
    _, _, ratio_label = ASPECT_RATIOS.get(ratio_key, (0, 0, ratio_key))
    model      = MODELS.get(settings.get("model", "flux"), settings.get("model", "flux"))
    style      = settings.get("style") or "None"
    enhance    = "✅ ON" if settings.get("enhance") else "❌ OFF"
    seed       = settings.get("seed") or "🎲 Random"
    return (
        f"⚙️ *Current Settings*\n\n"
        f"🤖 Model: `{model}`\n"
        f"🎨 Style: `{style}`\n"
        f"📐 Ratio: `{ratio_label}`\n"
        f"✨ Enhance: {enhance}\n"
        f"🌱 Seed: `{seed}`"
    )


# ─────────────────────────────────────────────
#  PERSISTENT BOTTOM KEYBOARD
# ─────────────────────────────────────────────

def persistent_keyboard():
    """Always-visible bottom keyboard buttons (like SMSly style)"""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🎨 Generate"),   KeyboardButton("🎲 Random")],
            [KeyboardButton("📦 Batch"),      KeyboardButton("🔁 Regenerate")],
            [KeyboardButton("⚙️ Settings"),   KeyboardButton("🎭 Styles")],
            [KeyboardButton("🤖 Models"),     KeyboardButton("📐 Ratio")],
            [KeyboardButton("📜 History"),    KeyboardButton("💡 Ideas")],
            [KeyboardButton("❓ Help")],
        ],
        resize_keyboard=True,
    )

# ─────────────────────────────────────────────
#  KEYBOARDS
# ─────────────────────────────────────────────

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎨 Generate Image",  callback_data="gen_start"),
            InlineKeyboardButton("🔀 Random Image",    callback_data="gen_random"),
        ],
        [
            InlineKeyboardButton("📦 Batch Generate",  callback_data="batch_start"),
            InlineKeyboardButton("🔁 Regenerate Last", callback_data="regen_last"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings",        callback_data="menu_settings"),
            InlineKeyboardButton("📜 History",         callback_data="menu_history"),
        ],
        [
            InlineKeyboardButton("🎭 Styles",          callback_data="menu_styles"),
            InlineKeyboardButton("📐 Aspect Ratio",    callback_data="menu_ratio"),
        ],
        [
            InlineKeyboardButton("🤖 Models",          callback_data="menu_models"),
            InlineKeyboardButton("💡 Prompt Ideas",    callback_data="prompt_ideas"),
        ],
        [
            InlineKeyboardButton("❓ Help",            callback_data="menu_help"),
        ],
    ])

def settings_keyboard(settings: dict):
    enhance_text = "✅ Enhance: ON" if settings.get("enhance") else "❌ Enhance: OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Change Model",        callback_data="menu_models")],
        [InlineKeyboardButton("🎨 Change Style",        callback_data="menu_styles")],
        [InlineKeyboardButton("📐 Change Ratio",        callback_data="menu_ratio")],
        [InlineKeyboardButton(enhance_text,             callback_data="toggle_enhance")],
        [InlineKeyboardButton("🌱 Set Custom Seed",     callback_data="set_seed")],
        [InlineKeyboardButton("🔄 Reset All Settings",  callback_data="reset_settings")],
        [InlineKeyboardButton("🏠 Main Menu",           callback_data="menu_main")],
    ])

def models_keyboard(current: str):
    rows = []
    for key, label in MODELS.items():
        check = "✅ " if key == current else ""
        rows.append([InlineKeyboardButton(f"{check}{label}", callback_data=f"set_model_{key}")])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="menu_settings")])
    return InlineKeyboardMarkup(rows)

def styles_keyboard(current):
    rows = []
    items = list(STYLE_PRESETS.items())
    for i in range(0, len(items), 2):
        row = []
        for key, _ in items[i:i+2]:
            label = key.replace("_", " ").title()
            check = "✅ " if key == current else ""
            row.append(InlineKeyboardButton(f"{check}{label}", callback_data=f"set_style_{key}"))
        rows.append(row)
    rows.append([
        InlineKeyboardButton("🚫 No Style", callback_data="set_style_none"),
        InlineKeyboardButton("🔙 Back",     callback_data="menu_settings"),
    ])
    return InlineKeyboardMarkup(rows)

def ratio_keyboard(current: str):
    rows = []
    items = list(ASPECT_RATIOS.items())
    for i in range(0, len(items), 2):
        row = []
        for key, (_, _, label) in items[i:i+2]:
            check = "✅ " if key == current else ""
            row.append(InlineKeyboardButton(f"{check}{label}", callback_data=f"set_ratio_{key}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="menu_settings")])
    return InlineKeyboardMarkup(rows)

def after_image_keyboard(prompt: str, seed: int):
    safe_prompt = prompt[:40].replace(" ", "_")
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔁 Regenerate",         callback_data=f"regen_{seed}_{safe_prompt}"),
            InlineKeyboardButton("✏️ Edit Prompt",        callback_data="edit_prompt"),
        ],
        [
            InlineKeyboardButton("📦 Make 4 Variants",    callback_data=f"variants_{safe_prompt}"),
            InlineKeyboardButton("⬆️ Upscale (HD)",       callback_data=f"upscale_{seed}_{safe_prompt}"),
        ],
        [
            InlineKeyboardButton("💾 Save to History",    callback_data=f"save_hist_{safe_prompt}"),
            InlineKeyboardButton("🎨 Change Style",       callback_data="menu_styles"),
        ],
        [InlineKeyboardButton("🏠 Main Menu",             callback_data="menu_main")],
    ])

def history_keyboard(history: list):
    rows = []
    for i, item in enumerate(reversed(history[-10:])):
        short = item["prompt"][:25] + "…" if len(item["prompt"]) > 25 else item["prompt"]
        rows.append([InlineKeyboardButton(f"#{len(history)-i} {short}", callback_data=f"hist_view_{len(history)-1-i}")])
    rows.append([
        InlineKeyboardButton("🗑️ Clear History", callback_data="clear_history"),
        InlineKeyboardButton("🔙 Back",          callback_data="menu_main"),
    ])
    return InlineKeyboardMarkup(rows)

# ─────────────────────────────────────────────
#  COMMANDS
# ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome = (
        f"✨ *Welcome, {user.first_name}!*\n\n"
        "🎨 I'm your *AI Image Generator Bot* powered by *Pollinations.ai*!\n\n"
        "🖼️ *What I can do:*\n"
        "• Generate stunning AI images from text\n"
        "• Multiple artistic styles & models\n"
        "• Various aspect ratios\n"
        "• Batch generate variants\n"
        "• Save & view history\n"
        "• Custom seeds for reproducibility\n\n"
        "👇 *Choose an option below to get started:*"
    )
    await update.message.reply_text(
        "👇 *Quick buttons activated!*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=persistent_keyboard(),
    )
    await update.message.reply_text(
        welcome,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 *Bot Commands & Usage*\n\n"
        "*/start* — Show main menu\n"
        "*/generate <prompt>* — Quick generate\n"
        "*/random* — Random image\n"
        "*/settings* — View/change settings\n"
        "*/history* — View recent generations\n"
        "*/help* — This help message\n\n"
        "💡 *Tips:*\n"
        "• Be descriptive in your prompts!\n"
        "• Try different styles for variety\n"
        "• Use seeds to reproduce exact images\n"
        "• Batch mode generates 4 variants at once\n\n"
        "📝 *Example prompts:*\n"
        "`A magical forest at sunset`\n"
        "`Futuristic city with flying cars`\n"
        "`Portrait of a samurai warrior`"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=InlineKeyboardMarkup([[
                                        InlineKeyboardButton("🏠 Main Menu", callback_data="menu_main")
                                    ]]))

async def cmd_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        prompt = " ".join(context.args)
        await _do_generate(update, context, prompt)
    else:
        await update.message.reply_text(
            "✏️ *Send me your image prompt:*",
            parse_mode=ParseMode.MARKDOWN,
        )
        return WAITING_PROMPT

async def cmd_random(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompts = [
        "A majestic dragon soaring over mountains at golden hour",
        "Underwater city with bioluminescent creatures",
        "A lone astronaut standing on an alien planet",
        "Enchanted forest with glowing mushrooms and fairies",
        "Steampunk marketplace in a floating city",
        "Ancient temple hidden in misty jungle",
        "Cyberpunk street market at night with neon signs",
        "A cozy magical library with floating books",
        "Wolf howling at aurora borealis",
        "Futuristic samurai in a neon-lit dojo",
    ]
    prompt = random.choice(prompts)
    await _do_generate(update, context, prompt, msg_override=f"🎲 *Random prompt:* `{prompt}`")

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = get_user_settings(context)
    await update.message.reply_text(
        settings_text(settings),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=settings_keyboard(settings),
    )

async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history = get_history(context)
    if not history:
        await update.message.reply_text(
            "📭 *Your history is empty!*\nGenerate some images first.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎨 Generate Now", callback_data="gen_start"),
            ]]),
        )
        return
    await update.message.reply_text(
        f"📜 *Your Generation History* ({len(history)} total)\n\nTap to view:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=history_keyboard(history),
    )

# ─────────────────────────────────────────────
#  CORE IMAGE GENERATION
# ─────────────────────────────────────────────

async def _do_generate(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str,
                        msg_override: str = None, batch_index: int = None,
                        custom_seed: int = None, upscale: bool = False):
    settings = get_user_settings(context)
    if custom_seed:
        settings = settings.copy()
        settings["seed"] = custom_seed

    if upscale:
        settings = settings.copy()
        orig_ratio = settings.get("ratio", "square")
        w, h, label = ASPECT_RATIOS[orig_ratio]
        # Double resolution for upscale (cap at 2048)
        settings["ratio"] = orig_ratio
        ASPECT_RATIOS_temp = ASPECT_RATIOS.copy()
        ASPECT_RATIOS_temp[orig_ratio] = (min(w*2, 2048), min(h*2, 2048), label + " HD")

    msg = update.message or (update.callback_query.message if update.callback_query else None)
    if not msg:
        return

    status_text = (
        msg_override or
        (f"🖼️ *Generating variant #{batch_index}...*" if batch_index else "⏳ *Generating your image...*")
    )
    status_msg = await msg.reply_text(
        status_text + "\n\n`⏳ Please wait... (30-60 seconds)`",
        parse_mode=ParseMode.MARKDOWN,
    )

    await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.UPLOAD_PHOTO)

    try:
        image_bytes, seed = await generate_image_gemini(prompt, settings)
        bio = io.BytesIO(image_bytes)
        bio.name = "image.jpg"

        caption = (
            f"🎨 *Generated Image*\n\n"
            f"📝 `{prompt[:200]}`\n\n"
            f"🤖 Model: `Gemini Imagen 3`\n"
            f"🎭 Style: `{settings.get('style') or 'Default'}`\n"
            f"📐 Ratio: `{ASPECT_RATIOS[settings.get('ratio','square')][2]}`\n"
            f"🌱 Seed: `{seed}`"
        )

        await status_msg.delete()
        sent = await msg.reply_photo(
            photo=bio,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=after_image_keyboard(prompt, seed),
        )

        # Save to history
        history = get_history(context)
        history.append({
            "prompt": prompt,
            "seed": seed,
            "model": settings.get("model"),
            "style": settings.get("style"),
            "ratio": settings.get("ratio"),
        })
        if len(history) > 50:
            history.pop(0)
        context.user_data["last_prompt"] = prompt
        context.user_data["last_seed"] = seed

    except urllib.error.HTTPError as e:
        logger.error(f"HTTP Error: {e.code} - {e.read()[:200]}")
        if e.code == 429:
            msg_text = "⏳ *Rate limit!* ৩০ সেকেন্ড অপেক্ষা করে আবার চেষ্টা করুন।"
        elif e.code == 400:
            msg_text = "❌ *Prompt টা Gemini accept করেনি।* অন্য prompt দিয়ে চেষ্টা করুন।"
        else:
            msg_text = f"❌ *Generation failed!*\n\n`HTTP {e.code}`\n\nPlease try again."
        await status_msg.edit_text(
            msg_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔁 Retry", callback_data="regen_last"),
                InlineKeyboardButton("🏠 Menu",  callback_data="menu_main"),
            ]]),
        )
    except Exception as e:
        logger.error(f"Generation error: {e}")
        await status_msg.edit_text(
            f"❌ *Generation failed!*\n\n`{str(e)[:100]}`\n\nPlease try again.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔁 Retry", callback_data="regen_last"),
                InlineKeyboardButton("🏠 Menu",  callback_data="menu_main"),
            ]]),
        )

# ─────────────────────────────────────────────
#  CONVERSATION HANDLERS
# ─────────────────────────────────────────────

async def conv_receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text.strip()
    if not prompt:
        await update.message.reply_text("❌ Please enter a valid prompt!")
        return WAITING_PROMPT
    await _do_generate(update, context, prompt)
    return ConversationHandler.END

async def conv_receive_edit_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_prompt = update.message.text.strip()
    await _do_generate(update, context, new_prompt)
    return ConversationHandler.END

async def conv_receive_batch_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text.strip())
        count = max(2, min(count, 6))
    except ValueError:
        count = 4
    prompt = context.user_data.get("batch_prompt", "a beautiful landscape")
    for i in range(1, count + 1):
        await _do_generate(update, context, prompt, batch_index=i)
    return ConversationHandler.END

async def conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# ─────────────────────────────────────────────
#  CALLBACK QUERY HANDLER
# ─────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    data   = query.data
    msg    = query.message
    settings = get_user_settings(context)

    # ── Main Menu ──
    if data == "menu_main":
        await msg.edit_text(
            "🏠 *Main Menu*\n\nChoose an option:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )

    # ── Generate Start ──
    elif data == "gen_start":
        await msg.edit_text(
            "✏️ *Send your image prompt:*\n\n"
            "💡 _Tip: Be descriptive! E.g. 'A futuristic city at night with neon lights'_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="menu_main")
            ]]),
        )
        context.user_data["awaiting"] = "prompt"

    # ── Random Image ──
    elif data == "gen_random":
        await query.answer("🎲 Generating random image...")
        await cmd_random(update, context)

    # ── Regen Last ──
    elif data == "regen_last":
        last = context.user_data.get("last_prompt")
        if last:
            await _do_generate(update, context, last)
        else:
            await query.answer("⚠️ No previous generation found!", show_alert=True)

    # ── Batch Start ──
    elif data == "batch_start":
        last = context.user_data.get("last_prompt", "a beautiful artwork")
        context.user_data["batch_prompt"] = last
        await msg.edit_text(
            f"📦 *Batch Generate*\n\n"
            f"Last prompt: `{last}`\n\n"
            f"How many variants? (2-6)\n"
            f"_Reply with a number or tap below:_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("2️⃣  2 Images", callback_data="batch_run_2"),
                    InlineKeyboardButton("4️⃣  4 Images", callback_data="batch_run_4"),
                ],
                [
                    InlineKeyboardButton("6️⃣  6 Images", callback_data="batch_run_6"),
                ],
                [InlineKeyboardButton("❌ Cancel", callback_data="menu_main")],
            ]),
        )

    elif data.startswith("batch_run_"):
        count  = int(data.split("_")[-1])
        prompt = context.user_data.get("batch_prompt", "a beautiful artwork")
        await msg.edit_text(
            f"⏳ Generating *{count} images*...\n`{prompt}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        for i in range(1, count + 1):
            await _do_generate(update, context, prompt, batch_index=i)

    # ── Settings ──
    elif data == "menu_settings":
        await msg.edit_text(
            settings_text(settings),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=settings_keyboard(settings),
        )

    elif data == "toggle_enhance":
        settings["enhance"] = not settings.get("enhance", True)
        await msg.edit_reply_markup(reply_markup=settings_keyboard(settings))
        await query.answer(f"Enhance {'ON' if settings['enhance'] else 'OFF'}")

    elif data == "reset_settings":
        context.user_data["settings"] = DEFAULT_SETTINGS.copy()
        await query.answer("✅ Settings reset!")
        await msg.edit_text(
            settings_text(DEFAULT_SETTINGS),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=settings_keyboard(DEFAULT_SETTINGS),
        )

    # ── Models ──
    elif data == "menu_models":
        await msg.edit_text(
            "🤖 *Select AI Model:*\n\n"
            "Each model has a different style and quality.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=models_keyboard(settings.get("model", "flux")),
        )

    elif data.startswith("set_model_"):
        model = data[len("set_model_"):]
        settings["model"] = model
        await query.answer(f"✅ Model set to {MODELS.get(model, model)}")
        await msg.edit_reply_markup(reply_markup=models_keyboard(model))

    # ── Styles ──
    elif data == "menu_styles":
        await msg.edit_text(
            "🎨 *Select Art Style:*\n\n"
            "Styles add artistic direction to your prompt.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=styles_keyboard(settings.get("style")),
        )

    elif data.startswith("set_style_"):
        style = data[len("set_style_"):]
        settings["style"] = None if style == "none" else style
        await query.answer(f"✅ Style set to {style}")
        await msg.edit_reply_markup(reply_markup=styles_keyboard(settings.get("style")))

    # ── Ratio ──
    elif data == "menu_ratio":
        await msg.edit_text(
            "📐 *Select Aspect Ratio:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ratio_keyboard(settings.get("ratio", "square")),
        )

    elif data.startswith("set_ratio_"):
        ratio = data[len("set_ratio_"):]
        settings["ratio"] = ratio
        _, _, label = ASPECT_RATIOS[ratio]
        await query.answer(f"✅ Ratio set to {label}")
        await msg.edit_reply_markup(reply_markup=ratio_keyboard(ratio))

    # ── History ──
    elif data == "menu_history":
        history = get_history(context)
        if not history:
            await msg.edit_text(
                "📭 *No history yet!*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎨 Generate", callback_data="gen_start"),
                    InlineKeyboardButton("🔙 Back",     callback_data="menu_main"),
                ]]),
            )
        else:
            await msg.edit_text(
                f"📜 *History* ({len(history)} items):",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=history_keyboard(history),
            )

    elif data.startswith("hist_view_"):
        idx     = int(data.split("_")[-1])
        history = get_history(context)
        if 0 <= idx < len(history):
            item = history[idx]
            await msg.edit_text(
                f"📌 *History Item #{idx+1}*\n\n"
                f"📝 Prompt: `{item['prompt']}`\n"
                f"🤖 Model: `{item['model']}`\n"
                f"🎭 Style: `{item.get('style') or 'Default'}`\n"
                f"📐 Ratio: `{ASPECT_RATIOS.get(item.get('ratio','square'),(0,0,'Unknown'))[2]}`\n"
                f"🌱 Seed: `{item['seed']}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 Regenerate This", callback_data=f"regen_hist_{idx}")],
                    [InlineKeyboardButton("🔙 History",         callback_data="menu_history")],
                ]),
            )

    elif data.startswith("regen_hist_"):
        idx     = int(data.split("_")[-1])
        history = get_history(context)
        if 0 <= idx < len(history):
            item   = history[idx]
            prompt = item["prompt"]
            seed   = item.get("seed")
            await _do_generate(update, context, prompt, custom_seed=seed)

    elif data == "clear_history":
        context.user_data["history"] = []
        await query.answer("🗑️ History cleared!")
        await msg.edit_text(
            "✅ History cleared!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Menu", callback_data="menu_main")
            ]]),
        )

    # ── After-image actions ──
    elif data.startswith("regen_"):
        parts  = data.split("_", 2)
        seed   = int(parts[1]) if parts[1].isdigit() else None
        prompt = context.user_data.get("last_prompt", "beautiful artwork")
        await _do_generate(update, context, prompt, custom_seed=seed)

    elif data == "edit_prompt":
        await msg.reply_text(
            "✏️ *Send your edited prompt:*",
            parse_mode=ParseMode.MARKDOWN,
        )
        context.user_data["awaiting"] = "edit_prompt"

    elif data.startswith("variants_"):
        prompt = context.user_data.get("last_prompt", "beautiful artwork")
        await msg.edit_text(
            f"📦 *Generating 4 variants...*\n`{prompt}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        for i in range(1, 5):
            await _do_generate(update, context, prompt, batch_index=i)

    elif data.startswith("upscale_"):
        prompt = context.user_data.get("last_prompt", "beautiful artwork")
        parts  = data.split("_", 2)
        seed   = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        await _do_generate(update, context, prompt, custom_seed=seed, upscale=True)

    elif data.startswith("save_hist_"):
        await query.answer("✅ Saved to history!", show_alert=False)

    # ── Prompt Ideas ──
    elif data == "prompt_ideas":
        ideas = [
            "🌅 A dragon overlooking a misty mountain valley at sunrise",
            "🤖 Cyberpunk android playing chess in a neon-lit café",
            "🏰 Medieval castle floating on clouds with waterfalls",
            "🌊 Deep ocean bioluminescent creatures around a sunken ship",
            "🚀 Astronaut discovering ancient ruins on Mars",
            "🦋 Magical garden where flowers are made of stained glass",
            "🐉 Chinese dragon made of flowing water and clouds",
            "🌆 Retrofuturistic city from the 1950s vision of 2000",
        ]
        await msg.edit_text(
            "💡 *Prompt Ideas:*\n\n" + "\n".join(f"• `{p}`" for p in ideas),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎲 Use Random Idea", callback_data="gen_random")],
                [InlineKeyboardButton("🔙 Back",            callback_data="menu_main")],
            ]),
        )

    # ── Help ──
    elif data == "menu_help":
        help_text = (
            "❓ *Help & Guide*\n\n"
            "*🎨 Generating Images:*\n"
            "1. Tap 'Generate Image'\n"
            "2. Type your prompt\n"
            "3. Wait for the magic! ✨\n\n"
            "*⚙️ Settings:*\n"
            "• *Model* — Different AI engines\n"
            "• *Style* — Artistic presets\n"
            "• *Ratio* — Image dimensions\n"
            "• *Enhance* — Automatic prompt improvement\n"
            "• *Seed* — Reproducible results\n\n"
            "*📦 Batch Mode:*\n"
            "Generate 2-6 variants of one prompt\n\n"
            "*📜 History:*\n"
            "Stores your last 50 generations"
        )
        await msg.edit_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu_main")
            ]]),
        )

    # ── Set Seed ──
    elif data == "set_seed":
        await msg.edit_text(
            "🌱 *Set Custom Seed*\n\n"
            "Reply with a number (e.g. `42`)\n"
            "Or tap below for random seed:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎲 Use Random", callback_data="seed_random")],
                [InlineKeyboardButton("🔙 Back",       callback_data="menu_settings")],
            ]),
        )
        context.user_data["awaiting"] = "seed"

    elif data == "seed_random":
        settings["seed"] = None
        await query.answer("🎲 Seed set to random!")
        await msg.edit_text(
            settings_text(settings),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=settings_keyboard(settings),
        )

# ─────────────────────────────────────────────
#  TEXT MESSAGE HANDLER (awaiting inputs)
# ─────────────────────────────────────────────

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    awaiting = context.user_data.get("awaiting")
    text     = update.message.text.strip()

    # ── Handle persistent bottom keyboard buttons ──
    button_actions = {
        "🎨 Generate":   "prompt",
        "🎲 Random":     "random",
        "📦 Batch":      "batch",
        "🔁 Regenerate": "regen",
        "⚙️ Settings":   "settings",
        "🎭 Styles":     "styles",
        "🤖 Models":     "models",
        "📐 Ratio":      "ratio",
        "📜 History":    "history",
        "💡 Ideas":      "ideas",
        "❓ Help":       "help",
    }

    if text in button_actions:
        action = button_actions[text]

        if action == "prompt":
            context.user_data["awaiting"] = "prompt"
            await update.message.reply_text(
                "✏️ *Send your image prompt:*\n\n💡 _Be descriptive for best results!_",
                parse_mode=ParseMode.MARKDOWN,
            )
        elif action == "random":
            await cmd_random(update, context)
        elif action == "batch":
            last = context.user_data.get("last_prompt", "a beautiful artwork")
            context.user_data["batch_prompt"] = last
            await update.message.reply_text(
                f"📦 *Batch Generate*\n\nUsing: `{last}`\n\nSelect count:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("2️⃣ 2 Images", callback_data="batch_run_2"),
                        InlineKeyboardButton("4️⃣ 4 Images", callback_data="batch_run_4"),
                    ],
                    [InlineKeyboardButton("6️⃣ 6 Images", callback_data="batch_run_6")],
                    [InlineKeyboardButton("❌ Cancel",     callback_data="menu_main")],
                ]),
            )
        elif action == "regen":
            last = context.user_data.get("last_prompt")
            if last:
                await _do_generate(update, context, last)
            else:
                await update.message.reply_text("⚠️ No previous generation found! Generate something first.")
        elif action == "settings":
            settings = get_user_settings(context)
            await update.message.reply_text(
                settings_text(settings),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=settings_keyboard(settings),
            )
        elif action == "styles":
            settings = get_user_settings(context)
            await update.message.reply_text(
                "🎨 *Select Art Style:*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=styles_keyboard(settings.get("style")),
            )
        elif action == "models":
            settings = get_user_settings(context)
            await update.message.reply_text(
                "🤖 *Select AI Model:*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=models_keyboard(settings.get("model", "flux")),
            )
        elif action == "ratio":
            settings = get_user_settings(context)
            await update.message.reply_text(
                "📐 *Select Aspect Ratio:*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ratio_keyboard(settings.get("ratio", "square")),
            )
        elif action == "history":
            history = get_history(context)
            if not history:
                await update.message.reply_text(
                    "📭 *No history yet!* Generate some images first.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                await update.message.reply_text(
                    f"📜 *History* ({len(history)} items):",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=history_keyboard(history),
                )
        elif action == "ideas":
            ideas = [
                "A majestic dragon soaring over mountains at golden hour",
                "Underwater city with bioluminescent creatures",
                "A lone astronaut standing on an alien planet",
                "Enchanted forest with glowing mushrooms and fairies",
                "Steampunk marketplace in a floating city",
                "Cyberpunk street market at night with neon signs",
                "A cozy magical library with floating books",
                "Futuristic samurai in a neon-lit dojo",
            ]
            await update.message.reply_text(
                "💡 *Prompt Ideas — tap to copy:*\n\n" + "\n".join(f"• `{p}`" for p in ideas),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎲 Use Random Idea", callback_data="gen_random")
                ]]),
            )
        elif action == "help":
            await cmd_help(update, context)
        return

    # ── Handle awaiting inputs ──
    if awaiting == "prompt":
        context.user_data["awaiting"] = None
        await _do_generate(update, context, text)

    elif awaiting == "edit_prompt":
        context.user_data["awaiting"] = None
        await _do_generate(update, context, text)

    elif awaiting == "seed":
        context.user_data["awaiting"] = None
        settings = get_user_settings(context)
        try:
            seed = int(text)
            settings["seed"] = seed
            await update.message.reply_text(
                f"✅ Seed set to `{seed}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=settings_keyboard(settings),
            )
        except ValueError:
            await update.message.reply_text("❌ Invalid seed. Use a number like `42`.",
                                            parse_mode=ParseMode.MARKDOWN)

    else:
        # Treat any text as a prompt directly
        await _do_generate(update, context, text)

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    print("╔══════════════════════════════════════════╗")
    print("║   🎨  Pollinations AI Image Bot  🎨      ║")
    print("║   Starting up...                         ║")
    print("╚══════════════════════════════════════════╝")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("generate", cmd_generate))
    app.add_handler(CommandHandler("random",   cmd_random))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("history",  cmd_history))

    # Callback queries
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # Railway/Production: webhook mode হলে webhook use করো
    if WEBHOOK_URL:
        print(f"🌐 Webhook mode: {WEBHOOK_URL}")
        print(f"🔌 Port: {PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
            drop_pending_updates=True,
        )
    else:
        # Local: polling mode
        print("💻 Polling mode (local)...")
        print(f"✅ Bot is running! Press Ctrl+C to stop.\n")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
