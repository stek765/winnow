# The judge — how to produce the weekly recap

The judge is not code. It is a prompt, run in a session that has your profile
in context. Swap the model and nothing in the collector changes.

Run this on Sunday:

> Leggi i file in `findings/` dell'ultima settimana e il mio profilo in
> `profiles/<mio>.md`.
>
> Applica il criterio a due corsie:
> - 🎯 **Aggancio** — tocca qualcosa che ho già aperto. Soglia bassa: basta che
>   sia vero e vivo.
> - 🌍 **Apertura** — non tocca niente di mio ma è forte in sé (un modo di
>   guadagnare, un tool che cambia il flusso di lavoro, un segnale di dove va
>   il mercato). Soglia alta: deve valerne la pena da solo.
>
> Scarta tutto il resto, e in particolare qualunque cosa il cui unico
> beneficiario sia chi la vende.
>
> Scrivi il recap così:
> 1. **Intestazione** — quanti post, quanti tenuti, quanto è costato.
> 2. **💬 Commento** — UNO solo, non uno per riga. Cosa noti guardando il
>    mucchio (mode, ripetizioni fra account, pattern) e cosa dovrei farci.
> 3. **Righe tenute** — per ognuna: cosa è → è vivo? (usa i dati verificati,
>    non la caption) → cosa tocca di mio.
> 4. **Scarti** — una riga ciascuno, col motivo. Servono a farmi vedere cosa
>    hai buttato, così posso correggerti.

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
- `news` — what a post announced. It goes in the 🌍 Apertura lane by nature:
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
