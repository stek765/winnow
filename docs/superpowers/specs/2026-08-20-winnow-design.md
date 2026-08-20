# winnow — design

**Data:** 2026-08-20
**Stato:** design approvato, non ancora implementato

---

## 1. Il problema

L'autore salva ~30 post Instagram a settimana in cartelle tematiche. Il salvataggio
funziona; **il ritorno no**. I post restano lì e non vengono più riguardati.

Due aggravanti misurate, non supposte:

1. **8 su 10 sono clickbait.** Titoli tipo *"diventa ricco con Claude"* che non
   contengono niente di verificabile.
2. **L'informazione utile non sta nel testo.** Verificato il 2026-08-20 su un post
   reale (`/p/DcEYSBomGEy/`, account `getintoai`): la caption prometteva "9 repository"
   e non ne nominava **nessuna**. I nomi stavano dentro le 11 slide del carosello.
   Sotto, 192 commenti di persone che chiedevano i link. È il modello di business
   del post, non un caso.

## 2. Cosa NON è

**Non è un riassuntore.** Se restituisce 30 schede ordinate ha solo spostato il
problema: la cartella ricreata in markdown.

È un **buttafuori**: il suo lavoro è scartare ~24 post su 30 e giustificare i 6 che
tiene.

## 3. Il principio che regge tutto

> Il post non è la fonte. È solo un puntatore.

Quando un post dice `Open Notebook`, quel nome è **verificabile**. GitHub dice le
stelle vere, l'ultimo commit, se è archiviato. Costa poco (è testo) ed è **la
verità**, non il marketing dell'account.

Conseguenza operativa:

```
estrai l'entità → verificala alla fonte → giudicala contro obiettivi e vita dell'autore
```

Un post clickbait che contiene una repo viva da 37k stelle **passa**.
Un post curato che elenca repo morte da due anni **viene scartato**.
La caption non lo direbbe mai; la verifica sì.

## 4. Architettura — due motori

Il lavoro si spezza in due pezzi con bisogni opposti.

| | **Raccoglitore** | **Giudice** |
|---|---|---|
| Compito | naviga, legge le slide, estrae entità, verifica alle fonti | incrocia con obiettivi e scrive il recap |
| Come | Python + Playwright + Claude Haiku 4.5 via API | sessione Claude Code (o Hermes locale, in futuro) |
| Quando | ogni notte, cron | la domenica |
| Costo | ~$2/mese di API | zero extra |
| Output | `findings/YYYY-MM-DD.json` | il recap |

**Perché separati.** Il giudizio richiede di sapere cosa l'autore ha già deciso e
scartato — informazione che sta nel suo `profiles/<tuo>.md` e che è già nel contesto di una
sessione Claude Code. Raccontarla da capo a un modello via API costa di più e giudica
peggio.

**Portabilità** (vincolo dichiarato in `profiles/<tuo>.md`): CLI verificabili e file su disco,
nessuna integrazione proprietaria. Il giudice è sostituibile con un modello locale
senza toccare una riga del raccoglitore.

## 5. Il raccoglitore — flusso

```
1. apre le cartelle bersaglio                  → lista di shortcode
2. scarta quelli già visti (state/seen.json)   → solo il delta
3. per ogni nuovo: caption + tutte le slide    → Haiku 4.5, vision
4. estrae le entità (repo / modello / piattaforma / claim)
5. verifica ogni entità alla fonte
6. scrive findings/YYYY-MM-DD.json
```

**Il passo 2 è ciò che rende sostenibile il tutto.** Primo giro: macina l'arretrato.
Poi lavora su 4-5 post a notte, non 30.

### Cartelle bersaglio

| Cartella | URL | Priorità | Contenuto atteso |
|---|---|---|---|
| `github` | `/utente/saved/github/000000000000001/` | alta | nomi di repository |
| `MUST REWATCH` | `/utente/saved/must-rewatch/000000000000002/` | alta | notizie che possono cambiare decisioni |
| `AI` | `/utente/saved/ai/000000000000003/` | — | **disattivata** nella v1 |
| `elettronica` | `/utente/saved/elettronica/000000000000004/` | — | **disattivata** nella v1 |

`AI` ed `elettronica` restano configurate ma spente: parole dell'autore, *"il resto non
serve davvero"*. Si accendono cambiando una riga di config, non toccando il codice.

`girlz` e `Tutti i post` sono fuori perimetro.

