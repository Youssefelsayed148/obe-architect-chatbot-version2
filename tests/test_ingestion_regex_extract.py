from tools.ingestion.scrape_site import extract_category_slugs, extract_project_ids


def test_extract_category_slugs_from_html():
    html = """
    <a href="projectlists.php?category=publicncultural">Public</a>
    <script>var c = "projectlists.php?category=sports-and-leisure";</script>
    <a href="/obe/projectlists.php?category=villas_2026">Villas</a>
    """
    slugs = extract_category_slugs(html)
    assert slugs == {"publicncultural", "sports-and-leisure", "villas_2026"}


def test_extract_project_ids_from_html():
    html = """
    <a href="project-detail.php?id=91">Detail</a>
    <script>
      var d1 = "project-detail.php?id=102";
      var d2 = "/obe/project-detail.php?id=210";
    </script>
    """
    ids = extract_project_ids(html)
    assert ids == {"91", "102", "210"}
