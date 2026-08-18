from pathlib import Path

from pypdf import PdfReader

from app.ingestion.parser import ParsedDocument


class PdfParser:
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path) -> ParsedDocument:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(pages)
        return ParsedDocument(
            text=text, source_type="pdf", metadata={"page_count": len(reader.pages)}
        )