### Meccanica di navigazione (verificata 2026-08-20)

- Le cartelle hanno **URL stabili** → navigazione diretta, nessun click a tentoni.
- Le slide si raggiungono per URL: `/p/<shortcode>/?img_index=N`. **Nessuna
  automazione a coordinate.**
- ⚠️ Instagram carica solo le slide adiacenti: dopo un salto per URL serve
  **~5 secondi** di attesa prima di leggere, o l'immagine è vuota.
- L'albero di accessibilità (non gli screenshot) dà cartelle e shortcode a costo
  quasi zero. Gli screenshot servono **solo** per leggere le slide.

### Verifica per tipo di entità

| Entità | Fonte | Cosa si chiede |
|---|---|---|
| repository GitHub | API GitHub | stelle, ultimo commit, archiviato, licenza, descrizione reale |
| modello LLM | HuggingFace, **ordinato per download** | esiste? è il modello canonico o un fine-tune di terzi? + **`llmfit`**: ci gira sul suo hardware? |
| piattaforma / servizio | web | cos'è davvero, chi è il cliente, è già stata valutata e scartata? |
| idea di guadagno | web | **qualcuno lo fa davvero? cosa serve? chi ci guadagna, lui o chi vende il corso?** |

L'ultima riga è la più importante: *"modi per arricchirsi"* è il territorio dove la
spazzatura è più densa. Un'idea che non regge quelle tre domande **viene scartata
anche se suona bene**.

## 6. Il giudice — criterio

**Non** "riguarda le materie che studia?" ma **"serve alla vita che sta
costruendo?"** Il mestiere dell'utente è un mezzo verso l'obiettivo che ha scritto
nel profilo, non il perimetro del filtro.

Pesi indicativi: utilità della notizia in sé 9/10 · incrocio con gli interessi
dell'utente 8/10 · **utilità legata ai suoi interessi 10/10** · notizie in generale
8.5/10. La combinazione conta più di ciascun fattore preso da solo.

### Due corsie

| Corsia | Cosa passa | Soglia |
|---|---|---|
| 🎯 **Aggancio** | tocca una delle questioni che l'utente ha dichiarato aperte nel proprio profilo (lavoro, progetti in corso, studio, denaro, casa) | bassa — basta che sia vero e vivo |
| 🌍 **Apertura** | non tocca niente di suo, ma è forte in sé: modo di guadagnare, tool che cambia il flow, segnale di dove va il mercato | **alta** — deve valerne la pena da solo |

⚠️ **La corsia Apertura non è opzionale.** Un agente che tiene solo ciò che tocca un
progetto aperto uccide esattamente ciò che l'autore vuole: il tool figo per cui non ha
ancora un progetto, l'idea di guadagno in un campo mai toccato. Ma va tenuta stretta,
o il recap torna a 30 righe.

## 7. Formato del recap

```
📥 Settimana 33 · 31 post · 5 tenuti · costo $0.41

💬 Settimana strana: metà della cartella github erano varianti dello
   stesso post "N repos per Claude Code" da 4 account diversi. Segnale
   di moda, non di sostanza — ho tenuto solo l'unico con repo vive.
   La cosa che secondo me conta davvero questa settimana è open-notebook,
   e non per quello che è: perché ti obbliga a decidere una cosa che hai
   rimandato, cioè se la memoria documentale la fai archiviando
   (paperless) o interrogando. Sono due architetture diverse.

✅ open-notebook  ·  da "9 free GitHub repos" (getintoai)
   Alternativa self-hosted a NotebookLM: PDF/video/siti → assistente
   che ci chatti sopra. ⭐37k · ultimo commit 3 giorni fa · MIT
   → TOCCA: personal AI locale. Fa il pezzo "memoria documentale"
     che avevi assegnato a paperless-ngx, ma ci ragiona sopra invece
     di solo archiviare. Da confrontare prima di montare paperless.

❌ OpenSEO — SEO/marketing. Fuori da tutto quello che fa.
❌ "Diventa ricco con Claude" — nessuna entità verificabile. Vuoto.
❌ "Qwen 27B uncensored" — esiste, ma è un fine-tune di terzi, non un
   modello Qwen ufficiale. E non entra nella VRAM della tua GPU.
```

Tre livelli:

1. **Intestazione** — quanti post, quanti tenuti, **quanto è costato**.
2. **💬 Commento** — *uno solo per recap*, non uno per riga. Cosa si nota guardando
   il mucchio (pattern, mode, ripetizioni fra account) e **cosa l'autore dovrebbe
   farci**. È la parte che distingue un recap da un bollettino.
