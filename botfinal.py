# youtube_downloader_bot.py

import logging
import os
from pytube import YouTube
from moviepy.editor import VideoFileClip, AudioFileClip
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from uuid import uuid4

# --- Configuration ---
# Replace 'YOUR_TELEGRAM_BOT_TOKEN' with the token you get from BotFather
TELEGRAM_BOT_TOKEN = '8264683279:AAGoejkdiRl2kWe2NPu5bdQPE1hI5UvD9-4' 
DOWNLOAD_PATH = 'downloads'

# --- Setup Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def get_video_streams(yt: YouTube):
    """
    Fetches and organizes video and audio streams to solve the 360p-only issue.
    pytube often lists progressive streams (video+audio) only up to 360p or 720p.
    To get higher resolutions, we must get adaptive streams (video-only) and 
    merge them with an audio stream.
    """
    streams_dict = {}
    
    # Get adaptive streams (separate video and audio) for high quality
    video_streams = yt.streams.filter(adaptive=True, file_extension='mp4').order_by('resolution').desc()
    audio_stream = yt.streams.filter(only_audio=True, file_extension='mp4').order_by('abr').desc().first()

    for stream in video_streams:
        # Ignore streams without resolution (e.g., audio only)
        if stream.resolution:
            # Calculate file size in MB
            filesize = stream.filesize / (1024 * 1024)
            if filesize > 0 and stream.resolution not in streams_dict:
                 streams_dict[stream.resolution] = {
                    'video_itag': stream.itag,
                    'filesize_mb': filesize,
                    'audio_itag': audio_stream.itag if audio_stream else None
                }

    # Add audio-only option
    if audio_stream:
        audio_filesize = audio_stream.filesize / (1024 * 1024)
        streams_dict['audio_only'] = {
            'video_itag': None,
            'filesize_mb': audio_filesize,
            'audio_itag': audio_stream.itag
        }
        
    return streams_dict

def cleanup_files(files: list):
    """Deletes temporary files from the server."""
    for file_path in files:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up file: {file_path}")
            except OSError as e:
                logger.error(f"Error deleting file {file_path}: {e}")

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    await update.message.reply_html(
        "👋 <b>Welcome to the YouTube Downloader Bot!</b>\n\n"
        "Send me a YouTube video link and I'll give you options to download it as a video or audio file."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles messages containing YouTube links."""
    url = update.message.text
    if "youtube.com/" in url or "youtu.be/" in url:
        status_message = await update.message.reply_text("🔗 Got your link! Fetching video details...")
        
        try:
            yt = YouTube(url)
            streams = get_video_streams(yt)
            
            if not streams:
                await status_message.edit_text("❌ Sorry, I couldn't find any downloadable streams for this video.")
                return

            keyboard = []
            for res, data in streams.items():
                if res == 'audio_only':
                    label = f"🎵 Audio Only ({data['filesize_mb']:.2f} MB)"
                    callback_data = f"download_audio|{yt.video_id}|{data['audio_itag']}"
                else:
                    label = f"🎬 {res} ({data['filesize_mb']:.2f} MB)"
                    callback_data = f"download_video|{yt.video_id}|{data['video_itag']}|{data['audio_itag']}"
                
                keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await status_message.edit_text(
                f"✅ Found it! <b>{yt.title}</b>\n\n"
                "Please select a resolution to download:",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Error processing URL {url}: {e}")
            await status_message.edit_text("❌ An error occurred. Please check if the link is correct and public.")
    else:
        await update.message.reply_text("Please send me a valid YouTube link.")

# --- Callback Query Handler ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles button presses for downloads."""
    query = update.callback_query
    await query.answer() # Acknowledge the button press
    
    data = query.data.split('|')
    action = data[0]
    video_id = data[1]
    
    yt_url = f"https://www.youtube.com/watch?v={video_id}"
    yt = YouTube(yt_url)
    
    # Generate unique filenames to avoid conflicts
    unique_id = str(uuid4())
    
    video_path = None
    audio_path = None
    output_path = None

    await query.edit_message_text(text="⏳ Starting download...")

    try:
        if action == "download_video":
            video_itag = int(data[2])
            audio_itag = int(data[3])
            
            video_stream = yt.streams.get_by_itag(video_itag)
            audio_stream = yt.streams.get_by_itag(audio_itag)

            # Download video and audio streams
            await query.edit_message_text(text=f"📥 Downloading video ({video_stream.resolution})...")
            video_path = video_stream.download(output_path=DOWNLOAD_PATH, filename_prefix=f"{unique_id}_video_")
            
            await query.edit_message_text(text="📥 Downloading audio...")
            audio_path = audio_stream.download(output_path=DOWNLOAD_PATH, filename_prefix=f"{unique_id}_audio_")

            # Merge files
            await query.edit_message_text(text="🔄 Merging video and audio...")
            output_path = os.path.join(DOWNLOAD_PATH, f"{unique_id}_final.mp4")
            
            video_clip = VideoFileClip(video_path)
            audio_clip = AudioFileClip(audio_path)
            
            final_clip = video_clip.set_audio(audio_clip)
            final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
            
            final_clip.close()
            video_clip.close()
            audio_clip.close()

        elif action == "download_audio":
            audio_itag = int(data[2])
            audio_stream = yt.streams.get_by_itag(audio_itag)
            
            await query.edit_message_text(text="📥 Downloading audio...")
            output_path = audio_stream.download(output_path=DOWNLOAD_PATH, filename_prefix=f"{unique_id}_audio_")
            
        # Upload to Telegram
        if output_path and os.path.exists(output_path):
            file_size = os.path.getsize(output_path) / (1024 * 1024)
            
            if file_size > 50: # Telegram bot API limit is 50 MB
                await query.edit_message_text(text=f"⚠️ File is too large ({file_size:.2f} MB). Telegram bots can only upload files up to 50 MB.")
                return

            await query.edit_message_text(text=f"📤 Uploading to Telegram...")
            
            if action == "download_video":
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=open(output_path, 'rb'),
                    caption=yt.title,
                    supports_streaming=True
                )
            elif action == "download_audio":
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=open(output_path, 'rb'),
                    title=yt.title,
                    performer=yt.author
                )
            
            # Delete the status message
            await query.message.delete()
        else:
            await query.edit_message_text(text="❌ Failed to create the final file.")

    except Exception as e:
        logger.error(f"Error during download/upload for video_id {video_id}: {e}")
        await query.edit_message_text(text=f"❌ An unexpected error occurred: {e}")
        
    finally:
        # Clean up all temporary files
        cleanup_files([video_path, audio_path, output_path])


# --- Main Bot Logic ---
def main() -> None:
    """Start the bot."""
    # Create a directory for downloads if it doesn't exist
    if not os.path.exists(DOWNLOAD_PATH):
        os.makedirs(DOWNLOAD_PATH)

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Run the bot until the user presses Ctrl-C
    logger.info("Bot is running...")
    application.run_polling()


if __name__ == '__main__':
    main()
