
import os
import asyncio
import logging
import tempfile
import shutil
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import yt_dlp
import requests
import json
from urllib.parse import urlparse, parse_qs

# Load environment variables
load_dotenv()

# Configure logging
log_level = logging.DEBUG if os.getenv('DEBUG_MODE', 'false').lower() == 'true' else logging.INFO
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=log_level
)
logger = logging.getLogger(__name__)

# Bot configuration from environment
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

TELEGRAM_FILE_SIZE_LIMIT = int(os.getenv('MAX_FILE_SIZE_BYTES', 50 * 1024 * 1024))
CUSTOM_TEMP_DIR = os.getenv('TEMP_DIR')

class YouTubeDownloader:
    def __init__(self):
        if CUSTOM_TEMP_DIR and os.path.exists(os.path.dirname(CUSTOM_TEMP_DIR)):
            os.makedirs(CUSTOM_TEMP_DIR, exist_ok=True)
            self.temp_dir = CUSTOM_TEMP_DIR
        else:
            self.temp_dir = tempfile.mkdtemp()
        logger.info(f"Using temp directory: {self.temp_dir}")

    def extract_video_info(self, url):
        """Extract video information and available formats"""
        ydl_opts = {
            'quiet': not (log_level == logging.DEBUG),
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

        # Get video formats with better filtering
        for fmt in info['formats']:
            if (fmt.get('vcodec') != 'none' and 
                fmt.get('height') and 
                fmt.get('ext') in ['mp4', 'webm', 'mkv']):

                format_info = {
                    'format_id': fmt['format_id'],
                    'ext': fmt.get('ext', 'mp4'),
                    'height': fmt.get('height'),
                    'filesize': fmt.get('filesize') or fmt.get('filesize_approx', 0),
                    'fps': fmt.get('fps', 30),
                    'vcodec': fmt.get('vcodec', 'unknown'),
                    'acodec': fmt.get('acodec', 'none'),
                    'tbr': fmt.get('tbr', 0)  # Total bitrate
                }
                video_formats.append(format_info)

        # Get audio-only formats
        for fmt in info['formats']:
            if (fmt.get('acodec') != 'none' and 
                fmt.get('vcodec') == 'none' and
                fmt.get('ext') in ['mp3', 'm4a', 'webm', 'opus']):

                format_info = {
                    'format_id': fmt['format_id'],
                    'ext': fmt.get('ext', 'mp3'),
                    'abr': fmt.get('abr', 128),
                    'acodec': fmt.get('acodec', 'unknown'),
                    'filesize': fmt.get('filesize') or fmt.get('filesize_approx', 0)
                }
                audio_formats.append(format_info)

        # Sort and deduplicate video formats
        video_formats.sort(key=lambda x: (x['height'], x.get('tbr', 0)), reverse=True)
        seen_heights = set()
        unique_video_formats = []
        for fmt in video_formats:
            height_key = f"{fmt['height']}_{fmt['ext']}"
            if height_key not in seen_heights:
                seen_heights.add(height_key)
                unique_video_formats.append(fmt)

        # Sort audio formats by bitrate
        audio_formats.sort(key=lambda x: x['abr'], reverse=True)
        # Remove duplicates
        seen_abr = set()
        unique_audio_formats = []
        for fmt in audio_formats:
            abr_key = f"{fmt['abr']}_{fmt['ext']}"
            if abr_key not in seen_abr:
                seen_abr.add(abr_key)
                unique_audio_formats.append(fmt)

        return {
            'video': unique_video_formats[:8],  # Top 8 video qualities
            'audio': unique_audio_formats[:4],  # Top 4 audio qualities
            'title': info.get('title', 'Unknown'),
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail'),
            'subtitles': info.get('subtitles', {}),
            'automatic_captions': info.get('automatic_captions', {}),
            'uploader': info.get('uploader', 'Unknown'),
            'view_count': info.get('view_count', 0)
        }

    def download_media(self, url, format_id, output_path, media_type='video'):
        """Download media with specified format"""
        if media_type == 'audio':
            ydl_opts = {
                'format': format_id,
                'outtmpl': output_path,
                'quiet': not (log_level == logging.DEBUG),
                'no_warnings': True,
                'extractaudio': True,
                'audioformat': 'mp3',
                'audioquality': '192',
            }
        elif media_type == 'subtitle':
            ydl_opts = {
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': [format_id],
                'subtitlesformat': 'srt',
                'skip_download': True,
                'outtmpl': output_path,
                'quiet': not (log_level == logging.DEBUG),
            }
        elif media_type == 'thumbnail':
            ydl_opts = {
                'writethumbnail': True,
                'skip_download': True,
                'outtmpl': output_path,
                'quiet': not (log_level == logging.DEBUG),
            }
        else:  # video
            ydl_opts = {
                'format': format_id,
                'outtmpl': output_path,
                'quiet': not (log_level == logging.DEBUG),
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
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            logger.info(f"Uploading {file_size_mb:.1f}MB file to temp hosting")

            # Try file.io first (7-day retention)
            try:
                with open(file_path, 'rb') as f:
                    response = requests.post(
                        'https://file.io/', 
                        files={'file': f},
                        timeout=300  # 5 minute timeout for large files
                    )

                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        logger.info("Successfully uploaded to file.io")
                        return data.get('link')
            except Exception as e:
                logger.error(f"file.io upload failed: {e}")

            # Fallback to 0x0.st
            try:
                with open(file_path, 'rb') as f:
                    response = requests.post(
                        'https://0x0.st', 
                        files={'file': f},
                        timeout=300
                    )

                if response.status_code == 200:
                    logger.info("Successfully uploaded to 0x0.st")
                    return response.text.strip()
            except Exception as e:
                logger.error(f"0x0.st upload failed: {e}")

        except Exception as e:
            logger.error(f"Upload to temp host failed: {e}")

        return None

    def cleanup(self):
        """Clean up temporary directory"""
        try:
            if os.path.exists(self.temp_dir) and self.temp_dir != CUSTOM_TEMP_DIR:
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

downloader = YouTubeDownloader()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_text = """
🎥 **YouTube Downloader Bot**

Send me a YouTube URL and I'll help you download:
• 📹 Video in multiple qualities (up to 4K)
• 🎵 Audio in different bitrates  
• 📝 Subtitles in various languages
• 🖼️ Video thumbnails

**Features:**
• Smart quality detection
• Multiple format support
• Large file handling via temp hosting
• Subtitle support (manual + auto-generated)

Just paste any YouTube link to get started!

⚠️ **Note**: Large files will be uploaded to temporary hosting services due to Telegram limits.

Type /help for more information.
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = """
🆘 **Help & Instructions**

**How to use:**
1. Send any YouTube URL to the bot
2. Choose from the available options:
   • 🎥 Video Quality - Download video in various resolutions
   • 🎵 Audio Only - Extract audio in different bitrates
   • 📝 Subtitles - Download captions in multiple languages  
   • 🖼️ Thumbnail - Get the video thumbnail image

**Supported formats:**
• Video: MP4, WebM, MKV (144p to 4K+)
• Audio: MP3, M4A, WebM (64kbps to 320kbps)
• Subtitles: SRT format, multiple languages
• Images: JPG, PNG thumbnails

**File size limits:**
• Direct upload: Up to 50MB
• Large files: Uploaded to temporary hosting (7-day retention)

**Tips:**
• For best quality, choose MP4 format when available
• Audio-only files are smaller than video files
• Some videos may not have all quality options available

**Commands:**
• /start - Show welcome message
• /help - Show this help text

**Issues?** Try with a different YouTube URL or contact support.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

# [Rest of the functions remain the same as in the original bot...]
# [Including all the handler functions, keyboards, and main function]

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
    finally:
        downloader.cleanup()
