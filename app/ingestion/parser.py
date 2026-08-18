from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class ParsedDocument:
    text: str
    source_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentParser(Protocol):
    def supports(self, path: Path) -> bool: ...

    def parse(self, path: Path) -> ParsedDocument: ...
