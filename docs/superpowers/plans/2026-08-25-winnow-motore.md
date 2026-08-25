# winnow — il motore che parla · piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `winnow recap` diventa un comando solo — prepara, chiede il giudizio al
modello, scrive la pagina — e riparte da dove aveva lasciato invece che dagli
ultimi sette giorni di calendario.

**Architecture:** Il motore smette di stampare e comincia a *consegnare*: ogni
passo emette un evento, e due adattatori sottili lo mostrano (la CLI stampa,
l'API — nel piano successivo — serializza). È il pattern che `run.py` +
`progress.py` + `cli.py` già usano per la raccolta: questo piano lo estende al
recap. Il giro col copia-incolla sparisce: uno solo, che ritenta ciò che è
ritentabile (rete, limiti) e si ferma su ciò che non lo è (chiave revocata).

**Tech Stack:** Python 3.11+, stdlib. `providers.complete()` per parlare al
modello — già esiste e copre Anthropic, OpenAI e locale. **Nessuna dipendenza
nuova.**

**Spec:** `docs/superpowers/specs/2026-08-25-winnow-app-design.md` — questo piano
implementa §7.1 (il motore consegna), §8.1 (la finestra del recap) e §8.3 (le
slide dentro la pagina).

## Global Constraints

- **Python ≥ 3.11**, nessuna dipendenza nuova: `pyproject.toml` dichiara
  `playwright>=1.47`, `anthropic>=0.40`, `httpx>=0.27` e basta. Il server e
  tutto il resto stanno in stdlib.
- **Il raccoglitore non giudica.** Nessuna logica che pesa, ordina o sceglie
  entra in questo piano: il giudizio è il prompt più il profilo.
- **Mai riportare come verificato ciò che non lo è.** `checked=False`,
  `checked=True/exists=False` e `checked=True/exists=True` restano tre esiti
  distinti.
- **I test girano offline**: niente rete, niente Playwright, niente chiavi API.
  Sono 364 alla partenza e devono restare verdi a ogni commit: un
  rosso ferma il task, non si va avanti.
- **Gli accenti sono veri** in tutto ciò che finisce a schermo: `è`, `già`,
  `più`, `perché`. Mai `e'`.
- **Messaggi utente in inglese** nella CLI (come il resto del repo); i commenti
  di codice in inglese; i messaggi di commit in italiano.
- **Nessun `Co-Authored-By`** in nessun commit.
- Test: `pytest` dal venv pipx —
  `"/Users/stek/Library/Application Support/pipx/venvs/winnow/bin/python" -m pytest`

---

## File Structure

| File | Responsabilità |
|---|---|
| `winnow/window.py` | **nuovo.** Quali findings devono ancora essere giudicati. Puro. |
| `winnow/judge.py` | **nuovo.** Manda il pacchetto al modello e riporta la risposta. Ritenta il ritentabile. |
| `winnow/progress.py` | esiste. Estendere il vocabolario di eventi al recap. |
| `winnow/recap.py` | esiste. `run_recap` diventa un giro solo con `on_event`. |
| `winnow/render.py` | esiste. Le slide entrano nella pagina come data URI. |
| `winnow/paths.py` | esiste. Un percorso nuovo per il marcatore dei recap fatti. |
| `winnow/cli.py` | esiste. Adattatore: stampa gli eventi. |

---

## Task 1: Sapere fin dove si è già giudicato

**Files:**
- Create: `winnow/window.py`
- Modify: `winnow/paths.py`
- Test: `tests/test_window.py`

**Interfaces:**
- Consumes: `winnow.paths.state_dir()`, `winnow.paths.findings_dir()`
- Produces:
  - `judged_file() -> Path` (in `paths.py`)
  - `last_judged(path: Path) -> str | None` — la data ISO dell'ultimo giorno giudicato
  - `mark_judged(path: Path, day: str) -> None`
  - `pending_files(findings_dir: Path, after: str | None) -> list[Path]`

**Perché:** `week_files()` prende gli ultimi 7 giorni di calendario e non sa
niente di cosa sia già stato giudicato. Salti dieci giorni e tre giorni di
findings — pagati e raccolti — non li vede mai più nessuno. Vedi spec §8.1.

- [ ] **Step 1: Write the failing test**

```python
"""Quali findings devono ancora essere giudicati."""
from __future__ import annotations

import json

from winnow.window import last_judged, mark_judged, pending_files


def _findings(tmp_path, *days):
    d = tmp_path / "findings"
    d.mkdir(exist_ok=True)
    for day in days:
        (d / f"{day}.json").write_text(json.dumps({"posts": []}),
                                       encoding="utf-8")
    return d


def test_with_no_recap_ever_everything_is_pending(tmp_path):
    """Alla prima volta non c'è un "da dove": si prende tutto quello che c'è."""
    d = _findings(tmp_path, "2026-08-20", "2026-08-23", "2026-08-25")
    got = [p.stem for p in pending_files(d, None)]
    assert got == ["2026-08-20", "2026-08-23", "2026-08-25"]


def test_only_the_days_after_the_last_judgement(tmp_path):
    d = _findings(tmp_path, "2026-08-20", "2026-08-23", "2026-08-25")
    got = [p.stem for p in pending_files(d, "2026-08-23")]
    assert got == ["2026-08-25"]


def test_a_gap_of_ten_days_loses_nothing(tmp_path):
    """Il difetto che questo modulo esiste per chiudere: con una finestra
    mobile di sette giorni, il 2026-08-10 sarebbe uscito e non lo avrebbe più
    visto nessuno — pagato, raccolto, mai giudicato."""
    d = _findings(tmp_path, "2026-08-10", "2026-08-24", "2026-08-25")
    got = [p.stem for p in pending_files(d, "2026-08-09")]
    assert got == ["2026-08-10", "2026-08-24", "2026-08-25"]


def test_nothing_new_is_an_empty_list_and_not_an_error(tmp_path):
    d = _findings(tmp_path, "2026-08-25")
    assert pending_files(d, "2026-08-25") == []


def test_a_missing_findings_dir_is_empty(tmp_path):
    assert pending_files(tmp_path / "nope", None) == []


def test_a_file_that_is_not_a_date_is_ignored(tmp_path):
    """`.gitkeep` e i file di appoggio non sono giorni."""
    d = _findings(tmp_path, "2026-08-25")
    (d / ".gitkeep").write_text("", encoding="utf-8")
    (d / "note.json").write_text("{}", encoding="utf-8")
    assert [p.stem for p in pending_files(d, None)] == ["2026-08-25"]


def test_the_marker_round_trips(tmp_path):
    f = tmp_path / "judged.json"
    assert last_judged(f) is None
    mark_judged(f, "2026-08-25")
    assert last_judged(f) == "2026-08-25"


def test_the_marker_only_moves_forward(tmp_path):
    """Rigiudicare una settimana vecchia non deve far dimenticare quelle
    già fatte dopo."""
    f = tmp_path / "judged.json"
    mark_judged(f, "2026-08-25")
    mark_judged(f, "2026-08-20")
    assert last_judged(f) == "2026-08-25"


def test_a_corrupt_marker_is_a_shrug_and_not_a_crash(tmp_path):
    f = tmp_path / "judged.json"
    f.write_text("{{{", encoding="utf-8")
    assert last_judged(f) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"/Users/stek/Library/Application Support/pipx/venvs/winnow/bin/python" -m pytest tests/test_window.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'winnow.window'`

- [ ] **Step 3: Write minimal implementation**

Crea `winnow/window.py`:

```python
"""Quali findings devono ancora essere giudicati.

`week_files()` prendeva gli ultimi sette giorni di calendario, e da nessuna
parte esisteva uno stato "fin dove ho già giudicato". Due conseguenze, e la
seconda è quella grave: due recap ravvicinati rileggono e ripagano gli stessi
giorni; dieci giorni di pausa e tre giorni di findings escono dalla finestra e
non li vede mai più nessuno — pagati, raccolti, mai giudicati.

winnow esiste perché i post salvati non si riguardano mai: perderne un pezzo in
silenzio è esattamente il difetto che dovrebbe curare.

Il marcatore è un file solo, come `seen.json` per i post, e si muove solo in
avanti: rigiudicare una settimana vecchia non deve far dimenticare quelle già
fatte dopo.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def last_judged(path: Path) -> str | None:
    """L'ultimo giorno giudicato, o None se non è mai stato fatto un recap."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    day = data.get("last_judged")
    return day if isinstance(day, str) and DAY_RE.match(day) else None


def mark_judged(path: Path, day: str) -> None:
    """Sposta il segno in avanti. Mai indietro."""
    if not DAY_RE.match(day):
        return
    if (last_judged(path) or "") >= day:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last_judged": day}, indent=2),
                    encoding="utf-8")


def pending_files(findings_dir: Path, after: str | None) -> list[Path]:
    """I findings da giudicare, dal più vecchio.

    Selezionati per la data nel nome, non per mtime: un file riscritto da una
    corsa successiva dello stesso giorno non deve sembrare un giorno diverso.
    """
    if not findings_dir.is_dir():
        return []
    out = [p for p in findings_dir.glob("*.json") if DAY_RE.match(p.stem)]
    if after:
        out = [p for p in out if p.stem > after]
    return sorted(out)
```

In `winnow/paths.py`, dopo `state_dir()`:

```python
def judged_file() -> Path:
    """Fin dove il giudizio è arrivato. Come seen.json, ma per i recap."""
    return state_dir() / "judged.json"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"/Users/stek/Library/Application Support/pipx/venvs/winnow/bin/python" -m pytest tests/test_window.py -q`
Expected: PASS — tutti verdi

Poi la suite intera: `... -m pytest -q` → **tutto verde, e più test di prima**

- [ ] **Step 5: Commit**

```bash
git add winnow/window.py winnow/paths.py tests/test_window.py
git commit -m "feat: il recap riparte da dove aveva lasciato, non da sette giorni fa

week_files() prendeva gli ultimi sette giorni di calendario e da nessuna parte
esisteva uno stato 'fin dove ho gia' giudicato'. Salti dieci giorni e tre
giorni di findings escono dalla finestra: pagati, raccolti, mai giudicati.
winnow esiste perche' i post salvati non si riguardano mai — perderne un pezzo
in silenzio e' il difetto che dovrebbe curare.

Il marcatore si muove solo in avanti: rigiudicare una settimana vecchia non
deve far dimenticare quelle gia' fatte dopo."
```

---

## Task 2: Chiedere il giudizio al modello

**Files:**
- Create: `winnow/judge.py`
- Test: `tests/test_judge.py`

**Interfaces:**
- Consumes: `winnow.providers.complete(provider, model, base_url, system, text, images, max_tokens, temperature) -> tuple[str, int, int]`
- Produces:
  - `class Fatal(RuntimeError)` — un errore che non passa da solo
  - `is_retryable(exc: Exception) -> bool`
  - `backoff(attempt: int) -> float`
  - `ask(bundle: str, provider: str, model: str, base_url: str | None, on_event=None, sleep=time.sleep, complete=None, attempts: int = 5) -> tuple[str, int, int]`

**Perché:** oggi il giudizio passa da te: incolli il pacchetto, copi la risposta.
È l'unico punto del giro dove si può fallire senza capire perché, ed è misurato
(spec §1). Un giro solo, che aspetta quando ha senso aspettare.

- [ ] **Step 1: Write the failing test**

```python
"""Chiedere il giudizio, e sapere cosa vale la pena riprovare."""
from __future__ import annotations

import httpx
import pytest

from winnow.judge import Fatal, ask, backoff, is_retryable


@pytest.mark.parametrize("exc", [
    httpx.ConnectError("network is unreachable"),
    httpx.ReadTimeout("timed out"),
    httpx.RemoteProtocolError("server disconnected"),
])
def test_the_network_going_away_is_worth_waiting_for(exc):
    """Cade la rete: torna. Aspettare è la risposta giusta."""
    assert is_retryable(exc) is True


def test_a_rate_limit_is_worth_waiting_for():
    assert is_retryable(RuntimeError("429 rate limit exceeded")) is True


def test_the_server_being_broken_is_worth_waiting_for():
    assert is_retryable(RuntimeError("503 service unavailable")) is True


@pytest.mark.parametrize("msg", [
    "401 invalid api key",
    "403 forbidden",
    "credit balance is too low",
])
def test_a_revoked_key_is_never_worth_waiting_for(msg):
    """Riprovare una chiave revocata all'infinito è il vero casino: quella
    non passa da sola, e ogni tentativo è tempo perso a schermo fermo."""
    assert is_retryable(RuntimeError(msg)) is False


def test_the_wait_grows_so_it_does_not_hammer():
    waits = [backoff(n) for n in range(1, 5)]
    assert waits == sorted(waits) and waits[0] >= 1 and waits[-1] <= 120


def test_a_reply_that_arrives_is_returned_with_its_tokens():
    def ok(**kw):
        return "la risposta", 41000, 15000

    text, tin, tout = ask("il pacchetto", "anthropic", "m", None, complete=ok)
    assert text == "la risposta" and (tin, tout) == (41000, 15000)


def test_it_waits_and_tries_again_when_the_network_is_gone():
    calls, slept = [], []

    def flaky(**kw):
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("network is unreachable")
        return "arrivata", 10, 5

    text, _, _ = ask("p", "anthropic", "m", None,
                     complete=flaky, sleep=slept.append)
    assert text == "arrivata"
    assert len(calls) == 3 and len(slept) == 2


def test_it_says_it_is_waiting_instead_of_going_quiet():
    """Uno schermo fermo per quarantacinque secondi non si distingue da un
    programma piantato."""
    seen = []

    def flaky(**kw):
        if len(seen) < 1:
            raise httpx.ConnectError("down")
        return "ok", 1, 1

    ask("p", "anthropic", "m", None, complete=flaky, sleep=lambda s: None,
        on_event=lambda e, d: seen.append((e, d)))
    kinds = [e for e, _ in seen]
    assert "waiting" in kinds
    wait = dict(seen[kinds.index("waiting")][1])
    assert wait["seconds"] >= 1 and "attempt" in wait


def test_a_fatal_error_stops_at_once_without_waiting():
    calls, slept = [], []

    def dead(**kw):
        calls.append(1)
        raise RuntimeError("401 invalid api key")

    with pytest.raises(Fatal, match="invalid api key"):
        ask("p", "anthropic", "m", None, complete=dead, sleep=slept.append)
    assert len(calls) == 1 and slept == []


def test_it_gives_up_after_the_last_attempt_and_says_so():
    def always(**kw):
        raise httpx.ConnectError("still down")

    with pytest.raises(Fatal, match="3"):
        ask("p", "anthropic", "m", None, complete=always,
            sleep=lambda s: None, attempts=3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"/Users/stek/Library/Application Support/pipx/venvs/winnow/bin/python" -m pytest tests/test_judge.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'winnow.judge'`

- [ ] **Step 3: Write minimal implementation**

Crea `winnow/judge.py`:

```python
"""Chiedere il giudizio al modello, e sapere cosa vale la pena riprovare.

Il giro col copia-incolla non esiste più: era l'unico punto in cui si poteva
fallire senza capire perché, e il 2026-08-25 ha mangiato una risposta vera —
copiata dallo scrollback di un terminale, che manda a capo e tronca le righe
lunghe, era già rotta all'arrivo.

Un giro solo, e la distinzione che lo tiene onesto: **la rete che cade e un
limite di frequenza passano da soli, una chiave revocata no.** Riprovare la
seconda all'infinito è il vero casino — schermo fermo e nessuna speranza. Su
quella ci si ferma subito e si dice perché.
"""
from __future__ import annotations

import time
from pathlib import Path

from winnow import providers


class Fatal(RuntimeError):
    """Non passerà da solo: fermarsi è la risposta giusta."""


# Quello che il tempo aggiusta. Confrontato sul testo perché i tre provider
# alzano eccezioni diverse per la stessa identica situazione.
RETRY_MARKS = ("429", "rate limit", "500", "502", "503", "504",
               "timeout", "timed out", "connection", "network",
               "temporarily", "overloaded", "disconnect")

# Quello che il tempo non aggiusta, e che vince sul primo elenco: "401
# connection refused" è una chiave sbagliata, non una rete che torna.
FATAL_MARKS = ("401", "403", "invalid api key", "invalid_api_key",
               "authentication", "permission", "credit balance",
               "quota exceeded", "billing")


def is_retryable(exc: Exception) -> bool:
    msg = f"{type(exc).__name__} {exc}".lower()
    if any(m in msg for m in FATAL_MARKS):
        return False
    return any(m in msg for m in RETRY_MARKS)


def backoff(attempt: int) -> float:
    """5s, 15s, 45s, 120s. Cresce perché martellare un servizio in ginocchio
    lo tiene in ginocchio, e si ferma perché oltre due minuti tanto vale
    riprovare a mano."""
    return min(5.0 * (3 ** (attempt - 1)), 120.0)


def ask(bundle: str, provider: str, model: str, base_url: str | None,
        on_event=None, sleep=time.sleep, complete=None,
        attempts: int = 5) -> tuple[str, int, int]:
    """La risposta del modello e i token che è costata.

    `complete` e `sleep` si iniettano: è quello che rende testabile ogni
    ramo di questa funzione senza rete, senza chiavi e senza aspettare.
    """
    call = complete or (lambda **kw: providers.complete(**kw))

    def say(event: str, **data) -> None:
        if on_event:
            on_event(event, data)

    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        say("asking", attempt=attempt, of=attempts)
        try:
            return call(provider=provider, model=model, base_url=base_url,
                        system="", text=bundle, images=[],
                        max_tokens=16000, temperature=0.0)
        except Exception as exc:              # noqa: BLE001 — poi si smista
            if not is_retryable(exc):
                raise Fatal(str(exc)) from exc
            last = exc
            if attempt == attempts:
                break
            wait = backoff(attempt)
            # Detto, non subito: uno schermo fermo per quarantacinque secondi
            # non si distingue da un programma piantato.
            say("waiting", seconds=wait, attempt=attempt, why=str(exc)[:120])
            sleep(wait)
    raise Fatal(f"{attempts} attempts, still failing: {last}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"/Users/stek/Library/Application Support/pipx/venvs/winnow/bin/python" -m pytest tests/test_judge.py -q`
Expected: PASS — tutti verdi

Poi la suite intera: `... -m pytest -q` → **tutto verde, e più test di prima**

- [ ] **Step 5: Commit**

```bash
git add winnow/judge.py tests/test_judge.py
git commit -m "feat: il giudizio si chiede da soli, e si aspetta solo cio' che torna

Il giro col copia-incolla era l'unico punto in cui si poteva fallire senza
capire perche', e il 2026-08-25 ha mangiato una risposta vera: copiata dallo
scrollback di un terminale, che manda a capo e tronca, era gia' rotta
all'arrivo.

La distinzione che tiene onesto il ritentativo: rete caduta e limiti di
frequenza passano da soli, una chiave revocata no. Riprovare la seconda
all'infinito e' il vero casino — schermo fermo e nessuna speranza. E l'attesa
si dice mentre si aspetta: quarantacinque secondi di silenzio non si
distinguono da un programma piantato."
```

---

## Task 3: Il recap racconta cosa sta facendo

**Files:**
- Modify: `winnow/progress.py`
- Test: `tests/test_progress.py`

**Interfaces:**
- Consumes: `winnow.progress.line(event: str, data: dict) -> str` (esiste)
- Produces: la stessa `line()`, che ora conosce anche gli eventi del recap:
  `bundling`, `asking`, `waiting`, `judged`, `rendered`

**Perché:** spec §7.1. Il motore emette, `progress.py` traduce, `cli.py` stampa.
Quando arriverà l'API, leggerà gli stessi eventi senza toccare niente.

- [ ] **Step 1: Write the failing test**

Aggiungi in fondo a `tests/test_progress.py`:

```python
# --- il recap ------------------------------------------------------------

def test_the_bundle_says_what_went_in():
    out = line("bundling", {"days": 3, "posts": 30, "things": 144})
    assert "3" in out and "30" in out and "144" in out


def test_asking_names_the_attempt_only_when_it_is_not_the_first():
    """«tentativo 1 di 5» sul primo giro è rumore: dice che qualcosa è
    andato storto quando non è successo niente."""
    first = line("asking", {"attempt": 1, "of": 5})
    again = line("asking", {"attempt": 2, "of": 5})
    assert "1" not in first
    assert "2" in again


def test_waiting_says_how_long_and_why():
    out = line("waiting", {"seconds": 15.0, "attempt": 2,
                           "why": "network is unreachable"})
    assert "15" in out and "network" in out


def test_the_judgement_reports_what_it_cost():
    out = line("judged", {"kept": 15, "of": 144, "usd": 0.42})
    assert "15" in out and "144" in out and "0.42" in out


def test_the_page_says_where_it_is():
    out = line("rendered", {"path": "/tmp/recap/2026-08-25.html"})
    assert "2026-08-25.html" in out


def test_an_event_from_a_newer_version_is_ignored_and_not_a_crash():
    """Una corsa che è già costata soldi non deve morire perché un chiamante
    più nuovo ha emesso un evento che questa versione non ha mai visto."""
    assert line("something_new", {"whatever": 1}) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"/Users/stek/Library/Application Support/pipx/venvs/winnow/bin/python" -m pytest tests/test_progress.py -q`
Expected: FAIL — gli assert sui nuovi eventi falliscono (`line()` torna `""`)

- [ ] **Step 3: Write minimal implementation**

In `winnow/progress.py`, dentro `line()`, prima del `return ""` finale:

```python
    # --- il recap --------------------------------------------------------
    if event == "bundling":
        days = data.get("days", 0)
        day_word = "day" if days == 1 else "days"
        return (f"  bundling   {days} {day_word} · {data.get('posts', 0)} "
                f"posts · {data.get('things', 0)} things")
    if event == "asking":
        attempt = data.get("attempt", 1)
        # Il numero del tentativo solo quando non è il primo: dirlo sempre
        # segnala un problema che al primo giro non è successo.
        if attempt <= 1:
            return "  asking     the model is reading it…"
        return f"  asking     attempt {attempt} of {data.get('of', '?')}"
    if event == "waiting":
        secs = data.get("seconds", 0)
        return (f"  waiting    {secs:.0f}s before trying again "
                f"({data.get('why', 'no reason given')})")
    if event == "judged":
        return (f"  judged     {data.get('kept', 0)} of "
                f"{data.get('of', 0)} · USD {data.get('usd', 0):.2f}")
    if event == "rendered":
        return f"  → {data.get('path', '')}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"/Users/stek/Library/Application Support/pipx/venvs/winnow/bin/python" -m pytest tests/test_progress.py -q`
Expected: PASS

Poi la suite intera: `... -m pytest -q` → **tutto verde, e più test di prima**

- [ ] **Step 5: Commit**

```bash
git add winnow/progress.py tests/test_progress.py
git commit -m "feat: anche il recap dice a che punto e'

Stesso pattern della raccolta: run.py emette, progress.py traduce, cli.py
stampa. Quando arrivera' l'API leggera' gli stessi eventi senza toccare
niente — che e' tutto il motivo per cui la traduzione sta in un modulo suo.

Il numero del tentativo si dice solo quando non e' il primo: 'tentativo 1 di
5' segnala un problema che al primo giro non e' successo."
```

---

## Task 4: Le slide entrano nella pagina

**Files:**
- Modify: `winnow/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `winnow.render.shot_for(item, shots, shapes, shared) -> str` (esiste)
- Produces: `embed_shots: bool = False` come parametro di `render()` e
  `render_file()`; quando è `True` le immagini finiscono nella pagina come
  `data:` URI invece che come percorso relativo.

**Perché:** spec §8.3. Le pagine puntano a `../state/shots/…`, una cartella
condivisa che pesa 58 MB in due giorni e che nessuno pulisce. Non pulire =
decine di GB in un anno; pulire = **le pagine vecchie perdono le figure**, cioè
proprio l'archivio.

- [ ] **Step 1: Write the failing test**

Aggiungi in fondo a `tests/test_render.py`:

```python
# --- la pagina deve sopravvivere alla pulizia ---------------------------

def test_the_slides_can_travel_inside_the_page(tmp_path):
    """Le pagine puntano a una cartella condivisa che pesa 58 MB in due
    giorni (misurato 2026-08-25) e che nessuno pulisce. Non pulire sono
    decine di GB in un anno; pulire svuota le pagine vecchie — cioè proprio
    l'archivio. Dentro la pagina, come già il quadro, e il problema sparisce."""
    from winnow.render import render
    shots = tmp_path / "shots"
    shots.mkdir()
    (shots / "ABC_02.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
    page = render({"categories": [{"name": "c", "items": [
        {"title": "t", "post": "ABC", "slide": 2}]}]},
        shots=shots, out_dir=tmp_path, embed_shots=True)
    assert "data:image/png;base64," in page
    assert "shots/ABC_02.png" not in page


def test_by_default_the_page_still_links_its_slides(tmp_path):
    """Il comportamento di oggi non cambia da sotto i piedi a nessuno."""
    from winnow.render import render
    shots = tmp_path / "shots"
    shots.mkdir()
    (shots / "ABC_02.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    page = render({"categories": [{"name": "c", "items": [
        {"title": "t", "post": "ABC", "slide": 2}]}]},
        shots=shots, out_dir=tmp_path)
    assert "shots/ABC_02.png" in page


