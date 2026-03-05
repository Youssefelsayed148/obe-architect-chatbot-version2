from tools.ingestion.robots import parse_robots_txt


def test_robots_allow_and_disallow_longest_match():
    content = """
User-agent: *
Disallow: /obe/private/
Allow: /obe/private/public-note.php
"""
    policy = parse_robots_txt(content, user_agent="*")
    assert policy.can_fetch("/obe/index.php")
    assert not policy.can_fetch("/obe/private/secret.php")
    assert policy.can_fetch("/obe/private/public-note.php")


def test_robots_captures_sitemaps():
    content = """
User-agent: *
Disallow: /admin/
Sitemap: https://obearchitects.com/sitemap.xml
"""
    policy = parse_robots_txt(content, user_agent="*")
    assert policy.sitemaps == ["https://obearchitects.com/sitemap.xml"]
