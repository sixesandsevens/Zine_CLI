# zine-imposer

`zine-imposer` is a small CLI for turning a normal PDF or a stack of page images
into print-ready booklet/zine sheets.

It pads page counts to a multiple of 4, rearranges pages into booklet order, and
exports an imposed PDF you can print duplex and fold into a tiny pamphlet.

## Features

- Accepts a source PDF or a list of images in reading order
- Pads short page counts with blanks automatically
- Outputs imposed PDF pages in booklet/zine order
- Supports `letter` and `a4`
- Includes a `plan` command to preview the page layout before rendering
- Can export PNG previews of each imposed sheet side

## Install

```bash
pip install -e .
```

After that, you can run:

```bash
zine-imposer --help
```

## Requirements

- Python 3.10+
- Pillow
- PyMuPDF

They are installed automatically through `pyproject.toml` when you use
`pip install -e .`.

## Usage

### Preview imposition order

```bash
zine-imposer plan --pages 8
```

Example output:

```text
Source pages: 8

Sheet 1 front: 8 | 1
Sheet 1 back : 2 | 7

Sheet 2 front: 6 | 3
Sheet 2 back : 4 | 5
```

If the source page count is not divisible by 4, blank pages are added
automatically:

```bash
zine-imposer plan --pages 10
```

### Impose a PDF

```bash
zine-imposer impose \
  --pdf "CoopAndDagger.pdf" \
  --output "CoopAndDagger_zine.pdf"
```

### Impose images

```bash
zine-imposer impose \
  --images cover.png p2.png p3.png p4.png p5.png p6.png p7.png p8.png \
  --output "CoopAndDagger_zine.pdf"
```

### Add slot labels and preview PNGs

```bash
zine-imposer impose \
  --pdf "CoopAndDagger.pdf" \
  --output "CoopAndDagger_zine.pdf" \
  --preview-dir previews \
  --page-labels
```

### Use A4 output

```bash
zine-imposer impose \
  --pdf "CoopAndDagger.pdf" \
  --output "CoopAndDagger_zine_a4.pdf" \
  --paper a4
```

## Commands

### `plan`

Preview booklet order for a source page count:

```bash
zine-imposer plan --pages 12
```

### `impose`

Create the imposed output PDF:

```bash
zine-imposer impose --pdf input.pdf --output output.pdf
```

or:

```bash
zine-imposer impose --images page1.png page2.png page3.png page4.png --output output.pdf
```

## Common options

- `--paper letter|a4`
- `--dpi 300`
- `--margin 60`
- `--gutter 30`
- `--bg white`
- `--page-labels`
- `--preview-dir previews`

## Print Notes

- Print double-sided
- Flip on short edge
- Print at 100% scale

## Notes

The tool rasterizes PDF pages before composing the final output PDF. That keeps
the workflow simple and reliable, though it means source vector text will not be
preserved as vector content in the output.

For illustrated zines and weird little pamphlets, that is usually perfectly
fine.
