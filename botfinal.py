import os
import logging
import re
import json
from yt_dlp import YoutubeDL
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode

# --- Configuration ---
# Replace 'YOUR_TELEGRAM_BOT_TOKEN' with the token you got from BotFather
BOT_TOKEN = "8264683279:AAGoejkdiRl2kWe2NPu5bdQPE1hI5UvD9-4"
# --- End Configuration ---

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# A simple regex to find YouTube URLs
YOUTUBE_URL_REGEX = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}! 👋",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("How to use", callback_data="help")]
        ])
    )
    await help_command(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message."""
    help_text = (
        "🔗 **How to use this bot:**\n\n"
        "1. Send me any YouTube link (e.g., `youtube.com/watch?v=...` or `youtu.be/...`).\n"
        "2. I will show you a list of available download options.\n"
        "3. Choose the format you want (video, audio, or subtitles).\n"
        "4. Wait for me to download and upload the file for you.\n\n"
        "Enjoy! ✨"
    )
    # If called from a button, edit the message. Otherwise, send a new one.
    if update.callback_query:
        await update.callback_query.message.edit_text(help_text, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

# --- Message and Callback Handlers ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming messages to find YouTube links."""
    message_text = update.message.text
    match = re.search(YOUTUBE_URL_REGEX, message_text)

    if not match:
        await update.message.reply_text("Please send a valid YouTube video link.")
        return

    url = match.group(0)
    status_message = await update.message.reply_text("🔍 Processing your link, please wait...")

    try:
        # Use yt-dlp to extract video information
        ydl_opts = {'quiet': True, 'skip_download': True}
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)

        # Store video info in context for later use in callbacks
        context.user_data['video_info'] = info_dict
        context.user_data['video_url'] = url

        keyboard = build_keyboard(info_dict)

        if not keyboard:
             await status_message.edit_text("Couldn't find any downloadable formats for this video.")
             return

        await status_message.edit_text(
            f"🎬 **{info_dict.get('title', 'N/A')}**\n\n"
            "Please choose a format to download:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"Error processing URL {url}: {e}")
        await status_message.edit_text(f"Sorry, I couldn't process that link. 😞\nError: {e}")

def build_keyboard(info: dict) -> list:
    """Builds the inline keyboard with download options."""
    keyboard = []
    video_formats = []
    
    # Filter and sort video formats by resolution
    for f in info.get('formats', []):
        # We want video-only streams that we can merge with audio
        if f.get('vcodec') != 'none' and f.get('acodec') == 'none' and f.get('ext') == 'mp4':
            resolution = f.get('height')
            if resolution:
                # Avoid duplicates
                if not any(vf['resolution'] == resolution for vf in video_formats):
                    video_formats.append({
                        'resolution': resolution,
                        'format_id': f['format_id'],
                        'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                        'ext': f.get('ext')
                    })
    
    # Sort by resolution descending
    video_formats.sort(key=lambda x: x['resolution'], reverse=True)

    # Create buttons for video formats
    for vf in video_formats[:5]: # Limit to top 5 resolutions
        filesize_mb = f"{(vf['filesize'] / 1024 / 1024):.2f} MB" if vf['filesize'] else 'N/A'
        button_text = f"📹 {vf['resolution']}p ({vf['ext']}) - {filesize_mb}"
        callback_data = f"video|{vf['format_id']}|{vf['ext']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Add Audio button
    keyboard.append([InlineKeyboardButton("🎵 Audio Only (best quality, mp3)", callback_data="audio|best|mp3")])
    
    # Add Subtitle buttons
    subtitles = info.get('subtitles', {})
    if subtitles:
        subtitle_buttons = []
        for lang_code, sub_info in list(subtitles.items())[:3]: # Limit to 3 subtitle languages
            lang_name = sub_info[0].get('name', lang_code)
            subtitle_buttons.append(
                InlineKeyboardButton(f"📜 {lang_name}", callback_data=f"subtitle|{lang_code}|srt")
            )
        if subtitle_buttons:
            keyboard.append(subtitle_buttons)

    return keyboard

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the callback_data from the inline keyboard."""
    query = update.callback_query
    await query.answer()

    data = query.data
    
    if data == "help":
        await help_command(update, context)
        return
        
    url = context.user_data.get('video_url')
    if not url:
        await query.edit_message_text("Sorry, I lost the context. Please send the link again.")
        return

    try:
        download_type, format_id, ext = data.split('|')
        
        status_message = await query.edit_message_text(f"📥 **Downloading...**\nPlease wait, this might take a while depending on the file size.")
        
        output_filename = await download_file(url, download_type, format_id, ext, context)
        
        if not output_filename or not os.path.exists(output_filename):
            raise FileNotFoundError("Downloaded file not found.")

        await status_message.edit_text("📤 **Uploading to Telegram...**")
        
        # Upload the file
        if download_type == 'video':
            await context.bot.send_video(chat_id=query.message.chat_id, video=open(output_filename, 'rb'), supports_streaming=True)
        elif download_type == 'audio':
            await context.bot.send_audio(chat_id=query.message.chat_id, audio=open(output_filename, 'rb'))
        elif download_type == 'subtitle':
            await context.bot.send_document(chat_id=query.message.chat_id, document=open(output_filename, 'rb'))
        
        await status_message.delete()

    except Exception as e:
        logger.error(f"Error during download/upload: {e}")
        await query.edit_message_text(f"An error occurred: {e}")
    finally:
        # Clean up the downloaded file
        if 'output_filename' in locals() and os.path.exists(output_filename):
            os.remove(output_filename)


async def download_file(url: str, download_type: str, format_id: str, ext: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Downloads the file using yt-dlp based on user's choice."""
    # Sanitize title for filename
    title = context.user_data['video_info'].get('title', 'video')
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:50] # Limit length
    
    output_template = f'{safe_title}.%(ext)s'
    
    ydl_opts = {
        'outtmpl': output_template,
        'noplaylist': True,
    }

    if download_type == 'video':
        # THIS IS THE KEY: We specify the chosen video format ID and merge it with the best available audio
        ydl_opts['format'] = f'{format_id}+bestaudio/best'
        # To ensure the final container is mp4 if possible
        ydl_opts['merge_output_format'] = 'mp4'

    elif download_type == 'audio':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
        # The extension will be mp3 after post-processing
        output_template = f'{safe_title}.mp3'
        ydl_opts['outtmpl'] = output_template


    elif download_type == 'subtitle':
        ydl_opts['writesubtitles'] = True
        ydl_opts['subtitleslangs'] = [format_id] # format_id is the lang_code here
        ydl_opts['skip_download'] = True
        # The filename will be title.lang.ext
        output_template = f'{safe_title}.{format_id}.{ext}'
        ydl_opts['outtmpl'] = f'{safe_title}.%(ext)s'


    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # Determine the final output filename
    if download_type == 'audio':
        return f'{safe_title}.mp3'
    elif download_type == 'subtitle':
        # yt-dlp might create a vtt or srt, we check for it
        for file in os.listdir('.'):
            if file.startswith(safe_title) and file.endswith(f'.{format_id}.{ext}'):
                return file
        return f'{safe_title}.{format_id}.{ext}' # Fallback
    else: # Video
        return f'{safe_title}.mp4'


# --- Main Bot Execution ---

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
