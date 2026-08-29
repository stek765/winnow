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
        folders=[Folder("github", "/tizio/saved/github/111/", True)],
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
        folders=[Folder("github", "/tizio/saved/github/111/", True)],
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
        username="u", folders=[Folder("Salvati", "https://x/", True)],
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


def test_every_active_folder_is_listed_every_run(tmp_path, monkeypatch):
    """The run used to stop at the first folder that could fill it.

    Measured on a real account on 2026-08-29: seven active folders, six days
    of runs, and `seen.json` held posts from exactly two of them — `github`
    (61) and `must-rewatch` (24). The other five had never been opened, so
    adding a folder changed nothing at all, for ever, and nothing said so.
    A folder that is never read is a folder that does not exist.
    """
    import winnow.run as run
    from winnow.config import Config, Folder, Limits
    from winnow.extract import PostExtraction
    from winnow.state import load_seen

    listed: list[str] = []

    def fake_list(page, url, **kw):
        listed.append(url)
        return ["A1", "A2", "A3"] if "uno" in url else ["B1", "B2", "B3"]

    monkeypatch.setattr(run, "list_shortcodes", fake_list)
    monkeypatch.setattr(run, "capture_post",
                        lambda *a, **k: ("cap", "acct", [], False))
    monkeypatch.setattr(run, "extract_post",
                        lambda cfg, code, *a, **k:
                        PostExtraction(code, "acct", "cap", [], 0.001))

    cfg = Config(
        username="tizio", browser_profile=tmp_path / "prof",
        folders=[Folder("uno", "/tizio/saved/uno/111/", True),
                 Folder("due", "/tizio/saved/due/222/", True)],
        limits=Limits(3.0, 10.0, 2, 15, 0.92), model="claude-haiku-4-5",
    )
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"items": []})))

    run.collect(cfg, tmp_path / "state", tmp_path / "findings",
                tmp_path / "shots", http, _FakePage(),
                datetime(2026, 8, 21), search_delay=0)

    assert listed == ["/tizio/saved/uno/111/", "/tizio/saved/due/222/"]
    # Two slots, two folders: one each, not two from the first.
    seen = load_seen(tmp_path / "state" / "seen.json")
    assert set(seen) == {"A1", "B1"}


def test_the_run_is_dealt_one_post_at_a_time_to_each_folder():
    """A share, not a queue: the second folder must not wait for the first
    to run out of saved posts — which on a real account it never does."""
    from winnow.run import deal

    pools = [("github", ["g1", "g2", "g3", "g4"]),
             ("ai", ["a1", "a2"]),
             ("hacking", ["h1"])]
    assert deal(pools, 4) == [("g1", "github"), ("a1", "ai"),
                              ("h1", "hacking"), ("g2", "github")]


def test_a_folder_with_nothing_new_gives_its_slot_away():
    """Fair does not mean idle: an exhausted folder must not cost the run
    a post that another folder could have filled."""
    from winnow.run import deal

    pools = [("github", ["g1", "g2", "g3"]), ("ai", [])]
    assert deal(pools, 3) == [("g1", "github"), ("g2", "github"),
                              ("g3", "github")]


def test_when_there_are_more_folders_than_slots_the_hungriest_go_first():
    """With eight posts and twelve folders somebody is always left out, and
    dealing in config order leaves out the same four every single day —
    which is the bug this whole change is about, one level down. The folder
    that has given least so far picks first, so the queue turns over."""
    from winnow.run import deal

    pools = [("github", ["g1"]), ("ai", ["a1"]), ("nuova", ["n1"])]
    tally = {"github": 61, "ai": 24}          # `nuova` has given nothing
    assert deal(pools, 2, tally) == [("n1", "nuova"), ("a1", "ai")]


