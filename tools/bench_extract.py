"""Bench for the extraction prompt: real posts, expected outcome written by hand.

Not a unit test: it calls the API and costs about $0.03 a run. It exists because
a prompt change cannot be judged by reading it — on 2026-08-20 three wordings
each fixed one case and broke another, and only running them side by side
showed it.

Usage:  python bench.py [variant]
Variants live in PROMPTS. Expectations are about SHAPE, not exact wording:
how many ideas should come out, and which named artifacts must survive.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path.cwd()))
import anthropic

from winnow import extract as E
from winnow import paths
from winnow.budget import cost_usd
from winnow.setup import apply_env_file

apply_env_file(paths.env_file())
MODEL_ID = "claude-haiku-4-5-20251001"
PRICE_KEY = "claude-haiku-4-5"
SHOTS = paths.state_dir() / "shots"
F = json.loads((paths.findings_dir() / "2026-08-20.json").read_text())

# shortcode -> (why it is here, min ideas, max ideas, names that must survive)
# shortcode -> (why, expected shape, min entities, max entities, must survive)
CASES = {
    "DcN9kKpqfDR": ("video che il modello rifiuta (schema predatorio)", "news", 0, 2, []),
    "Db8izV9NWIG": ("reel di lifestyle", "other", 0, 2, ["coody.tents"]),
    "DcG2SSPjTJe": ("elenco di IDEE di software da costruire", "list", 6, 14, []),
    "DbYOhcTDWGZ": ("metodo: Claude che scrive Pine Script", "other", 1, 6,
                    ["Claude", "TradingView"]),
    "Db8FU2cAJ6F": ("elenco di 7 siti che pagano", "list", 5, 10,
                    ["Wellfound", "Contra", "Turing"]),
    "DcEpQxWDgi1": ("elenco di 7 repo veri", "list", 5, 10, ["cline/cline"]),
    "DcJ8R4BEx6e": ("notizia: la Cina abbassa il costo dell'AI di frontiera",
                    "news", 1, 8, []),
}

BASE_KINDS = '''  kind:  "repo" for a code repository (prefer the "owner/name" form when shown),
         "model" for an AI model, "platform" for a product or service,
         "idea" for a method or finding the post describes without naming a product,
         "claim" for a factual assertion with no named artifact.'''

PROMPTS = {
    # what ships today, for reference
    "current": E.SYSTEM_PROMPT,

    # ideas as a fifth kind in the existing list
    "listed": f"""You read slides from a social media carousel and extract, \
verbatim, the concrete things they name.

Return ONLY a JSON array. Each element:
{BASE_KINDS}
  name:  the exact name as written. Never invent, never expand an acronym.
         EXCEPTION: for "idea", write your own short title, max 8 words.
  blurb: one sentence, from the slide or the caption. For an "idea", state the
         method concretely enough to act on it months later.
  slide: the 1-based index of the slide it came from, or 0 for the caption.

Rules:
- Extract from the slides AND from the caption.
- An "idea" carries a method or a specific fact: what to do, to whom, using what.
  Hyped wording does not disqualify it. An invitation to comment, follow or DM
  is never an idea.
- Do not judge quality, usefulness, or credibility. That is not your job.
- If the post names nothing concrete and describes no method, return [].
""",

    "framing": f"""You read a social media post — its caption and the slides of \
its carousel — and extract what it puts on the table.

Return ONLY a JSON array. Each element:
{BASE_KINDS}
  name:  the verbatim name, or your own short title for an "idea" (max 8 words).
  blurb: one sentence. For an "idea", the method or the thing to build,
         concretely enough to act on it months later.
  slide: the 1-based slide index, or 0 when it came from the caption.

How to tell an "idea" from a "platform" — this is the distinction that matters:
- A "platform" EXISTS. You could sign up for it today. It has a maker.
- An "idea" is something the post suggests you DO or BUILD. A list titled
  "software ideas that make money", where each entry is a thing to build, is a
  list of IDEAS, even when the entries sound like product names
  ("Invoice Generator", "Booking System"). A workflow the post describes —
  "use X to do Y, then Z" — is an IDEA, and X stays a separate platform entry.

