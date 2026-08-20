# Working on winnow

Notes for an AI agent (or a human) picking this repo up cold. English, to match
the rest of the contributor-facing docs.

Read [`README.md`](README.md) for what it does and
[`docs/superpowers/specs/`](docs/superpowers/specs/) for why it is built this way.
Those specs record decisions that were argued once and should not be re-argued.

## Two rules that are not up for negotiation

1. **The collector never judges.** `extract.py` pulls out what is written;
   `verify.py` checks it against a source. Anything that weighs, ranks, or scores
   belongs to the judge — and the judge is a prompt plus a user-written profile
   ([`docs/recap-prompt.md`](docs/recap-prompt.md)), not code in this repo.
2. **Never report unverified as verified.** A network failure, a rate limit and a
   genuine 404 are three different outcomes:
   `checked=False` / `checked=True, exists=False` / `checked=True, exists=True`.
   Collapsing them quietly destroys the tool's entire value.

A corollary learned the hard way: attaching real numbers to the *wrong* project is
worse than not checking at all. It looks authoritative and it is false.

## Map

| File | Holds |
|---|---|
| `paths.py` | where config and data live (XDG, overridable — that is what makes it testable) |
| `config.py` | `config.toml` → `Config`. No personal data may exist outside it |
| `state.py` | `seen.json` — which posts were already processed |
| `budget.py` | spend ledger + the emergency brake. **The only module that can stop everything** |
| `browser.py` | Playwright: session, folder listing, slide capture |
| `extract.py` | slides → entities, via a cheap vision model |
| `verify.py` | GitHub / HuggingFace / llmfit |
| `run.py` | orchestration; writes `findings/` |
| `setup.py` | `winnow init` — guided, repeatable first-time setup |
| `cli.py` | argument parsing only; keep it thin |

Pure logic is separated from I/O on purpose: everything except `browser.py` is
tested without network or API access.

## Development

Installed editable, so edits take effect immediately with no reinstall:

```bash
pipx install --editable .
pipx inject winnow pytest
pytest                      # 101 tests, all offline
```

⚠️ Moving this directory breaks the installed command — reinstall if you do.

## Gotchas already paid for — do not rediscover these

- **Instagram has no `<article>` and no `<h1>`** on a post page. The caption *and*
  the account name come from the `og:description` meta tag.
- **`?img_index=N` does not work on a cold load.** It is handled client-side, so a
  fresh `goto` always lands on slide 1. Advance by clicking `aria-label="Avanti"`
  (localised — see `NEXT_LABELS`) and wait for the image source to actually change.
- **The visible slide is the largest-area image with `x >= 0`.** Filtering by width
  alone catches the suggested-posts thumbnails further down the page.
- **Wait for elements, never for a duration.** A fixed sleep silently truncated the
  folder listing — 12 posts instead of 24, and 0 instead of 12 on another folder. No
  error, just less data. That class of bug is the worst one here.
- **GitHub: search `in:name` and require the name to actually match.** Sorting by
  stars returns the most famous repo containing those words.
- **HuggingFace: sort by downloads.** The default order puts a zero-download
  conversion above the official model.
- **launchd, not cron, on macOS.** cron skips runs missed while the machine slept and
  never says so.
- **A model may wrap its JSON in a fence and then explain itself.** Parse the fenced
  block, or the outermost array — never assume the whole reply is JSON.
- **One bad post must not kill the run.** Each post is isolated; failures land in
  `findings.failed` and the post is marked seen so it is not paid for nightly.

## Ideas, not started

### An interface

Today winnow is a CLI that writes JSON, and the findings are read by a model. There
is no way to *look* at what it has collected — to browse a week, see what was kept
and thrown out, or correct a judgement.

Two directions, both open:

- **A TUI.** [Textual](https://textual.textualize.io/) is the natural fit and the
  author has used it before. A two-pane browser — findings on the left, the entity
  and its verification on the right — would sit naturally next to `winnow status`
  and require no server, no build step, and no second language.
- **A real UI.** More work and a bigger dependency surface, but it could show what a
  terminal cannot: thumbnails of the slides an entity came from, and a week at a
  glance.

Open questions before either is worth starting:

- Is the thing to browse the **findings** (facts) or the **recaps** (judgements)?
  They are different products. Findings are complete but dull; recaps are the part
  worth revisiting, and they do not currently get saved anywhere.
- **Would it actually get used?** The reason winnow exists is that saved posts never
  get revisited. An interface that must be opened deliberately risks inheriting
  exactly that problem.
- Should corrections feed back — marking a judgement wrong so the profile can be
  amended? That would close the loop, and it is the only feature here that would
  make the filter improve over time rather than stay still.