def test_a_missing_slide_does_not_break_an_embedded_page(tmp_path):
    from winnow.render import render
    page = render({"categories": [{"name": "c", "items": [
        {"title": "t", "post": "NOPE", "slide": 1}]}]},
        shots=tmp_path, out_dir=tmp_path, embed_shots=True)
    assert "<html" in page and "data:image/png" not in page
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"/Users/stek/Library/Application Support/pipx/venvs/winnow/bin/python" -m pytest tests/test_render.py -q -k "travel_inside or still_links or embedded_page"`
Expected: FAIL — `TypeError: render() got an unexpected keyword argument 'embed_shots'`

- [ ] **Step 3: Write minimal implementation**

In `winnow/render.py`, dopo `_rel()`:

```python
def _inline(path: str) -> str:
    """Un'immagine come data URI, o "" se non si può leggere.

    Le pagine del recap vengono spostate, mandate e riaperte a distanza di
    mesi. Un riferimento a una cartella condivisa — che oltretutto va pulita,
    o diventa decine di GB — è un buco che si apre da solo.
    """
    import base64
    try:
        data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:image/png;base64,{data}"
```

Poi cambia le firme e passa il flag lungo la catena:

```python
def kept_html(item: dict, i: int, cat: str, shots: Path | None,
              out_dir: Path | None, shapes: dict[str, str] | None = None,
              shared: set | None = None, siblings: dict | None = None,
              embed_shots: bool = False) -> str:
