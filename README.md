# Zine Imposer

> Turn your PDF into a printable zine in one command.

A small CLI tool for converting PDFs or images into print-ready zine / booklet
layout.

Takes your pages in normal reading order and rearranges them into proper
booklet imposition so you can:

- Print double-sided
- Fold in half
- Staple
- Done

---

## Features

- Accepts PDF or image input
- Automatically pads page count to multiples of 4
- Outputs print-ready imposed PDF
- Supports Letter and A4
- Optional page numbering overlay
- Optional preview image export
- Optional crop marks and fold guide
- Terminal dry-run planning
- Desktop preview UI
- Simple CLI interface

---

## Installation

### Option 1: Install with pipx

```bash
pipx install .
```

Then run:

```bash
zine-imposer --help
zine --help
```

### Option 2: Install locally for development

```bash
pip install -e .
```

Then run:

```bash
zine-imposer --help
zine --help
```

If editable install is awkward on your system, using a virtual environment is
the smoothest path:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Option 3: Run without installing

```bash
python3 zine_imposer_cli.py --help
```

### UI note

The desktop UI needs:

- `python3-tk`
- Pillow with `ImageTk` support

On Pop!_OS / Ubuntu, install Tkinter with:

```bash
sudo apt install python3-tk
```

## Usage

### 1. Impose a PDF

```bash
zine-imposer impose \
  --pdf "input.pdf" \
  --output "output_zine.pdf"
```

Shortcut:

```bash
zine impose \
  --pdf "input.pdf" \
  --output "output_zine.pdf"
```

### 2. Impose images

```bash
zine-imposer impose \
  --images page1.png page2.png page3.png page4.png \
           page5.png page6.png page7.png page8.png \
  --output "output_zine.pdf"
```

### 3. Preview imposition layout

```bash
zine-imposer plan --pages 8
```

Example output:

```text
Sheet 1 front: 8 | 1
Sheet 1 back : 2 | 7

Sheet 2 front: 6 | 3
Sheet 2 back : 4 | 5
```

### 4. Dry-run a real file before export

```bash
zine-imposer impose \
  --pdf "input.pdf" \
  --dry-run
```

This prints the exact imposed sheet order without writing the final PDF.

### 5. Open the desktop preview UI

```bash
zine-imposer ui
```

The UI lets you:

- choose a PDF or image set
- tweak layout settings
- preview each physical sheet as front/back together
- jump directly between sheet sides with the thumbnail strip
- export the imposed PDF after the dry run looks right

### 6. Generate preview images

```bash
zine-imposer impose \
  --pdf "input.pdf" \
  --output "output.pdf" \
  --preview-dir previews \
  --page-labels
```

### 7. Add crop marks and a fold guide

```bash
zine-imposer impose \
  --pdf "input.pdf" \
  --output "output.pdf" \
  --crop-marks \
  --fold-guide
```

If your path contains spaces or `&`, quote the whole path:

```bash
zine-imposer impose \
  --pdf "/home/christi/Desktop/Coop&Dagger/Coop&Dagger.pdf" \
  --dry-run
```

## Options

| Option | Description |
| --- | --- |
| `--paper` | `letter` (default) or `a4` |
| `--dpi` | Output DPI, default `300` |
| `--margin` | Outer margin in pixels |
| `--gutter` | Space between pages |
| `--bg` | Background color |
| `--page-labels` | Show page numbers on imposed sheets |
| `--preview-dir` | Export PNG previews |
| `--crop-marks` | Draw crop marks near the outer corners |
| `--fold-guide` | Draw a dashed line at the center fold |
| `--dry-run` | Print the imposition plan without writing the PDF |

## Printing Instructions

To assemble your zine correctly:

- Print double-sided
- Flip on short edge
- Print at 100% scale

Then:

- Stack pages
- Fold in half
- Staple along fold

If you enabled guides:

- Use crop marks as trim references
- Use the dashed center line as the fold guide

## How It Works

The tool rearranges pages into booklet order.

Example for 8 pages:

```text
Sheet 1 front: 8 | 1
Sheet 1 back : 2 | 7
Sheet 2 front: 6 | 3
Sheet 2 back : 4 | 5
```

This ensures pages appear in the correct order after folding.

## Notes

- PDF input is rasterized into images for consistent layout
- Output is optimized for printing, not editing
- Page count is padded automatically with blanks if needed
- Crop marks and fold guide are optional so clean output stays available
- The desktop UI uses the same layout engine as the CLI dry run and export

## Future Ideas

- Signature splitting for larger booklets
- Native PDF preservation without rasterization

## Linux Launcher Notes

A starter desktop launcher template lives at
[packaging/linux/zine-imposer.desktop](/home/christi/Projects/Zine_CLI/packaging/linux/zine-imposer.desktop).

For future Linux packaging work, the usual targets would be:

- desktop file: `share/applications/zine-imposer.desktop`
- app icon: `share/icons/hicolor/256x256/apps/zine-imposer.png`

The template is already set up to launch:

```bash
zine-imposer ui
```

If you later build a Debian package or app bundle, that template and the
bundled package icon should give you a clean starting point.

## Debian Package Notes

A starter Debian package layout lives under
[packaging/deb](/home/christi/Projects/Zine_CLI/packaging/deb).

To build a local `.deb` from the current source tree:

```bash
./packaging/deb/build-deb.sh
```

That produces a package like:

```bash
packaging/deb/dist/zine-imposer_0.1.1_all.deb
```

Install it with:

```bash
sudo apt install ./packaging/deb/dist/zine-imposer_0.1.1_all.deb
```

The Debian package includes:

- `/usr/bin/zine-imposer`
- `/usr/bin/zine`
- the desktop launcher
- the 256px app icon
- the bundled Python package under `/usr/lib/zine-imposer/src`

## License

MIT

## Why?

Because sometimes you need to turn a weird idea into a physical object.

Like a chicken-themed tabletop RPG.
