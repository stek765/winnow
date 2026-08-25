# winnow — l'app

**Data:** 2026-08-25
**Stato:** design approvato, non ancora implementato
**Sostituisce:** l'idea *"An interface"* aperta in `CLAUDE.md`, che restava indecisa
fra TUI e UI vera.

---

## 1. Il problema

winnow è diventato **undici comandi** (`init collect status recap render config
update reset-halt schedule login where`). Nove sono setup e manutenzione, due
sono il rito settimanale — e proprio quei due si spezzano in tre pezzi, perché
in mezzo ci sei tu a fare da ponte:

```
winnow recap  →  incolli nel modello  →  copi la risposta  →  winnow render
```

**Quel ponte è l'unico punto del giro dove un utente può fallire senza capire
perché**, ed è misurato: il 2026-08-25 una risposta è andata persa lì. Copiata
dallo scrollback di un terminale, che manda a capo e tronca le righe lunghe, è
arrivata a `winnow render` già rotta. Due bug del codice l'hanno peggiorata
(il ramo che gestiva l'errore JSON era irraggiungibile, e la risposta non veniva
salvata prima di essere validata): entrambi corretti, ma **la causa resta il
copia-incolla**, e nessun messaggio d'errore la elimina.

C'è anche una richiesta esplicita dell'autore, che riformula il problema:

> *«non ci deve essere un terminale.. io voglio un app»*

Non un'app *accanto* alla CLI. winnow **è** un'applicazione; la CLI resta sotto,
invisibile, perché qualcosa deve raccogliere alle 13:00 anche a finestra chiusa.

## 2. Cosa NON è

**Non è un pannello di controllo per gli undici comandi.** Trasformare ogni comando
in un bottone sposta il problema in una finestra più bella: resteresti tu a
decidere quale premere e in che ordine.

**Non è un archivio da sfogliare.** La ragione per cui winnow esiste è che i post
salvati non si riguardano mai; un'interfaccia che va aperta di proposito rischia
di ereditare esattamente quel problema. L'archivio c'è, ma non è il motivo per
cui apri l'app.

L'app è **un bottone che chiude il giro**. Tutto il resto le sta dietro.

---

## 3. Le decisioni bloccate

| Decisione | Scelta | Perché |
|---|---|---|
| Guscio finale | **Tauri** | Il difficile del multipiattaforma non è la finestra, è la distribuzione: Tauri impacchetta `.dmg`, `.deb`, `.AppImage` e ha l'aggiornatore dentro. |
| Guscio v1 | **browser senza barra** | Se la meta è Tauri, non ha senso comprare la finestra due volte: Tauri porta finestra e impacchettamento insieme. Costo zero adesso. |
| SwiftUI nativo | **escluso** | È solo Apple, e l'app deve girare anche su Linux. La decisione si è sciolta da sola quando è entrato quel vincolo. |
| Interfaccia | **HTML/CSS/JS** | È già dimostrato: la pagina del recap è quella lingua lì. E rende il guscio sostituibile. |
| Chi parla col modello | **l'app, via API** | Fa sparire il copia-incolla, cioè il difetto di §1. Costo stimato ≈ $0.30–0.60 a recap, ~$2/mese sopra l'attuale ~$1 di raccolta. |
| Il motore | **consegna dati, non stampa** | Vedi §7. |

⚠️ **L'unica decisione irreversibile è quella dell'interfaccia web.** Il guscio si
sostituisce; il paradigma dell'interfaccia no. Se un giorno la meta diventasse
SwiftUI nativo, la UI andrebbe rifatta da capo — di quel lavoro sopravvivrebbe
solo il motore e l'API. È scritto qui perché nessuno lo riscopra credendo che sia
un dettaglio.

---

## 4. Le cinque schermate

```
   PRIMO AVVIO                              POI, SEMPRE
   ┌──────────────────┐                     ┌──────────────────────────┐
   │   Benvenuto      │                     │        CASA              │
   │  ① il modello    │                     │  ● 30 post pronti        │
   │  ② il browser    │  ─────────────▶     │    raccolto oggi 13:00   │
   │  ③ Instagram     │                     │   [  Fai il recap  →  ]  │
   │  ④ le cartelle   │                     │  archivio   impostazioni │
   │  ⑤ chi sei       │                     └──────────────────────────┘
   └──────────────────┘                                 │
                        ┌───────────────────────────────┼─────────────────┐
                        ▼                               ▼                 ▼
                  IL RECAP                        ARCHIVIO         IMPOSTAZIONI
```

