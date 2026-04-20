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
- Optional crop marks and fold guide
- Dry-run planning in the terminal
- Desktop preview UI for checking sheet layout before export
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
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

try:
    from PIL import ImageTk
except (ModuleNotFoundError, ImportError):
    ImageTk = None  # type: ignore[assignment]

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ModuleNotFoundError:
    tk = filedialog = messagebox = ttk = None  # type: ignore[assignment]


DEFAULT_DPI = 300
CROP_MARK_LENGTH = 24
CROP_MARK_OFFSET = 10
FOLD_GUIDE_DASH = (10, 8)
PREVIEW_MAX_SIZE = (900, 650)
UI_COLORS = {
    "bg": "#11161d",
    "panel": "#18212b",
    "panel_alt": "#1f2a36",
    "border": "#2f3d4d",
    "text": "#e8eef5",
    "muted": "#9fb0c2",
    "accent": "#d97a2b",
    "accent_hover": "#f08c37",
    "input_bg": "#243140",
    "preview_bg": "#0d1218",
}
PAPER_SIZES_AT_300_DPI = {
    "letter": (3300, 2550),  # 11 x 8.5 landscape
    "a4": (3508, 2480),      # A4 landscape at ~300 DPI
}


class CliError(Exception):
    """Raised for user-facing CLI errors."""


@dataclass
class ImpositionOptions:
    paper: str = "letter"
    dpi: int = DEFAULT_DPI
    margin: int = 60
    gutter: int = 30
    bg: str = "white"
    page_labels: bool = False
    crop_marks: bool = False
    fold_guide: bool = False


@dataclass
class ImpositionResult:
    pages: List["Image.Image"]
    padded_pages: List[Optional["Image.Image"]]
    sheets: List["Image.Image"]
    plan: List[Tuple[int, int, int, int]]
    total_pages: int


# -----------------------------
# Argument parsing
# -----------------------------


def add_source_arguments(parser: argparse.ArgumentParser, *, required: bool) -> None:
    source = parser.add_mutually_exclusive_group(required=required)
    source.add_argument("--pdf", type=Path, help="Input PDF file")
    source.add_argument(
        "--images",
        nargs="+",
        type=Path,
        help="Input image files in reading order",
    )


def add_layout_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--paper",
        choices=sorted(PAPER_SIZES_AT_300_DPI.keys()),
        default="letter",
        help="Target paper size (default: letter)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"Render DPI for PDF input and output metadata (default: {DEFAULT_DPI})",
    )
    parser.add_argument(
        "--margin",
        type=int,
        default=60,
        help="Outer margin in pixels (default: 60)",
    )
    parser.add_argument(
        "--gutter",
        type=int,
        default=30,
        help="Space between imposed pages in pixels (default: 30)",
    )
    parser.add_argument(
        "--bg",
        default="white",
        help="Background color (default: white)",
    )
    parser.add_argument(
        "--page-labels",
        action="store_true",
        help="Draw source page numbers under each imposed slot.",
    )
    parser.add_argument(
        "--crop-marks",
        action="store_true",
        help="Draw crop marks near the outer corners of each sheet.",
    )
    parser.add_argument(
        "--fold-guide",
        action="store_true",
        help="Draw a dashed guide line at the vertical fold.",
    )


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
    add_source_arguments(impose, required=True)
    impose.add_argument(
        "--output",
        type=Path,
        help="Output imposed PDF path. Required unless --dry-run is used.",
    )
    impose.add_argument(
        "--preview-dir",
        type=Path,
        help="Optional directory to export preview PNGs of each imposed side.",
    )
    impose.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the imposition plan without writing the final PDF.",
    )
    add_layout_arguments(impose)

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

    ui = subparsers.add_parser(
        "ui",
        help="Open a small desktop UI for previewing and exporting imposed sheets.",
    )
    add_source_arguments(ui, required=False)
    add_layout_arguments(ui)

    return parser


# -----------------------------
# Page loading
# -----------------------------


def require_pillow(feature: str) -> None:
    if Image is None:
        raise CliError(
            f"Pillow is required for {feature}. Install dependencies with "
            "`pip install -e .` or `pip install Pillow`."
        )


def load_pdf_pages(pdf_path: Path, dpi: int) -> List["Image.Image"]:
    require_pillow("PDF rendering")
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
    pages: List["Image.Image"] = []

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


