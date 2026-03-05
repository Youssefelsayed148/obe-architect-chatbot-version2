import re

import pytest


def test_answer_question_answerable(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(rag_public.settings, "rag_public_top_k", 5)
    monkeypatch.setattr(rag_public.settings, "rag_public_min_confidence", 0.55)
    monkeypatch.setattr(rag_public.settings, "min_similarity_score", 0.75)
    monkeypatch.setattr(rag_public.settings, "rag_public_max_context_chars", 4000)
    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "chunk_id": 1,
                "url": "https://obearchitects.com/obe/project-detail.php?id=64",
                "title": "Minimal Villa",
                "chunk_text": "location: Dubai status: Completed built-up area: 2,845 sq.ft",
                "score": 0.91,
                "doc_type": "project",
            },
            {
                "chunk_id": 2,
                "url": "https://obearchitects.com/obe/project-detail.php?id=72",
                "title": "Country Side Luxurious Villa",
                "chunk_text": "location: Abu Dhabi status: Under Construction built-up area: 15,000 sq.ft",
                "score": 0.90,
                "doc_type": "project",
            }
        ],
    )

    class FailIfCalledClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def chat(self, *_args, **_kwargs):
            raise AssertionError("category overview should not call chat")

    monkeypatch.setattr(rag_public, "OllamaClient", FailIfCalledClient)

    result = rag_public.answer_question("tell me more about villas", top_k=3)

    assert "Villas Designed by OBE Architects" in result.answer
    first_line = result.answer.splitlines()[0].strip()
    assert first_line == "Villas Designed by OBE Architects"
    assert first_line != "Minimal Villa"
    assert "KEY HIGHLIGHTS" in result.answer
    assert re.search(r"(?m)^.*\*\*[A-Za-z/&\-\s]+:\*\* .+", result.answer)
    assert result.sources
    assert len(result.sources) <= 3
    assert all("project-detail.php?id=" in src["url"] for src in result.sources)
    assert result.confidence == pytest.approx(0.91)
    assert result.route_taken == "rag"
    assert result.retrieval_top_score == pytest.approx(0.91)
    assert result.retrieval_k == 10
    assert result.fallback_reason is None


def test_stable_sort_matches_uses_chunk_id_tiebreaker():
    import app.services.rag_public as rag_public

    matches = [
        {"chunk_id": 9, "score": 0.87, "url": "https://example.com/b", "chunk_text": "B"},
        {"chunk_id": 2, "score": 0.87, "url": "https://example.com/a", "chunk_text": "A"},
        {"chunk_id": 5, "score": 0.90, "url": "https://example.com/c", "chunk_text": "C"},
    ]

    sorted_matches = rag_public._stable_sort_matches(matches)  # noqa: SLF001
    assert [item["chunk_id"] for item in sorted_matches] == [5, 2, 9]


