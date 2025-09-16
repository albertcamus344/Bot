# Create requirements.txt with all necessary dependencies
requirements = '''
python-telegram-bot==20.5
yt-dlp==2023.9.24
requests==2.31.0
aiohttp==3.8.5
aiofiles==23.2.1
'''

with open('requirements.txt', 'w') as f:
    f.write(requirements.strip())

print("✅ Requirements file created: requirements.txt")