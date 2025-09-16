# Create setup script for easy installation
setup_script = '''#!/bin/bash

# YouTube Downloader Bot Setup Script

echo "🚀 Setting up YouTube Downloader Bot..."

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip3."
    exit 1
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv youtube_bot_env

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source youtube_bot_env/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

echo "✅ Setup complete!"
echo ""
echo "To run the bot:"
echo "1. source youtube_bot_env/bin/activate"
echo "2. python youtube_bot.py"
echo ""
echo "⚠️  Make sure to keep your bot token secure!"
'''

with open('setup.sh', 'w') as f:
    f.write(setup_script)

# Make setup script executable (on Unix systems)
import os
try:
    os.chmod('setup.sh', 0o755)
except:
    pass

print("✅ Setup script created: setup.sh")