def test_answer_question_unanswerable_when_no_matches(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(rag_public.settings, "rag_public_min_confidence", 0.55)
    monkeypatch.setattr(rag_public, "retrieve_chunks", lambda **_kwargs: [])

    class FailIfCalledClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def chat(self, *_args, **_kwargs):
            raise AssertionError("chat should not be called without matches")

    monkeypatch.setattr(rag_public, "OllamaClient", FailIfCalledClient)

    result = rag_public.answer_question("Unknown topic", top_k=3)

    assert "KEY HIGHLIGHTS" in result.answer
    assert "I don't know based on the available sources." not in result.answer
    assert 0 <= len(result.sources) <= 3
    assert all("project-detail.php?id=" in src["url"] for src in result.sources)
    assert all("about-us.php" not in src["url"] for src in result.sources)
    assert result.confidence == 0.0
    assert result.route_taken == "fallback"
    assert result.retrieval_top_score is None
    assert result.retrieval_k == 8
    assert result.fallback_reason == "no_chunks"


def test_answer_question_low_similarity_category_does_not_fallback(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(rag_public.settings, "min_similarity_score", 0.75)
    monkeypatch.setattr(rag_public, "retrieve_chunks", lambda **_kwargs: [
        {
            "chunk_id": 3,
            "url": "https://obearchitects.com/obe/project-detail.php?id=64",
            "title": "Minimal Villa",
            "chunk_text": "OBE Architects designs custom villas.",
            "score": 0.62,
        }
    ])

    class FailIfCalledClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def chat(self, *_args, **_kwargs):
            raise AssertionError("category overview should not call chat")

    monkeypatch.setattr(rag_public, "OllamaClient", FailIfCalledClient)

    result = rag_public.answer_question("tell me about villas", top_k=3)
    assert "Villas Designed by OBE Architects" in result.answer
    assert "KEY HIGHLIGHTS" in result.answer
    assert "I couldn't retrieve enough portfolio text to answer that precisely." not in result.answer
    assert result.route_taken == "rag"
    assert result.fallback_reason is None
    assert result.retrieval_top_score == pytest.approx(0.62)
    assert result.retrieval_k == 10
def test_category_overview_villas_never_uses_structured_fallback_phrase(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(rag_public.settings, "min_similarity_score_category", 0.95)
    monkeypatch.setattr(rag_public.settings, "rag_public_min_confidence", 0.99)
    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "chunk_id": 1,
                "url": "https://obearchitects.com/obe/project-detail.php?id=64",
                "title": "Minimal Villa",
                "chunk_text": "location: Dubai status: Completed built-up area: 2,845 sq.ft",
                "score": 0.62,
                "doc_type": "project",
            },
            {
                "chunk_id": 2,
                "url": "https://obearchitects.com/obe/project-detail.php?id=72",
                "title": "Country Side Luxurious Villa",
                "chunk_text": "location: Abu Dhabi status: Under Construction built-up area: 15,000 sq.ft",
                "score": 0.61,
                "doc_type": "project",
            },
        ],
    )

    result = rag_public.answer_question("tell me about villas", top_k=5)

    assert result.route_taken == "rag"
    assert result.fallback_reason is None
    assert result.answer.splitlines()[0].strip() == "Villas Designed by OBE Architects"
    assert "KEY HIGHLIGHTS" in result.answer
    assert "I couldn't retrieve enough portfolio text to answer that precisely." not in result.answer


def test_answer_question_ollama_failure_fallback_for_non_category(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(rag_public.settings, "rag_public_min_confidence", 0.55)
    monkeypatch.setattr(rag_public.settings, "rag_public_max_context_chars", 4000)
    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=92",
                "title": "The Court Villa",
                "chunk_text": "location: Dubai status: Completed built-up area: 9,000 sq.ft",
                "score": 0.88,
            }
        ],
    )

    class BrokenOllamaClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def chat(self, *_args, **_kwargs):
            raise RuntimeError("ollama unavailable")

    monkeypatch.setattr(rag_public, "OllamaClient", BrokenOllamaClient)

    result = rag_public.answer_question("Tell me more about Court Villa", top_k=3)

    assert "KEY HIGHLIGHTS" in result.answer
    assert result.sources[0]["url"] == "https://obearchitects.com/obe/project-detail.php?id=92"
    assert result.sources[0]["title"] == "The Court Villa"
    assert result.sources[0]["location"] == "Dubai"
    assert result.sources[0]["status"] == "Completed"
    assert result.sources[0]["size"] == "9,000 sq.ft"
    assert result.confidence == pytest.approx(0.88)
    assert result.route_taken == "fallback"
    assert result.fallback_reason == "other"


