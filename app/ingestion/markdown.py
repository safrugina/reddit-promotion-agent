from pathlib import Path

from app.ingestion.parser import ParsedDocument

MARKDOWN_EXTENSIONS = {".md", ".markdown", ".txt"}


class MarkdownTextParser:
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in MARKDOWN_EXTENSIONS

    def parse(self, path: Path) -> ParsedDocument:
        text = path.read_text(encoding="utf-8", errors="replace")
        return ParsedDocument(text=text, source_type="markdown_txt")
