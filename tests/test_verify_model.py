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


def test_verify_model_reports_absence_when_no_results():
    def handler(request):
        return httpx.Response(200, json=[])
    v = verify_model(_client(handler), "Qwen 27B uncensored")
    assert v.checked and not v.exists
    assert "nessun modello" in v.note.lower()


def test_verify_model_network_failure_is_not_verified():
    def handler(request):
        raise httpx.ConnectError("giu'")
    v = verify_model(_client(handler), "Qwen3-32B")
    assert v.checked is False


def test_hardware_note_is_empty_when_llmfit_is_absent(monkeypatch):
    monkeypatch.setattr("winnow.verify.llmfit_available", lambda: False)
    assert hardware_note("Qwen3-32B") == ""
