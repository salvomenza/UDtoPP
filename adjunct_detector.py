# ver. 25
"""
adjunct_detector.py

Rileva i sintagmi per cui UDPipe non consente di stabilire con certezza
se si tratta di argomenti o aggiunti, e costruisce la lista di domande
da porre all'utente prima della generazione dell'albero.

Struttura di una «scelta aggiunto»:
{
  "token_id": int,          # id del token testa del sintagma
  "form": str,              # forma superficiale (es. "in cucina")
  "deprel": str,            # etichetta UDPipe originale (es. "obl")
  "heuristic": str,         # "argomento" | "aggiunto"   (suggerimento euristico)
  "heuristic_reason": str,  # breve spiegazione del suggerimento
  "role": str | None,       # scelta utente: "argomento" | "aggiunto"
  "attach": str | None,     # scelta utente: "SV" | "Sv" | "ST" | "SC"
}

Le scelte vengono poi passate a build_tp() e generate_steps() come
dizionario  adjunct_choices = { token_id: {"role": ..., "attach": ...} }
"""

from __future__ import annotations
from typing import Optional

# ── Preposizioni tipicamente argomentali per certi verbi ────────────────────
# (lista non esaustiva — serve solo per l'euristica)
_PREP_ARG = {
    "parlare": {"di"},
    "dipendere": {"da"},
    "pensare": {"a", "di"},
    "credere": {"a", "in"},
    "andare": {"a", "in", "da", "verso"},
    "venire": {"da"},
    "abitare": {"a", "in"},
    "vivere": {"a", "in"},
    "lavorare": {"a", "in", "per"},
    "aspettare": {"di"},
    "smettere": {"di"},
    "cercare": {"di"},
    "cominciare": {"a", "di"},
    "iniziare": {"a"},
    "continuare": {"a"},
    "riuscire": {"a"},
    "finire": {"di"},
    "sperare": {"di", "in"},
    "occuparsi": {"di"},
    "interessarsi": {"a", "di"},
    "preoccuparsi": {"di", "per"},
    "accorgersi": {"di"},
    "fidarsi": {"di"},
    "trattare": {"di"},
    "consistere": {"in"},
}

# Preposizioni quasi sempre argomentali (indipendentemente dal verbo)
_PREP_ALMOST_ALWAYS_ARG = {"di", "da"}

# Preposizioni quasi sempre aggiunte (locative/temporali/strumentali)
_PREP_ALMOST_ALWAYS_ADJ = {"con", "senza", "durante", "dopo", "prima", "tra", "fra"}

# Categorie grammaticali che di solito introducono adjuncts temporali/locativi
_UPOS_ADJ = {"ADV"}


def _get_case_prep(token_id: int, tokens: list[dict]) -> Optional[str]:
    """Restituisce la preposizione 'case' che dipende da token_id, se presente."""
    case = next(
        (t["form"].lower() for t in tokens
         if t["deprel"] == "case" and t["head"] == token_id),
        None,
    )
    return case


def _surface_form(token_id: int, tokens: list[dict]) -> str:
    """Ricostruisce la forma superficiale del sintagma (prep + testa)."""
    tok = next((t for t in tokens if t["id"] == token_id), None)
    if tok is None:
        return "?"
    prep = _get_case_prep(token_id, tokens)
    if prep:
        return f"{prep} {tok['form']}"
    return tok["form"]