def test_answer_question_prefers_context_urls_then_falls_back(monkeypatch):
    import app.services.rag_public as rag_public

    calls = []

    def fake_retrieve_chunks(**kwargs):
        calls.append(kwargs)
        url_filters = kwargs.get("url_filters")
        if url_filters:
            return []
        return [
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=65",
                "title": "The Court Villa",
                "chunk_text": "location: Dubai status: Completed built-up area: 9,000 sq.ft",
                "score": 0.9,
            }
        ]

    monkeypatch.setattr(rag_public.settings, "rag_public_min_confidence", 0.55)
    monkeypatch.setattr(rag_public.settings, "rag_public_max_context_chars", 4000)
    monkeypatch.setattr(rag_public, "retrieve_chunks", fake_retrieve_chunks)

    class FakeOllamaClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def chat(self, *_args, **_kwargs):
            return "Court Villa\n\n**Key highlights**\n- **Location:** Dubai"

    monkeypatch.setattr(rag_public, "OllamaClient", FakeOllamaClient)

    result = rag_public.answer_question(
        "Tell me more about Court Villa",
        top_k=3,
        context_urls=["https://obearchitects.com/obe/project-detail.php?id=65"],
    )
    assert calls
    assert calls[0].get("url_filters") == ["https://obearchitects.com/obe/project-detail.php?id=65"]
    assert len(calls) >= 2
    assert result.sources
    assert len(result.sources) <= 3
    assert all("project-detail.php?id=" in src["url"] for src in result.sources)


def test_answer_question_filters_non_project_pages_and_caps_to_three(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(rag_public.settings, "rag_public_min_confidence", 0.1)
    monkeypatch.setattr(rag_public.settings, "rag_public_max_context_chars", 6000)
    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "url": "https://obearchitects.com/obe/about-us.php",
                "title": "About OBE",
                "chunk_text": "Our mission and company profile.",
                "score": 0.99,
                "doc_type": "page",
            },
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=64",
                "title": "Minimal Villa",
                "chunk_text": "built-up area: 9,900 sq.ft",
                "score": 0.98,
            },
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=65",
                "title": "Court Villa",
                "chunk_text": "location: Dubai status: Completed",
                "score": 0.97,
            },
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=72",
                "title": "Country Side Luxurious Villa",
                "chunk_text": "area: 15,000 sq.ft",
                "score": 0.96,
            },
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=92",
                "title": "Modern Single storey villa",
                "chunk_text": "location: Dubai",
                "score": 0.95,
            },
        ],
    )

    class FakeOllamaClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def chat(self, *_args, **_kwargs):
            return "Villas\n\n**Key highlights**\n- **Detail:** Test"

    monkeypatch.setattr(rag_public, "OllamaClient", FakeOllamaClient)

    result = rag_public.answer_question("tell me more about villas", top_k=8)

    assert len(result.sources) <= 3
    assert all("project-detail.php?id=" in src["url"] for src in result.sources)


def test_category_overview_for_commercial_has_expected_title_and_structure(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(rag_public.settings, "rag_public_min_confidence", 0.55)
    monkeypatch.setattr(rag_public.settings, "min_similarity_score", 0.75)
    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "chunk_id": 10,
                "url": "https://obearchitects.com/obe/project-detail.php?id=60",
                "title": "Business Center At Al Quoz",
                "chunk_text": "location: Dubai status: Completed built-up area: 12,000 sq.ft",
                "score": 0.89,
                "doc_type": "project",
            },
            {
                "chunk_id": 11,
                "url": "https://obearchitects.com/obe/project-detail.php?id=54",
                "title": "Community Retail Center",
                "chunk_text": "location: Dubai status: Design Competition built-up area: 9,900 sq.ft",
                "score": 0.88,
                "doc_type": "project",
            },
        ],
    )

    result = rag_public.answer_question("tell me about commercial projects", top_k=5)
    assert "Commercial Projects by OBE Architects" in result.answer
    assert "KEY HIGHLIGHTS" in result.answer
    assert re.search(r"(?m)^.*\*\*[A-Za-z/&\-\s]+:\*\* .+", result.answer)


