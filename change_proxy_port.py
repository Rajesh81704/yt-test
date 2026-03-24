"""
Usage: python change_proxy_port.py <new_port>
Example: python change_proxy_port.py 3128
"""
import sys
from pathlib import Path

def change_port(new_port: str):
    p = Path("proxies.properties")
    lines = p.read_text().splitlines()
    updated = []
    changed = 0
    for line in lines:
        if line.strip() and not line.startswith("#"):
            parts = line.split(":")
            if len(parts) >= 2:
                parts[1] = new_port
                line = ":".join(parts)
                changed += 1
        updated.append(line)
    p.write_text("\n".join(updated) + "\n")
    print(f"Done. Changed port to {new_port} on {changed} proxies.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python change_proxy_port.py <new_port>")
        sys.exit(1)
    change_port(sys.argv[1])
