import os



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
