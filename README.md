# PDF-to-Word

**Local-first PDF → editable Word (`.docx`)** with measurable quality gates.

Convert native-text PDFs into real Word documents you can edit—or into high-fidelity layouts that preserve pixel appearance. Deterministic code owns the main path; optional AI parsers are capability-gated; a validation engine decides pass/fail.

| | |
| --- | --- |
| **Release** | `v1.0.0-mvp` (2026-07-20) |
| **Pipeline** | Preflight → Route → Canonical IR → Render → Validate |
| **License** | Apache-2.0 |
| **Python** | ≥ 3.11 |

---

## Highlights

| Capability | Result (Attention paper, 11 pages) |
| --- | --- |
| Page count fidelity | **11 → 11** in all four modes |
| Text accuracy (`editable`) | **CER 0.0** |
| Native editable layout (`positioned`) | **mean MAD 0.0492** (≤ 0.055 gate) |
| Pixel proof (`hybrid` / `fidelity`) | **MAD 0.0198 / 0.0194** |
| Automated tests | **38 OK** (1 skipped) |
| Desktop UI | PySide6 GUI (preflight, convert, open DOCX) |

Artifacts: `workspace/archive/v1.0.0-mvp/` · Full write-up: [docs/DELIVERY_REPORT.md](docs/DELIVERY_REPORT.md)

---

## Two product paths

| Path | Modes | You care about… |
| --- | --- | --- |
| **Editable** | `editable`, `positioned` | Copy/paste, rewrite, native Word objects |
| **High fidelity** | `hybrid`, `fidelity` | Looks like the PDF (pixel MAD ≈ 0.02) |

### Mode guide

| Mode | What you get | MAD (baseline) | Best for |
| --- | --- | ---: | --- |
| **`editable`** | Flow paragraphs, real tables, soft page breaks | **0.0724** | Long-form editing & reflow |
| **`positioned`** | DrawingML text boxes, floating tables, image anchors | **0.0492** | Editable objects + coordinate layout |
| **`hybrid`** | Page snapshot behind + vanished editable layer | **0.0198** | Pixel-first, objects still in the package |
| **`fidelity`** | Snapshot-only visual proof | **0.0194** | Appearance proof / archival look |

---

## One-command setup

```bash
git clone <your-remote-url> PDF-to-Word   # or: git clone pdf2word-v1.0.0-mvp.gitbundle
cd PDF-to-Word
./scripts/setup.sh          # creates .venv, installs pinned deps + GUI
cp .env.example .env        # edit PDF2WORD_SOFFICE if needed
```

**Pinned core packages** (also in `requirements.txt` / `pyproject.toml`):

`pydantic==2.13.4` · `pdfplumber==0.11.10` · `pypdfium2==5.12.1` · `python-docx==1.2.0` · `Pillow==12.3.0` · GUI: `PySide6==6.11.1`

### LibreOffice (visual MAD / page count)

```bash
# macOS
brew install --cask libreoffice
# .env already points at:
# PDF2WORD_SOFFICE=/Applications/LibreOffice.app/Contents/MacOS/soffice
```

Details: [docs/SETUP_LIBREOFFICE.md](docs/SETUP_LIBREOFFICE.md)

---

## Quick start

### GUI (recommended for demos)

```bash
./start.sh gui
# equivalent: PYTHONPATH=src .venv/bin/python -m pdf2word gui
```

Drop a PDF → choose mode → **Preflight** or **Convert** → **Open output**.

### CLI convert

```bash
# Attention baseline, positioned mode, with validation
./start.sh convert NIPS-2017-attention-is-all-you-need-Paper.pdf \
  --pages 1-11 --mode positioned \
  --out workspace/jobs/demo/result.docx --dump-ir
```

### CLI flags

| Flag | Meaning |
| --- | --- |
| `--mode` | `editable` \| `positioned` \| `hybrid` \| `fidelity` |
| `--pages` | 1-based list/ranges, e.g. `1,3-5` |
| `--dump-ir` | Write Canonical IR JSON into the job folder |
| `--no-validate` | Skip post-render checks |
| `--no-visual-diff` | Structure/text/table/image only (no LibreOffice) |

Successful runs print `VALIDATION_PASSED` and, with LibreOffice,  
`VISUAL_PAGES: source=… rendered=… mean_mad=…`.

### Tests

```bash
./start.sh test
# or: PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

---

## Architecture (short)

```text
PDF → Preflight + Router → Parser (native / optional external)
    → Canonical IR (schema 1.4)
    → Renderer (editable | DrawingML family)
    → Validation (structure · text CER · table · image · visual MAD)
    → DOCX + job artifacts under workspace/jobs/
```

**Principles:** deterministic main chain · optional models for recognition · validator as gate · Agent repair deferred.

---

## Project layout

```text
src/pdf2word/     # package: cli, gui, IR, parsers, renderers, validation
tests/            # unit + integration
docs/             # delivery report, quality, setup, research
scripts/          # setup.sh
start.sh          # load .env and run convert | gui | test
.env.example      # PDF2WORD_SOFFICE and related knobs
requirements.txt  # pinned core deps
workspace/archive/v1.0.0-mvp/   # release DOCX + validation evidence
dist/releases/    # tarballs + git bundle (local packaging)
```

---

## Documentation

| Doc | Audience |
| --- | --- |
| [docs/DELIVERY_REPORT.md](docs/DELIVERY_REPORT.md) | **Project delivery report** (scope, metrics, reuse) |
| [docs/QUALITY_REPORT.md](docs/QUALITY_REPORT.md) | Detailed MAD / page-count audit trail |
| [docs/MVP.md](docs/MVP.md) | Implemented scope + next engineering steps |
| [docs/SETUP_LIBREOFFICE.md](docs/SETUP_LIBREOFFICE.md) | Visual validation install |
| [docs/OPEN_SOURCE_AUDIT.md](docs/OPEN_SOURCE_AUDIT.md) | Optional MinerU / Docling / PaddleOCR status |
| [third_party/README.md](third_party/README.md) | How to clone optional engines |

---

## What is deferred (post-MVP)

- Agent repair loop and IR patch storage  
- Full Docling / MinerU / PaddleOCR model runtimes  
- Scanned-page OCR; true cross-page table continuation  
- Nested formula OMML polish; pure-`positioned` page-2 residual  
- Cross-platform desktop packaging beyond macOS smoke  

External parsers stay **off** unless `PDF2WORD_ENABLE_EXTERNAL_PARSERS=1`.

---

## Backup & version freeze

| Item | Location |
| --- | --- |
| Git tag | `v1.0.0-mvp` on `main` |
| Evidence archive | `workspace/archive/v1.0.0-mvp/` |
| Packaged tarball | `dist/releases/pdf2word-v1.0.0-mvp-archive.tar.gz` |
| Offline git | `dist/releases/pdf2word-v1.0.0-mvp.gitbundle` |

**Push to remote** (when you have a GitHub/GitLab URL):

```bash
git remote add origin <YOUR_REPO_URL>
git push -u origin main
git push origin v1.0.0-mvp
```

Restore from bundle on another machine:

```bash
git clone pdf2word-v1.0.0-mvp.gitbundle PDF-to-Word
cd PDF-to-Word && git checkout v1.0.0-mvp
```

---

## Status in one line

Industrial, **validated** PDF→DOCX: use **`editable`** for semantics, **`positioned`** for native objects (MAD ≈ 0.049), **`hybrid`/`fidelity`** for pixel proof (MAD ≈ 0.02). OCR engines, full formula OMML, and Agent repair remain open.
