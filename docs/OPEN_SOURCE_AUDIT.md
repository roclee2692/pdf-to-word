# Open-Source Integration Audit

Audit date: 2026-07-20

## Result

The project now contains complete, non-shallow clones of the three planned optional parser repositories under `third_party/`. The application source still has no project-local root Git history, so the upstream commit pins are recorded in `third_party/README.md` and in every job's preflight artifact.

The project also has no local Git history or dependency lockfile, so the current runtime versions are verified facts for this machine rather than a fully reproducible repository snapshot.

## Confirmed local resources

| Resource | Local status | Actual use |
| --- | --- | --- |
| `pdfplumber` 0.11.10 | Installed in project `.venv` | `PdfPlumberBackend` opens the PDF and calls words, images, lines, rects, tables, and metadata APIs |
| `pypdfium2` 5.12.1 | Installed in project `.venv` | Renders page pixels for image crops |
| `python-docx` 1.2.0 | Installed in project `.venv` | `EditableDocxRenderer` creates paragraphs, tables, runs, headers, footers, and pictures |
| `Pillow` 12.3.0 | Installed in project `.venv` | Receives rendered page crops before they are written as PNGs |
| `pydantic` 2.13.4 | Installed in project `.venv` | Validates and serializes the Canonical Document IR |

## Missing optional resources

| Resource | Local status | Code status |
| --- | --- | --- |
| MinerU | Complete local clone; current project `.venv` probe is dependency-gated | Resource registry records the clone and prevents route selection until the entry point imports |
| Docling | Complete local clone; current project `.venv` probe is blocked by missing `docling_core`; model artifacts are not cached | Explicit opt-in route calls `DocumentConverter` when its runtime is installed; otherwise service records the failure and falls back to native |
| PaddleOCR | Complete local clone; runtime probe fails on missing `paddlex` | Resource registry records the clone and prevents route selection until the entry point imports |

The router now checks both the local clone and the actual upstream entry-point import. It persists repository status, commit, full-history status, import target, model-cache status, opt-in flag, and failure reason in `validation/preflight.json`; a cloned-but-uninstallable repository is not treated as executable.

## Verified call chain

`pdf2word.cli` -> `ConversionService` -> `PdfPlumberBackend` -> `PreflightAnalyzer` / `ParserRouter` -> `NativeTextParser` -> `EditableDocxRenderer` or `FidelityDocxRenderer`.

The native path is genuinely connected. Docling, MinerU, and PaddleOCR are selected only behind explicit capability probes and an opt-in flag; the current project `.venv` records all three as unavailable because their optional runtimes are not installed. This is an explicit, recorded limitation rather than a silent claim that all three upstream engines are production-ready.

## Sample evidence

The 11-page Attention paper has a native text layer on every page. The initial policy classifies pages 4, 5, and 7 as `docling` because of multi-column or formula-like signals. With external execution disabled by default, the current Phase 4 artifact records the preferred route and selects native; the optional runtime failures and clone commits remain visible in the preflight artifact.
