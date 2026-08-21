import json
from datetime import date, datetime

import httpx
import pytest
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


class _FakePage:
    url = "https://www.instagram.com/"


def test_one_broken_post_does_not_kill_the_whole_run(tmp_path, monkeypatch):
    """Osservato dal vivo il 2026-08-20: un post illeggibile ha fatto abortire
    il giro dopo aver speso e segnato dei post come visti, senza scrivere
    nulla. Di notte nessuno se ne accorge."""
    import winnow.run as run
    from winnow.config import Config, Folder, Limits
    from winnow.extract import PostExtraction

    cfg = Config(
        username="tizio", browser_profile=tmp_path / "prof",
        folders=[Folder("github", "/tizio/saved/github/111/", True, "repo")],
        limits=Limits(3.0, 10.0, 5, 15, 0.92), model="claude-haiku-4-5",
    )
    monkeypatch.setattr(run, "list_shortcodes", lambda page, url, **kw: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(run, "capture_post",
                        lambda *a, **k: ("cap", "acct", [], False))

    def fake_extract(cfg, code, account, caption, shots, is_video=False):
        if code == "BBB":
            raise ValueError("risposta non JSON dal modello")
        return PostExtraction(code, account, caption, [], 0.001)

    monkeypatch.setattr(run, "extract_post", fake_extract)

    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"items": []})))
    summary = run.collect(
        cfg, tmp_path / "state", tmp_path / "findings", tmp_path / "shots",
        http, _FakePage(), datetime(2026, 8, 20, 3, 0), search_delay=0,
    )

    assert summary["posts"] == 2, "gli altri due post devono essere processati"
    assert summary["failed"] == 1
    out = json.loads((tmp_path / "findings" / "2026-08-20.json").read_text())
    assert [p["shortcode"] for p in out["posts"]] == ["AAA", "CCC"]
    assert out["failed"][0]["shortcode"] == "BBB"
    assert "JSON" in out["failed"][0]["error"]


def test_a_failed_post_is_still_marked_seen(tmp_path, monkeypatch):
    """Se non lo segnassimo, ogni notte riproverebbe e rispenderebbe."""
    import winnow.run as run
    from winnow.config import Config, Folder, Limits
    from winnow.state import load_seen

    cfg = Config(
        username="tizio", browser_profile=tmp_path / "prof",
        folders=[Folder("github", "/tizio/saved/github/111/", True, "repo")],
        limits=Limits(3.0, 10.0, 5, 15, 0.92), model="claude-haiku-4-5",
    )
    monkeypatch.setattr(run, "list_shortcodes", lambda page, url, **kw: ["BBB"])
    monkeypatch.setattr(run, "capture_post",
                        lambda *a, **k: ("cap", "acct", [], False))
    monkeypatch.setattr(run, "extract_post", lambda *a, **k: (_ for _ in ()).throw(ValueError("rotto")))

    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    run.collect(cfg, tmp_path / "s", tmp_path / "f", tmp_path / "sh",
                http, _FakePage(), datetime(2026, 8, 20, 3, 0), search_delay=0)
    assert "BBB" in load_seen(tmp_path / "s" / "seen.json")


def test_collect_reports_each_step_while_it_runs(tmp_path, monkeypatch):
    """The events are what makes a paid, minutes-long run watchable. If this
    wiring breaks, a run goes back to being silent until the very end."""
    import winnow.run as run
    from winnow.config import Config, Folder, Limits

    monkeypatch.setattr(run, "list_shortcodes", lambda page, url, **kw: ["AAA", "BBB"])
    monkeypatch.setattr(
        run, "capture_post",
        lambda page, code, shots, mx: ("caption", "acct", ["s1.png", "s2.png"], False),
    )
    monkeypatch.setattr(
        run, "extract_post",
        lambda cfg, code, account, caption, shots, is_video=False:
        PostExtraction(
            shortcode=code, account=account, caption=caption,
            entities=[Entity("repo", "a/b", "", 1)], usd=0.004,
        ),
    )
    monkeypatch.setattr(
        run, "resolve_repo",
        lambda http, name: Verification(checked=True, exists=True, stars=7),
    )

    cfg = Config(
        username="u", folders=[Folder("Salvati", "https://x/", True, "saved")],
        model="m", limits=Limits(warn_eur_week=1.0, halt_eur_week=10.0,
                                 posts_per_run=10, max_slides=4, eur_per_usd=0.92),
        browser_profile=tmp_path / "prof",
    )
    seen: list[tuple[str, dict]] = []
    run.collect(cfg, tmp_path, tmp_path / "f", tmp_path / "s", None, None,
                datetime(2026, 8, 20, 13, 0), search_delay=0,
                on_event=lambda e, d: seen.append((e, d)))

    kinds = [e for e, _ in seen]
    assert kinds[0] == "folder"
    assert kinds.count("post") == 2, "un evento per post, numerato"
    assert "extracted" in kinds and "verified" in kinds
    assert kinds[-1] == "written", "l'ultima riga e' il file scritto"

    folder = dict(seen[0][1])
    assert folder["found"] == 2 and folder["new"] == 2
    written = dict(seen[-1][1])
    assert written["entities"] == 2 and written["verified"] == 2


