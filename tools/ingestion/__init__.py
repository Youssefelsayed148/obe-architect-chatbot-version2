__all__ = ["run_scrape", "chunk_documents", "smoke_validate_chunks"]


def run_scrape(*args, **kwargs):
    from tools.ingestion.scrape_site import run_scrape as _run_scrape

    return _run_scrape(*args, **kwargs)


def chunk_documents(*args, **kwargs):
    from tools.ingestion.chunk_docs import chunk_documents as _chunk_documents

    return _chunk_documents(*args, **kwargs)


def smoke_validate_chunks(*args, **kwargs):
    from tools.ingestion.chunk_docs import smoke_validate_chunks as _smoke_validate_chunks

    return _smoke_validate_chunks(*args, **kwargs)