def test_the_tally_is_read_from_the_posts_already_seen():
    """No new state file: `seen.json` has recorded the folder per post since
    the first run, so the count is already on disk."""
    from winnow.run import tally_by_folder

    seen = {"AAA": {"date": "2026-08-23", "folder": "github"},
            "BBB": {"date": "2026-08-24", "folder": "github"},
            "CCC": {"date": "2026-08-24", "folder": "ai"},
            "DDD": "vecchio formato senza cartella"}
    assert tally_by_folder(seen) == {"github": 2, "ai": 1}


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
        folders=[Folder("github", "/tizio/saved/github/111/", True)],
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


# --- two runs in one day are one day ---------------------------------------

def test_a_second_run_adds_to_the_day_instead_of_replacing_it(tmp_path):
    """Measured on 2026-08-21: a 48-post run costing $0.11 was overwritten by a
    19-post run twenty minutes later. Every post was already marked seen, so
    those 131 entities were gone for good — paid for, then deleted."""
    from winnow.run import merge_findings

    old = {"spend_usd": 0.1121, "failed": [],
           "posts": [{"shortcode": "AAA", "entities": [1, 2]},
                     {"shortcode": "BBB", "entities": [3]}]}
    new = {"spend_usd": 0.0308, "failed": [],
           "posts": [{"shortcode": "CCC", "entities": [4]}]}

    out = merge_findings(old, new)
    assert [p["shortcode"] for p in out["posts"]] == ["AAA", "BBB", "CCC"]
    assert out["spend_usd"] == 0.1429, "la spesa del giorno, non dell'ultimo giro"


def test_merging_does_not_duplicate_a_post_seen_twice(tmp_path):
    from winnow.run import merge_findings
    old = {"spend_usd": 0.01, "failed": [], "posts": [{"shortcode": "AAA"}]}
    new = {"spend_usd": 0.01, "failed": [], "posts": [{"shortcode": "AAA"}]}
    assert len(merge_findings(old, new)["posts"]) == 1


def test_merging_keeps_the_failures_of_both_runs():
    from winnow.run import merge_findings
    old = {"spend_usd": 0, "posts": [], "failed": [{"shortcode": "X", "error": "a"}]}
    new = {"spend_usd": 0, "posts": [], "failed": [{"shortcode": "Y", "error": "b"}]}
    assert {f["shortcode"] for f in merge_findings(old, new)["failed"]} == {"X", "Y"}


def test_write_findings_appends_to_an_existing_day(tmp_path):
    from winnow.run import write_findings
    from winnow.extract import PostExtraction

    path = tmp_path / "2026-08-21.json"
    write_findings(path, [PostExtraction("AAA", "a", "c", [], 0.01)], {}, 0.01)
    write_findings(path, [PostExtraction("BBB", "b", "c", [], 0.02)], {}, 0.02)

    out = json.loads(path.read_text())
    assert [p["shortcode"] for p in out["posts"]] == ["AAA", "BBB"]
    assert out["spend_usd"] == 0.03


def test_a_corrupt_day_file_is_set_aside_not_silently_dropped(tmp_path):
    """Losing the new findings to save a broken file, or the other way round,
    are both wrong: keep the run's output and move the wreck aside."""
    from winnow.run import write_findings
    from winnow.extract import PostExtraction

    path = tmp_path / "2026-08-21.json"
    path.write_text("{ questo non e' json", encoding="utf-8")
    write_findings(path, [PostExtraction("AAA", "a", "c", [], 0.01)], {}, 0.01)

    assert [p["shortcode"] for p in json.loads(path.read_text())["posts"]] == ["AAA"]
    assert (tmp_path / "2026-08-21.json.corrupt").exists()


