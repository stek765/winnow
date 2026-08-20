import json
from datetime import date

import httpx
from winnow.extract import Entity, PostExtraction
from winnow.run import enrich, findings_path, write_findings
from winnow.verify import Verification


def test_findings_path_is_one_file_per_day(tmp_path):
    assert findings_path(tmp_path, date(2026, 8, 20)) == tmp_path / "2026-08-20.json"


def test_enrich_routes_a_repo_slug_to_the_direct_lookup():
    def handler(request):
        assert request.url.path == "/repos/a/b"
        return httpx.Response(200, json={
            "stargazers_count": 10, "pushed_at": "2026-08-01T00:00:00Z",
            "archived": False, "license": {"spdx_id": "MIT"},
            "description": "x", "html_url": "https://github.com/a/b"})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    v = enrich(http, Entity("repo", "a/b", "", 2), {})
    assert v.checked and v.exists and v.stars == 10


def test_enrich_searches_github_for_a_display_name():
    def handler(request):
        assert request.url.path == "/search/repositories"
        return httpx.Response(200, json={"items": [
            {"full_name": "lfnovo/open-notebook", "name": "open-notebook",
             "stargazers_count": 37109, "pushed_at": "2026-08-16T00:00:00Z",
             "archived": False, "license": None, "description": "",
             "html_url": "https://github.com/lfnovo/open-notebook"}]})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    v = enrich(http, Entity("repo", "Open Notebook", "", 2), {})
    assert v.exists and v.stars == 37109


def test_enrich_uses_the_cache_instead_of_calling_twice():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"items": [
            {"full_name": "a/b", "name": "open-notebook", "stargazers_count": 1,
             "pushed_at": "2026-01-01T00:00:00Z", "archived": False,
             "license": None, "description": "", "html_url": "u"}]})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    cache: dict = {}
    e = Entity("repo", "Open Notebook", "", 2)
    enrich(http, e, cache)
    enrich(http, e, cache)
    assert len(calls) == 1, "la seconda volta deve arrivare dalla cache"


def test_enrich_leaves_a_claim_unverified_by_source():
    def handler(request):
        raise AssertionError("non deve chiamare la rete")
    http = httpx.Client(transport=httpx.MockTransport(handler))
    v = enrich(http, Entity("claim", "diventa ricco con l'AI", "", 1), {})
    assert v.checked is False


def test_write_findings_produces_readable_json(tmp_path):
    p = tmp_path / "2026-08-20.json"
    ex = PostExtraction(shortcode="AAA", account="tizio", caption="c",
                        entities=[Entity("repo", "a/b", "blurb", 2)], usd=0.01)
    write_findings(p, [ex], {("AAA", "a/b"): Verification(checked=True, exists=True, stars=5)}, 0.01)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["spend_usd"] == 0.01
    assert data["posts"][0]["shortcode"] == "AAA"
    assert data["posts"][0]["entities"][0]["verification"]["stars"] == 5
    assert data["posts"][0]["url"].endswith("/p/AAA/")