def load_image_pages(image_paths: Sequence[Path]) -> List["Image.Image"]:
    require_pillow("image input")
    if not image_paths:
        raise CliError("No image files were provided.")

    pages: List["Image.Image"] = []
    for path in image_paths:
        if not path.exists():
            raise CliError(f"Image not found: {path}")
        try:
            with Image.open(path) as img:
                pages.append(img.convert("RGB"))
        except Exception as exc:  # pragma: no cover - defensive
            raise CliError(f"Failed to open image '{path}': {exc}") from exc

    return pages


def load_source_pages(
    pdf_path: Optional[Path],
    image_paths: Optional[Sequence[Path]],
    dpi: int,
) -> Tuple[List["Image.Image"], str]:
    if pdf_path:
        return load_pdf_pages(pdf_path, dpi=dpi), pdf_path.name
    if image_paths:
        return load_image_pages(image_paths), f"{len(image_paths)} images"
    raise CliError("Provide either --pdf or --images.")


# -----------------------------
# Imposition logic
# -----------------------------


def padded_page_count(page_count: int) -> int:
    total = page_count
    while total % 4 != 0:
        total += 1
    return total


def build_imposition_plan(page_count: int) -> List[Tuple[int, int, int, int]]:
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


def format_slot(page_num: int, source_page_count: int) -> str:
    return str(page_num) if page_num <= source_page_count else "BLANK"


def format_plan_lines(
    plan: Sequence[Tuple[int, int, int, int]],
    source_page_count: int,
) -> List[str]:
    lines: List[str] = []
    for sheet_num, (fl, fr, bl, br) in enumerate(plan, start=1):
        lines.append(
            f"Sheet {sheet_num} front: "
            f"{format_slot(fl, source_page_count)} | {format_slot(fr, source_page_count)}"
        )
        lines.append(
            f"Sheet {sheet_num} back : "
            f"{format_slot(bl, source_page_count)} | {format_slot(br, source_page_count)}"
        )
        lines.append("")
    return lines[:-1] if lines else lines


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
    page: Optional["Image.Image"],
    box_w: int,
    box_h: int,
    bg: str,
) -> "Image.Image":
    require_pillow("sheet composition")
    if ImageOps is None:
        raise CliError("Pillow ImageOps support is unavailable.")
    canvas = Image.new("RGB", (box_w, box_h), bg)
    if page is None:
        return canvas

    fitted = ImageOps.contain(page, (box_w, box_h))
    x = (box_w - fitted.width) // 2
    y = (box_h - fitted.height) // 2
    canvas.paste(fitted, (x, y))
    return canvas


def draw_label(draw: "ImageDraw.ImageDraw", x: int, y: int, text: str) -> None:
    draw.text((x, y), text, anchor="ma", fill="black")


def draw_dashed_line(
    draw: "ImageDraw.ImageDraw",
    start: Tuple[int, int],
    end: Tuple[int, int],
    dash_pattern: Tuple[int, int] = FOLD_GUIDE_DASH,
    fill: str = "black",
    width: int = 1,
) -> None:
    x1, y1 = start
    x2, y2 = end
    dash_len, gap_len = dash_pattern

    if x1 == x2:
        y = y1
        step = 1 if y2 >= y1 else -1
        while (y - y2) * step <= 0:
            y_end = y + (dash_len * step)
            if (y_end - y2) * step > 0:
                y_end = y2
            draw.line((x1, y, x2, y_end), fill=fill, width=width)
            y = y_end + (gap_len * step)
        return

    if y1 == y2:
        x = x1
        step = 1 if x2 >= x1 else -1
        while (x - x2) * step <= 0:
            x_end = x + (dash_len * step)
            if (x_end - x2) * step > 0:
                x_end = x2
            draw.line((x, y1, x_end, y2), fill=fill, width=width)
            x = x_end + (gap_len * step)
        return

    draw.line((x1, y1, x2, y2), fill=fill, width=width)