Extract from the slides AND the caption; on a talking-head video the caption is
all there is. An invitation to comment, follow or DM is never an idea. Do not
judge quality or credibility — somebody else does that. Return [] only when
there is nothing.
""",

    # ideas asked for in their own paragraph, given equal billing
    "two-jobs": f"""You read a social media post — its caption and the slides of \
its carousel — and you have two jobs.

JOB 1. Extract every named artifact: code repositories, AI models, products,
services. Names verbatim, never invented, never expanded.

JOB 2. Extract every actionable idea: a method, a business idea, a technique or a
finding the post describes WITHOUT naming a product. This job matters as much as
the first one. On a talking-head video there are no slides worth reading and the
whole substance is in the caption — that is exactly where these live. Give each
idea a short title of your own, max 8 words.

Return ONLY a JSON array, both jobs mixed together. Each element:
{BASE_KINDS}
  name:  the verbatim name, or your own title for an "idea".
  blurb: one sentence. For an "idea", the method, concretely enough to act on it
         months later.
  slide: the 1-based slide index, or 0 when it came from the caption.

An invitation to comment, follow or DM is never an idea. Do not judge quality,
usefulness or credibility — somebody else does that. Hyped wording does not
disqualify a real method. Return [] only when there is neither a named artifact
nor a usable idea.
""",
}


def run_case(client, system, code):
    post = next(p for p in F["posts"] if p["shortcode"] == code)
    shots = sorted(SHOTS.glob(f"{code}_*.png"))
    # the fix from earlier: if the only images were junk, this is a video and the
    # caption is all there is. Here we simulate that by trusting slide count.
    # the refusal case is a reel: no readable slide, caption is everything
    caption_only = code == "DcN9kKpqfDR"
    tpl = E.VIDEO_TEMPLATE if caption_only else E.USER_TEMPLATE
    imgs = [] if caption_only else shots
    content = [{"type": "text", "text": tpl.format(
        account=post["account"], caption=post["caption"], n=len(imgs))}]
    content += [E._image_block(p) for p in imgs]
    r = client.messages.create(model=MODEL_ID, max_tokens=3000, system=system,
                               temperature=0.0,
                               messages=[{"role": "user", "content": content}])
    text = next(b.text for b in r.content if b.type == "text")
    usd = cost_usd(PRICE_KEY, r.usage.input_tokens, r.usage.output_tokens)
    try:
        shape, ents = E.parse_extraction(text)
        return shape, ents, usd, ""
    except Exception as exc:
        return "other", [], usd, f"{type(exc).__name__}: {exc}"


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "shipped"
    system = PROMPTS.get(which, E.SYSTEM_PROMPT)
    client = anthropic.Anthropic()
    spend = 0.0
    passed = 0
    print(f"=== variante: {which} ===\n")
    for code, (why, want_shape, lo, hi, must) in CASES.items():
        shape, ents, usd, err = run_case(client, system, code)
        spend += usd
        names = {e.name.lower() for e in ents}
        missing = [m for m in must if m.lower() not in names]
        shape_ok = shape == want_shape
        ok = (lo <= len(ents) <= hi) and not missing and not err
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {code}  {why}")
        print(f"      forma: {shape} ({'ok' if shape_ok else 'attesa ' + want_shape})"
              f"  voci: {len(ents)} (attese {lo}-{hi})"
              + (f"  mancanti: {missing}" if missing else "")
              + (f"  ERRORE: {err}" if err else ""))
        for e in ents[:8]:
            src = "caption" if e.slide == 0 else f"sl{e.slide}"
            print(f"        [{e.kind:8}] {e.name[:42]:42} {src}")
    print(f"\n{passed}/{len(CASES)} passati · USD {spend:.4f}")


if __name__ == "__main__":
    main()
