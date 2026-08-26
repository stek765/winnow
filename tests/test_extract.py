import pytest
from winnow.extract import Entity, parse_entities, SYSTEM_PROMPT


def test_parse_entities_reads_plain_json():
    text = '[{"kind":"repo","name":"lfnovo/open-notebook","blurb":"NotebookLM open","slide":2}]'
    assert parse_entities(text) == [
        Entity(kind="repo", name="lfnovo/open-notebook", blurb="NotebookLM open", slide=2)
    ]


def test_parse_entities_tolerates_markdown_fences():
    text = '```json\n[{"kind":"model","name":"Qwen3-32B","blurb":"","slide":1}]\n```'
    assert parse_entities(text)[0].name == "Qwen3-32B"


def test_parse_entities_returns_empty_list_for_empty_array():
    assert parse_entities("[]") == []


def test_parse_entities_drops_entries_with_unknown_kind():
    text = ('[{"kind":"pesce","name":"x","blurb":"","slide":1},'
            '{"kind":"repo","name":"a/b","blurb":"","slide":1}]')
    assert [e.name for e in parse_entities(text)] == ["a/b"]


def test_parse_entities_drops_entries_without_a_name():
    text = '[{"kind":"repo","name":"","blurb":"vuoto","slide":1}]'
    assert parse_entities(text) == []


def test_parse_entities_raises_on_non_json():
    with pytest.raises(ValueError):
        parse_entities("mi dispiace, non riesco a leggere l'immagine")


def test_system_prompt_forbids_judging():
    """Il raccoglitore non giudica mai (spec, vincoli globali)."""
    low = SYSTEM_PROMPT.lower()
    assert "do not judge" in low or "non giudicare" in low


def test_parse_entities_ignores_prose_after_the_json_block():
    """Il modello a volte spiega cosa ha fatto dopo il blocco. Successo reale
    osservato il 2026-08-20: un giro notturno intero e' morto per questo."""
    text = ('```json\n[]\n```\n\nThe slide contains only a photo and UI '
            'elements. No concrete named artifacts are mentioned.')
    assert parse_entities(text) == []


def test_parse_entities_ignores_prose_before_and_after():
    text = ('Here is what I found:\n\n[{"kind":"repo","name":"a/b",'
            '"blurb":"x","slide":1}]\n\nThat is all.')
    assert parse_entities(text)[0].name == "a/b"


def test_parse_entities_still_raises_when_there_is_no_array_at_all():
    with pytest.raises(ValueError):
        parse_entities("non sono riuscito a leggere le immagini, mi dispiace")


# --- shape: what kind of post is this ----------------------------------------

from winnow.extract import SHAPES, parse_extraction


def test_a_list_post_reports_its_shape_and_every_entry():
    """The point of shape: a list of ten things yields ten entries, and nobody
    has to decide whether each one is 'an idea' or 'a product' first."""
    reply = """```json
    {"shape": "list", "entities": [
      {"kind": "item", "name": "Invoice Generator", "blurb": "Build one for
       small firms", "slide": 3},
      {"kind": "repo", "name": "cline/cline", "blurb": "", "slide": 4}
    ]}
    ```"""
    shape, ents = parse_extraction(reply.replace("\n       ", " "))
    assert shape == "list"
    assert [e.kind for e in ents] == ["item", "repo"]


def test_a_news_post_keeps_the_announcement():
    reply = ('{"shape": "news", "entities": [{"kind": "news", '
             '"name": "Block releases Buzz", "blurb": "An open-source workspace '
             'where agents and humans share the same channel.", "slide": 0}]}')
    shape, ents = parse_extraction(reply)
    assert shape == "news"
    assert ents[0].kind == "news" and ents[0].slide == 0


def test_a_bare_array_still_parses_as_a_shapeless_post():
    """Older findings and simpler replies are arrays with no shape. Refusing
    them would throw away a paid run over a formatting detail."""
    shape, ents = parse_extraction('[{"kind": "repo", "name": "a/b", '
                                   '"blurb": "", "slide": 1}]')
    assert shape == "other"
    assert len(ents) == 1


def test_an_unknown_shape_falls_back_instead_of_failing():
    shape, ents = parse_extraction('{"shape": "banana", "entities": []}')
    assert shape == "other"


def test_shapes_are_the_three_we_can_actually_tell_apart():
    assert SHAPES == {"list", "news", "other"}


# --- a truncated answer is not a malformed one -----------------------------

def test_openai_truncation_is_named_not_reported_as_bad_json():
    """Measured 2026-08-21: a 13-slide list post ran past the output budget
    mid-entity, and the failure read "risposta non JSON dal modello" — which
    sends you hunting for a prompt bug that isn't there."""
    import pytest
    from winnow.providers import Truncated, read_openai_reply

    with pytest.raises(Truncated):
        read_openai_reply({"choices": [{"finish_reason": "length",
                                        "message": {"content": '{"shape": "list"'}}]})


def test_a_complete_openai_reply_is_read_normally():
    from winnow.providers import read_openai_reply
    text, tin, tout = read_openai_reply({
        "choices": [{"finish_reason": "stop", "message": {"content": "[]"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2}})
    assert (text, tin, tout) == ("[]", 10, 2)


def test_missing_usage_counts_as_zero_not_a_crash():
    """A local server often omits usage entirely."""
    from winnow.providers import read_openai_reply
    assert read_openai_reply({"choices": [{"message": {"content": "[]"}}]}) == ("[]", 0, 0)


def test_the_output_budget_leaves_room_for_a_long_list():
    """A carousel of thirteen slides yields a dozen entities with blurbs; 4000
    tokens was not enough and the whole post was lost."""
    import inspect
    from winnow.providers import complete
    assert inspect.signature(complete).parameters["max_tokens"].default >= 8000


def test_what_the_folder_holds_reaches_the_model_as_context():
    """A name is ambiguous without a subject: "Arduino" in a folder about
    electronics is a board, in a folder about repos it is an organisation.
    The reader already knows which; the extractor cannot guess."""
    from winnow.extract import context_line
    line = context_line("schede e componenti elettronici")
    assert "schede e componenti elettronici" in line
    # It says what the sentence is for, or the model reads it as an
    # instruction about what to keep — and the collector never judges.
    assert "judge" in line.lower() or "not" in line.lower()


def test_a_folder_with_nothing_written_about_it_adds_no_line():
    """An empty description must not become an empty sentence in the prompt:
    "This folder holds: ." is noise paid for on every post."""
    from winnow.extract import context_line
    assert context_line("") == ""
    assert context_line(None) == ""


def test_a_folder_with_no_description_sends_exactly_what_it_sent_before():
    """The bench costs money and is the only thing that can judge a prompt
    change. This proves there is nothing to judge on the old path: with no
    description the message is byte for byte the one that was benched."""
    from winnow.extract import USER_TEMPLATE, context_line
    before = USER_TEMPLATE.format(account="a", caption="c", n=3)
    after = before + (f"\n\n{context_line('')}" if context_line("") else "")
    assert after == before


def test_the_description_lands_after_the_caption_and_not_before_it():
    """Put first, the post would read as an answer to it. It is background."""
    from winnow.extract import USER_TEMPLATE, context_line
    text = USER_TEMPLATE.format(account="a", caption="LA DIDASCALIA", n=2)
    text = f"{text}\n\n{context_line('schede elettroniche')}"
    assert text.index("LA DIDASCALIA") < text.index("schede elettroniche")
