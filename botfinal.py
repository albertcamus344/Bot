# bot.py
import os
import re
import math
import tempfile
import asyncio
from datetime import timedelta

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from yt_dlp import YoutubeDL

BOT_TOKEN = os.environ["8264683279:AAGoejkdiRl2kWe2NPu5bdQPE1hI5UvD9-4"]

# Telegram Bot API limits (bots): up to ~2 GB; stay a bit under to be safe.
TELEGRAM_BOT_MAX_BYTES = 2_000_000_000  # bot hard limit; do not exceed [web:3][web:7][web:13]

YDL_BASE_OPTS = {
    # Keep yt-dlp updated or SABR/format issues can force 360p fallbacks. [web:6][web:9][web:12]
    "noplaylist": True,
    "ignoreerrors": False,
    "quiet": True,
    "no_warnings": True,
    "concurrent_fragment_downloads": 5,
    "retries": 5,
    "fragment_retries": 5,
    "http_chunk_size": 10485760,  # 10MB
    "prefer_free_formats": False,  # allow avc/h264/hevc/vp9/av1 etc. [web:1]
    "merge_output_format": "mp4",  # try to get mp4; yt-dlp will transcode/merge as needed [web:1]
    "outtmpl": "%(title).200B [%(id)s].%(ext)s",
    "writesubtitles": False,
    "writeautomaticsub": False,
    "subtitleslangs": ["en.*,.*"],  # prefer en and any available [web:1]
    "postprocessors": [
        {"key": "FFmpegMetadata"},
        {"key": "FFmpegEmbedSubtitle"}  # embed softsubs when possible [web:1]
    ],
}

YDL_LIST_OPTS = {
    **YDL_BASE_OPTS,
    "listformats": False,
    "dump_single_json": True,   # get full info dict with formats/subs [web:1]
}

URL_RE = re.compile(r"https?://(www\.)?(youtube\.com|youtu\.be)/\S+")

def human_size(n):
    units = ["B","KB","MB","GB","TB"]
    i = 0
    while n >= 1024 and i < len(units)-1:
        n /= 1024.0
        i += 1
    return f"{n:.2f} {units[i]}"

def build_format_rows(info):
    # Build friendly choices: distinct resolutions for muxed or mergeable formats, plus audio-only. [web:1]
    formats = info.get("formats", [])
    choices = {}
    audio_only = []

    for f in formats:
        fmt_id = f.get("format_id")
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        height = f.get("height")
        ext = f.get("ext")
        filesize = f.get("filesize") or f.get("filesize_approx")
        if (vcodec is None or vcodec == "none") and (acodec and acodec != "none"):
            audio_only.append({
                "id": fmt_id, "label": f"Audio {acodec or ''} {ext or ''} {human_size(filesize) if filesize else ''}".strip(),
                "filesize": filesize
            })
        elif vcodec and vcodec != "none":
            res = f"{height}p" if height else f.get("format_note") or "video"
            # store best size per res (prefer formats with acodec to avoid merging when possible) [web:1]
            key = (res, acodec != "none")
            prev = choices.get(key)
            if prev is None or (filesize and prev.get("filesize", 0) and filesize < prev["filesize"]):
                choices[key] = {
                    "id": fmt_id,
                    "res": res,
                    "has_audio": acodec != "none",
                    "filesize": filesize,
                    "ext": ext or "mp4",
                    "vcodec": vcodec,
                }

    # Collapse keys into buttons, prefer has-audio True first for each resolution. [web:1]
    by_res = {}
    for (res, has_audio), item in choices.items():
        best = by_res.get(res)
        if best is None or (has_audio and not best["has_audio"]):
            by_res[res] = item

    # Sort descending by numeric resolution when possible. [web:1]
    def res_key(r):
        try:
            return -int(r.replace("p",""))
        except:
            return 0
    ordered = [by_res[r] for r in sorted(by_res.keys(), key=res_key)]
    return ordered, audio_only

