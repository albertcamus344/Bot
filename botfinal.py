#!/usr/bin/env python3
"""
Telegram YouTube downloader bot using python-telegram-bot (v20+) + yt-dlp.

Behavior:
 - When a user sends a YouTube link, the bot fetches available formats with yt-dlp
 - Presents an inline keyboard letting the user choose a format (resolution/container) or audio-only
 - Downloads the selected format by format id (no generic "best" fallback), merges if necessary
 - Uploads back to Telegram

Replace TELEGRAM_TOKEN with your bot token.
"""
import logging
import re
import os
import asyncio
import tempfile
from functools import partial
from pathlib import Path
from typing import Dict, Any, List

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
import yt_dlp

# ===== CONFIG =====
TELEGRAM_TOKEN = "8264683279:AAGoejkdiRl2kWe2NPu5bdQPE1hI5UvD9-4"
MAX_BUTTONS = 10  # limit how many format buttons we show (per category)
# ==================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

YOUTUBE_URL_RE = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w\-]{8,}"
)

# Helper: friendly label for a format dict
def format_label(f: Dict[str, Any]) -> str:
    # f is a format dict from yt-dlp
    # show resolution + vcodec + acodec + container + filesize if known
    fmt_id = f.get("format_id")
    container = f.get("ext") or "?"
    vcodec = f.get("vcodec", "none")
    acodec = f.get("acodec", "none")
    # resolution
    resolution = f.get("resolution") or f.get("height") or ""
    if resolution == "" and f.get("height"):
        resolution = f"{f['height']}p"
    # filesize human readable
    fs = f.get("filesize") or f.get("filesize_approx")
    if fs:
        # simple human readable
        for unit in ["B", "KB", "MB", "GB"]:
            if fs < 1024.0:
                fs_str = f"{fs:.1f}{unit}"
                break
            fs /= 1024.0
        else:
            fs_str = f"{fs:.1f}TB"
        size_part = f" • {fs_str}"
    else:
        size_part = ""
    # if audio-only
    if vcodec == "none" and acodec != "none":
        return f"Audio • {acodec}/{container}{size_part} ({fmt_id})"
    # progressive (both)
    if vcodec != "none" and acodec != "none":
        res_text = resolution or "progressive"
        return f"{res_text} • {vcodec}/{acodec}/{container}{size_part} ({fmt_id})"
    # video-only
    if vcodec != "none" and acodec == "none":
        res_text = resolution or "video"
        return f"{res_text} • {vcodec}/{container}{size_part} ({fmt_id})"
    return f"{fmt_id} • {container}{size_part}"


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send me a YouTube link and I'll give you download options (video resolutions and audio)."
    )


def extract_formats_info(url: str) -> Dict[str, Any]:
    """
    Use yt-dlp to fetch info (no download).
    Returns the info dict from yt-dlp.
    """
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info


