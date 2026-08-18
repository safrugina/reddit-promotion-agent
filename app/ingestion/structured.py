import json
from pathlib import Path

import yaml

from app.ingestion.parser import ParsedDocument

STRUCTURED_EXTENSIONS = {".json", ".yaml", ".yml"}


class JsonYamlParser:
    """Parses JSON/YAML into pretty-printed text, keeping the raw structure in metadata."""

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in STRUCTURED_EXTENSIONS

    def parse(self, path: Path) -> ParsedDocument:
        raw = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".json":
            data = json.loads(raw)
        else:
            data = yaml.safe_load(raw)
        text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        fmt = path.suffix.lower().lstrip(".")
        return ParsedDocument(text=text, source_type="structured", metadata={"format": fmt})