3. **Righe** — per ogni tenuta: **cosa è** → **è vivo?** (dati verificati) → **cosa
   tocca di suo**.

Gli scarti restano visibili **in una riga sola**: servono a vedere *cosa ha buttato* e
a correggere il criterio se sbaglia.

## 8. Cadenza

- **Raccolta:** ogni notte. Poco materiale per volta, ritmo umano.
- **Recap:** settimanale, la domenica (~30 post macinati, ~6 tenuti).

## 9. Tetto di spesa e freno d'emergenza

Requisito esplicito dell'autore (2026-08-20): *"se vedi che superiamo 10€ in una
settimana interrompi tutto per sempre e avvisami"*.

### Doppio freno, e il secondo conta più del primo

| Livello | Chi lo fa rispettare | Soglia |
|---|---|---|
| **Interno** — contatore in `state/spesa.json` | il codice di winnow | avviso a **€3/sett**, arresto a **€10/sett** |
| **Esterno** — limite di spesa sulla chiave API | **Anthropic**, nella Console | da impostare a mano, sopra i €10 |

⚠️ **Il freno interno è sorvegliato dallo stesso programma che potrebbe avere il bug.**
Se il difetto sta nel loop di raccolta, il contatore può non scattare. Il limite sulla
chiave API è l'unica garanzia che non dipende dalla correttezza di questo codice.
**Vanno messi entrambi**, non uno o l'altro.

### Comportamento all'arresto

1. Scrive `state/HALTED` con data, spesa registrata e ultimi post processati.
2. **Non riparte mai da solo.** Finché quel file esiste, ogni run esce subito.
3. Si riparte solo cancellando il file a mano — atto deliberato, non un timeout.
4. Avvisa l'autore.

### Perché €10/settimana è la soglia giusta

La spesa attesa è **~$0.50/settimana**. Dieci euro sono **venti volte** il previsto:
a quel punto non è "un po' caro", è **un bug** — un ciclo che rilegge tutto, un
`seen.json` corrotto, un carosello infinito. Il tetto non serve a risparmiare: serve
a **fermare un difetto** prima che diventi una bolletta.

Ogni run registra il proprio costo, e il costo del batch compare nell'intestazione del
recap (vedi §7) — così la spesa è visibile ogni domenica, non solo quando esplode.

## 10. Forma open source

Deciso il 2026-08-20: il progetto nasce **con la forma di un progetto open source**,
ma **si pubblica solo quando funziona per l'autore**. Decidere la forma adesso costa
quasi zero; rifattorizzarla dopo il primo push costa molto.

### La tensione da sciogliere

La parte di maggior valore — il giudice che sa che *una certa categoria di prodotti
è già stata valutata e scartata, e perché* — è **esattamente la parte non
generalizzabile**. Nasce da anni di contesto personale. Un utente che installa il tool senza quel contesto riceverebbe
un riassuntore: cioè la cosa che §2 dice di non costruire.

### La soluzione: il profilo è il plugin

```
core (generalizzabile al 100%)     ← naviga, estrae, verifica alle fonti
        ↕
profilo.md  (scritto dall'utente)  ← obiettivi, decisioni prese, cosa ha già scartato
        ↕
giudice (intercambiabile)          ← Claude Code · API · modello locale
```

Il `profiles/<tuo>.md` dell'autore diventa **un esempio di profilo**, non parte del codice.

⭐ È anche la tesi del progetto, quella che va nel README: **la qualità del filtro
dipende da quanto bene hai scritto chi sei.** Nessun aggregatore di contenuti fa
questo — filtrano per argomento, non per persona.

### Igiene del repository (dal primo commit, non dopo)

| Versionato | **Mai versionato** |
|---|---|
| `winnow/` (core) | `config.toml` — chiavi API |
| `config.example.toml` | `profiles/*.md` tranne l'esempio |
| `profiles/esempio.md` | `state/` — `seen.json`, `spesa.json`, `HALTED` |
| `docs/` | `findings/` — contenuto letto dai post |

Nessuna credenziale, nessun URL di cartella personale, nessun nome utente nel codice:
tutto in config.

### Rischi accettati

- **Manutenzione.** Un progetto pubblico non finisce al primo commit: issue, PR,
  richieste d'aiuto. Va aperto al pubblico quando c'è il tempo di rispondere, non
  appena il codice compila.