async def progress_cb(current, total, update: Update, context: ContextTypes.DEFAULT_TYPE, prefix="Uploading"):
    try:
        pct = (current / total) * 100 if total else 0
        bar_len = 15
        filled = math.floor(bar_len * pct / 100)
        bar = "█"*filled + "·"*(bar_len - filled)
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_DOCUMENT)
        # Avoid spamming too frequently; this is a simple progress notifier pattern. [web:13]
        if int(pct) % 10 == 0:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"{prefix}: {bar} {pct:.0f}% ({human_size(current)}/{human_size(total)})"
            )
    except Exception:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send a YouTube link to get download options (resolutions, audio, subtitles).")  # [web:13]

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    match = URL_RE.search(text)
    if not match:
        return
    url = match.group(0)

    await update.message.reply_text("Fetching formats...")  # [web:13]

    # Ensure yt-dlp modern behavior to avoid 360p-only pitfalls:
    # - no stale cookies, no forced tv/web-client with SABR-only; rely on default client mix. [web:9][web:12]
    # - keep yt-dlp updated in environment (pip install -U yt-dlp regularly). [web:6][web:1]
    with YoutubeDL(YDL_LIST_OPTS) as ydl:
        info = ydl.extract_info(url, download=False)

    title = info.get("title", "video")
    formats = info.get("formats", [])
    subs = info.get("subtitles") or info.get("automatic_captions") or {}

    video_choices, audio_only = build_format_rows(info)

    buttons = []
    # Best (let yt-dlp pick bestvideo+bestaudio and merge)
    buttons.append([InlineKeyboardButton(text="Best (auto merge)", callback_data=f"best|{url}")])

    # Specific resolutions
    for item in video_choices[:12]:
        res = item["res"]
        label = f"{res}{' (muxed)' if item['has_audio'] else ''}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"v:{item['id']}|{url}")])

    # Audio-only options (present generic choice instead)
    if audio_only:
        buttons.append([InlineKeyboardButton(text="Audio only (best)", callback_data=f"audio|{url}")])

    # Subtitles toggle
    has_subs = bool(subs)
    if has_subs:
        buttons.append([InlineKeyboardButton(text="Include subtitles", callback_data=f"subs:on|{url}")])
        buttons.append([InlineKeyboardButton(text="Without subtitles", callback_data=f"subs:off|{url}")])

    # Keep a small context map per chat
    context.user_data["pending_url"] = url
    context.user_data["include_subs"] = has_subs  # default to include when available

    await update.message.reply_text(
        f"Select a download option for: {title}",  # [web:13]
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def on_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    # Parse toggles and commands
    if data.startswith("subs:"):
        val, url = data.split("|", 1)
        include = val.endswith("on")
        context.user_data["include_subs"] = include
        await query.edit_message_text(f"Subtitles: {'on' if include else 'off'}. Choose a quality above or pick Best/Audio.")  # [web:13]
        return

    if "|" in data:
        choice, url = data.split("|", 1)
    else:
        choice = data
        url = context.user_data.get("pending_url")

    include_subs = context.user_data.get("include_subs", False)

    # Build yt-dlp options based on choice
    ydl_opts = dict(YDL_BASE_OPTS)
    # Subtitle handling [web:1]
    if include_subs:
        ydl_opts["writesubtitles"] = True
        ydl_opts["writeautomaticsub"] = True
        ydl_opts["subtitleslangs"] = ["en.*,.*"]
        # Embed where possible via FFmpegEmbedSubtitle postprocessor already set [web:1]
    else:
        ydl_opts["writesubtitles"] = False
        ydl_opts["writeautomaticsub"] = False
        # Remove embed postprocessor if no subs
        ydl_opts["postprocessors"] = [pp for pp in ydl_opts["postprocessors"] if pp["key"] != "FFmpegEmbedSubtitle"]

    # Format selector to avoid 360p-only:
    # - For "best", explicitly request bestvideo*+bestaudio/best to get highest resoln + merge. [web:1][web:11]
    # - For specific format_id, use that format explicitly, and if it’s video-only, pair with bestaudio for merging. [web:1]
    if choice == "best":
        ydl_opts["format"] = "bv*+ba/b"  # robust best selection [web:1][web:11]
    elif choice == "audio":
        ydl_opts["format"] = "bestaudio/bestaudio*"
        # Convert to m4a/mp3 via postprocessor if needed (optional)
    elif choice.startswith("v:"):
        fmt_id = choice.split(":", 1)[1]
        # Try requested format; if video-only, merge with bestaudio. [web:1]
        ydl_opts["format"] = f"{fmt_id}+bestaudio/{fmt_id}"
    else:
        ydl_opts["format"] = "bv*+ba/b"

    # Use a private temp dir per task
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts["paths"] = {"home": tmpdir, "temp": tmpdir}
        # Avoid partially huge files beyond Telegram limit by pre-checking selected format size via info JSON. [web:13]
        # We’ll still guard after download, but try to avoid wasting bandwidth.
        # Note: exact merged size can differ; still re-check after download. [web:1]
        await query.edit_message_text("Downloading... this may take a while.")  # [web:13]
        file_path = None
        thumb_path = None
        title = "video"

        def progress_hook(d):
            # Optional: could add download progress messages here (status downloading)
            pass

        ydl_opts["progress_hooks"] = [progress_hook]

        try:
            loop = asyncio.get_event_loop()
            def run_download():
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    out = ydl.prepare_filename(info)
                    # If merged container differs, yt-dlp may return proper path via info dict
                    nonlocal_file = info.get("requested_downloads", [{}])[0].get("filepath") or out
                    return info, nonlocal_file
            info, file_path = await loop.run_in_executor(None, run_download)
            title = info.get("title") or "video"

            # Check size
            stat = os.stat(file_path)
            if stat.st_size > TELEGRAM_BOT_MAX_BYTES:
                await query.edit_message_text(
                    f"File is {human_size(stat.st_size)}, exceeds bot upload limit (~2 GB). Try a lower resolution or audio-only."  # [web:3][web:7][web:13]
                )
                return

            # Optional: try to locate a thumbnail created by yt-dlp/ffmpeg [web:3]
            for name in os.listdir(tmpdir):
                if name.lower().endswith((".jpg",".jpeg",".png")) and info.get("id","") in name:
                    thumb_path = os.path.join(tmpdir, name)
                    break

            await query.edit_message_text("Uploading to Telegram...")  # [web:13]

            # Choose send method: send_video for mp4 with small size, else send_document for general files. [web:13]
            filename = os.path.basename(file_path)
            mime_is_video = filename.lower().endswith((".mp4",".mkv",".webm",".mov"))
            chat_id = update.effective_chat.id
            total_size = stat.st_size
            sent = 0

            # python-telegram-bot handles upload streaming; add minimal progress pings. [web:13][web:8]
            # Simplify: use send_document for reliability across containers.
            with open(file_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=InputFile(f, filename=filename),
                    caption=title[:900],
                    thumbnail=InputFile(thumb_path) if thumb_path else None,
                )

            await context.bot.send_message(chat_id=chat_id, text="Done.")  # [web:13]

        except Exception as e:
            await query.edit_message_text(f"Error: {e}")  # [web:13]

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(on_choice))
    await app.initialize()
    await app.start()
    print("Bot started")
    await app.updater.start_polling()
    await app.updater.idle()

if __name__ == "__main__":
    asyncio.run(main())
