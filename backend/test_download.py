import instaloader
import os

sessionid = "49367419455%3AxScylb4HDGaCmD%3A13%3AAYiHyY8zbdE5_JHlwzFO1Wpm70kmtCJaNQ1WJg35uQ"

L = instaloader.Instaloader(
    dirname_pattern="test_download_{shortcode}",
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False,
    compress_json=False
)

# Inject session
L.context._session.cookies.set("sessionid", sessionid, domain=".instagram.com")

try:
    shortcode = 'DW13xFQkvMR' # Meta/Instagram demo reel
    print(f"Downloading post/reel {shortcode}...")
    post = instaloader.Post.from_shortcode(L.context, shortcode)
    L.download_post(post, target=f"test_download_{shortcode}")
    print(f"\nDownload completed!")
    
    download_dir = f"test_download_{shortcode}"
    if os.path.exists(download_dir):
        files = os.listdir(download_dir)
        print("Downloaded files:")
        for f in files:
            print(f" - {f}")
except Exception as e:
    print(f"Failed: {e}")