def test_ferma_stops_between_posts_and_keeps_what_was_read(tmp_path, monkeypatch):
    """«Ferma» never worked: `stopping` was set on the job and read by nobody,
    so the button was decoration on every run in the app. Stopping happens
    between two posts — never inside one, or a post is paid for and thrown
    away — and everything read so far is written exactly as if the queue had
    ended there."""
    import winnow.run as run
    from winnow.config import Config, Folder, Limits
    from winnow.extract import PostExtraction

    cfg = Config(
        username="tizio", browser_profile=tmp_path / "prof",
        folders=[Folder("github", "/tizio/saved/github/111/", True)],
        limits=Limits(3.0, 10.0, 5, 15, 0.92), model="claude-haiku-4-5",
    )
    monkeypatch.setattr(run, "list_shortcodes",
                        lambda page, url, **kw: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(run, "capture_post",
                        lambda *a, **k: ("cap", "acct", [], False))
    monkeypatch.setattr(run, "extract_post",
                        lambda cfg, code, account, caption, shots, is_video=False:
                        PostExtraction(code, account, caption, [], 0.001))

    read = []
    said = []
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"items": []})))
    summary = run.collect(
        cfg, tmp_path / "state", tmp_path / "findings", tmp_path / "shots",
        http, _FakePage(), datetime(2026, 8, 28, 3, 0), search_delay=0,
        on_event=lambda e, d: (said.append(e), read.append(d)),
        # Pressed while the first post is being read.
        should_stop=lambda: len([e for e in said if e == "post"]) >= 1,
    )

    assert summary["posts"] == 1, "quello già letto resta, gli altri due no"
    assert "stopped" in said
    out = json.loads((tmp_path / "findings" / "2026-08-28.json").read_text())
    assert [p["shortcode"] for p in out["posts"]] == ["AAA"]


def test_ferma_is_answered_between_two_names_not_only_two_posts(tmp_path,
                                                                monkeypatch):
    """Without a GitHub token a source lookup waits up to a minute, and a post
    with twelve names is twelve of them. «Ferma» pressed there used to wait
    for the whole post to finish."""
    import winnow.run as run
    from winnow.config import Config, Folder, Limits
    from winnow.extract import Entity, PostExtraction

    cfg = Config(
        username="tizio", browser_profile=tmp_path / "prof",
        folders=[Folder("github", "/tizio/saved/github/111/", True)],
        limits=Limits(3.0, 10.0, 5, 15, 0.92), model="claude-haiku-4-5",
    )
    monkeypatch.setattr(run, "list_shortcodes", lambda page, url, **kw: ["AAA"])
    monkeypatch.setattr(run, "capture_post",
                        lambda *a, **k: ("cap", "acct", [], False))
    names = [Entity(kind="repo", name=f"o/r{i}", blurb="", slide=1)
             for i in range(6)]
    monkeypatch.setattr(run, "extract_post",
                        lambda *a, **k: PostExtraction("AAA", "acct", "cap",
                                                       names, 0.001))
    looked = []
    monkeypatch.setattr(run, "enrich",
                        lambda *a, **k: looked.append(a[1]) or run.Verification(
                            checked=True, exists=True))

    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"items": []})))
    run.collect(cfg, tmp_path / "state", tmp_path / "findings",
                tmp_path / "shots", http, _FakePage(),
                datetime(2026, 8, 28, 3, 0), search_delay=0,
                should_stop=lambda: len(looked) >= 2)
    assert len(looked) == 2, "deve fermarsi a metà del post, non alla fine"


def test_the_wait_between_lookups_is_slept_in_slices(monkeypatch):
    """A minute answered in a minute is a button that does not work."""
    import winnow.run as run
    from winnow.extract import Entity

    slept = []
    monkeypatch.setattr(run.time, "sleep", slept.append)
    monkeypatch.setattr(run, "resolve_repo",
                        lambda http, name: run.Verification(checked=True,
                                                            exists=True))
    stop = {"now": False}

    def watching():
        stop["now"] = len(slept) >= 3
        return stop["now"]

    run.enrich(None, Entity(kind="repo", name="o/r", blurb="", slide=1), {},
               delay=60.0, should_stop=watching)
    assert sum(slept) <= 4, "non deve dormire i sessanta secondi interi"
