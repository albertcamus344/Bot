
import os
import asyncio
import logging
import tempfile
import shutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import yt_dlp
import requests
import json
from urllib.parse import urlparse, parse_qs

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "8264683279:AAGoejkdiRl2kWe2NPu5bdQPE1hI5UvD9-4"
TELEGRAM_FILE_SIZE_LIMIT = 50 * 1024 * 1024  # 50MB limit for bots

class YouTubeDownloader:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()

    def extract_video_info(self, url):
        """Extract video information and available formats"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        except Exception as e:
            logger.error(f"Error extracting video info: {e}")
            return None

    def get_available_formats(self, info):
        """Parse available video formats and return organized data"""
        if not info or 'formats' not in info:
            return None

        video_formats = []
        audio_formats = []

        # Get video formats
        for fmt in info['formats']:
            if fmt.get('vcodec') != 'none' and fmt.get('height'):
                format_info = {
                    'format_id': fmt['format_id'],
                    'ext': fmt.get('ext', 'mp4'),
                    'height': fmt.get('height'),
                    'filesize': fmt.get('filesize', 0),
                    'fps': fmt.get('fps', 30),
                    'vcodec': fmt.get('vcodec', 'unknown'),
                    'acodec': fmt.get('acodec', 'none')
                }
                video_formats.append(format_info)

        # Get audio-only formats
        for fmt in info['formats']:
            if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                format_info = {
                    'format_id': fmt['format_id'],
                    'ext': fmt.get('ext', 'mp3'),
                    'abr': fmt.get('abr', 128),
                    'acodec': fmt.get('acodec', 'unknown'),
                    'filesize': fmt.get('filesize', 0)
                }
                audio_formats.append(format_info)

        # Sort video formats by height (quality)
        video_formats.sort(key=lambda x: x['height'], reverse=True)
        # Remove duplicates based on height
        seen_heights = set()
        unique_video_formats = []
        for fmt in video_formats:
            if fmt['height'] not in seen_heights:
                seen_heights.add(fmt['height'])
                unique_video_formats.append(fmt)

        # Sort audio formats by bitrate
        audio_formats.sort(key=lambda x: x['abr'], reverse=True)

        return {
            'video': unique_video_formats[:6],  # Limit to top 6 qualities
            'audio': audio_formats[:3],  # Limit to top 3 audio qualities
            'title': info.get('title', 'Unknown'),
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail'),
            'subtitles': info.get('subtitles', {}),
            'automatic_captions': info.get('automatic_captions', {})
        }

    def download_media(self, url, format_id, output_path, media_type='video'):
        """Download media with specified format"""
        if media_type == 'audio':
            ydl_opts = {
                'format': format_id,
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'extractaudio': True,
                'audioformat': 'mp3',
                'audioquality': '192',
            }
        elif media_type == 'subtitle':
            ydl_opts = {
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': [format_id],  # format_id here is language code
                'subtitlesformat': 'srt',
                'skip_download': True,
                'outtmpl': output_path,
                'quiet': True,
            }
        elif media_type == 'thumbnail':
            ydl_opts = {
                'writethumbnail': True,
                'skip_download': True,
                'outtmpl': output_path,
                'quiet': True,
            }
        else:  # video
            ydl_opts = {
                'format': format_id,
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
            }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return True
        except Exception as e:
            logger.error(f"Download error: {e}")
            return False

    def upload_to_temp_host(self, file_path):
        """Upload large files to temporary hosting service"""
        try:
            # Using file.io as temporary hosting (7-day retention)
            with open(file_path, 'rb') as f:
                response = requests.post('https://file.io/', files={'file': f})

            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data.get('link')

            # Fallback to 0x0.st (simpler service)
            with open(file_path, 'rb') as f:
                response = requests.post('https://0x0.st', files={'file': f})

            if response.status_code == 200:
                return response.text.strip()

        except Exception as e:
            logger.error(f"Upload to temp host failed: {e}")

        return None

downloader = YouTubeDownloader()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_text = """
🎥 **YouTube Downloader Bot**

Send me a YouTube URL and I'll help you download:
• Video in multiple qualities (up to 4K)
• Audio in different bitrates  
• Subtitles in various languages
• Video thumbnails

Just paste any YouTube link to get started!