def test_category_query_does_not_route_to_project_detail_handler(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(rag_public.settings, "min_similarity_score", 0.75)
    monkeypatch.setattr(rag_public, "retrieve_chunks", lambda **_kwargs: [
        {
            "chunk_id": 1,
            "url": "https://obearchitects.com/obe/project-detail.php?id=64",
            "title": "Minimal Villa",
            "chunk_text": "location: Dubai status: Completed built-up area: 2,845 sq.ft",
            "score": 0.9,
            "doc_type": "project",
        },
        {
            "chunk_id": 2,
            "url": "https://obearchitects.com/obe/project-detail.php?id=72",
            "title": "Country Side Luxurious Villa",
            "chunk_text": "location: Abu Dhabi status: Under Construction built-up area: 15,000 sq.ft",
            "score": 0.89,
            "doc_type": "project",
        },
    ])

    class FailIfCalledClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def chat(self, *_args, **_kwargs):
            raise AssertionError("LLM project-detail flow should not be used for category query")

    monkeypatch.setattr(rag_public, "OllamaClient", FailIfCalledClient)
    result = rag_public.answer_question("tell me more about villas", top_k=5)
    assert result.answer.splitlines()[0].strip() == "Villas Designed by OBE Architects"
    assert "KEY HIGHLIGHTS" in result.answer
    assert len(result.sources) <= 3
    assert all("project-detail.php?id=" in src["url"] for src in result.sources)


def test_category_switching_overrides_previous_context(monkeypatch):
    import app.services.rag_public as rag_public

    calls = []

    def fake_retrieve_chunks(**kwargs):
        calls.append(kwargs)
        return [
            {
                "chunk_id": 20,
                "url": "https://obearchitects.com/obe/project-detail.php?id=60",
                "title": "Business Center At Al Quoz",
                "chunk_text": "location: Dubai status: Completed built-up area: 12,000 sq.ft commercial project",
                "score": 0.91,
                "doc_type": "project",
            },
            {
                "chunk_id": 21,
                "url": "https://obearchitects.com/obe/project-detail.php?id=54",
                "title": "Community Retail Center",
                "chunk_text": "location: Dubai status: Design Competition built-up area: 9,900 sq.ft commercial",
                "score": 0.90,
                "doc_type": "project",
            },
        ]

    monkeypatch.setattr(rag_public.settings, "min_similarity_score", 0.75)
    monkeypatch.setattr(rag_public, "retrieve_chunks", fake_retrieve_chunks)
    result = rag_public.answer_question(
        "tell me about commercial projects",
        top_k=5,
        context_urls=["https://obearchitects.com/obe/project-detail.php?id=999-sports"],
    )

    assert result.answer.splitlines()[0].strip() == "Commercial Projects by OBE Architects"
    assert "KEY HIGHLIGHTS" in result.answer
    assert all(call.get("url_filters") in (None, []) for call in calls)
    assert result.sources == []


def test_commercial_category_overview_does_not_fail_when_chunks_lack_commercial_keyword(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(rag_public.settings, "min_similarity_score", 0.75)
    monkeypatch.setattr(rag_public, "retrieve_chunks", lambda **_kwargs: [
        {
            "chunk_id": 31,
            "url": "https://obearchitects.com/obe/project-detail.php?id=60",
            "title": "Business Center At Al Quoz",
            "chunk_text": "location: Dubai status: Completed built-up area: 12,000 sq.ft",
            "score": 0.90,
            "doc_type": "project",
        },
        {
            "chunk_id": 32,
            "url": "https://obearchitects.com/obe/project-detail.php?id=54",
            "title": "Community Retail Center",
            "chunk_text": "location: Dubai status: Design Competition built-up area: 9,900 sq.ft",
            "score": 0.89,
            "doc_type": "project",
        },
    ])

    result = rag_public.answer_question("tell me about commercial projects", top_k=5)
    assert result.route_taken == "rag"
    assert result.answer.splitlines()[0].strip() == "Commercial Projects by OBE Architects"
    assert "KEY HIGHLIGHTS" in result.answer


def test_sanitize_answer_enforces_template():
    import app.services.rag_public as rag_public

    out = rag_public._sanitize_answer(  # noqa: SLF001
        "Random paragraph about villas. * area is large.\nFollow-up question: one?\nFollow-up question: two?"
    )
    assert "KEY HIGHLIGHTS" in out
    assert out.count("Follow-up question:") <= 1


def test_answer_question_passes_stable_sampling_options(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(rag_public.settings, "rag_public_min_confidence", 0.1)
    monkeypatch.setattr(rag_public.settings, "rag_public_max_context_chars", 4000)
    monkeypatch.setattr(rag_public.settings, "rag_llm_temperature", 0.25)
    monkeypatch.setattr(rag_public.settings, "rag_llm_top_p", 0.9)
    monkeypatch.setattr(rag_public.settings, "rag_llm_repeat_penalty", 1.08)
    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=65",
                "title": "The Court Villa",
                "doc_type": "project",
                "chunk_text": "location: Dubai status: Completed",
                "score": 0.9,
            }
        ],
    )

    captured = {}

    class FakeOllamaClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def chat(self, *_args, **kwargs):
            captured.update(kwargs)
            return "Court Villa\n\n**Key highlights**\n- **Location:** Dubai"

    monkeypatch.setattr(rag_public, "OllamaClient", FakeOllamaClient)

    result = rag_public.answer_question("Tell me more about Court Villa", top_k=3)
    assert result.sources
    assert captured["options"]["temperature"] == 0.25
    assert captured["options"]["top_p"] == 0.9
    assert captured["options"]["repeat_penalty"] == 1.08


