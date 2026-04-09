import re

with open(r'd:\superbrain\backend\main.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Fix 1: _parse_field for TAGS was reading 📸 and no variable existed for tags init correctly in old code, wait, let's look at what was there.
code = code.replace(
    'summary = _parse_field(summary_text, "📸", "TAGS")',
    'summary = _parse_field(summary_text, "📸", "SUMMARY")\n        raw_tags = _parse_field(summary_text, "🏷️", "TAGS")'
)

# Fix 2: inject music extraction
code = code.replace(
    '# Category: grab first word/phrase',
    '''music = _parse_field(summary_text, "🎵", "MUSIC")
        if not music:
            _mm = re.search(r'(?:^|\\n)\\s*\\*{0,2}MUSIC\\*{0,2}:?\\s*([^\\n]+)', summary_text, re.IGNORECASE)
            if _mm:
                music = _mm.group(1).strip()

        # Category: grab first word/phrase'''
)

with open(r'd:\superbrain\backend\main.py', 'w', encoding='utf-8') as f:
    f.write(code)