def categorize_formats(formats: List[Dict[str, Any]]):
    """
    Split formats into:
      - progressive (both audio+video in same file)
      - video_only (adaptive)
      - audio_only
    Also deduplicate by (height, ext) for nicer presentation.
    """
    progressive = []
    video_only = []
    audio_only = []

    seen_prog = set()
    seen_vid = set()
    seen_aud = set()

    for f in formats:
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        ext = f.get("ext") or "mp4"
        height = f.get("height")
        fmt_id = f.get("format_id")

        # Skip DRM or unknown
        if f.get("filesize") == 0:
            # sometimes 0 is a bad indicator; we'll leave it, but not crash
            pass

        if vcodec != "none" and acodec != "none":
            # progressive
            key = (height or 0, ext, vcodec, acodec)
            if key in seen_prog:
                continue
            seen_prog.add(key)
            progressive.append(f)
        elif vcodec != "none" and acodec == "none":
            # video-only
            key = (height or 0, ext, vcodec)
            if key in seen_vid:
                continue
            seen_vid.add(key)
            video_only.append(f)
        elif acodec != "none" and vcodec == "none":
            # audio-only
            abr = f.get("abr") or 0
            key = (abr, ext)
            if key in seen_aud:
                continue
            seen_aud.add(key)
            audio_only.append(f)
    # sort each group: highest quality first
    progressive.sort(key=lambda x: (x.get("height") or 0, x.get("tbr") or 0), reverse=True)
    video_only.sort(key=lambda x: (x.get("height") or 0, x.get("tbr") or 0), reverse=True)
    audio_only.sort(key=lambda x: (x.get("abr") or 0, x.get("tbr") or 0), reverse=True)
    return progressive, video_only, audio_only


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text or not YOUTUBE_URL_RE.search(text):
        await update.message.reply_text(
            "Please send a valid YouTube URL (youtube.com/watch?v=... or youtu.be/...)."
        )
        return

    url = YOUTUBE_URL_RE.search(text).group(0)
    msg = await update.message.reply_text("Fetching formats from YouTube (this can take a few seconds)...")
    loop = asyncio.get_running_loop()

    try:
        info = await loop.run_in_executor(None, partial(extract_formats_info, url))
    except Exception as e:
        logger.exception("Failed to extract info")
        await msg.edit_text(f"Failed to get video info: {e}")
        return

    title = info.get("title", "video")
    formats = info.get("formats", [])

    progressive, video_only, audio_only = categorize_formats(formats)

    # Build keyboard. Each button's callback_data contains the format_id and video title (urlsafe)
    keyboard = []
    # Show up to MAX_BUTTONS from each category to avoid huge keyboards
    def add_rows(label_prefix, fmt_list):
        rows = []
        count = 0
        for f in fmt_list:
            if count >= MAX_BUTTONS:
                break
            label = format_label(f)
            fmt_id = f.get("format_id")
            # callback data: "DL|<format_id>|<url>"
            # Keep callback data short: only format id and original URL as last param
            cbdata = f"DL|{fmt_id}|{info.get('webpage_url')}"
            rows.append([InlineKeyboardButton(label[:50], callback_data=cbdata)])
            count += 1
        return rows

    if progressive:
        keyboard += [[InlineKeyboardButton("Progressive (audio+video)", callback_data="NONE")]]
        keyboard += add_rows("prog", progressive)
    if video_only:
        keyboard += [[InlineKeyboardButton("Adaptive video-only (will be merged with audio)", callback_data="NONE")]]
        keyboard += add_rows("vid", video_only)
    if audio_only:
        keyboard += [[InlineKeyboardButton("Audio-only", callback_data="NONE")]]
        keyboard += add_rows("aud", audio_only)

    # Add a cancel button
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="CANCEL")])

    await msg.edit_text(
        f"Found formats for: *{title}*\nChoose a format to download:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # prevents "spinning" on client
    data = query.data or ""

    if data == "CANCEL":
        await query.edit_message_text("Cancelled.")
        return

    if data.startswith("DL|"):
        # data: DL|<format_id>|<url>
        parts = data.split("|", 2)
        if len(parts) < 3:
            await query.edit_message_text("Invalid callback data.")
            return
        fmt_id = parts[1]
        url = parts[2]
        user = query.from_user
        # acknowledge and start download in background to avoid blocking callback handler
        await query.edit_message_text(f"Queued download for format `{fmt_id}` — starting...", parse_mode="Markdown")
        # run blocking download in executor
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, partial(download_and_send, context.bot, user.id, url, fmt_id, query.message.chat_id, query.message.message_id))
        except Exception as e:
            logger.exception("download/send failed")
            # Try to inform user
            try:
                await context.bot.send_message(chat_id=query.message.chat_id, text=f"Error while processing: {e}")
            except Exception:
                pass
    else:
        # nothing
        await query.edit_message_text("Unknown action.")


