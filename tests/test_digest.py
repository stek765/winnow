"""Block 1: the week arranged. Arranging is allowed; weighing is not."""
from __future__ import annotations

from winnow.digest import CHECKABLE, gather, render, render_thing, sort_key


def _post(account="acc", shortcode="AAA", entities=()):
    return {"shortcode": shortcode, "account": account, "caption": "buy now",
            "url": f"https://www.instagram.com/p/{shortcode}/",
            "entities": list(entities)}


def _ent(name, kind="repo", blurb="", **verification):
    v = {"checked": False, "exists": None, "stars": None, "last_commit": None,
         "archived": None, "license": None, "description": None, "url": None,
         "note": ""}
    v.update(verification)
    return {"name": name, "kind": kind, "blurb": blurb, "slide": 1,
            "verification": v}


def _day(posts, spend=0.01, failed=(), ):
    return {"spend_usd": spend, "failed": list(failed), "posts": list(posts)}


def test_the_same_project_under_two_names_is_one_entry():
    """`llama.cpp` in one post and `ggml-org/llama.cpp` in the next is one
    thing. The source URL is the only identifier that survives how somebody
    chose to type it."""
    checked = dict(checked=True, exists=True, stars=9,
                   url="https://github.com/ggml-org/llama.cpp")
    d = gather([_day([_post(entities=[_ent("llama.cpp", **checked)]),
                      _post(shortcode="BBB",
                            entities=[_ent("ggml-org/llama.cpp", **checked)])])])
    assert len(d["things"]) == 1
    assert d["things"][0]["posts"] == 2


def test_nothing_is_dropped():
    d = gather([_day([_post(entities=[_ent(f"thing{i}") for i in range(5)])])])
    assert {t["name"] for t in d["things"]} == {f"thing{i}" for i in range(5)}


def test_a_later_failure_does_not_erase_an_earlier_verification():
    """Run one confirms the repo; run two hits a rate limit. Keeping the
    second would turn a fact back into a question."""
    good = _ent("x", checked=True, exists=True, stars=42,
                url="https://github.com/o/x")
    bad = _ent("x", checked=False, note="429 rate limited")
    d = gather([_day([_post(entities=[good])]),
                _day([_post(shortcode="BBB", entities=[bad])])])
    assert len(d["things"]) == 1
    assert d["things"][0]["verification"]["stars"] == 42


def test_the_source_description_beats_the_caption():
    d = gather([_day([_post(entities=[
        _ent("x", blurb="THE CAPTION", checked=True, exists=True,
             description="THE SOURCE", url="https://github.com/o/x")])])])
    w = d["things"][0]["what_it_is"]
    assert w["text"] == "THE SOURCE" and w["trusted"] is True


def test_one_account_repeating_a_name_is_flagged_as_their_letterhead():
    """Measured: `OmniGet` in 27 posts, all from one account, off a fixed
    final slide. That is an observation about the data — the judge still
    decides what it means."""
    posts = [_post(shortcode=f"P{i}", entities=[_ent("OmniGet", kind="platform")])
             for i in range(6)]
    d = gather([_day(posts)])
    t = d["things"][0]
    assert t["boilerplate"] and t["posts"] == 6
    assert "same" in "\n".join(render_thing(t))


def test_the_same_name_from_many_accounts_is_not_a_watermark():
    posts = [_post(account=f"acc{i}", shortcode=f"P{i}",
                   entities=[_ent("ollama/ollama")]) for i in range(6)]
    assert gather([_day(posts)])["things"][0]["boilerplate"] is False


def test_an_unchecked_claim_says_nothing_about_being_unchecked():
    """`platform`, `item`, `news` and `claim` have no registry: repeating
    "not checked" under each of two hundred entries teaches the reader to
    skip the line that matters on a repo."""
    d = gather([_day([_post(entities=[
        _ent("12% from your couch", kind="claim", blurb="sure",
             note="a claim with no artefact named")])])])
    body = "\n".join(render_thing(d["things"][0]))
    assert "not checked" not in body


def test_an_unchecked_repo_does_say_so():
    d = gather([_day([_post(entities=[
        _ent("o/x", note="network error: timed out")])])])
    body = "\n".join(render_thing(d["things"][0]))
    assert "not checked" in body and "network error" in body


def test_a_doubt_is_never_printed_twice_in_the_same_words():
    d = gather([_day([_post(entities=[_ent("o/x", note="429")])])])
    body = "\n".join(render_thing(d["things"][0]))
    assert body.count("429") == 1


def test_absence_is_stated_and_not_confused_with_not_checked():
    d = gather([_day([_post(entities=[
        _ent("ghost/repo", checked=True, exists=False)])])])
    body = "\n".join(render_thing(d["things"][0]))
    assert "nothing under this name" in body and "not checked" not in body


def test_checked_things_come_before_unchecked_ones():
    real = {"kind": "repo", "name": "a", "posts": 1, "boilerplate": False,
            "doubts": [], "seen": [], "what_it_is": {},
            "verification": {"checked": True, "exists": True, "stars": 1}}
    unknown = {**real, "name": "b", "verification": {"checked": False}}
    assert sorted([unknown, real], key=sort_key)[0] is real


def test_a_kind_nobody_planned_for_still_gets_printed():
    """A section per known kind would silently swallow whatever the extractor
    invents next."""
    d = gather([_day([_post(entities=[_ent("mystery", kind="podcast")])])])
    assert "mystery" in render(d, 1)


def test_the_header_states_the_size_and_the_cost_of_the_week():
    d = gather([_day([_post(entities=[_ent("a")])], spend=0.35)])
    head = render(d, 3).splitlines()[0]
    assert "1 saved post" in head and "3 days" in head and "$0.35" in head


