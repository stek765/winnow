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