⚠️ **Note**: Large files will be uploaded to temporary hosting services due to Telegram limits.
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def handle_youtube_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle YouTube URL and show download options"""
    url = update.message.text.strip()

    # Validate YouTube URL
    if 'youtube.com' not in url and 'youtu.be' not in url:
        await update.message.reply_text("❌ Please send a valid YouTube URL.")
        return

    # Show processing message
    processing_msg = await update.message.reply_text("🔍 Analyzing video... Please wait.")

    # Extract video info
    info = downloader.extract_video_info(url)
    if not info:
        await processing_msg.edit_text("❌ Failed to extract video information. Please check the URL.")
        return

    formats_data = downloader.get_available_formats(info)
    if not formats_data:
        await processing_msg.edit_text("❌ No downloadable formats found.")
        return

    # Store video info in context
    context.user_data['video_info'] = info
    context.user_data['formats_data'] = formats_data
    context.user_data['video_url'] = url

    # Create inline keyboard for options
    keyboard = create_main_menu_keyboard(formats_data)

    title = formats_data['title'][:50] + "..." if len(formats_data['title']) > 50 else formats_data['title']
    duration = f"{formats_data['duration']//60}:{formats_data['duration']%60:02d}" if formats_data['duration'] else "Unknown"

    info_text = f"""
📹 **{title}**
⏱️ Duration: {duration}

Choose what to download:
    """

    await processing_msg.edit_text(info_text, reply_markup=keyboard, parse_mode='Markdown')

def create_main_menu_keyboard(formats_data):
    """Create main menu inline keyboard"""
    keyboard = []

    # Video options
    if formats_data['video']:
        keyboard.append([InlineKeyboardButton("🎥 Video Quality", callback_data="show_video")])

    # Audio options
    if formats_data['audio']:
        keyboard.append([InlineKeyboardButton("🎵 Audio Only", callback_data="show_audio")])

    # Subtitles
    subtitles_available = formats_data['subtitles'] or formats_data['automatic_captions']
    if subtitles_available:
        keyboard.append([InlineKeyboardButton("📝 Subtitles", callback_data="show_subtitles")])

    # Thumbnail
    if formats_data['thumbnail']:
        keyboard.append([InlineKeyboardButton("🖼️ Thumbnail", callback_data="download_thumbnail")])

    return InlineKeyboardMarkup(keyboard)

def create_video_keyboard(video_formats):
    """Create video quality selection keyboard"""
    keyboard = []

    for fmt in video_formats:
        size_mb = fmt['filesize'] / (1024*1024) if fmt['filesize'] else 0
        size_text = f" ({size_mb:.1f}MB)" if size_mb > 0 else ""

        quality_text = f"{fmt['height']}p"
        if fmt['fps'] and fmt['fps'] > 30:
            quality_text += f" {fmt['fps']}fps"

        button_text = f"{quality_text}{size_text}"
        callback_data = f"download_video_{fmt['format_id']}"

        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def create_audio_keyboard(audio_formats):
    """Create audio quality selection keyboard"""
    keyboard = []

    for fmt in audio_formats:
        size_mb = fmt['filesize'] / (1024*1024) if fmt['filesize'] else 0
        size_text = f" ({size_mb:.1f}MB)" if size_mb > 0 else ""

        button_text = f"{fmt['abr']}kbps {fmt['ext']}{size_text}"
        callback_data = f"download_audio_{fmt['format_id']}"

        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def create_subtitles_keyboard(subtitles, auto_captions):
    """Create subtitles language selection keyboard"""
    keyboard = []
    languages = set()

    # Add manual subtitles
    for lang in subtitles.keys():
        languages.add(lang)

    # Add automatic captions
    for lang in auto_captions.keys():
        languages.add(lang)

    # Common languages first
    priority_langs = ['en', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'zh', 'ja', 'ko']
    sorted_languages = []

    for lang in priority_langs:
        if lang in languages:
            sorted_languages.append(lang)
            languages.remove(lang)

    sorted_languages.extend(sorted(languages))

    for lang in sorted_languages[:15]:  # Limit to 15 languages
        lang_name = get_language_name(lang)
        callback_data = f"download_subtitle_{lang}"
        keyboard.append([InlineKeyboardButton(f"{lang_name} ({lang})", callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def get_language_name(lang_code):
    """Get readable language name from code"""
    lang_map = {
        'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
        'it': 'Italian', 'pt': 'Portuguese', 'ru': 'Russian', 'zh': 'Chinese',
        'ja': 'Japanese', 'ko': 'Korean', 'ar': 'Arabic', 'hi': 'Hindi',
        'tr': 'Turkish', 'pl': 'Polish', 'nl': 'Dutch'
    }
    return lang_map.get(lang_code, lang_code.upper())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks"""
    query = update.callback_query
    await query.answer()

    data = query.data
    formats_data = context.user_data.get('formats_data')

    if not formats_data:
        await query.edit_message_text("❌ Session expired. Please send the YouTube URL again.")
        return

    if data == "show_video":
        keyboard = create_video_keyboard(formats_data['video'])
        await query.edit_message_text("🎥 **Select Video Quality:**", reply_markup=keyboard, parse_mode='Markdown')

    elif data == "show_audio":
        keyboard = create_audio_keyboard(formats_data['audio'])
        await query.edit_message_text("🎵 **Select Audio Quality:**", reply_markup=keyboard, parse_mode='Markdown')

    elif data == "show_subtitles":
        subtitles = formats_data['subtitles']
        auto_captions = formats_data['automatic_captions']
        keyboard = create_subtitles_keyboard(subtitles, auto_captions)
        await query.edit_message_text("📝 **Select Subtitle Language:**", reply_markup=keyboard, parse_mode='Markdown')

    elif data == "back_to_main":
        keyboard = create_main_menu_keyboard(formats_data)
        title = formats_data['title'][:50] + "..." if len(formats_data['title']) > 50 else formats_data['title']
        duration = f"{formats_data['duration']//60}:{formats_data['duration']%60:02d}" if formats_data['duration'] else "Unknown"

        info_text = f"""
📹 **{title}**
⏱️ Duration: {duration}

Choose what to download:
        """
        await query.edit_message_text(info_text, reply_markup=keyboard, parse_mode='Markdown')

    elif data.startswith("download_"):
        await handle_download(query, context)

