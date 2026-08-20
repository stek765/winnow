import httpx
import pytest
from winnow.verify import normalize_repo_name, verify_repo


def test_normalize_accepts_owner_slash_name():
    assert normalize_repo_name("lfnovo/open-notebook") == "lfnovo/open-notebook"


def test_normalize_strips_github_urls():
    assert normalize_repo_name("https://github.com/lfnovo/open-notebook") == "lfnovo/open-notebook"
    assert normalize_repo_name("github.com/lfnovo/open-notebook.git") == "lfnovo/open-notebook"


def test_normalize_returns_none_for_a_bare_display_name():
    """'Open Notebook' non e' un repo: non si indovina l'owner."""
    assert normalize_repo_name("Open Notebook") is None


def test_normalize_returns_none_for_empty():
    assert normalize_repo_name("   ") is None


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_verify_repo_reads_the_fields_that_matter():
    def handler(request):
        assert request.url.path == "/repos/lfnovo/open-notebook"
        return httpx.Response(200, json={
            "stargazers_count": 37000,
            "pushed_at": "2026-08-17T10:00:00Z",
            "archived": False,
            "license": {"spdx_id": "MIT"},
            "description": "Open source NotebookLM alternative",
            "html_url": "https://github.com/lfnovo/open-notebook",
        })
    v = verify_repo(_client(handler), "lfnovo/open-notebook")
    assert v.checked and v.exists
    assert v.stars == 37000
    assert v.license == "MIT"
    assert v.last_commit == "2026-08-17"


def test_verify_repo_marks_a_404_as_checked_and_absent():
    def handler(request):
        return httpx.Response(404, json={"message": "Not Found"})
    v = verify_repo(_client(handler), "tizio/inesistente")
    assert v.checked and not v.exists


def test_network_failure_is_never_reported_as_verified():
    def handler(request):
        raise httpx.ConnectError("rete assente")
    v = verify_repo(_client(handler), "lfnovo/open-notebook")
    assert v.checked is False
    assert "rete" in v.note.lower() or "network" in v.note.lower()


def test_rate_limit_is_not_reported_as_absent():
    def handler(request):
        return httpx.Response(403, json={"message": "API rate limit exceeded"})
    v = verify_repo(_client(handler), "lfnovo/open-notebook")
    assert v.checked is False
    assert v.exists is False or v.exists is None


def test_search_repo_finds_by_display_name():
    from winnow.verify import search_repo

    def handler(request):
        assert request.url.path == "/search/repositories"
        assert "stars" in str(request.url)
        return httpx.Response(200, json={"items": [
            {"full_name": "lfnovo/open-notebook", "name": "open-notebook",
             "stargazers_count": 37109,
             "pushed_at": "2026-08-16T00:00:00Z", "archived": False,
             "license": {"spdx_id": "MIT"}, "description": "NotebookLM alternative",
             "html_url": "https://github.com/lfnovo/open-notebook"},
            {"full_name": "tizio/open-notebook-clone", "name": "open-notebook-clone",
             "stargazers_count": 3},
        ]})
    v = search_repo(_client(handler), "Open Notebook")
    assert v.checked and v.exists and v.stars == 37109


def test_search_repo_reports_absence_when_no_results():
    from winnow.verify import search_repo

    def handler(request):
        return httpx.Response(200, json={"items": []})
    v = search_repo(_client(handler), "coso che non esiste")
    assert v.checked and not v.exists


def test_search_repo_rate_limit_is_not_absence():
    from winnow.verify import search_repo

    def handler(request):
        return httpx.Response(403, json={"message": "rate limit"})
    v = search_repo(_client(handler), "Open Notebook")
    assert v.checked is False


def test_resolve_repo_uses_direct_lookup_when_a_slug_is_given():
    from winnow.verify import resolve_repo

    def handler(request):
        assert request.url.path == "/repos/lfnovo/open-notebook"
        return httpx.Response(200, json={
            "stargazers_count": 1, "pushed_at": "2026-01-01T00:00:00Z",
            "archived": False, "license": None, "description": "",
            "html_url": "https://github.com/lfnovo/open-notebook"})
    assert resolve_repo(_client(handler), "lfnovo/open-notebook").exists


def test_resolve_repo_falls_back_to_search_for_a_display_name():
    from winnow.verify import resolve_repo

    def handler(request):
        assert request.url.path == "/search/repositories"
        return httpx.Response(200, json={"items": [
            {"full_name": "lfnovo/open-notebook", "name": "open-notebook",
             "stargazers_count": 37109,
             "pushed_at": "2026-08-16T00:00:00Z", "archived": False,
             "license": {"spdx_id": "MIT"}, "description": "x",
             "html_url": "https://github.com/lfnovo/open-notebook"}]})
    assert resolve_repo(_client(handler), "Open Notebook").stars == 37109


def test_search_repo_rejects_a_famous_repo_whose_name_does_not_match():
    """'AI Job Search' non deve diventare career-ops solo perche' ha 66k stelle."""
    from winnow.verify import search_repo

    def handler(request):
        return httpx.Response(200, json={"items": [
            {"full_name": "santifer/career-ops", "name": "career-ops",
             "stargazers_count": 66316, "description": "AI job search system"},
        ]})
    v = search_repo(_client(handler), "AI Job Search")
    assert v.checked and v.exists is False
    assert "career-ops" in v.note


def test_search_repo_flags_homonyms():
    from winnow.verify import search_repo

    def handler(request):
        return httpx.Response(200, json={"items": [
            {"full_name": "a/openseo", "name": "OpenSEO", "stargazers_count": 900,
             "pushed_at": "2026-08-01T00:00:00Z", "archived": False,
             "license": None, "description": "", "html_url": "u1"},
            {"full_name": "b/OpenSEO", "name": "openseo", "stargazers_count": 161,
             "pushed_at": "2016-01-02T00:00:00Z", "archived": False,
             "license": None, "description": "", "html_url": "u2"},
        ]})
    v = search_repo(_client(handler), "OpenSEO")
    assert v.exists and v.stars == 900
    assert "omonimi" in v.note and "2016" in v.note
