"""
clean-tools.py -- Turns Freebuff's raw research output into a clean
tools.txt that the loader can eat.

Input:  D:\\Nate\\tools\\tools-researched-raw.txt
Output: D:\\Nate\\tools\\tools.txt

Format target:
    name | category | verified/unverified | description

Input format (what Freebuff actually produced):
    name | category | description                 <- status inferred: verified
    name | unknown  | description                 <- status inferred: unverified
"""

import re
import sys
from pathlib import Path

RAW_FILE = Path(r"D:\Nate\tools\tools-researched-raw.txt")
OUT_FILE = Path(r"D:\Nate\tools\tools.txt")
BACKUP   = Path(r"D:\Nate\tools\tools.txt.bak")


def normalize(text: str) -> str:
    """Turn fancy unicode punctuation into plain ASCII."""
    return (text
            .replace("\u2014", "--")
            .replace("\u2013", "-")
            .replace("\u2018", "'")
            .replace("\u2019", "'")
            .replace("\u201c", '"')
            .replace("\u201d", '"'))


def strip_markdown(line: str) -> str:
    line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
    line = re.sub(r"\*(.+?)\*", r"\1", line)
    line = re.sub(r"`(.+?)`", r"\1", line)
    return line


def parse_line(line: str):
    """
    Freebuff's format: name | category | description
    Returns (name, category, status, description) or None.
    """
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 3:
        return None

    name = parts[0].lower().replace(" ", "-")
    if not name or len(name) > 60:
        return None
    if name.startswith(("*", "#", "-", "=")):
        return None

    # Freebuff's lines are 3-field. Handle that first.
    if len(parts) == 3:
        category, description = parts[1], parts[2]
    elif len(parts) == 4:
        # If someone already added a status field, honor it.
        category, status_given, description = parts[1], parts[2], parts[3]
        status_given = status_given.strip().lower()
        if status_given in ("verified", "unverified"):
            category_out = category.strip() or "Unknown"
            status_out = status_given
            return (
                name,
                category_out,
                status_out,
                description.strip() or "Unable to research -- needs manual lookup.",
            )
        else:
            # 4th field was something else -- treat as 3-field + extra
            description = " | ".join([parts[2], parts[3]])
            category = parts[1]
    else:
        category = parts[1]
        description = " | ".join(parts[2:])

    category = category.strip()
    description = description.strip() or "Unable to research -- needs manual lookup."

    # THE RULE:
    #   category == "unknown"  ->  unverified, category = "Unknown"
    #   anything else          ->  verified, category stays as-is
    if category.lower() in ("unknown", "unverified", "unclear", ""):
        return (name, "Unknown", "unverified", description)

    return (name, category, "verified", description)


def main():
    if not RAW_FILE.exists():
        print(f"[ERROR] Raw file not found: {RAW_FILE}")
        sys.exit(1)

    if OUT_FILE.exists():
        OUT_FILE.replace(BACKUP)
        print(f"[OK] Backed up old tools.txt to {BACKUP.name}")

    raw = normalize(RAW_FILE.read_text(encoding="utf-8", errors="replace"))

    tools = {}
    skipped = []
    for lineno, line in enumerate(raw.splitlines(), 1):
        line = strip_markdown(line).strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            skipped.append((lineno, line[:60]))
            continue
        parsed = parse_line(line)
        if parsed is None:
            skipped.append((lineno, line[:60]))
            continue
        name, category, status, description = parsed
        tools[name] = (name, category, status, description)

    with OUT_FILE.open("w", encoding="utf-8") as fh:
        fh.write("# Nate's tool library\n")
        fh.write("# One tool per line, pipe-separated, EXACTLY 4 fields:\n")
        fh.write("#   name | category | verified/unverified | description\n")
        fh.write("# Blank lines and lines starting with '#' are ignored by the loader.\n")
        for name in sorted(tools):
            n, c, s, d = tools[name]
            fh.write(f"{n} | {c} | {s} | {d}\n")

    verified   = sum(1 for t in tools.values() if t[2] == "verified")
    unverified = len(tools) - verified

    print()
    print("=" * 60)
    print(f"Read:   {RAW_FILE}")
    print(f"Wrote:  {OUT_FILE}")
    print("=" * 60)
    print(f"Total tools written: {len(tools)}")
    print(f"  Verified:   {verified}")
    print(f"  Unverified: {unverified}")
    print(f"Lines skipped: {len(skipped)}")
    if skipped:
        print()
        print("First few skipped (for sanity check):")
        for lineno, snippet in skipped[:5]:
            print(f"  line {lineno}: {snippet}")
    print()
    print("Next step:  python load-tools.py")


if __name__ == "__main__":
    main()