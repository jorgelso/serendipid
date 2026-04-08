import instaloader
import logging

logging.basicConfig(level=logging.INFO)
sessionid = "49367419455%3AxScylb4HDGaCmD%3A13%3AAYiHyY8zbdE5_JHlwzFO1Wpm70kmtCJaNQ1WJg35uQ"

L = instaloader.Instaloader()
L.context._session.cookies.set("sessionid", sessionid, domain=".instagram.com")

try:
    print("Testing profile fetch...")
    profile = instaloader.Profile.from_username(L.context, 'zuck')
    print(f"Success! Found profile: {profile.full_name} ({profile.followers} followers)")
    
    print("Testing post download...")
    post = instaloader.Post.from_shortcode(L.context, 'DW13xFQkvMR')
    print(f"Success! Found post by: {post.owner_username}, Caption: {str(post.caption)[:30]}...")
    
    print("Session ID works perfectly.")
except Exception as e:
    print(f"Failed: {e}")
