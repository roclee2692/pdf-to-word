# Pinned upstream resources

These repositories are complete local clones used as optional parser resources. The application never imports them implicitly: a parser is executable only when its runtime dependencies and declared entry point pass the resource probe in `pdf2word.parsers.adapter_registry`.

| Resource | Local path | Commit | Runtime status |
| --- | --- | --- | --- |
| MinerU | `third_party/MinerU` | `79d6d8d79fb8f3ddba5cc34c07a16f0ec36f56c7` | cloned; runtime probe still dependency-gated |
| Docling | `third_party/docling` | `43f56c40191da8ddea14236b7c07e271cf359829` | project `.venv` probe blocked by `docling_core`; model artifacts not cached |
| PaddleOCR | `third_party/PaddleOCR` | `211989f046cc1878460f9e65574690c00a127a1a` | cloned; dependencies not installed |

The exact commit, full-history flag, import probe, and failure reason are persisted in each job's `validation/preflight.json`.
