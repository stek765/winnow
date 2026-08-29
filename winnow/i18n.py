"""What winnow says, in the language the reader chose.

English is the default and the source: every key is written in English first,
and Italian is an override. That order is deliberate — the tool is published
in English, and a missing Italian string should fall back to something a
reader can act on rather than to a key nobody can read.

Only the parts a *reader* sees live here: the window, and the chrome of the
pages winnow builds. The terminal stays English (it always was). What the
model writes inside a recap or a draw follows this same choice — the prompts
carry a `{language}` that `prompt_body` fills in — because a window set to
English whose ideas come back in Italian is winnow disagreeing with a setting
the reader has just changed.
"""
from __future__ import annotations

DEFAULT = "en"
LANGS = ("en", "it")

# Named, because these are shown to the reader in the settings sheet and a
# code is not a name.
NAMES = {"en": "English", "it": "Italiano"}

# The same languages named *in English*, which is what goes into a prompt:
# the prompt is written in English and «write in Italiano» is a sentence in
# two languages. Separate from NAMES because that one is the endonym, which is
# right in a settings sheet and wrong in an instruction.
IN_ENGLISH = {"en": "English", "it": "Italian"}


def language_name(lang: str) -> str:
    """What to call this language inside a prompt."""
    return IN_ENGLISH.get(lang, IN_ENGLISH[DEFAULT])

