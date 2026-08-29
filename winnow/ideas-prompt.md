# The ideas — what a pile of saved things would do for one person

The recap answers *is this worth my time*. This answers a different question,
and it is the one nobody else can answer for you: **what would this thing do
in my life?** Not what it does — that is on its README.

`winnow ideas` builds three blocks: a handful of things **drawn at random**
from everything ever kept, the profile, and this file as the closing ask.
Everything above the line is for you; everything below is block 3.

**One idea per draw, not a page of them.** Seven ideas arrive as a document,
and a document gets skimmed and closed. One arrives as a proposal — it is read,
and then either taken or thrown away, which is the only two things an idea is
for. Another one is one press of the die away, and it costs about a cent.

**Why random and not the best ones.** A judge that always starts from what
matters most keeps landing on the same three subjects, which are the ones
already being worked on — and an idea you already had is not an idea. The draw
is the material: an unlikely pairing is the only thing here that can surprise
its reader. It also means some of what comes up will lead nowhere, and saying
so is part of the answer, not a failure of it.

**Why the profile is a tint and not the brief.** Read against a plan, every
drawn thing becomes a compliance check against that plan — that failure was
measured on a real recap, where fifteen saved posts were dismissed by quoting
the reader's plan back at them. Here the profile is only there so an idea can
be *about a real life* instead of about nobody: the machine on the desk, the
things already installed, the months that are free and the ones that are not.

## The prompt

<!-- PROMPT -->

> **Write in {language}.** That is the language winnow is set to, and this is
> for me to read, not to publish.
>
> Above you have things I saved and winnow kept, **drawn at random**. Not a
> ranking, not a plan, not a to-do list. Pick **the one pairing that is worth
> my time** and answer one question with it: **what would this do in my life?**
>
> Not what it is. Not whether it is good. What it would *change* — an evening,
> a habit, a project I already have half-built, a thing I would stop paying
> for, a thing I would understand that I do not understand now.
>
> **One idea. Not two, not a list.** If several of the drawn things belong in
> the same idea, use them; if the best idea uses one of them, use one. What you
> leave out is not reported — another draw is one press away.
>
> **How to write it.**
>
> - **Throw it out, do not sell it.** It is a hypothesis. Write it like
>   someone thinking out loud, not like someone who has decided. «Si potrebbe»,
>   not «devi». Say what is weak about it in the same breath.
> - **Concrete or nothing.** «Potresti usarlo per imparare» is not an idea.
>   «Lo punti sul firmware che hai già in casa e vedi cosa trova in una sera»
>   is one. Name the thing that already exists in my life that it would touch.
> - **Never audit my plan.** Do not tell me it contradicts what I decided, do
>   not rank my priorities, do not hand me a schedule.
>
> Answer with **JSON only**, in a ```json fence, in this shape — a single
> object, no array:
>
> ```json
> {
>   "title": "at most five words, naming the idea and not the tool",
>   "uses": ["exact names of the drawn things this idea uses"],
>   "gist": "THREE LINES ON A NARROW CARD: at most 28 words and 170
>            characters, counted, hard limits. Forty words became six lines on
>            the card and stopped being a glance, which is the only thing this
>            field is for. The whole idea in plain words: what I would end up
>            with, and what it touches that already exists. It has to stand
>            alone — never a teaser, never «scopri come», never a question.
>            Everything that does not fit belongs in `idea`, which has room.",
>   "difficulty": "exactly one of: facile, media, tosta. These three are keys,
>            not words to show me — the page prints them in {language} itself.
>            Write them exactly as they are here whatever language you answer
>            in, or the page cannot colour them.",
>   "time": "how long the whole thing takes before it is usable, two or three
>            words **in {language}** — an evening, a weekend, a fortnight.
>            Honest, not encouraging.",
>   "idea": "four to six sentences. The idea in full — how it would actually
>            work, what it would replace or unlock, why these things together.
>            Say here what the gist had no room for; never repeat it word for
>            word.",
>   "first_step": "one sentence, one evening, something I could start tonight
>                  without buying anything",
>   "shaky": "one sentence on what is weak about it — what would have to be
>             true for it to work, or why you are not convinced. Empty string
>             only if there is genuinely nothing."
> }
> ```
>
> No text outside the fence. No emoji anywhere.
