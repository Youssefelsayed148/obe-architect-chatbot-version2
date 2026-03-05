from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

from fpdf import FPDF
from fpdf.errors import FPDFException


def _safe_text(value: str) -> str:
    # Keep PDF generation robust with core fonts.
    return value.encode("latin-1", "replace").decode("latin-1")


def _write_wrapped(pdf: FPDF, text: str, line_height: float, width: int = 110) -> None:
    normalized = text.replace("\t", "    ")
    wrapped = textwrap.wrap(
        normalized,
        width=width,
        break_long_words=True,
        break_on_hyphens=True,
    ) or [" "]

    for segment in wrapped:
        value = segment if segment else " "
        try:
            pdf.multi_cell(0, line_height, value, new_x="LMARGIN", new_y="NEXT")
        except FPDFException:
            # Last-resort fallback for edge cases in line-breaking.
            for tiny in textwrap.wrap(value.strip() or " ", width=40, break_long_words=True):
                pdf.multi_cell(0, line_height, tiny, new_x="LMARGIN", new_y="NEXT")


def render_markdown_to_pdf(input_path: Path, output_path: Path) -> None:
    lines = input_path.read_text(encoding="utf-8").splitlines()

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_title("OBE Architects Bot - Master Handoff")

    in_code_block = False

    for raw_line in lines:
        line = raw_line.rstrip()

        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            pdf.ln(1.5)
            continue

        if in_code_block:
            pdf.set_font("Courier", size=9)
            _write_wrapped(pdf, _safe_text(line if line else " "), 4.8, width=96)
            continue

        if line.startswith("# "):
            pdf.set_font("Helvetica", style="B", size=16)
            pdf.multi_cell(0, 8, _safe_text(line[2:].strip()), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
            continue

        if line.startswith("## "):
            pdf.set_font("Helvetica", style="B", size=13)
            pdf.multi_cell(0, 7, _safe_text(line[3:].strip()), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(0.5)
            continue

        if line.startswith("### "):
            pdf.set_font("Helvetica", style="B", size=11)
            pdf.multi_cell(0, 6, _safe_text(line[4:].strip()), new_x="LMARGIN", new_y="NEXT")
            continue

        pdf.set_font("Helvetica", size=10)
        _write_wrapped(pdf, _safe_text(line if line else " "), 5.5, width=110)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate handoff PDF from markdown.")
    parser.add_argument(
        "--input",
        default="PROJECT_HANDOFF_MASTER_2026-02-23.md",
        help="Input markdown path",
    )
    parser.add_argument(
        "--output",
        default="PROJECT_HANDOFF_MASTER_2026-02-23.pdf",
        help="Output PDF path",
    )
    args = parser.parse_args()

    render_markdown_to_pdf(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