```

e dentro, al posto della riga `src = _rel(...)`:

```python
    found = shot_for(item, shots, shapes, shared)
    src = (_inline(found) if embed_shots and found
           else _rel(found, out_dir))
```

In `render()`, aggiungi `embed_shots: bool = False` alla firma e passalo a
`kept_html(...)`. In `render_file()`, aggiungi `embed_shots: bool = False` e
passalo a `render(...)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `"/Users/stek/Library/Application Support/pipx/venvs/winnow/bin/python" -m pytest tests/test_render.py -q`
Expected: PASS

Poi la suite intera: `... -m pytest -q` → **tutto verde, e più test di prima**

- [ ] **Step 5: Commit**

```bash
git add winnow/render.py tests/test_render.py
git commit -m "feat: le slide possono viaggiare dentro la pagina

Le pagine puntavano a ../state/shots/, una cartella condivisa che pesa 58 MB
in due giorni e che nessuno pulisce. Due strade opposte e tutte e due
sbagliate: non pulire sono decine di GB in un anno, pulire svuota le pagine
vecchie — cioe' proprio l'archivio che si vuole avere.

Dentro la pagina come data URI, la stessa cosa che si fa gia' col quadro.
Spento di default: il comportamento di oggi non cambia sotto i piedi a
nessuno."
```