def test_follow_up_question_is_grounded_to_context():
    import app.services.rag_public as rag_public

    out = rag_public._sanitize_answer(  # noqa: SLF001
        (
            "Villas Designed by OBE Architects\n\n"
            "**Key highlights**\n"
            "- **Location:** Dubai\n"
            "- **Built-up area:** 9,000 sq.ft\n\n"
            "Follow-up question: Which project has the largest built-up area?"
        ),
        context_text="The Court Villa location Dubai built-up area 9,000 sq.ft",
        sources=[
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=65",
                "title": "The Court Villa",
                "location": "Dubai",
                "status": "Completed",
                "size": "9,000 sq.ft",
                "overview": "Charming design with open green spaces.",
            }
        ],
    )
    assert "Follow-up question:" in out
    assert out.count("Follow-up question:") == 1


def test_offtopic_follow_up_gets_replaced_or_removed():
    import app.services.rag_public as rag_public

    out = rag_public._sanitize_answer(  # noqa: SLF001
        (
            "Villas Designed by OBE Architects\n\n"
            "**Key highlights**\n"
            "- **Location:** Dubai\n\n"
            "Follow-up question: What is your design philosophy for skyscraper cities?"
        ),
        context_text="The Court Villa location Dubai status Completed",
        sources=[
            {
                "url": "https://obearchitects.com/obe/project-detail.php?id=65",
                "title": "The Court Villa",
                "location": "Dubai",
                "status": "Completed",
                "size": None,
                "overview": "Charming design with open green spaces.",
            }
        ],
    )
    assert "design philosophy" not in out.lower()
    assert out.count("Follow-up question:") == 1


def test_normalize_sources_supports_legacy_urls():
    import app.services.rag_public as rag_public

    out = rag_public._normalize_sources(  # noqa: SLF001 - validating backward compatibility helper
        ["https://obearchitects.com/obe/project-detail.php?id=65"]
    )
    assert out == [
        {
            "url": "https://obearchitects.com/obe/project-detail.php?id=65",
            "title": "Source",
            "location": None,
            "status": None,
            "size": None,
            "overview": None,
        }
    ]


