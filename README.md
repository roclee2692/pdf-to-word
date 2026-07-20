# PDF-to-Word

Local-first PDF → editable Word (`.docx`) reconstruction.

Pipeline: **preflight → route → Canonical IR → render → validate**.  
Deterministic code owns the main path; optional parsers are capability-gated; the validator decides pass/fail. The Agent repair loop is deferred.

**Release:** `v1.0.0-mvp` (2026-07-20)

## Requirements

- Python **≥ 3.11**
- Core deps: `pydantic`, `pdfplumber`, `pypdfium2`, `python-docx`, `Pillow`
- Optional GUI: `PySide6`
- Optional visual validation: [LibreOffice](docs/SETUP_LIBREOFFICE.md) + `PDF2WORD_SOFFICE`

```bash
cd /Users/raelon/Documents/Projects/PDF-to-Word
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[gui]'
# visual loop (macOS):
export PDF2WORD_SOFFICE="/Applications/LibreOffice.app/Contents/MacOS/soffice"
```

## CLI

```bash
export PDF2WORD_SOFFICE="/Applications/LibreOffice.app/Contents/MacOS/soffice"
PYTHONPATH=src .venv/bin/python -m pdf2word convert \
  "NIPS-2017-attention-is-all-you-need-Paper.pdf" \
  --pages 1-11 \
  --mode positioned \
  --out workspace/jobs/demo/result.docx \
  --dump-ir
```

Flags:

| Flag | Meaning |
| --- | --- |
| `--mode` | `editable` \| `positioned` \| `hybrid` \| `fidelity` |
| `--pages` | 1-based list/ranges, e.g. `1,3-5` |
| `--dump-ir` | Write Canonical IR JSON into the job folder |
| `--no-validate` | Skip post-render checks |
| `--no-visual-diff` | Keep structure/text/table/image; skip LibreOffice MAD |

Default validation prints `VALIDATION_PASSED`, layer statuses, and (when LO is available) `VISUAL_PAGES: source=… rendered=… mean_mad=…`.

## GUI

```bash
PYTHONPATH=src .venv/bin/python -m pdf2word gui
# or after install: pdf2word gui
```

Drop a PDF (or Browse), set page range (blank = all), pick a mode, then **Preflight** or **Convert**. The log shows routing and validation; **Open output** opens the DOCX via the desktop service.

## Mode selection

| Mode | What you get | Typical MAD (Attention 11p) | Best for |
| --- | --- | ---: | --- |
| `editable` | Flow paragraphs, real tables, soft page breaks | **0.0724** | Copy/edit, long-form reflow |
| `positioned` | DrawingML text boxes, floating tables, image anchors | **0.0492** | Editable objects + pixel gate ≤0.055 |
| `hybrid` | Page snapshot `behindDoc` + vanished editable layer | **0.0198** | Pixel-first with objects still in the package |
| `fidelity` | Snapshot-only proof paint | **0.0194** | Visual proof / pixel authority |

Notes:

- Prefer DrawingML (`wp:anchor` + `wps:txbx`); do **not** use `w:framePr` under LibreOffice (page-count collapse).
- `editable` uses continuous flow + soft breaks (hard per-page sections previously blew 11 → 21 pages).
- External parsers (Docling / MinerU / PaddleOCR) are **off** unless `PDF2WORD_ENABLE_EXTERNAL_PARSERS=1`; missing runtimes fall back to native.

## Acceptance (Attention paper, 11 pages)

Sample: `NIPS-2017-attention-is-all-you-need-Paper.pdf`  
Release run: `workspace/jobs/release-v1/` + archive `workspace/archive/v1.0.0-mvp/`

| Gate | Result |
| --- | --- |
| Page count | **11 → 11** (all four modes) |
| Text CER (`editable`) | **0.0** |
| `positioned` mean MAD | **0.0492** (≤ 0.055) |
| `hybrid` / `fidelity` mean MAD | **0.0198** / **0.0194** |
| Structure / table / image (`editable`) | pass |
| Unit tests | **38 OK** (1 skipped) |

## Tests

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

## Project layout

```text
src/pdf2word/
  cli.py              # convert + gui
  gui.py              # optional PySide6 shell
  domain/ir_models.py # Canonical IR (schema 1.4)
  pdf_backends/       # PdfPlumberBackend
  parsers/            # native + optional adapters
  routing/            # preflight + router
  renderers/          # editable + DrawingML fidelity family
  services/           # ConversionService
  storage/            # job workspace
  validation/         # structure / text / table / image / visual MAD
tests/
docs/                 # MVP, QUALITY_REPORT, SETUP_LIBREOFFICE, …
third_party/          # optional full clones (not required for native path)
workspace/
  jobs/               # per-run artifacts (gitignored)
  archive/v1.0.0-mvp/ # release DOCX + validation reports
```

## Docs

| File | Contents |
| --- | --- |
| [docs/MVP.md](docs/MVP.md) | Implemented scope + next engineering steps |
| [docs/QUALITY_REPORT.md](docs/QUALITY_REPORT.md) | MAD / page-count evidence |
| [docs/SETUP_LIBREOFFICE.md](docs/SETUP_LIBREOFFICE.md) | LO install + `PDF2WORD_SOFFICE` |
| [docs/OPEN_SOURCE_AUDIT.md](docs/OPEN_SOURCE_AUDIT.md) | Upstream clone / import status |
| [docs/RESEARCH.md](docs/RESEARCH.md) | External pain points and design choices |
| [third_party/README.md](third_party/README.md) | MinerU / Docling / PaddleOCR notes |

## Deferred (post-MVP)

- Agent repair loop + IR patch/revision storage
- Executable Docling model cache; MinerU / PaddleOCR runtimes (`paddlex`, modelscope, …)
- Scanned-page OCR path; real cross-page table continuation
- Further pure-`positioned` page-2 residual (~0.064 individual page)
- Cross-platform desktop packaging beyond macOS Cocoa smoke

## One-line status

Main chain is an **industrial, validated** PDF→DOCX path (page count, CER, MAD). Use `editable` for semantics, `positioned` for native objects (MAD ≈ 0.049), `hybrid`/`fidelity` for pixel proof (MAD ≈ 0.02). External OCR/parsers, full formula OMML, and Agent repair remain open.