- **Instagram.** Un tool pubblico che automatizza Instagram può attirare richieste di
  rimozione. Non è un blocco — ne esistono molti — ma va saputo prima, non dopo.

### Nome

`winnow` resta il nome di lavoro. La scelta di un nome inglese per la pubblicazione
è rimandabile a costo zero: si decide al momento del push, non adesso.

## 11. Struttura su disco

```
winnow/
├── winnow/               # core — generalizzabile, nessun dato personale
│   ├── browser.py          # Playwright: sessione, navigazione, cattura slide
│   ├── extract.py          # Haiku 4.5: slide → entità strutturate
│   ├── verify.py           # GitHub / HuggingFace / web / llmfit
│   ├── state.py            # seen.json, spesa.json, HALTED
│   └── cli.py              # winnow raccogli | stato | recap
├── profiles/
│   └── esempio.md          # profilo d'esempio (versionato)
├── config.example.toml     # versionato
├── config.toml             # ⛔ gitignore — chiavi, cartelle, username
├── state/                  # ⛔ gitignore
├── findings/               # ⛔ gitignore
└── docs/superpowers/specs/
```

CLI, file su disco, niente database.

## 12. Errori e casi limite

| Caso | Comportamento richiesto |
|---|---|
| **Sessione Instagram scaduta** | **Fermarsi e avvisare.** Mai ciclare a vuoto, mai ritentare in loop. È il fallimento più probabile. |
| Checkpoint / rate limit Instagram | Fermarsi, registrare, riprovare la notte dopo. Non insistere. |
| Slide vuota dopo il salto per URL | Riprovare una volta dopo attesa; poi saltare la slide e annotarlo |
| Post senza entità verificabili | Scartato con motivo `nessuna entità` — resta nel recap come riga di scarto |
| Verifica alla fonte fallita (rete, 404) | Entità tenuta ma marcata `non verificata`. Mai spacciare per verificato ciò che non lo è. |
| Post già visto | Saltato senza costo |

**Profilo browser dedicato.** Playwright usa un profilo persistente separato, non il
Brave di tutti i giorni. Il login si fa a mano, una volta ogni tanto.

**Ritmo umano.** Poche pagine per giro, attese reali, intervalli non regolari. Non è
paranoia: 30 post da 11 slide in quattro minuti ogni notte si fa notare.

## 13. Test

- `verify.py` e `state.py`: test veri, sono logica pura e deterministica.
- `extract.py`: test su un piccolo corpus di slide salvate su disco, così non serve
  rete né API per girare.
- `browser.py`: non si testa in automatico. Si verifica a mano contro Instagram.

## 14. Fuori perimetro (per ora)

- Scansione del feed o di account sorvegliati — **valutata e scartata**: farebbe
  giudicare tutto alla cieca, costa ~10× ed è meno preciso. Il salvataggio manuale
  dell'autore è il filtro migliore e costa un tap.
- Cartelle `girlz` e `Tutti i post`.
- Notifiche Telegram / demone col giudizio incluso — ha senso quando Hermes gira
  davvero sull'Omen, non prima.
- Test autonomi dei tool trovati (richiesta iniziale dell'autore): rimandato, va
  ridiscusso a parte quando il winnow funziona.

## 15. Decisioni prese, da non riaprire

| Decisione | Motivo |
|---|---|
| Input = cartelle salvate, non il feed | Il tap dell'autore è il segnale di interesse migliore e gratuito |
| Estrazione via Haiku, giudizio via sessione Claude Code | Il giudice ha bisogno del `profiles/<tuo>.md` nel contesto |
| Si leggono **tutte** le slide, non solo la copertina | La copertina è la promessa clickbait; il valore sta dentro |
| Verifica alla fonte obbligatoria | È l'unica difesa contro l'8 su 10 di spazzatura |
| Corsia Apertura sempre attiva | Senza, il filtro diventa a mente chiusa |
| Tetto di spesa doppio (interno + chiave API) | Un freno sorvegliato dal programma che ha il bug non è un freno |
| Il recap porta un commento, non solo righe | Senza commento è un bollettino: elenca senza dire cosa farne |
| Forma open source da subito, pubblicazione dopo | Rifattorizzare dopo il push costa; pubblicare a ottobre costa attenzione che non ha |
| Il profilo è il plugin, non il codice | È l'unico modo di generalizzare senza perdere la parte di valore |
