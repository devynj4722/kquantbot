import os

def fix_env():
    with open(".env", "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    out_lines = []
    in_key = False
    key_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("KALSHI_API_KEY="):
            out_lines.append(line)
        elif stripped.startswith("KALSHI_PRIVATE_KEY"):
            in_key = True
            val = stripped.split("=", 1)[1].strip()
            if val.startswith('"'):
                # Already quoted/formatted
                return
            key_lines.append(val)
        elif in_key:
            if stripped.startswith("-----END "):
                key_lines.append(stripped)
                # finished
                in_key = False
                joined_key = "\\n".join(key_lines)
                out_lines.append(f'KALSHI_PRIVATE_KEY="{joined_key}"\n')
            elif stripped:
                key_lines.append(stripped)
        else:
            if stripped:
                 out_lines.append(line)
                 
    with open(".env", "w", encoding="utf-8") as f:
        f.writelines(out_lines)

if __name__ == "__main__":
    fix_env()
    print("Fixed .env")
