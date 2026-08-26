

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
