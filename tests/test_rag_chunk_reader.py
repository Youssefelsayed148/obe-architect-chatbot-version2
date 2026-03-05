from tools.rag.load_embeddings import parse_chunk_line


def test_parse_chunk_line_valid_payload():
    line = (
        '{"url":"https://obearchitects.com/obe/project-detail.php?id=1",'
        '"title":"Project A","chunk_index":2,"chunk_text":"sample text","chunk_char_len":11}'
    )
    parsed = parse_chunk_line(line)
    assert parsed is not None
    assert parsed.url.endswith("id=1")
    assert parsed.title == "Project A"
    assert parsed.chunk_index == 2
    assert parsed.chunk_text == "sample text"
    assert parsed.chunk_char_len == 11


def test_parse_chunk_line_skips_empty_chunk():
    line = (
        '{"url":"https://obearchitects.com/obe/project-detail.php?id=1",'
        '"title":"Project A","chunk_index":0,"chunk_text":"   ","chunk_char_len":3}'
    )
    assert parse_chunk_line(line) is None
