from __future__ import annotations

from typing import Protocol

from pdf2word.domain import DocumentIR
from pdf2word.pdf_backends import PdfBackend


class DocumentParser(Protocol):
    name: str

    def parse(self, backend: PdfBackend, pages: list[int]) -> DocumentIR:
        ...