---

## Task 5: Un comando solo

**Files:**
- Modify: `winnow/recap.py`
- Modify: `winnow/cli.py`
- Test: `tests/test_recap.py`

**Interfaces:**
- Consumes: `window.pending_files`, `window.last_judged`, `window.mark_judged`,
  `judge.ask`, `judge.Fatal`, `render.render_file`, `progress.line`
- Produces:
  `run_recap(now=None, open_file=True, on_event=None, ask=None) -> int`

**Perché:** è il punto di arrivo di tutto il piano. I tre passi di oggi
diventano uno, e il recap parte da dove aveva lasciato.

- [ ] **Step 1: Write the failing test**

Aggiungi in fondo a `tests/test_recap.py`:

```python
# --- un comando solo -----------------------------------------------------

def _fixture(tmp_path, monkeypatch, days=("2026-08-25",)):
    """Un winnow finto e completo: findings, profilo, cartelle."""
    import json as _json

    import winnow.recap as R
    findings = tmp_path / "findings"
    findings.mkdir()
    for d in days:
        (findings / f"{d}.json").write_text(_json.dumps(
            {"spend_usd": 0.01,
             "posts": [{"shortcode": "A", "shape": "news", "entities": []}]}),
            encoding="utf-8")
    (tmp_path / "profile.md").write_text("# io", encoding="utf-8")
    monkeypatch.setattr(R.paths, "findings_dir", lambda: findings)
    monkeypatch.setattr(R.paths, "recap_dir", lambda: tmp_path / "recap")
    monkeypatch.setattr(R.paths, "profile_file", lambda: tmp_path / "profile.md")
    monkeypatch.setattr(R.paths, "judged_file", lambda: tmp_path / "judged.json")
    monkeypatch.setattr(R.paths, "shots_dir", lambda: tmp_path / "shots")
    monkeypatch.setattr(R.paths, "state_dir", lambda: tmp_path)
    return findings


ANSWER = '```json\n{"week": "2026-08-25", "counts": {"kept": 1}, ' \
         '"categories": [], "discarded": []}\n```'


def test_one_command_bundles_asks_and_renders(tmp_path, monkeypatch):
    """I tre passi di prima — prepara, incolla, riprendi — diventano uno."""
    from winnow.recap import run_recap
    _fixture(tmp_path, monkeypatch)
    assert run_recap(open_file=False,
                     ask=lambda *a, **k: (ANSWER, 100, 50)) == 0
    pages = list((tmp_path / "recap").glob("*.html"))
    assert len(pages) == 1


def test_the_marker_moves_only_after_the_page_exists(tmp_path, monkeypatch):
    """Segnare come giudicato un giorno il cui recap è fallito lo perde per
    sempre: la prossima corsa non lo guarda più."""
    from winnow.judge import Fatal
    from winnow.recap import run_recap
    from winnow.window import last_judged
    _fixture(tmp_path, monkeypatch)

    def dead(*a, **k):
        raise Fatal("401 invalid api key")

    assert run_recap(open_file=False, ask=dead) == 1
    assert last_judged(tmp_path / "judged.json") is None


def test_a_second_run_with_nothing_new_says_so_and_costs_nothing(
        tmp_path, monkeypatch):
    from winnow.recap import run_recap
    _fixture(tmp_path, monkeypatch)
    run_recap(open_file=False, ask=lambda *a, **k: (ANSWER, 100, 50))

    calls = []

    def counted(*a, **k):
        calls.append(1)
        return ANSWER, 100, 50

    assert run_recap(open_file=False, ask=counted) == 0
    assert calls == []


def test_the_answer_is_written_down_before_it_is_parsed(tmp_path, monkeypatch):
    """Un giudizio costa soldi veri. Se il JSON è rotto si aggiusta a mano —
    ma solo se esiste ancora."""
    from winnow.recap import run_recap
    _fixture(tmp_path, monkeypatch)
    assert run_recap(open_file=False,
                     ask=lambda *a, **k: ("non è json", 100, 50)) == 1
    saved = list((tmp_path / "recap").glob("*.answer*.md"))
    assert saved and "non è json" in saved[0].read_text(encoding="utf-8")


def test_it_reports_as_it_goes(tmp_path, monkeypatch):
    from winnow.recap import run_recap
    _fixture(tmp_path, monkeypatch)
    seen = []
    run_recap(open_file=False, ask=lambda *a, **k: (ANSWER, 100, 50),
              on_event=lambda e, d: seen.append(e))
    assert "bundling" in seen and "judged" in seen and "rendered" in seen
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"/Users/stek/Library/Application Support/pipx/venvs/winnow/bin/python" -m pytest tests/test_recap.py -q -k "one_command or marker_moves or nothing_new or written_down_before or reports_as_it_goes"`
Expected: FAIL — `TypeError: run_recap() got an unexpected keyword argument 'ask'`

