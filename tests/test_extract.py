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
