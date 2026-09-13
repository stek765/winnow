import os

import pytest

# --- the SDK moved under us -------------------------------------------------
#
# anthropic 1.0.0 removed `temperature` from `messages.create`. winnow declared
# `anthropic>=0.40` with no ceiling, so a fresh install today got the new SDK
# and *every* extraction died with a TypeError before a single post was read.
# Found on 2026-08-26 by an experiment that was measuring something else.

def test_temperature_is_only_sent_to_an_sdk_that_takes_it():
    """Passed blind it is a TypeError; dropped blind it is a silent change to
    a documented invariant. So it is asked for, and the answer is honest."""
    from winnow.providers import accepts_temperature

    class Old:
        def create(self, *, model, max_tokens, system, temperature, messages):
            ...

    class New:
        def create(self, *, model, max_tokens, system, messages):
            ...

    assert accepts_temperature(Old().create) is True
    assert accepts_temperature(New().create) is False


def test_a_wrapper_that_hides_its_arguments_is_assumed_to_take_it():
    """`**kwargs` tells us nothing. Guessing "no" would quietly turn off
    determinism on an SDK that supports it; guessing "yes" fails loudly and
    is therefore the safer guess."""
    from winnow.providers import accepts_temperature

    def wrapper(**kwargs):
        ...

    assert accepts_temperature(wrapper) is True


def test_the_key_file_is_loaded_where_the_key_is_needed(tmp_path, monkeypatch):
    """It used to be loaded by `winnow collect` alone. The window runs recaps
    and draws in a server process that never touches that command, and every
    one of them died on «Could not resolve authentication method» with the key
    on disk the whole time."""
    from winnow import paths, providers
    env = tmp_path / "env"
    env.write_text('ANTHROPIC_API_KEY="sk-ant-fromfile"\n', encoding="utf-8")
    monkeypatch.setattr(paths, "env_file", lambda: env)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    providers.load_key("anthropic")
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-fromfile"


def test_a_key_in_the_environment_wins_over_the_file(tmp_path, monkeypatch):
    """One run on another account by exporting a variable, without editing
    anything on disk."""
    from winnow import paths, providers
    env = tmp_path / "env"
    env.write_text('ANTHROPIC_API_KEY="sk-ant-fromfile"\n', encoding="utf-8")
    monkeypatch.setattr(paths, "env_file", lambda: env)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-exported")
    providers.load_key("anthropic")
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-exported"


def test_a_local_model_has_no_key_to_look_for(tmp_path, monkeypatch):
    from winnow import paths, providers
    monkeypatch.setattr(paths, "env_file", lambda: tmp_path / "nothing")
    providers.load_key("local")          # must not raise


def test_stop_asked_cuts_the_stream_instead_of_waiting_it_out(monkeypatch):
    """The streamed reply used to be uninterruptible: `judge.ask` only checks
    `should_stop` before a call and inside a backoff, never while the model
    itself is writing — which is where a recap spends most of its time.
    `_anthropic` must stop pulling from `text_stream` as soon as it is asked,
    not read every piece and decide afterwards."""
    import sys
    import types

    from winnow import providers

    class FakeStream:
        def __init__(self, pieces):
            self.text_stream = iter(pieces)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            raise AssertionError("must stop before the reply is complete")

    class FakeMessages:
        def stream(self, **kw):
            return FakeStream(["uno", "due", "tre", "quattro"])

    class FakeAnthropic:
        def __init__(self):
            self.messages = FakeMessages()

    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = FakeAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)

    seen = []                             # cumulative characters, per piece
    with pytest.raises(providers.Interrupted):
        providers._anthropic("m", "", "hi", [], 100, 0.0,
                             on_progress=seen.append,
                             should_stop=lambda: len(seen) >= 2)
    assert seen == [3, 6]                 # "uno", then "unodue" — never "tre"
