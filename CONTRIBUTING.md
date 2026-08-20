# Contributing

winnow is small on purpose. Two rules shape every change:

1. **The collector never judges.** It extracts what is written and checks it at
   the source. Anything that weighs, ranks, or scores belongs to the judge — and
   the judge is a prompt plus your profile, not code in this repo.
2. **Never report unverified as verified.** A network failure, a rate limit and
   a genuine 404 are three different outcomes. Collapsing them is the one bug
   that quietly destroys the tool's whole value.

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
pytest
```

## Tests

Pure logic — state, budget, parsing, normalization — is tested and must stay
tested. Browser navigation is not tested automatically: it is verified by hand
against the real site, because the DOM changes without notice.

If you add a new source of truth (a registry, an API), add it to `verify.py`
with the same three-way outcome: verified-present, verified-absent, not-checked.

## Adding support for another platform

The collector is written against Instagram's saved folders, but nothing in
`extract.py`, `verify.py`, `state.py` or `budget.py` knows that. A new platform
means a new module with the same shape as `browser.py`. Open an issue first —
it's worth agreeing on the boundary before the code exists.