- [ ] **Step 3: Write minimal implementation**

In `winnow/recap.py` sostituisci `run_recap` con:

```python
def run_recap(now: datetime | None = None, open_file: bool = True,
              on_event=None, ask=None) -> int:
    """Prepara, chiedi, scrivi la pagina. Un giro solo.

    Prima erano tre — `winnow recap`, incolla nel modello, `winnow render` —
    e il passaggio in mezzo era l'unico punto in cui si poteva fallire senza
    capire perché. Il 2026-08-25 ha mangiato una risposta vera.
    """
    from winnow import judge, window
    from winnow.render import render_file

    now = now or datetime.now()

    def say(event: str, **data) -> None:
        if on_event:
            on_event(event, data)

    profile_path = paths.profile_file()
    if not profile_path.exists():
        print(f"  ❌ no profile: {profile_path}")
        print("     run 'winnow init', it creates one to fill in.")
        return 1

    judged = paths.judged_file()
    files = window.pending_files(paths.findings_dir(),
                                 window.last_judged(judged))
    if not files:
        print("  Nothing new since the last recap.")
        return 0

    days = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    profile = profile_path.read_text(encoding="utf-8")
    profile, missing = resolve_includes(profile, profile_path.parent)
    for m in missing:
        print(f"  ⚠️  the profile points at {m}, which cannot be read.")

    facts = digest.gather(days, now.date().isoformat())
    # build_bundle vuole i PERCORSI, non i giorni già letti.
    bundle = build_bundle(prompt_body(package_file("recap-prompt.md")),
                          profile, files, package_file("mentality.md"),
                          now.date().isoformat())
    say("bundling", days=len(files), posts=facts["posts"],
        things=len(facts["things"]))

    cfg = config.load(paths.config_file())
    try:
        text, tin, tout = (ask or judge.ask)(
            bundle, cfg.api.provider, cfg.api.model, cfg.api.base_url,
            on_event=on_event)
    except judge.Fatal as e:
        print(f"  ❌ {e}")
        return 1

    # Scritta prima di essere letta: un giudizio costa soldi veri, e una
    # risposta rotta su disco si aggiusta a mano — una persa no.
    recap_dir = paths.recap_dir()
    recap_dir.mkdir(parents=True, exist_ok=True)
    stem = now.date().isoformat()
    src = recap_dir / f"{stem}.answer.md"
    n = 2
    while src.exists():
        src = recap_dir / f"{stem}.answer-{n}.md"
        n += 1
    src.write_text(text, encoding="utf-8")

    usd = providers.cost(cfg.api.provider, cfg.api.model, tin, tout)
    try:
        out = render_file(src, embed_shots=True)
    except json.JSONDecodeError as e:
        print(f"  ❌ the answer is not valid JSON: {e.msg}")
        print(f"     saved anyway: {src}")
        return 1

    data = extract_json(text)
    say("judged", kept=(data.get("counts") or {}).get("kept", 0),
        of=len(facts["things"]), usd=usd)
    say("rendered", path=str(out))

    # Il segno si muove solo adesso: marcare come giudicato un giorno il cui
    # recap è fallito lo perde per sempre.
    window.mark_judged(judged, files[-1].stem)

    print(f"  → {out}")
    if open_file and sys.stdout.isatty():
        import webbrowser
        webbrowser.open(f"file://{out.resolve()}")
    return 0
```

