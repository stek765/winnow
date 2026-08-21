<div align="center">

# winnow

**You save a post on Instagram and forget it. winnow doesn't. Analytical tool to find, verify and resume what you need, aligned with your goals.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: pytest](https://img.shields.io/badge/tested%20with-pytest-0a9edc.svg)](https://docs.pytest.org/)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

<img src="assets/winnower-millet.jpg" alt="Jean-François Millet, The Winnower (c. 1847-48)" width="360">

<sub>Jean-François Millet, <em>The Winnower</em>, c. 1847–48. National Gallery, London. Public domain.</sub>

</div>

<br>
<br>

## How it works

1. **You save a post** and forget it.
2. **Every night** winnow opens the new ones, reads **every slide of the
   carousel**, and checks each name it finds at the source — stars, last
   commit, archived or not. Facts only: it decides nothing.
3. **Once a week** `winnow recap` puts those facts next to **your profile**,
   and what comes back is about you, not about the topic.

<p align="center"><img src="assets/winnow-demo.gif" alt="Six drawn scenes: a post is saved on Instagram, the saved folder fills up, winnow opens every slide of the carousel, pulls out the names, checks each one at the source with real star counts, and your profile decides which ones survive into the weekly recap." width="840"></p>

## Overview Pipeline:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/diagrams/winnow-pipeline-dark.png">
  <img src="assets/diagrams/winnow-pipeline.png" alt="A saved Instagram post is opened slide by slide, a vision model extracts the names it mentions, each name is checked against GitHub or Hugging Face, and only verified facts are written to the findings file. A spend brake can halt the run.">
</picture>

<br> 

> A click-bait post that happens to contain a live repo with 37k stars passes. 
> 
> A beautifully made post listing repos dead for two years gets thrown out.

The caption would never tell you which is which. The check and verification process does.

## Install

```bash
pipx install git+https://github.com/stek765/winnow

winnow init
```

That is the whole setup — one command asks for what it can't guess and does
everything else itself. → [**What `winnow init` does**](#what-winnow-init-does)

## Commands

Five. Everything else `init` does for you.

| | |
|---|---|
| `winnow init` | set up, or fix whatever is missing |
| `winnow collect` | one pass now, instead of waiting for tonight |
| `winnow status` | is it alive, what did it find, what has it cost |
| `winnow recap` | the week + your profile, ready to paste into a model |
| `winnow reset-halt` | restart after the spend brake stopped it |


<br>
<br>

---

<br>

```console
$ winnow status                               (Example)
stato        attivo
spesa 7gg    USD 0.0553
programmato  ogni giorno alle 13:00 (launchd)
post visti   15
ultimo giro  20/08 18:29 (0h fa) — 8 post, 36 entita', 11 verificate
da leggere   1 file in findings/  →  winnow recap
```

`status` speaks up on its own when the last run is over 36h old, when posts
failed, or when the brake stopped it.

`winnow schedule --at 09:00 | --off`, `winnow login` and `winnow where` are
still there for when you want them directly.

## Once a week

<table>
<tr>
<td width="50%"><img src="assets/diagrams/winnow-half-tool.png" alt="A post saved on Instagram becomes, every night, the weekly recap: kept, thrown out, why — one minute to read."></td>
<td width="50%"><img src="assets/diagrams/winnow-half-you.png" alt="A file called profile.md — what you want, what you already decided, what you ruled out — turns the week into a filtered list. Two things, both verified alive with tens of thousands of stars: a self-hosted notes app is kept because it matches what you want, another crypto bot is thrown out because it falls under what you ruled out. Both real, both alive: your file decided."></td>
</tr>
<tr>
<td valign="top">

**winnow's half — automatic.**

`you save` → `winnow collect` (nightly) → `findings/`

</td>
<td valign="top">

**Your half — one file, written once.**

`winnow init` → rewrite `profile.md` → `winnow recap`

</td>
</tr>
</table>

### `winnow recap` puts the prompt, your profile and the week's findings on the clipboard. Paste them into a model and ask.

<br>
<br>

## What it costs

Measured, not estimated — two runs of 8 posts, 20 and 21 August, Claude Haiku:

| | |
|---|---|
| one post | **$0.0046** |
| one full run (8 posts) | **$0.037** |
| a week of daily runs | **~$0.26** |
| warning expense | `warn_eur_week = 3.0€` in `config.toml` |
| **max expense** | `halt_eur_week = 10.0€` — restart with `winnow reset-halt` |

Only posts you haven't seen are paid for, so a quiet week costs less. The brake
is not there to save money: a bill twenty times the estimate isn't a price, it's
a bug — a loop re-reading everything, a corrupt state file.

> ⚠️ Set a hard limit on the API key too, in the provider's console. The
> internal brake is policed by the same program that might contain the bug.

<br>

## Where things live

Nothing sits next to the code, so the command works from any directory.
`winnow where` prints the lot.

```
~/.config/winnow/
├── config.toml          your username and saved folders
├── profile.md           who you are — the judge reads this
└── env                  ANTHROPIC_API_KEY, mode 600

~/.local/share/winnow/
├── findings/2026-08-21.json    what a run found, one file per day
├── recap/2026-08-21.md         what `winnow recap` bundled for you
├── state/
│   ├── seen.json               posts already paid for
│   ├── spend.json              the ledger
│   ├── collect.log             what the last runs did
│   └── HALTED                  present = stopped on spend
└── browser-profile/            its own Chromium session, not yours
```

All of it is gitignored, and a test enforces that no personal data reaches the
source. Saved posts never leave the machine except as slides sent to the
extraction model. Override the two roots with `XDG_CONFIG_HOME` /
`XDG_DATA_HOME`, or `WINNOW_CONFIG_DIR` / `WINNOW_DATA_DIR`.

## What `winnow init` does

It asks for the API key and writes it with the right permissions, downloads the
browser, opens a window for you to sign in, **reads your saved folders off your
account** and asks which ones to watch, drops a starter profile in
`~/.config/winnow/profile.md`, and installs the daily run. Rerun it any time: it
reports where you stand instead of starting over — including telling you off
while the profile is still the example.

```console
$ winnow init

  Serve una chiave API di Anthropic (console.anthropic.com).
  Incolla la chiave (invio per saltare): ······
  ✅ scritta in ~/.config/winnow/env (600)

  Accedere a Instagram adesso? [S/n]
  cerco le tue cartelle salvate...

  Cartelle salvate trovate:

     1. github
     2. ai
     3. gym

  Quali vuoi far leggere a winnow? (es. 1,3-4) 1,2
  Di queste, quali contengono repo o tool? (invio = nessuna) 1
  ✅ 2 cartelle attive in ~/.config/winnow/config.toml

  creato ~/.config/winnow/profile.md da riscrivere con la tua situazione

  Programmarla alle 13:00? [S/n, oppure HH:MM]
  ✅ programmato ogni giorno alle 13:00 (launchd)
```

Three things stay yours, because no code can do them: **creating the API key**
(set a spend limit while you're there), **signing in** — winnow never types your
password, and the session lives in a browser profile of its own — and **writing
the profile**, which is the whole point of the tool.

Scheduling picks itself: launchd on macOS, a systemd timer or cron on Linux.
Pick an hour the machine is awake and unlocked — collecting opens a browser
window, and that needs a graphical session.

## More

The recap prompt: [`winnow/recap-prompt.md`](winnow/recap-prompt.md) — it ships
with the package, so `winnow recap` works without a checkout.
Why it is built this way: [`docs/superpowers/specs/`](docs/superpowers/specs/).

MIT — see [LICENSE](LICENSE).
