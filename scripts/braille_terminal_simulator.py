#!/usr/bin/env python3
"""Interactive Terminal Refreshable Braille Display (RBD) Simulator.

Simulates:
- 40-cell physical electro-mechanical pin lifting
- 6-dot Unicode dot matrix rendering
- Tactile AST Diff preview and Perkins keyboard chord inputs
"""
import sys
from pathlib import Path

# Reconfigure stdout to UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure volcan_amazon repo root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.domain.braille_translator import text_to_braille, BrailleDiffDigest


def render_tactile_pin_cells(braille_str: str, max_cells: int = 40) -> str:
    """Renders a simulated ASCII dot matrix for physical Braille pins."""
    cells = list(braille_str[:max_cells])
    while len(cells) < max_cells:
        cells.append("\u2800")

    # Build 3-row pin matrix for 6-dot cells
    top_row = []
    mid_row = []
    bot_row = []

    for c in cells:
        cp = ord(c) - 0x2800
        # Dot 1 (0x01) / Dot 4 (0x08)
        d1 = "o" if cp & 0x01 else "."
        d4 = "o" if cp & 0x08 else "."
        top_row.append(f"{d1}{d4}")

        # Dot 2 (0x02) / Dot 5 (0x10)
        d2 = "o" if cp & 0x02 else "."
        d5 = "o" if cp & 0x10 else "."
        mid_row.append(f"{d2}{d5}")

        # Dot 3 (0x04) / Dot 6 (0x20)
        d3 = "o" if cp & 0x04 else "."
        d6 = "o" if cp & 0x20 else "."
        bot_row.append(f"{d3}{d6}")

    header = "+" + "--+" * (max_cells - 1) + "--+"
    r1 = "|" + "|".join(top_row) + "|"
    r2 = "|" + "|".join(mid_row) + "|"
    r3 = "|" + "|".join(bot_row) + "|"
    footer = "+" + "--+" * (max_cells - 1) + "--+"

    return f"{header}\n{r1}\n{r2}\n{r3}\n{footer}"


def main() -> None:
    sample_diff = "+ kms_key = os.environ.get('KMS_KEY_ID')\n- return 'hardcoded_secret'"
    digest = BrailleDiffDigest.from_diff(sample_diff)

    print("=" * 64)
    print("   VOLCAN REFRESHABLE BRAILLE DISPLAY TERMINAL SIMULATOR")
    print("=" * 64)
    print(f"\n[SUMMARY] {digest.braille_summary}")
    print(f"Additions: +{digest.additions_count} | Deletions: -{digest.deletions_count}\n")
    print("Simulated 20-Cell Physical Pin Matrix (o = Raised Pin, . = Flat Pin):")
    print(render_tactile_pin_cells(digest.lines[0].braille, 20))
    print("\nText Representation:")
    for line in digest.lines:
        print(f"[{line.line_type}] {line.text}")
        print(f"  -> Braille: {line.braille}\n")
    print("Braille Terminal Simulator execution completed successfully.")


if __name__ == "__main__":
    main()