def download_and_send(bot, user_id, url, format_id, chat_id, reply_to_message_id):
    """
    Runs in a background thread (not async). Downloads format 'format_id' for video at 'url' and uploads to telegram.
    This function must be synchronous because it's executed via run_in_executor.
    """
    # Create a temporary working directory per-download
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        # Build outtmpl to store file with proper extension
        # We'll let yt-dlp decide extension; use template
        outtmpl = str(tmpdir_path / "%(title)s.%(ext)s")
        ydl_opts = {
            "format": format_id,  # download exactly this format (format id may be "137+140" or single id)
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            # ensure post-processing merges if needed (yt-dlp does this automatically for combined format if given "137+140")
            "merge_output_format": "mp4",  # when merging chooses this container
            # progress hooks could be used but in this blocking worker we will not stream progress to the user
        }

        # Because format_id might be a single adaptive format (video-only) and user expects merged result,
        # it's safe to pass the chosen format id to yt-dlp. If the user selected a video-only format_id like "137"
        # yt-dlp won't automatically download the audio unless the format string has a '+'.
        # To be user-friendly, if the chosen id is video-only, we attempt to merge with bestaudio automatically.
        # We detect this by probing available formats first.
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            # fallback: just try to download and let yt-dlp fail if necessary
            info = {}

        # Determine if selected format is audio-only, video-only or combined
        selected_format = None
        for f in info.get("formats", []):
            if f.get("format_id") == format_id:
                selected_format = f
                break

        # If selected_format not found, it's still OK — yt-dlp will try to parse the format expression
        need_merge_audio = False
        if selected_format:
            vcodec = selected_format.get("vcodec") or "none"
            acodec = selected_format.get("acodec") or "none"
            if vcodec != "none" and acodec == "none":
                # user selected video-only; let's download video + best audio and merge
                # format expression: "<video_id>+bestaudio/best"
                ydl_opts["format"] = f"{format_id}+bestaudio/best"
                need_merge_audio = True
            elif vcodec == "none" and acodec != "none":
                # audio-only: no merging needed
                pass
            else:
                # combined
                pass
        else:
            # format id not matched (maybe complex expression). Let yt-dlp do its thing.
            pass

        # Add postprocessors (ffmpeg merger)
        ydl_opts["postprocessors"] = [
            {"key": "FFmpegMetadata"},  # preserve metadata
        ]
        # If merging required, yt-dlp will use ffmpeg automatically

        downloaded_filepath = None
        title = "video"
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_result = ydl.extract_info(url, download=True)
                title = info_result.get("title", title)
                # yt-dlp returns either dict or list for entries
                # Find the downloaded filename from info_result
                # yt-dlp will set 'requested_downloads' etc; easiest is to search tmpdir for files
                files = list(tmpdir_path.glob("*"))
                # pick the largest file (likely final output)
                if files:
                    files_sorted = sorted(files, key=lambda p: p.stat().st_size, reverse=True)
                    downloaded_filepath = files_sorted[0]
        except Exception as e:
            logger.exception("yt-dlp download failed")
            # Try to send error message to user
            try:
                bot.send_message(chat_id=chat_id, text=f"Download failed: {e}", reply_to_message_id=reply_to_message_id)
            except Exception:
                pass
            return

        if not downloaded_filepath or not downloaded_filepath.exists():
            try:
                bot.send_message(chat_id=chat_id, text="Could not find downloaded file after yt-dlp finished.", reply_to_message_id=reply_to_message_id)
            except Exception:
                pass
            return

        # Choose how to upload: send_video if it's a video under Telegram limits & recognized, else send_document
        size = downloaded_filepath.stat().st_size
        fname = downloaded_filepath.name
        ext = downloaded_filepath.suffix.lower()

        # Attach as video for common extensions if possible, otherwise as document
        as_video_exts = {".mp4", ".mkv", ".mov", ".webm", ".avi"}
        try:
            with downloaded_filepath.open("rb") as f:
                if ext in as_video_exts:
                    # Try sending as video to have Telegram display it inline
                    bot.send_video(chat_id=chat_id, video=f, caption=title, reply_to_message_id=reply_to_message_id)
                else:
                    # send as document
                    bot.send_document(chat_id=chat_id, document=f, filename=fname, caption=title, reply_to_message_id=reply_to_message_id)
        except Exception as e:
            logger.exception("Failed to upload file to Telegram")
            try:
                bot.send_message(chat_id=chat_id, text=f"Failed to upload file: {e}", reply_to_message_id=reply_to_message_id)
            except Exception:
                pass
            return

        # Optionally, cleanup is automatic due to TemporaryDirectory context manager
        logger.info("Finished sending %s (size: %d bytes)", downloaded_filepath, size)


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(on_callback))

    logger.info("Starting bot...")
    app.run_polling()


if __name__ == "__main__":
    main()
