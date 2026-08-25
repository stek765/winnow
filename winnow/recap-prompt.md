# The judge — how to produce the weekly recap

The judge is not code. It is a prompt plus the profile you wrote. Swap the
model and nothing in the collector changes.

`winnow recap` builds four blocks: the week's findings, the mentality
(`winnow/mentality.md` — the same for everyone), your profile, and this file as
the closing ask. Everything above the line is for you; everything below is
block 4.

## The prompt

<!-- PROMPT -->

> **Write the recap in the language my profile is written in** — that is the
> language I think in, and this is for me to read, not to publish.
>
> Produce it in this shape, in this order. Nothing else.
>
> **1 — The pile. Two short paragraphs, and they have to earn their place.**
> The page already prints the counts. **Never restate a number I can see** —
> «thirty posts, fifteen kept, one unreadable» is the header, not a thought.
>
> Say the thing the numbers cannot: what the pile is mostly made of, what is
> conspicuously *missing*, who benefits. Then end on something I can act on —
> a knob to turn, a folder to change, a habit that is costing me. If the
> paragraph could have been written without reading this particular week,
> delete it and write the one that could not.
>
> **2 — What is worth my time**, split into a handful of **sections that come
> out of this week's pile**, not a fixed list — name them after what they are
> about. Inside a section, most worth my time first.
>
> **Section names are at most three words** — «Reverse engineering»,
> «Self-hosting», «Trading». They become filter buttons on a page, and a name
> that wraps onto two lines is not a button. Put the argument in the entries,
> never in the heading. **No emoji anywhere in the recap**, headings included.
>
> Every entry is four lines, always in this order:
>
> - **A plain sentence saying what the thing does**, as the headline — «an
>   encrypted network that runs on 150 bit/s radio», not `markqvist/Reticulum`.
>   A repo slug cannot be scanned, and scanning is the point.
> - **Is it real and alive** — the verified numbers, never the caption. Say
>   plainly when nothing could be checked.
> - **What it answers of mine** — which question of mine it touches, or, when
>   it touches nothing of mine, why it stands up on its own anyway.
> - **The doubt**, when there is one worth passing on. Skip the line otherwise.
>
> **How those lines have to read.** The prose is where this stops being
> pleasant to use, and three rules kill the whole problem:
>
> - **Never open on a pronoun.** «È l'unica cosa che…», «Questo fa…», «Serve
>   a…» all force me back up to the heading to find out what «it» is — on
>   every single entry. Name the thing, or name what it does: «Bumblebee
>   guarda i pacchetti che hai su disco…».
> - **One idea per sentence, two sentences per line.** A sentence carrying a
>   main clause, a subordinate and an aside is one I have to read twice.
> - **Whole sentences.** «Nessuno dai dati.» is a note to yourself, not a
>   sentence — write «Dai dati non emerge nessun dubbio.» or drop the line.
>
> The test: each line must **stand on its own without the heading above it**.
> If it does not, it is not written yet.
>
> Two things earn a place in that list, and **both lanes stay open**:
>
> - it **hooks onto something of mine** — a question I have open, a tool I
>   already use, a decision I am in the middle of. Low bar.
> - it **stands on its own** — it changes how something is done, it is a way
>   to earn, it is a real shift in the field. High bar, and it belongs here
>   even when it touches nothing in my profile. Cutting this lane turns the
>   filter into an echo of what I already think, which is the one outcome I do
>   not want.
>
> **3 — The name, the numbers, the link** go at the end of each entry as a
> footnote, not at the front.
>
> **4 — What you binned. One line per thing, never one line per group.**
> Every single thing in block 1 appears exactly once: either above, or here.
>
> A list post is only packaging. Its thirty-fourth entry gets its own line and
> its own reason, weighed exactly like a thing that was the whole subject of
> its own post — somebody saved all fifty, not the wrapper. «Repos everyone
> knows (18 of them)» is not a line: it is eighteen lines, each with a name.
> This is the section I read to correct you, and a bucket cannot be corrected —
> I cannot see which eighteen, so I cannot tell you which one you got wrong.
>
> Binning something for being famous is a fine reason. Binning it *invisibly*,
> because it was travelling inside a list, is not.
>
> **Every binned thing also carries a `verdict`: two or three words, in
> capitals, naming the single reason it stopped.** The page groups by verdict
> and prints the count beside each, and that count is the part I read first —
> it is the shape of how you are thinking, and it is what lets me say «thirty-
> one for out-of-scope is too many, show me those thirty-one». A hundred and
> twenty-nine prose lines cannot be argued with; ten counted groups can.
>
> Reuse these wherever they fit, so that one week can be compared with the
> next. The first six say something about **the feed**, the last four about
> **me** — that division is the useful one, and it is why they are ordered so:
>
> | verdict | when |
> |---|---|
> | `NON ESISTE` | no source has anything under that name |
> | `FERMO DA ANNI` | real, and untouched — while the post calls it current |
> | `NOME FRAGILE` | several projects answer to the name, or the source replied under a different owner: the numbers may not be its own |
> | `CHI CI GUADAGNA` | the only beneficiary is whoever is selling it |
> | `SOLO ANNUNCIO` | news with no artefact behind it |
> | `NON VERIFICATO` | no public registry to ask. **Not** the same as absent |
> | `DOPPIONE` | the caption's spelling of something already listed |
> | `GIA' TUO` | I already have it installed |
> | `LO CONOSCI` | true, alive, and famous enough that I already know it |
> | `FUORI BERSAGLIO` | true and alive, and touches nothing I do |
>
> Invent a new one when none of these is honest — a forced fit is worse than a
> new word. Do not invent one to avoid saying `FUORI BERSAGLIO`.
>
> ⚠️ **The reason belongs to the thing, not to the group. A reason that fits
> twenty things is not a reason** — it is the group's name written a second
> time. `"why": "famoso"` under twenty entries, or one sentence at the top of
> a list of bare names, are the same refusal wearing different clothes: I
> cannot argue with either, and arguing with it is the only reason this
> section exists.
>
> Write what makes *that* thing droppable: «468k stelle, un elenco di API
> gratuite che si apre una volta e non si riapre» can be contested. «famoso»
> cannot. If two entries could swap reasons without anyone noticing, neither
> has been given one.
>
> ⚠️ **`checked: false` never becomes `LO CONOSCI`.** When no source answered,
> the verdict is `NON VERIFICATO` — even when you are certain you know the
> thing, and especially then. Answering from what you know instead of from
> what was checked is the one move that makes the whole tool worthless: it is
> the difference between a filter and an opinion.
>
> **Write `post` and `slide` on the binned things too, not only on the kept
> ones.** The page uses them to print, beside each thing that got through, the
> other things that were on that same slide and what stopped each of them —
> which is the answer to the question I actually ask looking at a wall of
> fifty links: *why this one and not the other forty-nine?*
>
> ---
>
> **Then, last, repeat the whole thing as one JSON block** in a ```json fence.
> That block becomes a page of pictures, so it needs two things the prose does
> not: a **`title` of at most six words** — what the tile says — and the
> **`post` and `slide`** each thing came from, which are written next to it in
> block 1 (`post DcNOt8mkugc slide 3`). The page shows me that slide, so I can
> see what you saw before I read a word of what you thought about it.
>
> Put anything shaky in **`doubt`**, on its own — not buried in `why`. It is
> the field I look at first.
>
> ```json
> {
>   "week": "2026-08-23",
>   "counts": {"posts": 15, "kept": 9, "failed": 0, "usd": 0.08},
>   "comment": "the paragraphs from 1, blank line between them",
>   "categories": [
>     {"name": "Reverse engineering", "items": [
>       {"title": "Sei parole, non di piu'",
>        "does": "the plain sentence — what it does",
>        "why": "what it answers of mine",
>        "doubt": "the weak point, or leave it out",
>        "kind": "tool|model|product|news|claim",
>        "post": "DcNOt8mkugc", "slide": 3,
>        "name": "owner/repo", "url": "https://...",
>        "stars": 8575, "last_commit": "2026-08",
>        "state": "alive|stale|unknown|absent"}
>     ]}
>   ],
>   "discarded": [{"name": "owner/repo", "verdict": "LO CONOSCI",
>                  "why": "the reason",
>                  "post": "DcNOt8mkugc", "slide": 3}]
> }
> ```