Aggiungi in cima a `recap.py`: `from winnow import config, providers` e
`from winnow.render import extract_json`.

In `winnow/cli.py`, `_cmd_recap` diventa:

```python
def _cmd_recap(args) -> int:
    from winnow.progress import line
    from winnow.recap import run_recap

    def show(event: str, data: dict) -> None:
        text = line(event, data)
        if text:
            print(text, flush=True)

    return run_recap(open_file=not args.no_open, on_event=show)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"/Users/stek/Library/Application Support/pipx/venvs/winnow/bin/python" -m pytest tests/test_recap.py -q`
Expected: PASS

Poi la suite intera: `... -m pytest -q` → **tutto verde, e più test di prima**

- [ ] **Step 5: Commit**

```bash
git add winnow/recap.py winnow/cli.py tests/test_recap.py
git commit -m "feat: winnow recap fa tutto da solo

Prepara, chiede il giudizio al modello, scrive la pagina. I tre passi di
prima — recap, incolla, render — diventano uno, e il passaggio in mezzo era
l'unico punto in cui si poteva fallire senza capire perche'.

Il segno di 'fin dove ho giudicato' si sposta solo dopo che la pagina esiste:
marcare come fatto un giorno il cui recap e' fallito lo perde per sempre.

La risposta si scrive su disco prima di essere letta. Un giudizio costa soldi
veri: rotto su disco si aggiusta a mano, perso no."
```

