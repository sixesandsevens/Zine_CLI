#!/usr/bin/env python3
"""
zine-imposer

A small CLI tool that accepts a PDF or a list of images and converts them into
booklet / zine imposition format suitable for duplex printing.

Features
- Accepts PDF input or image input
- Pads page count to a multiple of 4 with blank pages
- Outputs imposed PDF in booklet order
- Supports Letter and A4 output
- Optional page labels
- Optional preview image export for each imposed side
- Friendly CLI help and validation

Examples
--------

PDF input:
    python zine_imposer_cli.py impose \
        --pdf CoopAndDagger.pdf \
        --output CoopAndDagger_zine.pdf

Image input:
    python zine_imposer_cli.py impose \
        --images page1.png page2.png page3.png page4.png \
                 page5.png page6.png page7.png page8.png \
        --output CoopAndDagger_zine.pdf

Preview imposed sheets:
    python zine_imposer_cli.py impose \
        --pdf CoopAndDagger.pdf \
        --output CoopAndDagger_zine.pdf \
        --preview-dir previews \
        --page-labels

Check imposition order only:
    python zine_imposer_cli.py plan --pages 8

Print notes
-----------
- Print double-sided
- Flip on SHORT edge
- Print at 100% scale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

try:
    import fitz  # PyMuPDF
except ModuleNotFoundError:
    fitz = None

try:
    from PIL import Image, ImageDraw, ImageOps
except ModuleNotFoundError:
    Image = ImageDraw = ImageOps = None  # type: ignore[assignment]


DEFAULT_DPI = 300
PAPER_SIZES_AT_300_DPI = {
    "letter": (3300, 2550),  # 11 x 8.5 landscape
    "a4": (3508, 2480),      # A4 landscape at ~300 DPI
}


class CliError(Exception):
    """Raised for user-facing CLI errors."""


# -----------------------------
# Argument parsing
# -----------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zine-imposer",
        description="Convert a PDF or images into print-ready zine/booklet layout.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    impose = subparsers.add_parser(
        "impose",
        help="Create an imposed zine PDF from a PDF or image pages.",
    )
    source = impose.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path, help="Input PDF file")
    source.add_argument(
        "--images",
        nargs="+",
        type=Path,
        help="Input image files in reading order",
    )

    impose.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output imposed PDF path",
    )
    impose.add_argument(
        "--paper",
        choices=sorted(PAPER_SIZES_AT_300_DPI.keys()),
        default="letter",
        help="Target paper size (default: letter)",
    )
    impose.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"Render DPI for PDF input and output metadata (default: {DEFAULT_DPI})",
    )
    impose.add_argument(
        "--margin",
        type=int,
        default=60,
        help="Outer margin in pixels (default: 60)",
    )
    impose.add_argument(
        "--gutter",
        type=int,
        default=30,
        help="Space between imposed pages in pixels (default: 30)",
    )
    impose.add_argument(
        "--bg",
        default="white",
        help="Background color (default: white)",
    )
    impose.add_argument(
        "--page-labels",
        action="store_true",
        help="Draw source page numbers under each imposed slot.",
    )
    impose.add_argument(
        "--preview-dir",
        type=Path,
        help="Optional directory to export preview PNGs of each imposed side.",
    )

    plan = subparsers.add_parser(
        "plan",
        help="Show the imposition order for a given page count.",
    )
    plan.add_argument(
        "--pages",
        type=int,
        required=True,
        help="Source page count in reading order.",
    )

    return parser


# -----------------------------
# Page loading
# -----------------------------


def load_pdf_pages(pdf_path: Path, dpi: int) -> List[Image.Image]:
    if fitz is None:
        raise CliError(
            "PyMuPDF is required for PDF input. Install dependencies with "
            "`pip install -e .` or `pip install PyMuPDF`."
        )
    if not pdf_path.exists():
        raise CliError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise CliError(f"Expected a PDF file, got: {pdf_path}")

    doc = fitz.open(pdf_path)
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    pages: List[Image.Image] = []

    try:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            pages.append(img)
    finally:
        doc.close()

    if not pages:
        raise CliError(f"PDF contains no pages: {pdf_path}")

    return pages



def load_image_pages(image_paths: Sequence[Path]) -> List[Image.Image]:
    if Image is None:
        raise CliError(
            "Pillow is required for image input. Install dependencies with "
            "`pip install -e .` or `pip install Pillow`."
        )
    if not image_paths:
        raise CliError("No image files were provided.")

    pages: List[Image.Image] = []
    for path in image_paths:
        if not path.exists():
            raise CliError(f"Image not found: {path}")
        try:
            pages.append(Image.open(path).convert("RGB"))
        except Exception as exc:  # pragma: no cover - defensive
            raise CliError(f"Failed to open image '{path}': {exc}") from exc

    return pages


# -----------------------------
# Imposition logic
# -----------------------------


def padded_page_count(page_count: int) -> int:
    total = page_count
    while total % 4 != 0:
        total += 1
    return total



def build_imposition_plan(page_count: int) -> List[Tuple[int, int, int, int]]:
    """
    Return a list of tuples:
        (front_left, front_right, back_left, back_right)
    using 1-based page numbering.

    Example for 8 pages:
        [(8, 1, 2, 7), (6, 3, 4, 5)]
    """
    if page_count <= 0:
        raise CliError("Page count must be greater than zero.")

    total = padded_page_count(page_count)
    pairs: List[Tuple[int, int, int, int]] = []

    left = total
    right = 1
    for _ in range(total // 4):
        front_left = left
        front_right = right
        right += 1
        left -= 1

        back_left = right
        back_right = left
        right += 1
        left -= 1

        pairs.append((front_left, front_right, back_left, back_right))

    return pairs


# -----------------------------
# Image composition
# -----------------------------


def get_sheet_size(paper: str, dpi: int) -> Tuple[int, int]:
    try:
        base_w, base_h = PAPER_SIZES_AT_300_DPI[paper]
    except KeyError as exc:
        raise CliError(f"Unsupported paper size: {paper}") from exc

    if dpi == 300:
        return base_w, base_h

    scale = dpi / 300.0
    return int(round(base_w * scale)), int(round(base_h * scale))



def fit_page_to_box(
    page: Optional[Image.Image],
    box_w: int,
    box_h: int,
    bg: str,
) -> Image.Image:
    if Image is None or ImageOps is None:
        raise CliError(
            "Pillow is required to compose imposed sheets. Install dependencies "
            "with `pip install -e .` or `pip install Pillow`."
        )
    canvas = Image.new("RGB", (box_w, box_h), bg)
    if page is None:
        return canvas

    fitted = ImageOps.contain(page, (box_w, box_h))
    x = (box_w - fitted.width) // 2
    y = (box_h - fitted.height) // 2
    canvas.paste(fitted, (x, y))
    return canvas



def draw_label(draw: ImageDraw.ImageDraw, x: int, y: int, text: str) -> None:
    draw.text((x, y), text, anchor="ma", fill="black")



def compose_sheet_side(
    left_page: Optional[Image.Image],
    right_page: Optional[Image.Image],
    sheet_size: Tuple[int, int],
    margin: int,
    gutter: int,
    bg: str,
    left_label: Optional[str] = None,
    right_label: Optional[str] = None,
) -> Image.Image:
    if Image is None or ImageDraw is None:
        raise CliError(
            "Pillow is required to compose imposed sheets. Install dependencies "
            "with `pip install -e .` or `pip install Pillow`."
        )
    sheet_w, sheet_h = sheet_size
    sheet = Image.new("RGB", (sheet_w, sheet_h), bg)

    if margin < 0 or gutter < 0:
        raise CliError("Margin and gutter must be zero or greater.")

    content_w = sheet_w - (2 * margin)
    content_h = sheet_h - (2 * margin)
    if content_w <= gutter + 10 or content_h <= 10:
        raise CliError("Margin/gutter settings leave no usable page area.")

    slot_w = (content_w - gutter) // 2
    slot_h = content_h

    left_img = fit_page_to_box(left_page, slot_w, slot_h, bg)
    right_img = fit_page_to_box(right_page, slot_w, slot_h, bg)

    left_x = margin
    right_x = margin + slot_w + gutter
    top_y = margin

    sheet.paste(left_img, (left_x, top_y))
    sheet.paste(right_img, (right_x, top_y))

    if left_label or right_label:
        draw = ImageDraw.Draw(sheet)
        label_y = sheet_h - max(18, margin // 2)
        if left_label:
            draw_label(draw, left_x + slot_w // 2, label_y, left_label)
        if right_label:
            draw_label(draw, right_x + slot_w // 2, label_y, right_label)

    return sheet


# -----------------------------
# Output helpers
# -----------------------------


def pad_pages(pages: Sequence[Image.Image]) -> List[Optional[Image.Image]]:
    padded: List[Optional[Image.Image]] = list(pages)
    while len(padded) % 4 != 0:
        padded.append(None)
    return padded



def save_previews(preview_dir: Path, sheets: Sequence[Image.Image]) -> None:
    preview_dir.mkdir(parents=True, exist_ok=True)
    for index, sheet in enumerate(sheets, start=1):
        path = preview_dir / f"sheet_{index:02d}.png"
        sheet.save(path, format="PNG")



def save_pdf(output_path: Path, sheets: Sequence[Image.Image], dpi: int) -> None:
    if not sheets:
        raise CliError("No imposed sheets to save.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheets[0].save(
        output_path,
        format="PDF",
        resolution=dpi,
        save_all=True,
        append_images=list(sheets[1:]),
    )


# -----------------------------
# Commands
# -----------------------------


def command_plan(args: argparse.Namespace) -> int:
    if args.pages <= 0:
        raise CliError("--pages must be greater than zero.")

    total = padded_page_count(args.pages)
    plan = build_imposition_plan(args.pages)

    print(f"Source pages: {args.pages}")
    if total != args.pages:
        print(f"Padded pages: {total} (blank pages added)")
    print()

    for sheet_num, (fl, fr, bl, br) in enumerate(plan, start=1):
        print(f"Sheet {sheet_num} front: {format_slot(fl, args.pages)} | {format_slot(fr, args.pages)}")
        print(f"Sheet {sheet_num} back : {format_slot(bl, args.pages)} | {format_slot(br, args.pages)}")
        print()

    return 0



def command_impose(args: argparse.Namespace) -> int:
    if Image is None:
        raise CliError(
            "Pillow is required for `impose`. Install dependencies with "
            "`pip install -e .` or `pip install Pillow`."
        )
    if args.pdf:
        pages = load_pdf_pages(args.pdf, dpi=args.dpi)
        source_name = args.pdf.name
    else:
        pages = load_image_pages(args.images)
        source_name = f"{len(args.images)} images"

    padded = pad_pages(pages)
    total_pages = len(padded)
    plan = build_imposition_plan(len(pages))
    sheet_size = get_sheet_size(args.paper, args.dpi)

    def get_page(page_num: int) -> Optional[Image.Image]:
        return padded[page_num - 1]

    imposed_sheets: List[Image.Image] = []
    for fl, fr, bl, br in plan:
        front = compose_sheet_side(
            left_page=get_page(fl),
            right_page=get_page(fr),
            sheet_size=sheet_size,
            margin=args.margin,
            gutter=args.gutter,
            bg=args.bg,
            left_label=str(fl) if args.page_labels and fl <= len(pages) else ("BLANK" if args.page_labels else None),
            right_label=str(fr) if args.page_labels and fr <= len(pages) else ("BLANK" if args.page_labels else None),
        )
        imposed_sheets.append(front)

        back = compose_sheet_side(
            left_page=get_page(bl),
            right_page=get_page(br),
            sheet_size=sheet_size,
            margin=args.margin,
            gutter=args.gutter,
            bg=args.bg,
            left_label=str(bl) if args.page_labels and bl <= len(pages) else ("BLANK" if args.page_labels else None),
            right_label=str(br) if args.page_labels and br <= len(pages) else ("BLANK" if args.page_labels else None),
        )
        imposed_sheets.append(back)

    save_pdf(args.output, imposed_sheets, args.dpi)
    if args.preview_dir:
        save_previews(args.preview_dir, imposed_sheets)

    print(f"Loaded: {source_name}")
    print(f"Source pages: {len(pages)}")
    if total_pages != len(pages):
        print(f"Padded to: {total_pages} pages (blank pages added)")
    print(f"Output paper: {args.paper} @ {args.dpi} DPI")
    print(f"Created {len(imposed_sheets)} imposed sheet sides")
    print(f"Saved PDF: {args.output}")
    if args.preview_dir:
        print(f"Saved previews: {args.preview_dir}")
    print()
    print("Print settings:")
    print("- Double-sided")
    print("- Flip on SHORT edge")
    print("- Scale 100%")

    return 0


# -----------------------------
# Formatting helpers
# -----------------------------


def format_slot(page_num: int, total_pages: int) -> str:
    return str(page_num) if page_num <= total_pages else "BLANK"


# -----------------------------
# Entry point
# -----------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "plan":
            return command_plan(args)
        if args.command == "impose":
            return command_impose(args)
        raise CliError(f"Unknown command: {args.command}")
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
pip install -e .