async def handle_download(query, context):
    """Handle actual download requests"""
    data = query.data
    formats_data = context.user_data.get('formats_data')
    video_url = context.user_data.get('video_url')

    if not formats_data or not video_url:
        await query.edit_message_text("❌ Session expired. Please send the YouTube URL again.")
        return

    # Show downloading message
    await query.edit_message_text("⬇️ **Downloading...** Please wait, this may take a few minutes.")

    try:
        if data == "download_thumbnail":
            await download_thumbnail(query, context, video_url, formats_data)
        elif data.startswith("download_video_"):
            format_id = data.replace("download_video_", "")
            await download_video(query, context, video_url, format_id, formats_data)
        elif data.startswith("download_audio_"):
            format_id = data.replace("download_audio_", "")
            await download_audio(query, context, video_url, format_id, formats_data)
        elif data.startswith("download_subtitle_"):
            lang_code = data.replace("download_subtitle_", "")
            await download_subtitle(query, context, video_url, lang_code, formats_data)

    except Exception as e:
        logger.error(f"Download error: {e}")
        await query.edit_message_text("❌ Download failed. Please try again or choose a different format.")

async def download_thumbnail(query, context, video_url, formats_data):
    """Download and send thumbnail"""
    try:
        thumbnail_url = formats_data['thumbnail']
        if thumbnail_url:
            # Download thumbnail directly from URL
            response = requests.get(thumbnail_url)
            if response.status_code == 200:
                await context.bot.send_photo(
                    chat_id=query.message.chat.id,
                    photo=response.content,
                    caption=f"🖼️ Thumbnail: {formats_data['title']}"
                )
                await query.edit_message_text("✅ Thumbnail sent successfully!")
            else:
                await query.edit_message_text("❌ Failed to download thumbnail.")
        else:
            await query.edit_message_text("❌ No thumbnail available.")
    except Exception as e:
        logger.error(f"Thumbnail download error: {e}")
        await query.edit_message_text("❌ Failed to send thumbnail.")

