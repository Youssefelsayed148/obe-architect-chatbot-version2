from tools.ingestion.utils import is_in_path_scope, is_same_registrable_domain, normalize_url


def test_normalize_url_keeps_allowed_query_keys_and_strips_unknown():
    url, removed = normalize_url(
        "https://obearchitects.com/obe/projectlists.php?category=publicncultural&utm_source=abc",
        base_url="https://obearchitects.com/obe/",
        allowed_query_keys=["category", "id"],
    )
    assert removed is True
    assert url == "https://obearchitects.com/obe/projectlists.php?category=publicncultural"


def test_normalize_url_keeps_id_query_key():
    url, removed = normalize_url(
        "https://obearchitects.com/obe/project-detail.php?id=91#section",
        base_url="https://obearchitects.com/obe/",
        allowed_query_keys=["category", "id"],
    )
    assert removed is False
    assert url == "https://obearchitects.com/obe/project-detail.php?id=91"


def test_same_registrable_domain_default():
    assert is_same_registrable_domain(
        "https://www.obearchitects.com/obe/index.php",
        "https://obearchitects.com/obe/",
        allow_subdomains=False,
    )
    assert not is_same_registrable_domain(
        "https://example.com/obe/index.php",
        "https://obearchitects.com/obe/",
        allow_subdomains=False,
    )


def test_path_prefix_scope():
    assert is_in_path_scope("https://obearchitects.com/obe/about-us.php", "/obe/")
    assert not is_in_path_scope("https://obearchitects.com/blog/post-1", "/obe/")
