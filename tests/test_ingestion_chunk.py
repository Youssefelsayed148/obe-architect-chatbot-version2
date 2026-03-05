from tools.ingestion.chunk_docs import chunk_text


def test_chunk_text_uses_overlap():
    text = "A" * 7000
    chunks = chunk_text(text, chunk_size_chars=3200, overlap_chars=250)
    assert len(chunks) == 3
    assert len(chunks[0]) == 3200
    assert chunks[0][-250:] == chunks[1][:250]


def test_chunk_text_rejects_invalid_overlap():
    try:
        chunk_text("abc", chunk_size_chars=300, overlap_chars=300)
        assert False, "Expected ValueError"
    except ValueError:
        assert True
