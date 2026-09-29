"""Writes the companion page's @font-face rules from the font files in docs/fonts.

The page is one HTML file served three ways: GitHub Pages serves docs/index.html,
the FastAPI app returns the same bytes at / and /demo, and the container copies
only that one file. A font the page fetched from anywhere else would be a second
thing every one of those paths had to ship, or a request to another origin. So
the three woff2 files are inlined as data: URIs between two markers in the
page's first <style> block, and this script is the only thing that writes them.

Source of the files, fetched on 2026-09-26 and committed unchanged:

* https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700
  &family=JetBrains+Mono:wght@400;600&display=swap, requested with a desktop
  Chrome User-Agent. Only the ``/* latin */`` blocks were kept, and only the
  woff2 files they name were downloaded from fonts.gstatic.com.
* JetBrains Mono is served as one variable file for both weights, so it is one
  file here with a weight range, not two copies of the same bytes.
* Licences: https://raw.githubusercontent.com/google/fonts/main/ofl/
  atkinsonhyperlegible/OFL.txt and .../ofl/jetbrainsmono/OFL.txt, committed
  beside the files. Both families are under the SIL Open Font License 1.1.

Usage:
    python scripts/embed_fonts.py           rewrite the block in docs/index.html
    python scripts/embed_fonts.py --check   exit 1 if the block is out of date
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "index.html"
FONT_DIR = ROOT / "docs" / "fonts"

BEGIN = "    /* fonts:begin, written by scripts/embed_fonts.py; do not edit by hand */\n"
END = "    /* fonts:end */\n"
NOTICE = (
    "    /* Atkinson Hyperlegible, Copyright 2020 Braille Institute of America, Inc.\n"
    "       JetBrains Mono, Copyright 2020 The JetBrains Mono Project Authors.\n"
    "       Both are licensed under the SIL Open Font License, Version 1.1; the full\n"
    "       text is in docs/fonts/OFL-AtkinsonHyperlegible.txt and OFL-JetBrainsMono.txt. */\n"
)

#: family, CSS weight (a range for a variable file), file name
FACES = (
    ("Atkinson Hyperlegible", "400", "atkinson-hyperlegible-400-latin.woff2"),
    ("Atkinson Hyperlegible", "700", "atkinson-hyperlegible-700-latin.woff2"),
    ("JetBrains Mono", "400 600", "jetbrains-mono-400-600-latin.woff2"),
)

#: The latin range Google Fonts declares for these files, kept so a browser
#: never downloads (here: decodes) a face for text it cannot draw.
LATIN_RANGE = (
    "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, "
    "U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, "
    "U+2212, U+2215, U+FEFF, U+FFFD"
)


def font_block() -> str:
    rules = []
    for family, weight, name in FACES:
        data = base64.b64encode((FONT_DIR / name).read_bytes()).decode("ascii")
        rules.append(
            "    @font-face {\n"
            f"      font-family: \"{family}\";\n"
            "      font-style: normal;\n"
            f"      font-weight: {weight};\n"
            "      font-display: swap;\n"
            f"      src: url(data:font/woff2;base64,{data}) format(\"woff2\");\n"
            f"      unicode-range: {LATIN_RANGE};\n"
            "    }\n"
        )
    return BEGIN + NOTICE + "".join(rules) + END


def current_block(html: str) -> str:
    start = html.index(BEGIN)
    end = html.index(END, start) + len(END)
    return html[start:end]


def main(argv: list[str]) -> int:
    html = PAGE.read_text(encoding="utf-8")
    wanted = font_block()
    if "--check" in argv:
        if current_block(html) != wanted:
            print("docs/index.html: the @font-face block is out of date; run python scripts/embed_fonts.py")
            return 1
        print("docs/index.html: the @font-face block matches docs/fonts")
        return 0
    updated = html.replace(current_block(html), wanted)
    PAGE.write_text(updated, encoding="utf-8", newline="\n")
    print(f"docs/index.html: {len(html.encode('utf-8'))} -> {len(updated.encode('utf-8'))} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
