# PDF-to-Word v1.0.2 Mode-Specific Acceptance Archive

Sample: `NIPS-2017-attention-is-all-you-need-Paper.pdf`, 11 pages.

| File | Intended use | Pages | mean MAD |
| --- | --- | ---: | ---: |
| `docx/editable.docx` | Edit text, formulas, and native tables | 11 -> 11 | 0.0737 |
| `docx/positioned.docx` | Native objects placed close to PDF coordinates | 11 -> 11 | 0.0495 |
| `docx/hybrid.docx` | Snapshot review with retained hidden object layer | 11 -> 11 | 0.0203 |
| `docx/fidelity.docx` | Visual archive with snapshot proof | 11 -> 11 | 0.0197 |

All four outputs have readable table column separators. Native modes use full Word cell grids; fidelity adds vertical DrawingML separators without adding a second table or blank rows. Formula behavior follows the mode contract documented in the project README.

Evidence is split by mode under `validation/`, `preflight/`, and `ir/`. The originating job directories are recorded in `RELEASE_METRICS.json`.