def test_posts_that_named_nothing_are_counted_not_hidden():
    d = gather([_day([_post()])])
    assert len(d["empty"]) == 1
    assert "named nothing" in render(d, 1)


def test_posts_that_could_not_be_read_are_carried_through():
    d = gather([_day([], failed=[{"shortcode": "ZZZ", "error": "clipped area"}])])
    assert "ZZZ" in render(d, 1) and "clipped area" in render(d, 1)


def test_only_repos_and_models_have_a_source_to_ask():
    assert CHECKABLE == {"repo", "model"}


def test_a_model_has_likes_and_a_repo_has_stars():
    d = gather([_day([_post(entities=[
        _ent("Qwen3", kind="model", checked=True, exists=True, stars=7,
             url="https://huggingface.co/Qwen/Qwen3")])])])
    assert "7 likes" in "\n".join(render_thing(d["things"][0]))


def test_a_missing_account_does_not_print_an_empty_handle():
    d = gather([_day([_post(account="", entities=[_ent("x")])])])
    assert "@ " not in "\n".join(render_thing(d["things"][0]))


def test_the_list_entry_and_the_repo_it_points_at_are_one_thing():
    """A list post names the entry as a human writes it, and the slide beside
    it carries the repo path. Kept apart, `RAGFlow` sits unchecked among the
    list entries while `infiniflow/ragflow` sits verified two sections above."""
    d = gather([_day([_post(entities=[
        _ent("RAGFlow", kind="item", note="an entry of a list"),
        _ent("infiniflow/ragflow", checked=True, exists=True, stars=89038,
             url="https://github.com/infiniflow/ragflow")])])])
    assert len(d["things"]) == 1
    t = d["things"][0]
    assert t["kind"] == "repo" and t["verification"]["stars"] == 89038


def test_spelling_does_not_split_a_thing_in_two():
    d = gather([_day([_post(entities=[
        _ent("Lobe Chat", kind="item"),
        _ent("lobehub/lobe-chat", checked=True, exists=True, stars=8,
             url="https://github.com/lobehub/lobe-chat")])])])
    assert len(d["things"]) == 1


def test_a_source_that_answered_under_another_path_says_so():
    """GitHub follows renames, so the numbers can land next to the name the
    caption used while belonging to a repository somewhere else. A transfer
    and a wrong match look identical once the stars are printed."""
    d = gather([_day([_post(entities=[
        _ent("ggerganov/llama.cpp", checked=True, exists=True, stars=125175,
             url="https://github.com/ggml-org/llama.cpp")])])])
    assert "ggml-org/llama.cpp" in "\n".join(render_thing(d["things"][0]))


def test_a_difference_of_case_alone_is_not_worth_a_warning():
    d = gather([_day([_post(entities=[
        _ent("Aider-ai/aider", checked=True, exists=True, stars=1,
             url="https://github.com/Aider-AI/aider")])])])
    assert "rename" not in "\n".join(render_thing(d["things"][0]))


def test_a_bare_name_resolving_to_an_owner_is_not_a_rename():
    d = gather([_day([_post(entities=[
        _ent("Strix", checked=True, exists=True, stars=1,
             url="https://github.com/usestrix/strix")])])])
    assert "rename" not in "\n".join(render_thing(d["things"][0]))


def test_the_post_and_the_slide_travel_with_the_thing():
    """The recap shows the slide the reader would have seen; without the
    shortcode and the slide number there is no way to find that picture."""
    d = gather([_day([_post(shortcode="ABC", entities=[
        {"name": "x", "kind": "repo", "blurb": "", "slide": 4,
         "verification": {"checked": False}}])])])
    line = "\n".join(render_thing(d["things"][0]))
    assert "post ABC" in line and "slide 4" in line


def test_fame_does_not_decide_where_a_thing_is_printed():
    """Measured 2026-08-24 on a real week: 120 repos, 48 of them from a single
    "50 GitHub repos" listicle — and because the order was `-stars`, **28 of
    the top 30** entries were that one post's famous names. Everything from
    the other 22 posts, each saved for one specific thing, started at rank 32;
    the post about reverse-engineering tools started at rank 82.

    The judge read the head of the list and answered from it: it binned "the
    mega-list of eternal repos" and kept four of its entries anyway. Star
    count is a popularity ranking, and popularity is what makes a repo *not*
    worth reporting — the reader already knows it. Position must carry no
    information, so equally-checked things are printed by name.
    """
    v = dict(checked=True, exists=True)
    famous = {"kind": "repo", "name": "zzz/known-by-everyone", "posts": 1,
              "boilerplate": False, "doubts": [], "seen": [], "what_it_is": {},
              "verification": {**v, "stars": 500_000}}
    obscure = {**famous, "name": "aaa/nobody-has-heard-of-it",
               "verification": {**v, "stars": 5}}
    assert sorted([famous, obscure], key=sort_key)[0] is obscure


def test_how_many_posts_named_a_thing_does_not_decide_either():
    """The mentality says it outright: seven accounts posting the same list is
    one source, not seven. Sorting by it contradicted the block that teaches
    the reader to ignore it."""
    v = {"checked": True, "exists": True, "stars": 1}
    repeated = {"kind": "repo", "name": "zzz/reposted", "posts": 9,
                "boilerplate": False, "doubts": [], "seen": [],
                "what_it_is": {}, "verification": v}
    once = {**repeated, "name": "aaa/named-once", "posts": 1}
    assert sorted([repeated, once], key=sort_key)[0] is once
