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
> **1 — The pile, in one paragraph.** What you notice looking at all of it at
> once: what it is mostly made of, what is conspicuously missing, who benefits.
> One paragraph. Not one comment per entry.
>
> **2 — What is worth my time**, split into a handful of **sections that come
> out of this week's pile**, not a fixed list — name them after what they are
> about. Inside a section, most worth my time first.
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
>   "comment": "the paragraph from 1, blank line between paragraphs",
>   "categories": [
>     {"name": "the section name from 2", "icon": "one emoji", "items": [
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
>   "discarded": [{"name": "owner/repo", "why": "the reason",
>                   "post": "DcNOt8mkugc", "slide": 3}]
> }
> ```
