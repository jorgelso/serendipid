import os
import uuid

# 1. Generate backend ID
backend_id_path = r'd:\superbrain\backend\config\backend_id.txt'
if not os.path.exists(backend_id_path):
    with open(backend_id_path, 'w', encoding='utf-8') as f:
        f.write(str(uuid.uuid4()))

# 2. Inject into api.py /queue-status
api_path = r'd:\superbrain\backend\api.py'
content = open(api_path, 'r', encoding='utf-8').read()

if 'backend_id.txt' not in content:
    content = content.replace(
        'return {',
        '''
    backend_id = "unknown"
    backend_id_path = get_config_path("backend_id.txt")
    if backend_id_path.exists():
        backend_id = backend_id_path.read_text().strip()
    
    return {
        "backendId": backend_id,
''',
        1)
    open(api_path, 'w', encoding='utf-8').write(content)

# 3. Model Router quota detection fix
router_path = r'd:\superbrain\backend\core\model_router.py'
import re
content = open(router_path, 'r', encoding='utf-8').read()
content = content.replace('raise Exception(f"Quota exhausted: {e}")', 'raise RateLimitError(str(e))')
content = content.replace('except Exception as e:', 'except Exception as e:\n            if "429" in str(e) or "quota" in str(e).lower():\n                raise RateLimitError("Quota limit hit")\n            raise e')
open(router_path, 'w', encoding='utf-8').write(content)

# 4. Update Github Action
github_path = r'd:\superbrain\.github\workflows\build-apk.yml'
if os.path.exists(github_path):
    content = open(github_path, 'r', encoding='utf-8').read()
    # Ensure NPM publishing is completely removed
    if 'npm publish' in content:
        content = re.sub(r'- name: Publish to NPM.*?npm publish', '', content, flags=re.DOTALL)
        open(github_path, 'w', encoding='utf-8').write(content)

