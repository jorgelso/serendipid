import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.model_router import get_router
router = get_router()
try:
    router._api_keys['GROQ_API_KEY'] = None
    router._api_keys['GEMINI_API_KEY'] = None
    print('Testing OpenRouter...')
    response = router.generate_text('Say exactly: OpenRouter is working!')
    print('Response:', response)
except Exception as e:
    print('Error:', e)