def _heuristic(root_lemma: str, token: dict, tokens: list[dict]) -> tuple[str, str]:
    """
    Restituisce (suggerimento, motivazione).
    suggerimento: "argomento" | "aggiunto"
    """
    prep = _get_case_prep(token["id"], tokens)
    upos = token.get("upos", "")

    # advmod è quasi sempre aggiunto
    if token["deprel"] == "advmod":
        return "aggiunto", "gli avverbi modificatori sono quasi sempre aggiunti"

    # upos avverbiale senza preposizione → aggiunto
    if upos in _UPOS_ADJ:
        return "aggiunto", "elemento avverbiale tipicamente aggiunto"

    if prep is None:
        # obl senza preposizione: raro ma possibile (es. dativi liberi)
        return "aggiunto", "sintagma obliquo senza preposizione: probabile aggiunto"

    # Preposizioni quasi sempre aggiunte
    if prep in _PREP_ALMOST_ALWAYS_ADJ:
        return "aggiunto", f"la preposizione «{prep}» introduce quasi sempre un aggiunto"

    # Verbo nella lista con preposizioni argomentali note
    if root_lemma in _PREP_ARG and prep in _PREP_ARG[root_lemma]:
        return "argomento", (
            f"il verbo «{root_lemma}» seleziona tipicamente "
            f"un complemento introdotto da «{prep}»"
        )

    # Preposizioni «di» e «da» spesso argomentali, ma non sempre
    if prep in _PREP_ALMOST_ALWAYS_ARG:
        return "argomento", (
            f"la preposizione «{prep}» introduce spesso un argomento, "
            f"ma può anche introdurre un aggiunto"
        )

    # Default: aggiunto (locativo/temporale/strumentale)
    return "aggiunto", (
        f"la preposizione «{prep}» introduce tipicamente "
        f"un modificatore locativo, temporale o strumentale"
    )


def detect_ambiguous_adjuncts(tokens: list[dict]) -> list[dict]:
    """
    Restituisce la lista di sintagmi ambigui (argomento vs aggiunto)
    dipendenti dalla radice.

    Vengono inclusi:
    - tutti gli «obl» non-wh, non-agent
    - gli «advmod» (quasi sempre aggiunti, ma rendiamo esplicita la scelta)

    Non vengono inclusi (non ambigui):
    - obl:agent  → sempre aggiunto del passivo
    - obj / iobj → sempre argomenti
    - nsubj      → sempre argomento
    - nmod       → modificatore nominale, gestito separatamente
    - xcomp/ccomp → quasi sempre argomenti, non li tocchiamo qui
    """
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root:
        return []

    from ud_to_chomsky import is_wh_token  # import locale per evitare circolarità

    ambiguous = []

    for t in tokens:
        if t["head"] != root["id"]:
            continue

        deprel = t["deprel"]

        # obl: il caso principale di ambiguità
        if deprel == "obl":
            if is_wh_token(t):
                continue  # wh-element: gestito a parte dal sistema esistente
            hint, reason = _heuristic(root["lemma"], t, tokens)
            ambiguous.append({
                "token_id": t["id"],
                "form": _surface_form(t["id"], tokens),
                "deprel": deprel,
                "heuristic": hint,
                "heuristic_reason": reason,
                "role": None,
                "attach": None,
            })

        # advmod: includiamo anche questi per trasparenza didattica
        elif deprel == "advmod":
            ambiguous.append({
                "token_id": t["id"],
                "form": _surface_form(t["id"], tokens),
                "deprel": deprel,
                "heuristic": "aggiunto",
                "heuristic_reason": "gli avverbi modificatori sono quasi sempre aggiunti",
                "role": None,
                "attach": None,
            })

    return ambiguous


def apply_adjunct_choices(
    adjuncts: list[dict],
    choices: dict[int, dict],
) -> list[dict]:
    """
    Applica le scelte dell'utente alla lista di aggiunti.
    choices = { token_id: {"role": "argomento"|"aggiunto",
                            "attach": "SV"|"Sv"|"ST"|"SC"} }
    """
    result = []
    for a in adjuncts:
        tid = a["token_id"]
        if tid in choices:
            a = dict(a)  # copia
            a["role"] = choices[tid].get("role", a["heuristic"])
            a["attach"] = choices[tid].get("attach", "Sv")
        else:
            # Nessuna scelta: usa il suggerimento euristico con attach default
            a = dict(a)
            a["role"] = a["heuristic"]
            a["attach"] = "Sv"
        result.append(a)
    return result


def adjuncts_as_dict(adjuncts_with_choices: list[dict]) -> dict[int, dict]:
    """
    Converte la lista in un dizionario token_id → {role, attach}
    pronti per essere consumati da build_tp() e generate_steps().
    """
    return {
        a["token_id"]: {"role": a["role"], "attach": a["attach"]}
        for a in adjuncts_with_choices
        if a["role"] is not None
    }
