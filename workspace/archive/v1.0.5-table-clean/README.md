# v1.0.5-table-clean

Fix for hybrid/fidelity pages 8–9 extra table borders and page-1 chrome double-print.

## Root cause
- **fidelity** drew inferred vertical column lines (`_append_table_grid_overlay`) on top of the page snapshot → misaligned junk lines on STEM tables.
- **hybrid** floated native Word tables with borders over the page snapshot (text vanished, borders stayed) → double grids.
- Header/footer Word fields still painted while snapshot already contained page chrome.

## Fix
- `positioned` / `fidelity` + snapshot: page picture only.
- `hybrid` + snapshot: page picture + vanished searchable text only (no tables/images/separators).
- Hide Word header/footer runs when a page snapshot is present.

## Metrics (Attention 11p)
| mode | pages | mean MAD |
| positioned | 11→11 | 0.0194 |
| hybrid | 11→11 | 0.0194 |
| fidelity | 11→11 | 0.0194 |

Open `docx/hybrid.docx` and `docx/fidelity.docx` and check pages 8–9.
