# Create comprehensive README
readme_content = '''# YouTube Downloader Telegram Bot

A powerful Telegram bot that allows you to download YouTube videos in multiple qualities, extract audio, download subtitles in various languages, and get video thumbnails.

## 🌟 Features

- **Multiple Video Qualities**: Download videos in various resolutions (360p to 4K+)
- **Audio Extraction**: Extract audio-only files in different bitrates
- **Subtitle Support**: Download subtitles in multiple languages (manual and auto-generated)
- **Thumbnail Download**: Get video thumbnails
- **Large File Handling**: Automatically uploads large files to temporary hosting services
- **Smart Format Detection**: Uses yt-dlp for reliable format detection
- **User-Friendly Interface**: Intuitive inline keyboard navigation

## 📋 Requirements

- Python 3.8 or higher
- Telegram Bot Token (from @BotFather)
- Internet connection

## 🚀 Quick Setup

### Option 1: Automatic Setup (Recommended)
```bash
chmod +x setup.sh
./setup.sh
```

### Option 2: Manual Setup
1. Create virtual environment:
```bash
python3 -m venv youtube_bot_env
source youtube_bot_env/bin/activate  # On Windows: youtube_bot_env\\Scripts\\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## 🔧 Configuration

1. **Get Bot Token**: 
   - Message @BotFather on Telegram
   - Create a new bot with `/newbot`
   - Copy your bot token

2. **Update Token**: 
   - Open `youtube_bot.py`
   - Replace the BOT_TOKEN variable with your token:
   ```python
   BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
   ```

## 🏃‍♂️ Running the Bot

```bash
# Activate virtual environment (if not already active)
source youtube_bot_env/bin/activate

# Run the bot
python youtube_bot.py
```

## 💡 Usage

1. Start a conversation with your bot
2. Send `/start` to see welcome message
3. Send any YouTube URL
4. Choose from available options:
   - 🎥 **Video Quality**: Multiple resolution options
   - 🎵 **Audio Only**: Different bitrate options  
   - 📝 **Subtitles**: Available languages
   - 🖼️ **Thumbnail**: Video thumbnail image

## 🎯 Supported Formats

### Video Formats
- MP4, WebM, MKV
- Resolutions: 144p to 4K+ (when available)
- Various codecs: H.264, VP9, AV1

### Audio Formats  
- MP3, M4A, WebM
- Bitrates: 64kbps to 320kbps
- Audio codecs: AAC, Opus, Vorbis

### Subtitles
- Format: SRT (SubRip Text)
- Manual and auto-generated captions
- Multiple languages supported

## 🔒 Security Notes

- **Never share your bot token publicly**
- The token in the code is for demonstration only
- Consider using environment variables for production:
```python
import os
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
```

## 📁 File Size Limits

- **Telegram Limit**: 50MB for bot uploads
- **Large Files**: Automatically uploaded to temporary hosting
- **Hosting Services Used**: file.io (7-day retention) and 0x0.st

## 🛠️ Troubleshooting

### Common Issues:

1. **"No formats found"**
   - Video might be private or region-restricted
   - Try a different YouTube URL

2. **Download fails**
   - Check internet connection
   - Video might be very new (processing)
   - Try again after a few minutes

3. **Bot doesn't respond**
   - Check bot token is correct
   - Ensure bot is running
   - Check logs for errors

### Dependencies Issues:
```bash
# Update yt-dlp for latest YouTube support
pip install --upgrade yt-dlp

# If ffmpeg is required for some formats:
# Ubuntu/Debian: sudo apt install ffmpeg
# macOS: brew install ffmpeg
# Windows: Download from https://ffmpeg.org/
```

## 📊 Technical Details

- **Backend**: python-telegram-bot library
- **YouTube Processing**: yt-dlp (youtube-dl successor)
- **File Hosting**: file.io and 0x0.st APIs
- **Async Processing**: Full async/await support
- **Memory Management**: Temporary file cleanup

## 🤝 Contributing

Feel free to submit issues and enhancement requests!

## ⚖️ Legal Notice

- Respect YouTube's Terms of Service
- Only download content you have permission to download
- This bot is for educational and personal use only
- Users are responsible for their usage compliance

## 📝 License

This project is open source. Use responsibly and at your own risk.

## 🆘 Support

If you encounter issues:
1. Check the troubleshooting section
2. Review bot logs for specific errors
3. Ensure all dependencies are properly installed
4. Try with different YouTube videos to isolate the issue

---

**Happy downloading! 🎉**
'''

with open('README.md', 'w', encoding='utf-8') as f:
    f.write(readme_content)

print("✅ README file created: README.md")