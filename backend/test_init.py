import asyncio
import os
from instagram.instagram_downloader import download_instagram_content
from analyzers.music_identifier import identify_music

async def test():
    print('Downloading...')
    try:
        url = 'https://www.instagram.com/reel/DWGy0xKk0DV/?igsh=bDJ5ZHozOHh6dHFr'
        folder = download_instagram_content(url)
        print('Downloaded to:', folder)
        # Find the .mp3 file in the folder
        audio_path = None
        for root, dirs, files in os.walk(folder):
            for file in files:
                if file.endswith('.mp3'):
                    audio_path = os.path.join(root, file)
                    break
        print('Identifying music on:', audio_path)
        music_res = await identify_music(audio_path)
        print('Music Result:', music_res)
    except Exception as e:
        print('Error:', e)
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test())
