import httpx
from winnow.verify import verify_model, hardware_note


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_verify_model_finds_an_existing_model():
    def handler(request):
        assert "/api/models" in request.url.path
        return httpx.Response(200, json=[{
            "modelId": "Qwen/Qwen3-32B", "downloads": 900000, "likes": 1200,
        }])
    v = verify_model(_client(handler), "Qwen3-32B")
    assert v.checked and v.exists
    assert v.description and "Qwen/Qwen3-32B" in v.description


def test_hf_finding_nothing_is_not_proof_of_absence():
    def handler(request):
        return httpx.Response(200, json=[])
    v = verify_model(_client(handler), "Qwen 27B uncensored")
    assert v.checked is False
    assert "proprietary" in v.note


def test_verify_model_network_failure_is_not_verified():
    def handler(request):
        raise httpx.ConnectError("giu'")
    v = verify_model(_client(handler), "Qwen3-32B")
    assert v.checked is False


def test_hardware_note_is_empty_when_llmfit_is_absent(monkeypatch):
    monkeypatch.setattr("winnow.verify.llmfit_available", lambda: False)
    assert hardware_note("Qwen3-32B") == ""


def test_a_model_whose_name_does_not_match_is_not_a_hit():
    """The failure this rule exists for, found on 2026-08-20: searching
    'Claude Code' returned a random GGUF conversion with that word buried in
    its name, and winnow reported its 707 likes as if they were Claude Code's.
    Real numbers on the wrong project are worse than no check at all."""
    def handler(request):
        return httpx.Response(200, json=[{
            "modelId": "DavidAU/Qwen3.6-40B-Claude-4.6-Opus-Deckard-NEO-GGUF",
            "downloads": 384393, "likes": 707,
        }])
    v = verify_model(_client(handler), "Claude Code")
    assert v.checked is False, "scartato, non dichiarato inesistente"
    assert v.stars is None and v.url is None, "i 707 like non sono suoi"
    assert "claude code" in v.note.lower()


def test_the_discarded_near_misses_are_named_so_the_judge_can_see_them():
    def handler(request):
        return httpx.Response(200, json=[
            {"modelId": "someone/Totally-Unrelated", "downloads": 10, "likes": 1},
        ])
    v = verify_model(_client(handler), "Codex")
    # In `candidates` and not buried in the prose: the reader has to be handed
    # what was thrown away, not made to parse a sentence for it.
    assert "someone/Totally-Unrelated" in v.candidates


def test_punctuation_and_case_do_not_stop_a_real_match():
    def handler(request):
        return httpx.Response(200, json=[{
            "modelId": "deepseek-ai/DeepSeek-V4-Flash", "downloads": 5000,
            "likes": 3571,
        }])
    v = verify_model(_client(handler), "deepseek v4 flash")
    assert v.exists and v.stars == 3571
    assert v.url == "https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash"


def test_an_owner_qualified_name_matches_the_full_id():
    def handler(request):
        return httpx.Response(200, json=[{
            "modelId": "Qwen/Qwen3-32B", "downloads": 900000, "likes": 1200,
        }])
    v = verify_model(_client(handler), "Qwen/Qwen3-32B")
    assert v.exists


def test_the_matching_model_wins_even_when_a_louder_one_is_listed_first():
    def handler(request):
        return httpx.Response(200, json=[
            {"modelId": "bartowski/Qwen3-8B-GGUF", "downloads": 900000, "likes": 999},
            {"modelId": "Qwen/Qwen3-8B", "downloads": 400000, "likes": 500},
        ])
    v = verify_model(_client(handler), "Qwen3-8B")
    assert v.exists and v.stars == 500
    assert v.description == "Qwen/Qwen3-8B"


def test_a_proprietary_model_is_unknown_not_absent():
    """Osservato dal vivo il 2026-08-21: `✗ Claude — non esiste alla fonte`.
    HuggingFace ospita pesi aperti; Claude, GPT e Gemini non ci sono e non ci
    saranno mai. Dire "non esiste" del modello piu' usato al mondo e' falso."""
    def handler(request):
        return httpx.Response(200, json=[])
    v = verify_model(_client(handler), "Claude")
    assert v.checked is False
    assert v.exists is not False


def test_llmfit_failure_does_not_leak_its_usage_screen():
    """`llmfit fit Claude` stampa l'help, e quell'help finiva incollato nei
    findings e poi nel contesto del giudice, dove sembra un guasto di winnow."""
    from winnow.verify import hardware_note
    import winnow.verify as verify

    class Done:
        returncode = 2
        stdout = ""
        stderr = "error: unexpected argument 'Claude'\n\nUsage: llmfit fit [OPTIONS]"

    verify.llmfit_available = lambda: True
    verify.subprocess.run = lambda *a, **k: Done()
    assert hardware_note("Claude") == ""