---

## Task 6: Il README racconta il giro nuovo

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Test: `tests/test_recap.py`

**Interfaces:**
- Consumes: niente
- Produces: niente codice

**Perché:** il README descrive i tre passi col copia-incolla, che non esistono
più. Un README che racconta un giro che non c'è è peggio di nessun README.

- [ ] **Step 1: Write the failing test**

Aggiungi in fondo a `tests/test_recap.py`:

```python
def test_the_readme_does_not_describe_a_flow_that_is_gone():
    """Il copia-incolla non esiste più: un README che lo racconta manda
    l'utente a cercare un passaggio che non c'è."""
    import pathlib
    text = pathlib.Path("README.md").read_text(encoding="utf-8")
    body = text.lower()
    assert "copy the model's whole answer" not in body
    assert "winnow recap" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"/Users/stek/Library/Application Support/pipx/venvs/winnow/bin/python" -m pytest tests/test_recap.py -q -k readme`
Expected: FAIL — la frase c'è ancora

- [ ] **Step 3: Write minimal implementation**

In `README.md`, sostituisci la sezione *"Every week — two commands, with a
paste in between"* con:

````markdown
### Every week — one command

```bash
winnow recap
```

It bundles the days you have not judged yet, sends them to your model, and
opens the page. Nothing to copy, nothing to paste.