def test_build_source_item_extracts_structured_fields():
    import app.services.rag_public as rag_public

    src = rag_public._build_source_item(  # noqa: SLF001 - validating parser behavior
        {
            "url": "https://obearchitects.com/obe/project-detail.php?id=65",
            "title": "",
            "chunk_text": (
                "The Court Villa\n"
                "client: Private\n"
                "location: Dubai\n"
                "status: Completed\n"
                "built-up area: 2,845 sq.ft\n"
                "Charming design with open green spaces."
            ),
        }
    )
    assert src["title"] == "The Court Villa"
    assert src["location"] == "Dubai"
    assert src["status"] == "Completed"
    assert src["size"] == "2,845 sq.ft"
    assert "Charming design" in str(src["overview"])


def test_stability_contract_category_title_for_education(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(rag_public.settings, "min_similarity_score_category", 0.65)
    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "chunk_id": 1,
                "url": "https://obearchitects.com/obe/projectlists.php?category=education",
                "title": "Education",
                "chunk_text": "location: Dubai status: Completed built-up area: 10,000 sq.ft",
                "score": 0.9,
                "doc_type": "page",
            }
        ],
    )

    result = rag_public.answer_question("tell me about education projects", top_k=5)
    assert result.answer.splitlines()[0].strip() == "Education Projects by OBE Architects"
    assert "KEY HIGHLIGHTS" in result.answer
    assert "Random Project" not in result.answer.splitlines()[0]


def test_stability_contract_category_switching_to_commercial(monkeypatch):
    import app.services.rag_public as rag_public

    calls = []

    def fake_retrieve_chunks(**kwargs):
        calls.append(kwargs)
        return [
            {
                "chunk_id": 2,
                "url": "https://obearchitects.com/obe/projectlists.php?category=commercial",
                "title": "Commercial",
                "chunk_text": "commercial projects in Dubai",
                "score": 0.89,
                "doc_type": "page",
            }
        ]

    monkeypatch.setattr(rag_public.settings, "min_similarity_score_category", 0.65)
    monkeypatch.setattr(rag_public, "retrieve_chunks", fake_retrieve_chunks)
    result = rag_public.answer_question(
        "tell me about commercial projects",
        top_k=5,
        context_urls=["https://obearchitects.com/obe/project-detail.php?id=78"],
    )
    assert result.answer.splitlines()[0].strip() == "Commercial Projects by OBE Architects"
    assert all(call.get("url_filters") in (None, []) for call in calls)


def test_stability_contract_category_overview_bullets_max_six(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(rag_public.settings, "min_similarity_score_category", 0.65)
    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "chunk_id": 3,
                "url": "https://obearchitects.com/obe/projectlists.php?category=sports",
                "title": "Sports",
                "chunk_text": (
                    "location: Dubai status: Completed built-up area: 12,000 sq.ft "
                    "number of floors: 2 design style: Contemporary features: Football stadium "
                    "typical spaces: Grandstand materials: Steel site context: Urban"
                ),
                "score": 0.9,
                "doc_type": "page",
            }
        ],
    )
    result = rag_public.answer_question("tell me about sports projects", top_k=5)
    bullets = [line for line in result.answer.splitlines() if line.strip().startswith("- **")]
    assert len(bullets) <= 6


def test_stability_contract_no_generic_fallback_phrase(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(rag_public, "retrieve_chunks", lambda **_kwargs: [])
    result = rag_public.answer_question("unknown ask", top_k=3)
    assert "I don't know based on the available sources." not in result.answer


def test_category_overview_ignores_rag_public_min_confidence_gate(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(rag_public.settings, "min_similarity_score_category", 0.65)
    monkeypatch.setattr(rag_public.settings, "rag_public_min_confidence", 0.95)
    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "chunk_id": 4,
                "url": "https://obearchitects.com/obe/projectlists.php?category=sports",
                "title": "Sports",
                "chunk_text": "location: Dubai status: Completed built-up area: 12,000 sq.ft",
                "score": 0.8,
                "doc_type": "page",
            }
        ],
    )

    result = rag_public.answer_question("tell me about sports projects", top_k=5)

    assert result.route_taken == "rag"
    assert result.fallback_reason is None
    assert result.retrieval_top_score == pytest.approx(0.8)
    assert result.answer.splitlines()[0].strip() == "Sports Facilities Designed by OBE Architects"


