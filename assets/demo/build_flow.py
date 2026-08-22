"""The winnow loop as one line: once, then daily on its own, then weekly."""
from pathlib import Path

OUT = Path("/Users/stek/Stek_stuff/Progetti_personali/PRACTICE_and_projects/other/winnow/assets/diagrams")
FONTS = ("https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1"
         "&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&display=swap")

LIGHT = dict(paper="#f5f5f5", ink="#2d3142", muted="#4f5d75", soft="#7a8399",
             accent="#eb6c36", step="#ffffff", store="rgba(45,49,66,0.06)",
             tint="rgba(235,108,54,0.08)", rule="rgba(45,49,66,0.12)",
             tag="rgba(79,93,117,0.40)", atag="rgba(235,108,54,0.50)")
DARK = dict(paper="#2d3142", ink="#f5f5f5", muted="#bfc0c0", soft="#8e98ac",
            accent="#f08a59", step="rgba(245,245,245,0.05)",
            store="rgba(0,0,0,0.22)", tint="rgba(240,138,89,0.12)",
            rule="rgba(245,245,245,0.14)", tag="rgba(191,192,192,0.40)",
            atag="rgba(240,138,89,0.50)")

W, H = 1120, 400
NODE_W, NODE_H, GAP = 128, 88, 40
X0, NY = 76, 168
STEP = NODE_W + GAP

NODES = [
    # x-index, tag, name, sub, kind
    (0, "CMD", "winnow init", "una volta, 5 min", "step"),
    (1, "AUTO", "winnow collect", "13:00, launchd", "auto"),
    (2, "FILE", "findings/", "un file al giorno", "store"),
    (3, "CMD", "winnow recap", "tutto negli appunti", "step"),
    (4, "TU", "un modello", "incolli e mandi", "focal"),
    (5, "CMD", "winnow render", "si apre da sola", "focal"),
]

BANDS = [(0, 0, "UNA VOLTA"),
         (1, 2, "OGNI GIORNO · WINNOW, DA SOLO"),
         (3, 5, "OGNI SETTIMANA · TU, DUE COMANDI")]


def nx(i: int) -> int:
    return X0 + i * STEP


