from app.rag.retriever import RETRIEVAL_SQL, _row_to_match


def test_retrieval_sql_contains_expected_fields():
    sql = " ".join(RETRIEVAL_SQL.split())
    assert "rc.id AS chunk_id" in sql
    assert "rc.chunk_text" in sql
    assert "AS url" in sql
    assert "rd.title" in sql
    assert "rd.doc_type" in sql
    assert "AS score" in sql
    assert "ORDER BY score DESC, rc.id ASC" in sql


def test_row_to_match_keys():
    row = {"chunk_id": 7, "url": "https://example.com/a", "title": "A", "doc_type": "project", "chunk_text": "Chunk", "score": 0.9}
    match = _row_to_match(row)
    assert sorted(match.keys()) == ["chunk_id", "chunk_text", "doc_type", "score", "title", "url"]


def test_retrieve_chunks_unfiltered_uses_two_sql_params(monkeypatch):
    import app.rag.retriever as retriever

    class FakeCursor:
        def __init__(self):
            self.execute_calls = []

        def execute(self, sql, params):
            self.execute_calls.append((sql, params))

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class FakeConnection:
        def __init__(self, cursor):
            self._cursor = cursor

        def cursor(self, **_kwargs):
            return self._cursor

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class FakeEmbedder:
        def get_embeddings(self, _texts):
            return [[0.1, 0.2]]

    fake_cursor = FakeCursor()
    monkeypatch.setattr(retriever, "connect", lambda _dsn: FakeConnection(fake_cursor))

    retriever.retrieve_chunks(query="villa", top_k=5, min_score=0.0, embedder=FakeEmbedder())

    assert len(fake_cursor.execute_calls) == 1
    _sql, params = fake_cursor.execute_calls[0]
    assert len(params) == 2
    assert params[1] == 5


def test_retrieve_chunks_filtered_uses_three_sql_params(monkeypatch):
    import app.rag.retriever as retriever

    class FakeCursor:
        def __init__(self):
            self.execute_calls = []

        def execute(self, sql, params):
            self.execute_calls.append((sql, params))

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class FakeConnection:
        def __init__(self, cursor):
            self._cursor = cursor

        def cursor(self, **_kwargs):
            return self._cursor

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class FakeEmbedder:
        def get_embeddings(self, _texts):
            return [[0.1, 0.2]]

    fake_cursor = FakeCursor()
    monkeypatch.setattr(retriever, "connect", lambda _dsn: FakeConnection(fake_cursor))

    retriever.retrieve_chunks(
        query="villa",
        top_k=6,
        min_score=0.0,
        embedder=FakeEmbedder(),
        url_filters=[" https://obearchitects.com/obe/project-detail.php?id=65 ", ""],
    )

    assert len(fake_cursor.execute_calls) == 1
    _sql, params = fake_cursor.execute_calls[0]
    assert len(params) == 3
    assert params[1] == ["https://obearchitects.com/obe/project-detail.php?id=65"]
    assert params[2] == 6
