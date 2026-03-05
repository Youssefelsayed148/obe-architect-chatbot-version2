def test_source_overview_is_clean_and_compact():
    import app.services.rag_public as rag_public

    source = rag_public._build_source_item(  # noqa: SLF001 - targeted parser validation
        {
            "url": "https://obearchitects.com/obe/project-detail.php?id=92",
            "title": "Modern Single storey villa",
            "chunk_text": (
                "Modern Single storey villa\n"
                "location: Dubai\n"
                "status: Completed\n"
                "built-up area: 2,845 sq.ft\n"
                "Simple and classy design in a modern look with wide windows and bright rooms.\n"
                "Projects Home Contact us"
            ),
        }
    )

    assert source["url"]
    assert source["title"]
    overview = str(source.get("overview") or "")
    assert overview
    assert len(overview) <= 220
    assert "location:" not in overview.lower()
    assert "status:" not in overview.lower()