def svg(c: dict, slug: str) -> str:
    p = []
    # bands: a hairline per phase with the label above it
    for a, b, label in BANDS:
        x1, x2 = nx(a), nx(b) + NODE_W
        mid = (x1 + x2) // 2
        p.append(f'<text x="{mid}" y="{112}" fill="{c["soft"]}" font-size="8" '
                 f'font-family="\'Geist Mono\', monospace" text-anchor="middle" '
                 f'letter-spacing="0.14em">{label}</text>')
        p.append(f'<line x1="{x1}" y1="{128}" x2="{x2}" y2="{128}" '
                 f'stroke="{c["rule"]}" stroke-width="1"/>')

    # arrows first, so boxes paint over them
    for i in range(len(NODES) - 1):
        accent = i >= 3
        col = c["accent"] if accent else c["muted"]
        mk = "arrA" if accent else "arrM"
        p.append(f'<line x1="{nx(i) + NODE_W}" y1="{NY + NODE_H // 2}" '
                 f'x2="{nx(i + 1) - 4}" y2="{NY + NODE_H // 2}" stroke="{col}" '
                 f'stroke-width="1.2" marker-end="url(#{mk})"/>')

    for i, tag, name, sub, kind in NODES:
        x = nx(i)
        fill = {"step": c["step"], "store": c["store"], "focal": c["tint"],
                "auto": c["step"]}[kind]
        stroke = {"step": c["ink"], "store": c["muted"], "focal": c["accent"],
                  "auto": c["muted"]}[kind]
        # dashed = nobody types this one; launchd does
        dash = ' stroke-dasharray="5,4"' if kind == "auto" else ""
        tstroke = c["atag"] if kind == "focal" else c["tag"]
        tfill = c["accent"] if kind == "focal" else c["soft"]
        tw = 8 + len(tag) * 6
        p.append(f'<rect x="{x}" y="{NY}" width="{NODE_W}" height="{NODE_H}" rx="6" '
                 f'fill="{c["paper"]}"/>')
        p.append(f'<rect x="{x}" y="{NY}" width="{NODE_W}" height="{NODE_H}" rx="6" '
                 f'fill="{fill}" stroke="{stroke}" stroke-width="1"{dash}/>')
        p.append(f'<rect x="{x + 8}" y="{NY + 8}" width="{tw}" height="12" rx="2" '
                 f'fill="transparent" stroke="{tstroke}" stroke-width="0.8"/>')
        p.append(f'<text x="{x + 8 + tw // 2}" y="{NY + 17}" fill="{tfill}" '
                 f'font-size="7" font-family="\'Geist Mono\', monospace" '
                 f'text-anchor="middle" letter-spacing="0.08em">{tag}</text>')
        family = ("'Geist Mono', monospace" if name.startswith("winnow")
                  else "'Geist', sans-serif")
        p.append(f'<text x="{x + NODE_W // 2}" y="{NY + 52}" fill="{c["ink"]}" '
                 f'font-size="12" font-weight="600" font-family="{family}" '
                 f'text-anchor="middle">{name}</text>')
        p.append(f'<text x="{x + NODE_W // 2}" y="{NY + 72}" fill="{c["muted"]}" '
                 f'font-size="9" font-family="\'Geist Mono\', monospace" '
                 f'text-anchor="middle">{sub}</text>')

    # legend
    p.append(f'<line x1="40" y1="{308}" x2="{W - 40}" y2="{308}" '
             f'stroke="{c["rule"]}" stroke-width="0.8"/>')
    p.append(f'<text x="40" y="{328}" fill="{c["muted"]}" font-size="8" '
             f'font-family="\'Geist Mono\', monospace" letter-spacing="0.18em">'
             f'LEGENDA</text>')
    items = [(40, c["step"], c["ink"], "", "un comando che dai tu"),
             (232, c["step"], c["muted"], ' stroke-dasharray="3,2"',
              "gira da solo, non lo scrivi"),
             (500, c["store"], c["muted"], "", "quello che resta su disco"),
             (720, c["tint"], c["accent"], "", "dove il lavoro diventa tuo")]
    for x, fill, stroke, ldash, label in items:
        p.append(f'<rect x="{x}" y="{344}" width="14" height="10" rx="2" '
                 f'fill="{fill}" stroke="{stroke}" stroke-width="1"{ldash}/>')
        p.append(f'<text x="{x + 20}" y="{352}" fill="{c["muted"]}" font-size="8.5" '
                 f'font-family="\'Geist\', sans-serif">{label}</text>')

    body = "\n      ".join(p)
    return f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{slug}-title {slug}-desc">
      <title id="{slug}-title">Come si usa winnow</title>
      <desc id="{slug}-desc">Once: winnow init. Every day, on its own: winnow collect writes one findings file. Every week, two commands from you: winnow recap puts the week on your clipboard, you paste it into a model, and winnow render turns the answer into a page that opens itself.</desc>
      <defs>
        <marker id="arrM" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{c["muted"]}"/></marker>
        <marker id="arrA" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{c["accent"]}"/></marker>
      </defs>
      <rect width="100%" height="100%" fill="{c["paper"]}"/>
      <text x="40" y="48" fill="{c["soft"]}" font-size="8" font-family="'Geist Mono', monospace" letter-spacing="0.14em">WINNOW · IL GIRO</text>
      <text x="40" y="80" fill="{c["ink"]}" font-size="24" font-family="'Instrument Serif', serif">Una volta, poi da solo</text>
      {body}
    </svg>'''


def page(c: dict, slug: str) -> str:
    return f'''<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Come si usa winnow</title>
<link href="{FONTS}" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Geist',system-ui,sans-serif;background:{c["paper"]};
color:{c["ink"]};min-height:100vh;display:flex;align-items:center;
justify-content:center;padding:3rem 2rem}}
svg{{width:100%;max-width:1120px;display:block}}
</style></head><body>{svg(c, slug)}</body></html>'''


for variant, colours in (("", LIGHT), ("-dark", DARK)):
    slug = f"winnow-flow{variant}"
    (OUT / f"{slug}.html").write_text(page(colours, slug), encoding="utf-8")
    print("→", OUT / f"{slug}.html")