# --- pacing and backlog ----------------------------------------------------

def test_search_delay_follows_the_token():
    """Waiting 7s while authenticated is three quarters of a run spent on
    nothing — the difference between forty minutes and two hours on a backlog."""
    from winnow.run import SEARCH_DELAY_S, SEARCH_DELAY_TOKEN_S, search_delay
    assert search_delay(True) == SEARCH_DELAY_TOKEN_S
    assert search_delay(False) == SEARCH_DELAY_S
    assert SEARCH_DELAY_TOKEN_S < SEARCH_DELAY_S


def test_has_github_token_reads_the_environment():
    from winnow.run import has_github_token
    assert has_github_token({"GITHUB_TOKEN": "ghp_x"})
    assert not has_github_token({})
    assert not has_github_token({"GITHUB_TOKEN": ""})


def test_a_full_run_does_not_list_the_folders_below(tmp_path, monkeypatch):
    """Listing a folder means scrolling it. Once the run is full there is
    nothing to gain, and a minute of scrolling a real account to lose."""
    import winnow.run as run
    from winnow.config import Config, Folder, Limits
    from winnow.extract import PostExtraction

    listed: list[str] = []

    def fake_list(page, url, **kw):
        listed.append(url)
        return ["AAA", "BBB", "CCC"]

    monkeypatch.setattr(run, "list_shortcodes", fake_list)
    monkeypatch.setattr(run, "capture_post",
                        lambda *a, **k: ("cap", "acct", [], False))
    monkeypatch.setattr(run, "extract_post",
                        lambda cfg, code, *a, **k:
                        PostExtraction(code, "acct", "cap", [], 0.001))

    cfg = Config(
        username="tizio", browser_profile=tmp_path / "prof",
        folders=[Folder("uno", "/tizio/saved/uno/111/", True, "repo"),
                 Folder("due", "/tizio/saved/due/222/", True, "repo")],
        limits=Limits(3.0, 10.0, 2, 15, 0.92), model="claude-haiku-4-5",
    )
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"items": []})))

    events: list[str] = []
    run.collect(cfg, tmp_path / "state", tmp_path / "findings", tmp_path / "shots",
                http, _FakePage(), datetime(2026, 8, 21), search_delay=0,
                on_event=lambda e, d: events.append(f"{e}:{d.get('name', '')}"))

    assert listed == ["/tizio/saved/uno/111/"]     # la seconda non viene aperta
    assert "folder_skipped:due" in events          # ma viene detto


def test_a_skipped_folder_does_not_read_as_an_empty_one():
    """Silence would look like "nothing new there", which is a lie."""
    from winnow.progress import line
    assert "saltata" in line("folder_skipped", {"name": "must-rewatch"})


# --- a broken key must not eat the backlog ---------------------------------

def test_a_key_without_credit_stops_the_run_and_marks_nothing(tmp_path, monkeypatch):
    """The whole point of the queue is that unread posts stay unread. Marking
    them seen on an account-level failure burns a backlog in one go and never
    retries it — with --posts 50, fifty posts gone without a word read."""
    import winnow.run as run
    from winnow.config import Config, Folder, Limits
    from winnow.state import load_seen

    class NoCredit(Exception):
        status_code = 400

        def __str__(self):
            return "Your credit balance is too low to access the API"

    monkeypatch.setattr(run, "list_shortcodes", lambda page, url, **kw: ["AAA", "BBB"])
    monkeypatch.setattr(run, "capture_post",
                        lambda *a, **k: ("cap", "acct", [], False))
    monkeypatch.setattr(run, "extract_post",
                        lambda *a, **k: (_ for _ in ()).throw(NoCredit()))

    cfg = Config(
        username="tizio", browser_profile=tmp_path / "prof",
        folders=[Folder("github", "/tizio/saved/github/111/", True, "repo")],
        limits=Limits(3.0, 10.0, 8, 15, 0.92), model="claude-haiku-4-5",
    )
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"items": []})))

    with pytest.raises(run.Unusable):
        run.collect(cfg, tmp_path / "state", tmp_path / "findings",
                    tmp_path / "shots", http, _FakePage(),
                    datetime(2026, 8, 21), search_delay=0)

    assert load_seen(tmp_path / "state" / "seen.json") == {}, \
        "la coda deve restare intatta"


@pytest.mark.parametrize("exc,fatal", [
    (type("E", (Exception,), {"status_code": 401})(), True),
    (type("E", (Exception,), {"status_code": 429})(), True),
    (ValueError("Your credit balance is too low"), True),
    (ValueError("invalid api key provided"), True),
    (ValueError("risposta non JSON dal modello"), False),
    (TimeoutError("slide non caricata"), False),
])
def test_only_account_level_failures_stop_everything(exc, fatal):
    from winnow.run import is_unusable
    assert is_unusable(exc) is fatal