**Benvenuto** sono i sei passi di `winnow init` diventati schermate. Il passo ⑥
(l'orario della raccolta) esce dal primo avvio e va nelle impostazioni con un
valore già scelto: **non è una domanda da fare a chi ha appena installato**.

**Il recap finito è la pagina che esiste già** — il quadro di Millet, le voci con
la slide da cui vengono, gli scarti raggruppati per verdetto. Non si riprogetta:
diventa una schermata dell'app.

---

## 5. La casa non ha una faccia sola

Il bottone cambia in base a cosa serve adesso. Cinque stati, cinque schermate:

```
  ● pronto            30 post · raccolto oggi 13:00
                      [  Fai il recap  →  ]

  ○ niente di nuovo   nessun post nuovo dall'ultimo recap
                      [  Raccogli ora  ]

  ⟳ sta lavorando     36 su 41 · $0.09 finora
                      [  ferma  ]

  ⚠ ti sei sconnesso  Instagram ha chiuso la sessione
                      [  Rientra  ]

  ⛔ freno tirato      spesa oltre €10 in una settimana
                      [  Riparti  ]
```

**Non esiste una schermata vuota in cui non sai cosa fare.** In ogni situazione
c'è una cosa sola da premere, e il bottone dice cosa succederà.

Gli ultimi due stati esistono perché sono i due modi in cui winnow si ferma
davvero: la sessione Instagram che scade e il freno di spesa. Oggi te ne accorgi
solo se lanci `winnow status` — cioè, per un utente dell'app, **mai**.

---

## 6. Ciclo di vita

| Quando | Cosa succede |
|---|---|
| Doppio click | Si apre la finestra; sotto parte il motore su una porta locale. |
| Chiudi la finestra | Il motore si spegne con lei. Niente resta acceso. |
| 13:00, app chiusa | Il servizio di sistema raccoglie lo stesso. Riaprendo trovi i post pronti. |
| 13:00, app aperta | Vedi la raccolta scorrere in diretta. |
| Riapri mentre è aperta | Torna la finestra esistente, non una seconda. |

---

## 7. Il confine

> **La finestra non tocca mai i file.** Non legge `findings/`, non scrive
> `config.toml`. Chiede al motore e riceve dati.

È la regola che fa esistere Tauri domani: se la finestra sapesse dove stanno i
file, cambiarla vorrebbe dire riscrivere anche quella conoscenza.

### 7.1 Il motore consegna, non stampa

Oggi i comandi *dicono* le cose mentre lavorano:

```python
print("  ✓ Immich — 112528 ★")
```

Per mostrare quella riga in una schermata bisognerebbe **rileggere quel testo e
ricostruirci dentro il dato**. E il giorno che qualcuno cambia `✓` in `✅`, l'app
smette di capire senza dire niente — è leggere un sensore dalla stampa di debug
sulla UART invece che dal registro.

Quindi i comandi diventano funzioni che restituiscono risultati ed emettono
eventi:

```python
on_event({"kind": "verified", "name": "Immich", "stars": 112528})
```

e sopra ci stanno **due adattatori sottili**: la CLI stampa l'evento come oggi,
l'API lo serializza. Il motore non sa cosa sia HTTP.

⚠️ **Il refactoring si fa un comando alla volta**, insieme alla schermata che lo
usa. Non tutti prima.

### 7.2 La superficie

```
GET   /api/state              tutto ciò che serve alla casa in un colpo:
                              post pronti, ultima raccolta, spesa,
                              sessione Instagram viva? freno tirato?
POST  /api/collect            → id del lavoro
POST  /api/recap              → id del lavoro
GET   /api/jobs/{id}          a che punto è, evento per evento
POST  /api/jobs/{id}/stop
GET   /api/recaps             l'archivio
GET   /api/recaps/{settimana} la pagina di quella settimana
GET   /api/config   PUT /api/config
POST  /api/login    POST /api/reset-halt    POST /api/update
```

**`/api/recap` è un comando solo**: prepara, manda al modello, riceve,
renderizza. I tre passaggi di §1 diventano un lavoro che riporta a che punto è.

### 7.3 La finestra non decide niente

> Mostra lo stato e manda comandi. Nessun giudizio, nessun calcolo, nessuna
> conoscenza di dove stiano i file.

È la regola in cima al `CLAUDE.md` — *«il raccoglitore non giudica»* — applicata
un piano più su. Con una conseguenza pratica: **se nel browser non c'è logica,
non c'è niente da testare nel browser.**

---

## 8. Tre difetti da correggere, emersi disegnando

### 8.1 Il recap prende una finestra mobile, non «la settimana»

`week_files()` seleziona **gli ultimi 7 giorni di calendario**, e non esiste da
nessuna parte uno stato *"fin dove ho già giudicato"*. Due conseguenze:

| | |
|---|---|
| Due recap ravvicinati | Domenica giudichi lun–dom; mercoledì rigiudichi mar–mer **più** gio–dom già visti. Rileggi e ripaghi. |
| Salti dieci giorni | I giorni 8, 9 e 10 escono dalla finestra e **non li vede più nessuno**: pagati, raccolti, mai giudicati. |

Il secondo è quello grave: winnow esiste perché i post salvati non si riguardano
mai, e qui è il tool stesso a perderne un pezzo in silenzio.

➡️ **Il recap parte dall'ultimo recap fatto, non da sette giorni fa.** Serve un
pezzo di stato, come `seen.json` per i post. Senza recap precedenti, prende tutto.

⭐ Non è un dettaglio dell'app: **«30 post pronti» sulla casa può essere una frase
onesta solo se *pronti* significa «non ancora giudicati»**, e la finestra mobile
quel numero non lo sa calcolare. È il disegno della schermata ad aver fatto
emergere il difetto.

### 8.2 L'archivio riapre la pagina, non la ricostruisce

Le pagine esistono già come file `.html` completi. L'archivio le riapre; non
rigenera niente. Il recap del 25 agosto, fra sei mesi, si apre identico.

### 8.3 Le pagine vecchie si svuotano

Le slide **non sono dentro** la pagina:

```html
src="../state/shots/Dbnx278iPKV_04.png"
```

Gli screenshot stanno in una cartella condivisa che pesa **58 MB per due giorni**
(misurato 2026-08-25) e che **nessuno pulisce**. Due strade opposte:

- non pulire mai → decine di GB in un anno
- pulire → **le pagine vecchie perdono le figure**, cioè proprio l'archivio

➡️ **Quando un recap è finito, le sue slide entrano dentro la pagina** come
`data:` URI — la stessa cosa che si fa già col quadro di Millet. Una quindicina
di immagini: la pagina passa da ~190 KB (misurata) a 1–2 MB e diventa un file unico che
sopravvive a qualsiasi pulizia. Gli screenshot sciolti si possono poi cancellare
dopo N settimane senza perdere niente.

---

## 9. Errori e casi limite

| Situazione | Cosa fa l'app |
|---|---|
| Sessione Instagram scaduta | Stato ⚠ sulla casa, bottone che apre la finestra di login. |
| Freno di spesa tirato | Stato ⛔, con quanto e perché, e il bottone per ripartire. |
| Il modello non risponde / chiave scaduta | Il lavoro fallisce e lo dice; **il pacchetto resta su disco** e si può ritentare senza ricostruirlo. |
| Risposta del modello non valida | Salvata comunque, come già fa `render_clipboard`. La pagina non si apre, l'errore mostra la riga. |
| Porta locale occupata | Ne prova un'altra. La finestra non deve mai aprirsi su una pagina bianca. |
| Nessuna rete | `/api/state` risponde lo stesso con quello che sa da disco, e dichiara cosa non ha potuto chiedere. Mai «tutto a posto» per silenzio. |
| Primo avvio, Chromium da scaricare | ~150 MB. Va **raccontato** con una barra vera, non lasciato a una finestra ferma. |

---

## 10. Test

I 364 test restano dove sono: offline, sul motore, senza rete né Playwright né
chiavi. Non cambia niente per loro.

- **Il motore**: come oggi. Il refactoring di §7.1 li tocca solo dove un comando
  passa da `print` a evento — e quella è una cosa in più da verificare, non in
  meno.
- **L'API**: si prova chiamandola con un motore finto. Nessuna infrastruttura
  nuova.
- **Il browser**: niente. Per costruzione (§7.3) non c'è logica da testare.

Il giorno che il guscio diventa Tauri, nessuno di questi test si tocca.

---

## 11. Cosa resta fuori, deliberatamente

- **Correggere un giudizio sbagliato** perché torni nel profilo. È la cosa che
  farebbe *migliorare* il filtro invece di lasciarlo fermo, ed è la più
  interessante — ma richiede l'archivio funzionante e recap salvati in forma
  strutturata. Dopo.
- **Windows.** Il vincolo dichiarato è Mac e Linux.
- **Multiutente, sincronizzazione, cloud.** winnow è una cosa che gira sulla tua
  macchina; non cambia.