async def download_video(query, context, video_url, format_id, formats_data):
    """Download and send video"""
    try:
        # Create temporary file path
        safe_title = "".join(c for c in formats_data['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
        output_path = os.path.join(downloader.temp_dir, f"{safe_title}_%(format_id)s.%(ext)s")

        # Download video
        success = downloader.download_media(video_url, format_id, output_path, 'video')

        if success:
            # Find the downloaded file
            files = [f for f in os.listdir(downloader.temp_dir) if f.startswith(safe_title)]
            if files:
                file_path = os.path.join(downloader.temp_dir, files[0])
                file_size = os.path.getsize(file_path)

                if file_size > TELEGRAM_FILE_SIZE_LIMIT:
                    # Upload to temporary hosting
                    await query.edit_message_text("📤 File too large for Telegram. Uploading to temporary hosting...")

                    temp_url = downloader.upload_to_temp_host(file_path)
                    if temp_url:
                        await query.edit_message_text(
                            f"✅ **Video ready for download!**\n\n"
                            f"📹 {formats_data['title']}\n"
                            f"💾 Size: {file_size/(1024*1024):.1f} MB\n"
                            f"🔗 [Download Link]({temp_url})\n\n"
                            f"⚠️ Link expires in 7 days",
                            parse_mode='Markdown'
                        )
                    else:
                        await query.edit_message_text("❌ Failed to upload to hosting service.")
                else:
                    # Send via Telegram
                    with open(file_path, 'rb') as video_file:
                        await context.bot.send_video(
                            chat_id=query.message.chat.id,
                            video=video_file,
                            caption=f"🎥 {formats_data['title']}"
                        )
                    await query.edit_message_text("✅ Video sent successfully!")

                # Cleanup
                os.remove(file_path)
            else:
                await query.edit_message_text("❌ Downloaded file not found.")
        else:
            await query.edit_message_text("❌ Video download failed.")

    except Exception as e:
        logger.error(f"Video download error: {e}")
        await query.edit_message_text("❌ Video download failed.")

async def download_audio(query, context, video_url, format_id, formats_data):
    """Download and send audio"""
    try:
        safe_title = "".join(c for c in formats_data['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
        output_path = os.path.join(downloader.temp_dir, f"{safe_title}_audio.%(ext)s")

        success = downloader.download_media(video_url, format_id, output_path, 'audio')

        if success:
            files = [f for f in os.listdir(downloader.temp_dir) if f.startswith(f"{safe_title}_audio")]
            if files:
                file_path = os.path.join(downloader.temp_dir, files[0])
                file_size = os.path.getsize(file_path)

                if file_size > TELEGRAM_FILE_SIZE_LIMIT:
                    await query.edit_message_text("📤 Audio file too large. Uploading to temporary hosting...")

                    temp_url = downloader.upload_to_temp_host(file_path)
                    if temp_url:
                        await query.edit_message_text(
                            f"✅ **Audio ready for download!**\n\n"
                            f"🎵 {formats_data['title']}\n"
                            f"💾 Size: {file_size/(1024*1024):.1f} MB\n"
                            f"🔗 [Download Link]({temp_url})\n\n"
                            f"⚠️ Link expires in 7 days",
                            parse_mode='Markdown'
                        )
                    else:
                        await query.edit_message_text("❌ Failed to upload to hosting service.")
                else:
                    with open(file_path, 'rb') as audio_file:
                        await context.bot.send_audio(
                            chat_id=query.message.chat.id,
                            audio=audio_file,
                            caption=f"🎵 {formats_data['title']}"
                        )
                    await query.edit_message_text("✅ Audio sent successfully!")

                os.remove(file_path)
            else:
                await query.edit_message_text("❌ Downloaded audio file not found.")
        else:
            await query.edit_message_text("❌ Audio download failed.")

    except Exception as e:
        logger.error(f"Audio download error: {e}")
        await query.edit_message_text("❌ Audio download failed.")

async def download_subtitle(query, context, video_url, lang_code, formats_data):
    """Download and send subtitles"""
    try:
        safe_title = "".join(c for c in formats_data['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
        output_path = os.path.join(downloader.temp_dir, f"{safe_title}.%(ext)s")

        success = downloader.download_media(video_url, lang_code, output_path, 'subtitle')

        if success:
            # Look for subtitle files
            subtitle_files = [f for f in os.listdir(downloader.temp_dir) 
                            if f.startswith(safe_title) and f.endswith('.srt')]

            if subtitle_files:
                file_path = os.path.join(downloader.temp_dir, subtitle_files[0])

                with open(file_path, 'rb') as subtitle_file:
                    await context.bot.send_document(
                        chat_id=query.message.chat.id,
                        document=subtitle_file,
                        filename=f"{safe_title}_{lang_code}.srt",
                        caption=f"📝 Subtitles ({get_language_name(lang_code)}): {formats_data['title']}"
                    )
                await query.edit_message_text("✅ Subtitles sent successfully!")

                os.remove(file_path)
            else:
                await query.edit_message_text(f"❌ No subtitles found for language: {get_language_name(lang_code)}")
        else:
            await query.edit_message_text("❌ Subtitle download failed.")

    except Exception as e:
        logger.error(f"Subtitle download error: {e}")
        await query.edit_message_text("❌ Subtitle download failed.")

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube_url))
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Start the bot
    print("🚀 YouTube Downloader Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
