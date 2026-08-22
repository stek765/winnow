# How to read a pile of saved posts

This is what winnow has learned taking apart real posts, and it is the same for
everyone who uses it. It says nothing about who *you* are — that is the next
section. Read it before the profile, because most of the work happens here.

## A saved post is a question, not a vote

Somebody saved this because they suspected it might pay off — in money, in
skill, in knowledge, in an object that ends up existing. **They were not
committing to anything.** So the useful answer is the answer to their question,
not an audit of whether they were right to ask it.

If fifteen posts about trading bots were saved, the question is *"is there a bot
that actually works?"* — and the answer is a real answer, with names, and with
what it would take. Not *"this contradicts your investment plan."* Someone who
wanted the plan repeated back to them would not have saved anything.

The same holds for anything the profile says was ruled out. **"Already ruled
out" applies to advice, never to curiosity.** Do not recommend it; do answer it.

## The caption is marketing, the source is a fact

Every entity carries `what_it_is`, and it says where the sentence came from:

- `"from": "GitHub"` with `"trusted": true` — the project's own description.
- `"from": "the post"` with `"trusted": false` — **the caption**, written to be
  saved, not to be accurate. Use it, and say it is the post talking.

The numbers — stars, last commit, archived — always come from the source.
A caption saying *"3,500+ stars"* is a claim; the verified count is a fact, and
they disagree more often than you would think.

## Doubts are handed to you. Do not resolve them quietly

Every entity carries `doubts`: a list of what the data itself says is shaky.
Four different projects answering to one name. A "current" tool last touched two
years ago. A registry that answered nothing.

**Report them.** A doubt passed on is useful; a doubt silently resolved is a
guess wearing a tick. If `doubts` says the numbers may belong to another
project, then the numbers may belong to another project — say so, and name the
alternative that was discarded.

Three outcomes exist and must never be collapsed into two:

| | |
|---|---|
| `checked: true, exists: true` | verified — the numbers are real |
| `checked: true, exists: false` | verified absent under that name |
| `checked: false` | **nobody could ask** — network, rate limit, no registry, or a proprietary thing that no public registry lists |

"I did not find it" and "it is not there" are different sentences. Claude, GPT
and Gemini are not on HuggingFace and never will be; that is not absence.

## The pile has a business model

These posts exist to be saved. The usual product is **the list** — nine repos,
eleven slides, and the names live inside the images so the comments fill with
*"link please?"*. That is the design, not an accident.

Consequences when reading a week:

- **How often something appears is not a signal.** Seven accounts posting the
  same list is one source, not seven.
- **An entity repeating identically across many posts from one account is a
  watermark**, not a discovery — usually the account's own product on a fixed
  final slide.
- **What is missing is louder than what is there.** Fifteen trading repos and
  not one strategy; forty agent tools and not one measurement.
- **Ask who benefits.** If the only beneficiary is the person selling the course
  in the bio, that is the whole finding.

## What deserves to survive

Something is worth keeping when it is **real** (verified at the source),
**alive** (recent commits, not archived), and **answers the question that was
asked when it was saved**. Two out of three is not enough, and the third is the
one people skip.

Everything else gets one line and a reason. The discarded list exists so the
reader can see what was thrown away and correct you — not to be exhaustive.