# key → {lang: text}. English is complete by construction: `t()` falls back to
# it, and a test asserts every key has one.
STRINGS: dict[str, dict[str, str]] = {
    # --- the home screen, decided in appstate.py -----------------------
    "home.collected_on": {"en": "Collected on {day}",
                          "it": "Raccolti il {day}"},
    "home.collected_between": {"en": "Collected between {a} and {b}",
                               "it": "Raccolti fra il {a} e il {b}"},
    "home.days_pending_one": {"en": "1 day not judged yet",
                              "it": "1 giorno non ancora giudicato"},
    "home.days_pending": {"en": "{n} days not judged yet",
                          "it": "{n} giorni non ancora giudicati"},
    "home.busy.collect": {"en": "Collecting", "it": "Sto raccogliendo"},
    "home.busy.recap": {"en": "Making the recap", "it": "Sto facendo il recap"},
    "home.busy.ideas": {"en": "Drawing an idea", "it": "Sto pescando un'idea"},
    "home.busy.folders": {"en": "Reading your folders",
                          "it": "Sto guardando le tue cartelle"},
    "home.busy.other": {"en": "Working", "it": "Sto lavorando"},
    "home.busy.spent": {"en": "${usd} so far", "it": "${usd} finora"},
    "home.stop": {"en": "Stop", "it": "Ferma"},
    "home.logged_out": {"en": "Instagram has closed the session",
                        "it": "Instagram ha chiuso la sessione"},
    "home.logged_out.detail": {
        "en": "Until you sign back in, nothing new arrives.",
        "it": "Finché non rientri non arriva niente di nuovo."},
    "home.login": {"en": "Sign back in", "it": "Rientra"},
    "home.brake": {"en": "Brake on", "it": "Freno tirato"},
    "home.brake.detail": {
        "en": "Spending went past this week's limit.",
        "it": "La spesa ha superato il limite della settimana."},
    "home.restart": {"en": "Start again", "it": "Riparti"},
    "home.ready.one": {"en": "1 post to judge", "it": "1 post da giudicare"},
    "home.ready": {"en": "{n} posts to judge", "it": "{n} post da giudicare"},
    "home.recap": {"en": "Make the recap", "it": "Fai il recap"},
    "home.collect_now": {"en": "Collect now", "it": "Raccogli ora"},
    "home.nothing": {"en": "All judged", "it": "Tutto giudicato"},
    "home.nothing.detail": {
        "en": "There is nothing left to read. Save something on Instagram, "
              "then collect it from here or wait for tomorrow's run.",
        "it": "Non è rimasto niente da leggere. Salva qualcosa su Instagram, "
              "poi raccoglilo da qui o aspetta la corsa di domani."},

    # --- what a run says, while it runs -------------------------------
    "run.failed.profile": {"en": "no profile: {path}",
                           "it": "manca il profilo: {path}"},
    "run.failed.config": {"en": "no configuration: {path}",
                          "it": "manca la configurazione: {path}"},
    "run.failed.thin": {
        "en": "too little kept to draw from: make a recap first",
        "it": "c'è troppo poco da cui pescare: fai prima un recap"},
    "run.failed.credential": {
        "en": "the profile holds a credential: it was not sent",
        "it": "il profilo contiene una credenziale: non l'ho mandato"},
    "run.failed.truncated": {
        "en": "the answer was cut off; the part written is saved in {file}",
        "it": "la risposta si è troncata; il pezzo scritto è salvato in {file}"},
    "run.failed.json": {
        "en": "the answer is not valid JSON ({why}); saved anyway in {file}",
        "it": "la risposta non è JSON valido ({why}); salvata comunque in {file}"},
    "run.stopped.before": {"en": "stopped before calling the model",
                           "it": "fermata prima di chiamare il modello"},
    "run.stopped.waiting": {"en": "stopped while waiting to try again",
                            "it": "fermata mentre aspettava di riprovare"},
    "run.stopped.folder": {"en": "stopped while reading the folder",
                           "it": "fermata mentre leggeva la cartella"},

    # --- the pages winnow builds --------------------------------------
    "page.source_found": {"en": "found at the source",
                          "it": "trovato alla fonte"},
    "page.source_none": {"en": "no source to ask",
                         "it": "nessuna fonte da chiedere"},
    "page.source_missing": {"en": "the source does not find it",
                            "it": "la fonte non lo trova"},
    "page.no_answer": {"en": "the source did not answer",
                       "it": "la fonte non ha risposto"},
    # The ten verdicts. The Italian is the **key** — it is what the prompt
    # asks the model to write, what `VERDICT_ORDER` sorts by, and what a merge
    # groups on, so it must stay put whatever language the reader picked. Only
    # what is printed changes. A key that varied with the language would make
    # two recaps of the same week ungroupable.
    "verdict.NON ESISTE": {"en": "DOES NOT EXIST", "it": "NON ESISTE"},
    "verdict.FERMO DA ANNI": {"en": "DEAD FOR YEARS", "it": "FERMO DA ANNI"},
    "verdict.NOME FRAGILE": {"en": "SHAKY NAME", "it": "NOME FRAGILE"},
    "verdict.CHI CI GUADAGNA": {"en": "SOMEBODY IS SELLING",
                                "it": "CHI CI GUADAGNA"},
    "verdict.SOLO ANNUNCIO": {"en": "ANNOUNCEMENT ONLY",
                              "it": "SOLO ANNUNCIO"},
    "verdict.NON VERIFICATO": {"en": "NOT VERIFIED", "it": "NON VERIFICATO"},
    "verdict.SCATOLA CHIUSA": {"en": "CLOSED BOX", "it": "SCATOLA CHIUSA"},
    "verdict.DOPPIONE": {"en": "DUPLICATE", "it": "DOPPIONE"},
    "verdict.GIA' TUO": {"en": "ALREADY YOURS", "it": "GIA' TUO"},
    "verdict.LO CONOSCI": {"en": "YOU KNOW IT", "it": "LO CONOSCI"},
    "verdict.FUORI BERSAGLIO": {"en": "OFF TARGET", "it": "FUORI BERSAGLIO"},
    "verdict.ALTRO": {"en": "OTHER", "it": "ALTRO"},
    "verdict.kept": {"en": "KEPT", "it": "TENUTA"},
    "page.posts_read": {"en": "posts read", "it": "post letti"},
    "page.one_of_n": {"en": "one of {n} on this slide",
                      "it": "una di {n} su questa slide"},
    "page.what_became": {"en": "and what became of them",
                         "it": "e cosa ne è stato"},
    "page.the_post": {"en": "the post", "it": "il post"},
    "page.stars": {"en": "stars", "it": "stelle"},
    "page.open": {"en": "open", "it": "apri"},
    "page.same_slide": {"en": "On the same slide, and what became of them",
                        "it": "Sulla stessa slide, e cosa ne è stato"},

    "page.saved": {"en": "{n} things saved.", "it": "{n} cose salvate."},
    "page.worth": {"en": "{n} are worth your time.",
                   "it": "{n} valgono il tuo tempo."},
    "page.comment": {"en": "The week's comment",
                     "it": "Il commento della settimana"},
    "page.credit": {
        "en": "Jean-François Millet, <em>The Winnower</em>, 1847–48. "
              "Public domain.",
        "it": "Jean-François Millet, <em>Il vagliatore</em>, 1847–48. "
              "Pubblico dominio."},
    "page.kept_eyebrow": {"en": "Kept", "it": "Passate"},
    "page.kept_heading": {"en": "What is worth your time",
                          "it": "Cosa vale il tuo tempo"},
    "page.all": {"en": "All", "it": "Tutte"},
    "page.kept": {"en": "kept", "it": "passate"},
    "page.unreadable": {"en": "unreadable", "it": "illeggibili"},
    "page.spent": {"en": "spent", "it": "spesi"},
    "page.stale": {"en": "years untouched", "it": "fermo da anni"},
    "page.last_commit": {"en": "last commit {when}",
                         "it": "ultimo commit {when}"},
    "page.stopped_since": {"en": "untouched since {when}",
                           "it": "fermo dal {when}"},
    "page.why_label": {"en": "Why it got through", "it": "Perché passa"},
    "page.doubt_label": {"en": "Doubt", "it": "Dubbio"},
    "page.stopped_eyebrow": {"en": "Stopped", "it": "Fermate"},
    "page.stopped_heading": {"en": "{n} things did not get through",
                             "it": "{n} cose non sono passate"},
    "page.stopped_intro": {
        "en": "Each with its own name and its own reason, because a heap "
              "cannot be corrected. The numbers below are the shape of the "
              "reasoning: if one of them is wrong, that is where it shows.",
        "it": "Ognuna col suo nome e il suo motivo, perché un mucchio non si "
              "può correggere. I numeri qui sotto sono la forma del "
              "ragionamento: se uno è sbagliato, è lì che si vede."},
    "page.art_alt": {
        "en": "A farmer throws grain into the air: the wind carries the "
              "chaff away.",
        "it": "Un contadino lancia il grano in aria: il vento porta via la "
              "pula."},
    "page.many_on_slide": {"en": "this slide names many",
                           "it": "questa slide ne nomina molti"},

    # --- the merged page ----------------------------------------------
    "merge.why": {"en": "why", "it": "perché"},
    "merge.n_recaps": {"en": "{n} recaps", "it": "{n} recap"},
    # «da {a} a {b}» reads as a period, and a merge is a *selection*: the one
    # made of 23, 24 and 28 August was read as containing the 27th. «chosen
    # between» says the two dates are the ends of a choice, not its content.
    "merge.label_many": {"en": "{n} recaps chosen between {a} and {b}",
                         "it": "{n} recap scelti tra {a} e {b}"},
    "merge.harvest_of": {"en": "The harvest of {days}",
                         "it": "Il raccolto di {days}"},
    "merge.counts": {"en": "{things} things &middot; {weeks} recaps &middot; "
                           "{posts} posts read &middot; ${usd} spent",
                     "it": "{things} cose &middot; {weeks} recap &middot; "
                           "{posts} post letti &middot; ${usd} spesi"},
    "merge.title": {"en": "The harvest, {label} — winnow",
                    "it": "Il raccolto, {label} — winnow"},

    # --- the ideas page -----------------------------------------------
    "idea.title": {"en": "Ideas — winnow", "it": "Idee — winnow"},
    "idea.heading": {"en": "Ideas", "it": "Idee"},
    "idea.difficulty": {"en": "difficulty", "it": "difficoltà"},
    # The three the prompt allows, as keys. Italian because that is what the
    # prompt asks for and what `HARD` colours on — the same rule as a verdict:
    # a key that moved with the language would recolour every page ever made.
    "difficulty.facile": {"en": "easy", "it": "facile"},
    "difficulty.media": {"en": "medium", "it": "media"},
    "difficulty.tosta": {"en": "hard", "it": "tosta"},
    "idea.time": {"en": "time", "it": "tempo"},
    "idea.one_evening": {"en": "one evening", "it": "una sera"},
    "idea.but": {"en": "and it may not hold", "it": "e non è detto"},
    "idea.nothing_came": {"en": "Nothing came of these",
                          "it": "Non ne è uscito niente"},
    "idea.counts_one": {"en": "{drawn} things drawn at random out of {total} "
                              "&middot; 1 idea &middot; ${usd} spent",
                        "it": "{drawn} cose estratte a sorte su {total} "
                              "&middot; 1 idea &middot; ${usd} spesi"},
    "idea.counts": {"en": "{drawn} things drawn at random out of {total} "
                          "&middot; {n} ideas &middot; ${usd} spent",
                    "it": "{drawn} cose estratte a sorte su {total} "
                          "&middot; {n} idee &middot; ${usd} spesi"},

    # --- what the API answers when it refuses -------------------------
    "err.bad_url": {"en": "not a link this can open",
                    "it": "non è un link che si possa aprire"},
    "err.two_recaps": {"en": "at least two recaps are needed",
                       "it": "servono almeno due recap"},
    "err.missing_judgement": {"en": "the judgement of {days} is missing",
                              "it": "manca il giudizio di {days}"},
    "err.no_such_page": {"en": "no such page", "it": "non esiste"},
    "err.not_readable": {"en": "that judgement cannot be read as data",
                         "it": "il giudizio non è leggibile come dati"},
    "err.empty_key": {"en": "the key is empty", "it": "la chiave è vuota"},
    "err.no_key_needed": {"en": "{provider} does not use a key",
                          "it": "{provider} non usa una chiave"},
    "err.no_console": {"en": "no page for {provider}",
                       "it": "nessuna pagina per {provider}"},
    "err.no_config": {"en": "no config yet — run the setup",
                      "it": "manca la configurazione — fai il setup"},
    "err.busy": {"en": "something is already running",
                 "it": "c'è già qualcosa in corso"},
}


def t(key: str, lang: str = DEFAULT, **kw) -> str:
    """One string, in one language.

    Falls back to English rather than to the key: a reader who meets a gap in
    a translation should still get a sentence they can act on. An unknown key
    is a bug, and it shows as the key so it is caught rather than hidden.
    """
    row = STRINGS.get(key)
    if row is None:
        return key
    text = row.get(lang) or row[DEFAULT]
    return text.format(**kw) if kw else text
