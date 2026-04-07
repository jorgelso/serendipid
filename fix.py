import re
with open(r'd:\superbrain\backend\core\model_router.py', 'r', encoding='utf-8') as f:
    text = f.read()

bad_block = '''            except Exception as e:\\r\\n                if "429" in str(e) or "quota" in str(e).lower():\\r\\n                    raise RateLimitError("Quota limit hit")'''

bad_block2 = r'''            except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                raise RateLimitError("Quota limit hit")
            raise e'''

good_block = '''            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower():
                    raise RateLimitError("Quota limit hit")'''

text = text.replace(bad_block, good_block).replace(bad_block2, good_block)

# Just to be safe, replace any leftover literal backslash r backslash n
text = text.replace(r'\r\n', '\n')

with open(r'd:\superbrain\backend\core\model_router.py', 'w', encoding='utf-8') as f:
    f.write(text)
