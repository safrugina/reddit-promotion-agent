import pytest

from app.knowledge.chunking import chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_text_returns_single_chunk():
    text = "This is a short project description."
    chunks = chunk_text(text, chunk_size=1000, overlap=100)
    assert chunks == [text]


def test_long_text_is_split_into_multiple_chunks():
    paragraph = "Paragraph sentence. " * 20  # ~400 chars
    text = "\n\n".join([paragraph] * 5)  # ~2000 chars

    chunks = chunk_text(text, chunk_size=500, overlap=50)

    assert len(chunks) > 1
    assert all(len(c) <= 500 + 50 for c in chunks)  # allow slack for overlap carry-over


def test_chunks_cover_all_paragraphs():
    paragraphs = [f"Paragraph number {i}. " * 10 for i in range(6)]
    text = "\n\n".join(paragraphs)

    chunks = chunk_text(text, chunk_size=300, overlap=30)

    joined = " ".join(chunks)
    for i in range(6):
        assert f"Paragraph number {i}." in joined


def test_rejects_invalid_chunk_size():
    with pytest.raises(ValueError):
        chunk_text("hello", chunk_size=0)


def test_rejects_overlap_gte_chunk_size():
    with pytest.raises(ValueError):
        chunk_text("hello", chunk_size=100, overlap=100)
