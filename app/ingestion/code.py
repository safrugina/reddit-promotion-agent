from pathlib import Path

from app.ingestion.parser import ParsedDocument

# Extensions known to be UTF-8 text we're happy to ingest as "source code".
# The fallback parser below also accepts any other file it can decode as UTF-8,
# so this set mainly documents intent rather than gatekeeping.
SOURCE_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".sh", ".sql", ".toml", ".ini",
    ".cfg", ".env",
}


class SourceCodeParser:
    """Handles known source-code extensions explicitly."""

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in SOURCE_CODE_EXTENSIONS

    def parse(self, path: Path) -> ParsedDocument:
        text = path.read_text(encoding="utf-8", errors="replace")
        return ParsedDocument(text=text, source_type="source_code")


class GenericTextFallbackParser:
    """Last-resort parser: any file that decodes as UTF-8 text."""

    def supports(self, path: Path) -> bool:
        try:
            path.read_bytes()[:4096].decode("utf-8")
        except (UnicodeDecodeError, OSError):
            return False
        return True

    def parse(self, path: Path) -> ParsedDocument:
        text = path.read_text(encoding="utf-8", errors="replace")
        return ParsedDocument(text=text, source_type="text")
