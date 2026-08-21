# The judge — how to produce the weekly recap

The judge is not code. It is a prompt plus the profile you wrote. Swap the
model and nothing in the collector changes.

`winnow recap` bundles everything below this line together with your profile
and the week's findings, and copies it to the clipboard. Everything above the
line is for you; everything below is for the model.

## The prompt

<!-- PROMPT -->

> Below you have my profile and this week's findings: collected facts, already
> checked at the source. The judging is yours.
>
> **Write the recap in the language my profile is written in** — that is the
> language I think in, and this is for me to read, not to publish.
>
> Apply a two-lane rule:
> - 🎯 **Hook** — it touches something I already have open. Low bar: it only
>   has to be true and alive.
> - 🌍 **Opening** — it touches nothing of mine but is strong in itself (a way
>   to earn, a tool that changes how I work day to day, a signal of where the
>   market is going). High bar: it has to be worth it on its own.
>
> Throw out everything else, and in particular anything whose only beneficiary
> is the person selling it.
>
> Write the recap like this:
> 1. **Header** — how many posts, how many kept, what it cost.
> 2. **💬 Comment** — ONE, not one per line. What you notice looking at the
>    pile (fads, repetitions across accounts, patterns) and what I should do
>    about it.
> 3. **Kept** — for each: what it is → is it alive? (use the verified data,
>    never the caption) → what of mine it touches.
> 4. **Thrown out** — one line each, with the reason. They exist so I can see
>    what you binned and correct you.

## Reading `shape` and the kinds

Each post carries a `shape`, decided when it was read:

| `shape` | What the post was | What to expect in it |
|---|---|---|
| `list` | an enumeration — tools, sites, repos, things to build | one entity per entry |
| `news` | an announcement or a finding, often a talking-head video | the thing announced, plus anything it names |
| `other` | neither | whatever was named |

And each entity a `kind`. Three of them can be checked at a source (`repo`,
`model`) or cannot (`platform`, `item`, `news`, `claim`) — the last three are
**not failures of verification**, they are things no registry can answer for:

- `item` — an entry of a list that is not a product: a thing to build, a
  technique, a step. Judge it against the profile, never against a star count.
- `news` — what a post announced. It goes in the 🌍 Opening lane by nature:
  ask whether it changes anything for the reader, not whether it is popular.
- `slide: 0` means the entity came from the **caption**, not from a slide. On a
  video that is the only place it could come from.

## Reading the verification block

Each entity carries a `verification` object with three distinct outcomes.
Never collapse them:

| | Meaning |
|---|---|
| `checked: true, exists: true` | verified at the source — trust `stars`, `last_commit`, `archived` |
| `checked: true, exists: false` | verified absent — the thing does not exist under that name |
| `checked: false` | **not checked** — network down, rate limit, or no automatic source |

An old `last_commit` on an otherwise plausible entry usually means a homonym:
the slide meant a newer project that happens to share its name with an
abandoned one. Say so rather than declaring the project dead.