def test_stability_contract_drops_unsupported_numeric_fact():
    import app.services.rag_public as rag_public

    out = rag_public._sanitize_answer(  # noqa: SLF001
        "Test\n\n**Key highlights**\n- **Built-up area:** 99,999 sq.ft",
        context_text="The Court Villa built-up area 9,000 sq.ft in Dubai.",
        sources=[{"url": "https://obearchitects.com/obe/project-detail.php?id=65", "title": "The Court Villa"}],
        route_kind=rag_public.ROUTE_PROJECT_DETAIL,
    )
    assert "99,999 sq.ft" not in out


def test_category_overview_returns_follow_up_buttons(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "chunk_id": 1,
                "url": "https://obearchitects.com/obe/project-detail.php?id=64",
                "title": "Minimal Villa",
                "chunk_text": "location: Dubai status: Completed built-up area: 2,845 sq.ft",
                "score": 0.91,
                "doc_type": "project",
            }
        ],
    )

    class FakeOllamaClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def chat(self, *_args, **_kwargs):
            return "Villas Designed by OBE Architects\n\n**Key highlights**\n- **Location:** Dubai"

    monkeypatch.setattr(rag_public, "OllamaClient", FakeOllamaClient)

    result = rag_public.answer_question("tell me about villas", top_k=5)
    assert len(result.follow_up_buttons) <= 1
    assert "Follow-up question:" not in result.answer


def test_category_deep_dive_uses_last_category_slug(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "chunk_id": 1,
                "url": "https://obearchitects.com/obe/project-detail.php?id=64",
                "title": "Minimal Villa",
                "chunk_text": "materials: Limestone, glass features: Shaded courtyards design style: Contemporary",
                "score": 0.62,
                "doc_type": "project",
            }
        ],
    )

    result = rag_public.answer_question(
        "Can you provide more information about the exterior design features?",
        top_k=5,
        last_category_slug="villas",
    )

    first_line = result.answer.splitlines()[0].strip()
    assert "Exterior Design Features" in first_line
    assert "Villas" in first_line
    assert "I couldn't retrieve enough portfolio text to answer that precisely." not in result.answer


def test_category_deep_dive_does_not_use_generic_fallback(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "chunk_id": 2,
                "url": "https://obearchitects.com/obe/project-detail.php?id=72",
                "title": "Country Side Luxurious Villa",
                "chunk_text": "typical spaces: Courtyard, majlis features: Outdoor lounge",
                "score": 0.55,
                "doc_type": "project",
            }
        ],
    )

    result = rag_public.answer_question(
        "Can you describe typical interior and outdoor spaces included in the villas?",
        top_k=5,
        last_category_slug="villas",
    )
    assert "I couldn't retrieve enough portfolio text to answer that precisely." not in result.answer


def test_category_overview_no_buttons_after_followup_depth(monkeypatch):
    import app.services.rag_public as rag_public

    monkeypatch.setattr(
        rag_public,
        "retrieve_chunks",
        lambda **_kwargs: [
            {
                "chunk_id": 1,
                "url": "https://obearchitects.com/obe/project-detail.php?id=64",
                "title": "Minimal Villa",
                "chunk_text": "location: Dubai status: Completed built-up area: 2,845 sq.ft",
                "score": 0.91,
                "doc_type": "project",
            }
        ],
    )

    class FakeOllamaClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def chat(self, *_args, **_kwargs):
            return "Villas Designed by OBE Architects\n\n**Key highlights**\n- **Location:** Dubai"

    monkeypatch.setattr(rag_public, "OllamaClient", FakeOllamaClient)

    result = rag_public.answer_question(
        "tell me about villas",
        top_k=5,
        category_followup_step=3,
    )
    assert len(result.follow_up_buttons) <= 1





