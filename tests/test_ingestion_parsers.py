import hashlib
import json
from pathlib import Path

from app.ingestion.code import GenericTextFallbackParser, SourceCodeParser
from app.ingestion.markdown import MarkdownTextParser
from app.ingestion.service import DEFAULT_PARSERS, find_parser, hash_content
from app.ingestion.structured import JsonYamlParser


def test_markdown_parser_supports_md_and_txt(tmp_path: Path):
    parser = MarkdownTextParser()
    assert parser.supports(tmp_path / "readme.md")
    assert parser.supports(tmp_path / "notes.txt")
    assert not parser.supports(tmp_path / "data.json")


def test_markdown_parser_reads_text(tmp_path: Path):
    file = tmp_path / "readme.md"
    file.write_text("# Title\n\nSome content.", encoding="utf-8")

    parsed = MarkdownTextParser().parse(file)

    assert parsed.text == "# Title\n\nSome content."
    assert parsed.source_type == "markdown_txt"


def test_json_yaml_parser_parses_json(tmp_path: Path):
    file = tmp_path / "config.json"
    file.write_text(json.dumps({"name": "demo", "version": 1}), encoding="utf-8")

    parsed = JsonYamlParser().parse(file)

    assert "demo" in parsed.text
    assert parsed.metadata["format"] == "json"


def test_source_code_parser_supports_py(tmp_path: Path):
    parser = SourceCodeParser()
    assert parser.supports(tmp_path / "main.py")
    assert not parser.supports(tmp_path / "readme.md")


def test_generic_fallback_supports_utf8_text(tmp_path: Path):
    file = tmp_path / "unknown.xyz"
    file.write_text("plain text content", encoding="utf-8")

    parser = GenericTextFallbackParser()

    assert parser.supports(file)
    assert parser.parse(file).text == "plain text content"


def test_generic_fallback_rejects_binary(tmp_path: Path):
    file = tmp_path / "binary.dat"
    file.write_bytes(bytes([0xFF, 0xFE, 0x00, 0x80, 0x01]))

    assert not GenericTextFallbackParser().supports(file)


def test_find_parser_prefers_specific_over_fallback(tmp_path: Path):
    file = tmp_path / "readme.md"
    file.write_text("hello", encoding="utf-8")

    parser = find_parser(file, DEFAULT_PARSERS)

    assert isinstance(parser, MarkdownTextParser)


def test_hash_content_is_deterministic_sha256():
    content = b"hello world"
    expected = hashlib.sha256(content).hexdigest()
    assert hash_content(content) == expected
    assert hash_content(content) == hash_content(content)


def test_hash_content_differs_for_different_bytes():
    assert hash_content(b"a") != hash_content(b"b")