def draw_crop_marks(
    draw: "ImageDraw.ImageDraw",
    sheet_w: int,
    sheet_h: int,
    margin: int,
    length: int = CROP_MARK_LENGTH,
    offset: int = CROP_MARK_OFFSET,
    fill: str = "black",
    width: int = 1,
) -> None:
    left = margin
    right = sheet_w - margin
    top = margin
    bottom = sheet_h - margin

    draw.line((left - offset, top, left - offset + length, top), fill=fill, width=width)
    draw.line((left, top - offset, left, top - offset + length), fill=fill, width=width)
    draw.line((right + offset - length, top, right + offset, top), fill=fill, width=width)
    draw.line((right, top - offset, right, top - offset + length), fill=fill, width=width)
    draw.line((left - offset, bottom, left - offset + length, bottom), fill=fill, width=width)
    draw.line((left, bottom + offset - length, left, bottom + offset), fill=fill, width=width)
    draw.line((right + offset - length, bottom, right + offset, bottom), fill=fill, width=width)
    draw.line((right, bottom + offset - length, right, bottom + offset), fill=fill, width=width)


def compose_sheet_side(
    left_page: Optional["Image.Image"],
    right_page: Optional["Image.Image"],
    sheet_size: Tuple[int, int],
    margin: int,
    gutter: int,
    bg: str,
    left_label: Optional[str] = None,
    right_label: Optional[str] = None,
    crop_marks: bool = False,
    fold_guide: bool = False,
) -> "Image.Image":
    require_pillow("sheet composition")
    if ImageDraw is None:
        raise CliError("Pillow ImageDraw support is unavailable.")
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

    draw = ImageDraw.Draw(sheet)

    if left_label or right_label:
        label_y = sheet_h - max(18, margin // 2)
        if left_label:
            draw_label(draw, left_x + slot_w // 2, label_y, left_label)
        if right_label:
            draw_label(draw, right_x + slot_w // 2, label_y, right_label)

    if crop_marks:
        draw_crop_marks(draw, sheet_w, sheet_h, margin)

    if fold_guide:
        center_x = sheet_w // 2
        guide_top = margin // 2
        guide_bottom = sheet_h - (margin // 2)
        draw_dashed_line(draw, (center_x, guide_top), (center_x, guide_bottom))

    return sheet


def pad_pages(pages: Sequence["Image.Image"]) -> List[Optional["Image.Image"]]:
    padded: List[Optional["Image.Image"]] = list(pages)
    while len(padded) % 4 != 0:
        padded.append(None)
    return padded


def build_imposed_sheets(
    pages: Sequence["Image.Image"],
    options: ImpositionOptions,
) -> ImpositionResult:
    padded = pad_pages(pages)
    plan = build_imposition_plan(len(pages))
    sheet_size = get_sheet_size(options.paper, options.dpi)
    source_page_count = len(pages)

    def get_page(page_num: int) -> Optional["Image.Image"]:
        return padded[page_num - 1]

    sheets: List["Image.Image"] = []
    for fl, fr, bl, br in plan:
        front = compose_sheet_side(
            left_page=get_page(fl),
            right_page=get_page(fr),
            sheet_size=sheet_size,
            margin=options.margin,
            gutter=options.gutter,
            bg=options.bg,
            left_label=format_slot(fl, source_page_count) if options.page_labels else None,
            right_label=format_slot(fr, source_page_count) if options.page_labels else None,
            crop_marks=options.crop_marks,
            fold_guide=options.fold_guide,
        )
        sheets.append(front)

        back = compose_sheet_side(
            left_page=get_page(bl),
            right_page=get_page(br),
            sheet_size=sheet_size,
            margin=options.margin,
            gutter=options.gutter,
            bg=options.bg,
            left_label=format_slot(bl, source_page_count) if options.page_labels else None,
            right_label=format_slot(br, source_page_count) if options.page_labels else None,
            crop_marks=options.crop_marks,
            fold_guide=options.fold_guide,
        )
        sheets.append(back)

    return ImpositionResult(
        pages=list(pages),
        padded_pages=padded,
        sheets=sheets,
        plan=plan,
        total_pages=len(padded),
    )


def render_preview_image(sheet: "Image.Image", max_size: Tuple[int, int]) -> "Image.Image":
    require_pillow("preview rendering")
    preview = sheet.copy()
    preview.thumbnail(max_size)
    return preview


# -----------------------------
# Output helpers
# -----------------------------


def save_previews(preview_dir: Path, sheets: Sequence["Image.Image"]) -> None:
    preview_dir.mkdir(parents=True, exist_ok=True)
    for index, sheet in enumerate(sheets, start=1):
        path = preview_dir / f"sheet_{index:02d}.png"
        sheet.save(path, format="PNG")


def save_pdf(output_path: Path, sheets: Sequence["Image.Image"], dpi: int) -> None:
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


def options_from_args(args: argparse.Namespace) -> ImpositionOptions:
    return ImpositionOptions(
        paper=args.paper,
        dpi=args.dpi,
        margin=args.margin,
        gutter=args.gutter,
        bg=args.bg,
        page_labels=args.page_labels,
        crop_marks=args.crop_marks,
        fold_guide=args.fold_guide,
    )


def command_plan(args: argparse.Namespace) -> int:
    if args.pages <= 0:
        raise CliError("--pages must be greater than zero.")

    total = padded_page_count(args.pages)
    plan = build_imposition_plan(args.pages)

    print(f"Source pages: {args.pages}")
    if total != args.pages:
        print(f"Padded pages: {total} (blank pages added)")
    print()

    for line in format_plan_lines(plan, args.pages):
        print(line)

    return 0


def print_imposition_summary(
    source_name: str,
    result: ImpositionResult,
    options: ImpositionOptions,
) -> None:
    print(f"Loaded: {source_name}")
    print(f"Source pages: {len(result.pages)}")
    if result.total_pages != len(result.pages):
        print(f"Padded to: {result.total_pages} pages (blank pages added)")
    print(f"Output paper: {options.paper} @ {options.dpi} DPI")
    print(f"Created {len(result.sheets)} imposed sheet sides")


def command_impose(args: argparse.Namespace) -> int:
    require_pillow("`impose`")
    options = options_from_args(args)
    pages, source_name = load_source_pages(args.pdf, args.images, dpi=options.dpi)
    result = build_imposed_sheets(pages, options)

    print_imposition_summary(source_name, result, options)

    if args.dry_run:
        print("Dry run: enabled")
        print()
        for line in format_plan_lines(result.plan, len(result.pages)):
            print(line)
        return 0

    if args.output is None:
        raise CliError("--output is required unless --dry-run is used.")

    save_pdf(args.output, result.sheets, options.dpi)
    if args.preview_dir:
        save_previews(args.preview_dir, result.sheets)

    print(f"Saved PDF: {args.output}")
    if args.preview_dir:
        print(f"Saved previews: {args.preview_dir}")
    if args.crop_marks:
        print("Crop marks: enabled")
    if args.fold_guide:
        print("Fold guide: enabled")
    print()
    print("Print settings:")
    print("- Double-sided")
    print("- Flip on SHORT edge")
    print("- Scale 100%")

    return 0


class ZineImposerUI:
    def __init__(self, args: argparse.Namespace) -> None:
        if tk is None or ttk is None or filedialog is None or messagebox is None:
            raise CliError("Tkinter is required for the desktop UI.")
        if ImageTk is None:
            raise CliError("Pillow ImageTk support is required for the desktop UI.")

        try:
            self.root = tk.Tk()
        except tk.TclError as exc:  # type: ignore[union-attr]
            raise CliError(f"Unable to open the desktop UI: {exc}") from exc

        self.root.title("Zine Imposer")
        self.root.geometry("1280x860")
        self.root.minsize(1080, 720)
        self.configure_dark_theme()

        self.pdf_path: Optional[Path] = args.pdf
        self.image_paths: List[Path] = list(args.images or [])
        self.result: Optional[ImpositionResult] = None
        self.preview_index = 0
        self.preview_photo = None

        self.paper_var = tk.StringVar(value=args.paper)
        self.dpi_var = tk.StringVar(value=str(args.dpi))
        self.margin_var = tk.StringVar(value=str(args.margin))
        self.gutter_var = tk.StringVar(value=str(args.gutter))
        self.bg_var = tk.StringVar(value=args.bg)
        self.page_labels_var = tk.BooleanVar(value=args.page_labels)
        self.crop_marks_var = tk.BooleanVar(value=args.crop_marks)
        self.fold_guide_var = tk.BooleanVar(value=args.fold_guide)
        self.source_var = tk.StringVar(value=self.describe_source())
        self.status_var = tk.StringVar(value="Choose a PDF or image set, then preview the layout.")
        self.sheet_counter_var = tk.StringVar(value="No preview loaded")

        self.build_ui()

        if self.pdf_path or self.image_paths:
            self.refresh_preview()

    def configure_dark_theme(self) -> None:
        self.root.configure(bg=UI_COLORS["bg"])

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=UI_COLORS["bg"], foreground=UI_COLORS["text"])
        style.configure(
            "Dark.TFrame",
            background=UI_COLORS["bg"],
        )
        style.configure(
            "Panel.TFrame",
            background=UI_COLORS["panel"],
            borderwidth=0,
        )
        style.configure(
            "Preview.TFrame",
            background=UI_COLORS["panel_alt"],
            borderwidth=0,
        )
        style.configure(
            "Title.TLabel",
            background=UI_COLORS["panel"],
            foreground=UI_COLORS["text"],
            font=("TkDefaultFont", 10, "bold"),
        )
        style.configure(
            "PreviewTitle.TLabel",
            background=UI_COLORS["panel_alt"],
            foreground=UI_COLORS["text"],
            font=("TkDefaultFont", 11, "bold"),
        )
        style.configure(
            "Body.TLabel",
            background=UI_COLORS["panel"],
            foreground=UI_COLORS["text"],
        )
        style.configure(
            "Muted.TLabel",
            background=UI_COLORS["panel_alt"],
            foreground=UI_COLORS["muted"],
        )
        style.configure(
            "Dark.TButton",
            background=UI_COLORS["panel_alt"],
            foreground=UI_COLORS["text"],
            bordercolor=UI_COLORS["border"],
            focusthickness=0,
            focuscolor=UI_COLORS["panel_alt"],
            padding=(10, 7),
        )
        style.map(
            "Dark.TButton",
            background=[("active", UI_COLORS["input_bg"])],
            foreground=[("disabled", UI_COLORS["muted"])],
        )
        style.configure(
            "Accent.TButton",
            background=UI_COLORS["accent"],
            foreground="#fff7ef",
            bordercolor=UI_COLORS["accent"],
            focusthickness=0,
            focuscolor=UI_COLORS["accent"],
            padding=(10, 8),
        )
        style.map(
            "Accent.TButton",
            background=[("active", UI_COLORS["accent_hover"])],
            foreground=[("active", "#ffffff")],
        )
        style.configure(
            "Dark.TCheckbutton",
            background=UI_COLORS["panel"],
            foreground=UI_COLORS["text"],
            focuscolor=UI_COLORS["panel"],
        )
        style.map(
            "Dark.TCheckbutton",
            background=[("active", UI_COLORS["panel"])],
            foreground=[("active", UI_COLORS["text"])],
        )
        style.configure(
            "Dark.TEntry",
            fieldbackground=UI_COLORS["input_bg"],
            foreground=UI_COLORS["text"],
            insertcolor=UI_COLORS["text"],
            bordercolor=UI_COLORS["border"],
        )
        style.configure(
            "Dark.TCombobox",
            fieldbackground=UI_COLORS["input_bg"],
            background=UI_COLORS["input_bg"],
            foreground=UI_COLORS["text"],
            arrowcolor=UI_COLORS["text"],
            bordercolor=UI_COLORS["border"],
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", UI_COLORS["input_bg"])],
            foreground=[("readonly", UI_COLORS["text"])],
            selectbackground=[("readonly", UI_COLORS["input_bg"])],
            selectforeground=[("readonly", UI_COLORS["text"])],
        )

    def describe_source(self) -> str:
        if self.pdf_path:
            return str(self.pdf_path)
        if self.image_paths:
            return f"{len(self.image_paths)} images selected"
        return "No source selected"

    def build_ui(self) -> None:
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        controls = ttk.Frame(self.root, padding=14, style="Panel.TFrame")
        controls.grid(row=0, column=0, sticky="ns")

        preview = ttk.Frame(self.root, padding=(0, 14, 14, 14), style="Preview.TFrame")
        preview.grid(row=0, column=1, sticky="nsew")
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(1, weight=1)

        ttk.Label(controls, text="Source", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(controls, textvariable=self.source_var, wraplength=280, style="Body.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 8)
        )
        ttk.Button(controls, text="Choose PDF", command=self.choose_pdf, style="Dark.TButton").grid(
            row=2, column=0, sticky="ew", pady=2
        )
        ttk.Button(controls, text="Choose Images", command=self.choose_images, style="Dark.TButton").grid(
            row=2, column=1, sticky="ew", padx=(8, 0), pady=2
        )
        ttk.Button(controls, text="Clear Source", command=self.clear_source, style="Dark.TButton").grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(2, 12)
        )

        ttk.Label(controls, text="Layout", style="Title.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="w"
        )

        self.add_labeled_entry(controls, "Paper", self.paper_var, 5, combo_values=["letter", "a4"])
        self.add_labeled_entry(controls, "DPI", self.dpi_var, 6)
        self.add_labeled_entry(controls, "Margin", self.margin_var, 7)
        self.add_labeled_entry(controls, "Gutter", self.gutter_var, 8)
        self.add_labeled_entry(controls, "Background", self.bg_var, 9)

        ttk.Checkbutton(controls, text="Page labels", variable=self.page_labels_var, style="Dark.TCheckbutton").grid(
            row=10, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(controls, text="Crop marks", variable=self.crop_marks_var, style="Dark.TCheckbutton").grid(
            row=11, column=0, columnspan=2, sticky="w"
        )
        ttk.Checkbutton(controls, text="Fold guide", variable=self.fold_guide_var, style="Dark.TCheckbutton").grid(
            row=12, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        ttk.Button(controls, text="Preview Dry Run", command=self.refresh_preview, style="Accent.TButton").grid(
            row=13, column=0, columnspan=2, sticky="ew", pady=2
        )
        ttk.Button(controls, text="Export PDF", command=self.export_pdf, style="Dark.TButton").grid(
            row=14, column=0, columnspan=2, sticky="ew", pady=2
        )

        ttk.Label(controls, text="Plan", style="Title.TLabel").grid(
            row=15, column=0, columnspan=2, sticky="w", pady=(12, 4)
        )
        self.plan_text = tk.Text(
            controls,
            width=36,
            height=20,
            wrap="word",
            bg=UI_COLORS["input_bg"],
            fg=UI_COLORS["text"],
            insertbackground=UI_COLORS["text"],
            selectbackground=UI_COLORS["accent"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=UI_COLORS["border"],
            highlightcolor=UI_COLORS["accent"],
            padx=10,
            pady=10,
        )
        self.plan_text.grid(row=16, column=0, columnspan=2, sticky="nsew")
        controls.rowconfigure(16, weight=1)
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)

        ttk.Label(preview, text="Preview", style="PreviewTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self.preview_label = tk.Label(
            preview,
            anchor="center",
            bg=UI_COLORS["preview_bg"],
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=UI_COLORS["border"],
        )
        self.preview_label.grid(row=1, column=0, sticky="nsew")

        nav = ttk.Frame(preview, style="Preview.TFrame")
        nav.grid(row=2, column=0, sticky="ew", pady=(10, 4))
        nav.columnconfigure(1, weight=1)
        ttk.Button(nav, text="Previous", command=self.show_previous_sheet, style="Dark.TButton").grid(row=0, column=0, padx=(0, 8))
        ttk.Label(nav, textvariable=self.sheet_counter_var, style="Muted.TLabel").grid(row=0, column=1)
        ttk.Button(nav, text="Next", command=self.show_next_sheet, style="Dark.TButton").grid(row=0, column=2, padx=(8, 0))

        ttk.Label(preview, textvariable=self.status_var, wraplength=780, style="Muted.TLabel").grid(
            row=3, column=0, sticky="w", pady=(6, 0)
        )

    def add_labeled_entry(
        self,
        parent,
        label: str,
        variable,
        row: int,
        combo_values: Optional[Sequence[str]] = None,
    ) -> None:
        ttk.Label(parent, text=label, style="Body.TLabel").grid(row=row, column=0, sticky="w", pady=2)
        if combo_values:
            widget = ttk.Combobox(
                parent,
                textvariable=variable,
                values=list(combo_values),
                state="readonly",
                style="Dark.TCombobox",
            )
        else:
            widget = ttk.Entry(parent, textvariable=variable, style="Dark.TEntry")
        widget.grid(row=row, column=1, sticky="ew", pady=2, padx=(8, 0))

    def choose_pdf(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not selected:
            return
        self.pdf_path = Path(selected)
        self.image_paths = []
        self.source_var.set(self.describe_source())
        self.status_var.set("PDF selected. Click Preview Dry Run to render sheet previews.")

    def choose_images(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Choose Images",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.tif *.tiff *.webp *.bmp"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return
        self.image_paths = [Path(path) for path in selected]
        self.pdf_path = None
        self.source_var.set(self.describe_source())
        self.status_var.set("Images selected. Click Preview Dry Run to render sheet previews.")

    def clear_source(self) -> None:
        self.pdf_path = None
        self.image_paths = []
        self.result = None
        self.preview_index = 0
        self.preview_label.configure(image="", text="")
        self.plan_text.delete("1.0", tk.END)
        self.sheet_counter_var.set("No preview loaded")
        self.source_var.set(self.describe_source())
        self.status_var.set("Choose a PDF or image set, then preview the layout.")

    def options_from_ui(self) -> ImpositionOptions:
        try:
            dpi = int(self.dpi_var.get())
            margin = int(self.margin_var.get())
            gutter = int(self.gutter_var.get())
        except ValueError as exc:
            raise CliError("DPI, margin, and gutter must be integers.") from exc

        if dpi <= 0:
            raise CliError("DPI must be greater than zero.")

        return ImpositionOptions(
            paper=self.paper_var.get(),
            dpi=dpi,
            margin=margin,
            gutter=gutter,
            bg=self.bg_var.get().strip() or "white",
            page_labels=self.page_labels_var.get(),
            crop_marks=self.crop_marks_var.get(),
            fold_guide=self.fold_guide_var.get(),
        )

    def refresh_preview(self) -> None:
        try:
            options = self.options_from_ui()
            pages, source_name = load_source_pages(self.pdf_path, self.image_paths, options.dpi)
            self.result = build_imposed_sheets(pages, options)
        except CliError as exc:
            messagebox.showerror("Preview Error", str(exc))
            return

        self.preview_index = 0
        self.plan_text.delete("1.0", tk.END)
        self.plan_text.insert("1.0", "\n".join(format_plan_lines(self.result.plan, len(self.result.pages))))
        self.update_preview_image()

        padded_note = ""
        if self.result.total_pages != len(self.result.pages):
            padded_note = f" Padded to {self.result.total_pages} pages."
        self.status_var.set(
            f"Dry run preview ready for {source_name}. "
            f"{len(self.result.sheets)} imposed sides generated.{padded_note}"
        )

    def update_preview_image(self) -> None:
        if self.result is None or not self.result.sheets:
            self.preview_label.configure(image="", text="")
            self.sheet_counter_var.set("No preview loaded")
            return

        sheet = self.result.sheets[self.preview_index]
        preview = render_preview_image(sheet, PREVIEW_MAX_SIZE)
        self.preview_photo = ImageTk.PhotoImage(preview)
        self.preview_label.configure(image=self.preview_photo)
        self.sheet_counter_var.set(
            f"Sheet side {self.preview_index + 1} of {len(self.result.sheets)}"
        )

    def show_previous_sheet(self) -> None:
        if self.result is None or not self.result.sheets:
            return
        self.preview_index = (self.preview_index - 1) % len(self.result.sheets)
        self.update_preview_image()

    def show_next_sheet(self) -> None:
        if self.result is None or not self.result.sheets:
            return
        self.preview_index = (self.preview_index + 1) % len(self.result.sheets)
        self.update_preview_image()

    def export_pdf(self) -> None:
        try:
            options = self.options_from_ui()
            if self.result is None:
                pages, _source_name = load_source_pages(self.pdf_path, self.image_paths, options.dpi)
                self.result = build_imposed_sheets(pages, options)
        except CliError as exc:
            messagebox.showerror("Export Error", str(exc))
            return

        output_path = filedialog.asksaveasfilename(
            title="Save imposed PDF",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
        )
        if not output_path:
            return

        try:
            save_pdf(Path(output_path), self.result.sheets, options.dpi)
        except CliError as exc:
            messagebox.showerror("Export Error", str(exc))
            return

        self.status_var.set(f"Saved imposed PDF to {output_path}")
        messagebox.showinfo("Export Complete", f"Saved imposed PDF to:\n{output_path}")

    def run(self) -> int:
        self.root.mainloop()
        return 0


def command_ui(args: argparse.Namespace) -> int:
    app = ZineImposerUI(args)
    return app.run()


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
        if args.command == "ui":
            return command_ui(args)
        raise CliError(f"Unknown command: {args.command}")
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