If the network drops it waits and tries again — 5s, 15s, 45s — and says so
while it waits. If the key is dead it stops at once, because that one does not
fix itself.

The page shows what got through — each with the slide you would have seen on
Instagram — and, under it, **every single thing that did not**, grouped by the
verdict that stopped it, with the count beside each. That last part is the one
to argue with: if *31 out of scope* looks wrong, you can see which 31.

`winnow render answer.md` still turns a saved answer into a page, for when you
want to fix one by hand.
````

Nella tabella dei comandi, cambia la riga di `winnow recap` in:

```markdown
| `winnow recap` | the week judged and opened as a page — one command |
```

In `CLAUDE.md`, nella mappa dei moduli, aggiungi dopo la riga di `recap.py`:

```markdown
| `window.py` | quali findings devono ancora essere giudicati. Il recap riparte da lì, non da sette giorni fa |
| `judge.py` | manda il pacchetto al modello. Aspetta ciò che torna, si ferma su ciò che non torna |
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"/Users/stek/Library/Application Support/pipx/venvs/winnow/bin/python" -m pytest tests/ -q`
Expected: PASS — tutto verde

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md tests/test_recap.py
git commit -m "docs: il giro e' un comando solo

Il README raccontava i tre passi col copia-incolla, che non esistono piu'.
Un README che descrive un giro che non c'e' manda l'utente a cercare un
passaggio inesistente — peggio che non averlo."
```

---

## Cosa resta fuori da questo piano

- **L'app** (finestra, casa, primo avvio, impostazioni): piano successivo. Ha
  bisogno di questo motore sotto.
- **L'archivio** (sfogliare le settimane): piano successivo. Ha bisogno
  dell'app.
- **La pulizia degli screenshot vecchi**: diventa possibile dopo il Task 4
  (le pagine non dipendono più dalla cartella), ma non serve ancora — 58 MB non
  sono un problema oggi.
- **Correggere un giudizio** perché torni nel profilo: spec §11, deliberatamente
  fuori.
