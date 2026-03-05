CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_documents (
  id BIGSERIAL PRIMARY KEY,
  url TEXT UNIQUE NOT NULL,
  title TEXT,
  doc_type TEXT,
  source TEXT,
  content_hash TEXT,
  scraped_at_utc TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE IF EXISTS rag_documents
  ADD COLUMN IF NOT EXISTS doc_type TEXT;

CREATE TABLE IF NOT EXISTS rag_chunks (
  id BIGSERIAL PRIMARY KEY,
  document_url TEXT NOT NULL REFERENCES rag_documents(url) ON DELETE CASCADE,
  chunk_index INT NOT NULL,
  chunk_text TEXT NOT NULL,
  chunk_char_len INT NOT NULL,
  embedding VECTOR(768) NOT NULL,
  embedding_model TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(document_url, chunk_index, embedding_model)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_document_url
  ON rag_chunks(document_url);

-- IVFFLAT performs best when created after substantial data load and can be rebuilt later.
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_ivfflat
  ON rag_chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
