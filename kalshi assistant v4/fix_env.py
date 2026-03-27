"""
fix_env.py — Rewrites the KALSHI_PRIVATE_KEY in .env with clean Unix line endings.
Run this once, then restart main.py.
"""
import re

with open(".env", "r", encoding="utf-8") as f:
    content = f.read()

# Find KALSHI_PRIVATE_KEY value (handles multi-line quoted keys)
pattern = re.compile(
    r'(KALSHI_PRIVATE_KEY\s*=\s*)(\".*?\"|\'.*?\'|[^\n]+)',
    re.DOTALL
)
match = pattern.search(content)
if not match:
    print("ERROR: KALSHI_PRIVATE_KEY not found in .env")
    exit(1)

raw_val = match.group(2).strip().strip('"').strip("'")
# Normalize: replace literal \n with real newlines, collapse carriage returns
raw_val = raw_val.replace('\\n', '\n').replace('\r\n', '\n').replace('\r', '\n')

# Validate it looks like a PEM key
if '-----BEGIN' not in raw_val:
    print("ERROR: Key does not contain a PEM header. Check your .env")
    exit(1)

# Check it includes the end marker
if '-----END' not in raw_val:
    print("ERROR: Key is truncated — missing END marker.")
    exit(1)

lines = [l for l in raw_val.split('\n') if l.strip()]
print(f"Key has {len(lines)} lines. Header: {lines[0]}")
print(f"Footer: {lines[-1]}")

# Rewrite key in a clean quoted block
clean_key = '\n'.join(lines)
replacement = f'KALSHI_PRIVATE_KEY="{clean_key}"'

new_content = pattern.sub(replacement, content)

with open(".env", "w", encoding="utf-8", newline='\n') as f:
    f.write(new_content)

print("\n.env rewritten cleanly. Verifying...")

# Verify it loads
from dotenv import load_dotenv
from cryptography.hazmat.primitives.serialization import load_pem_private_key
import os
load_dotenv(override=True)
pk_str = os.getenv("KALSHI_PRIVATE_KEY", "").replace('\\n', '\n')
try:
    load_pem_private_key(pk_str.encode(), password=None)
    print("Private key loads OK!")
except Exception as e:
    print(f"Private key FAILED to load: {e}")
