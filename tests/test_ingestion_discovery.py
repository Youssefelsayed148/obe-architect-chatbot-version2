from tools.ingestion.scrape_site import _discover_links_from_html


def test_regex_project_links_anchor_to_base_url_not_current_url():
    html = "<script>var x='project-detail.php?id=91';</script>"
    discovered = _discover_links_from_html(
        current_url="https://obearchitects.com/obe/css/page.php",
        html=html,
        base_url="https://obearchitects.com/obe/",
    )
    assert "https://obearchitects.com/obe/project-detail.php?id=91" in discovered
    assert "https://obearchitects.com/obe/css/project-detail.php?id=91" not in discovered
