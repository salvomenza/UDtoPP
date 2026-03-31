# ver. 26.1
"""
adjunct_detector.py

Ver. 25: integrazione spaCy NER (it_core_news_md) per raffinare
l'euristica su preposizioni ambigue (a, in, su, da, verso):
  - testa GPE/LOC  -> locativo -> aggiunto
  - testa PER/ORG  -> dativo   -> argomento
"""

from __future__ import annotations
from typing import Optional
import functools


# Caricamento lazy del modello spaCy
@functools.lru_cache(maxsize=1)
def _get_nlp():
    try:
        import spacy
        return spacy.load("it_core_news_md",
                          disable=["parser", "tagger", "morphologizer", "lemmatizer"])
    except Exception:
        return None


def _ner_entities(frase: str) -> dict[str, str]:
    nlp = _get_nlp()
    if nlp is None:
        return {}
    doc = nlp(frase)
    return {ent.text.lower(): ent.label_ for ent in doc.ents}


_PREP_ARG = {
    "parlare":      {"di"},
    "dipendere":    {"da"},
    "pensare":      {"a", "di"},
    "credere":      {"a", "in"},
    "andare":       {"a", "in", "da", "verso"},
    "venire":       {"da"},
    "abitare":      {"a", "in"},
    "vivere":       {"a", "in"},
    "lavorare":     {"a", "in", "per"},
    "aspettare":    {"di"},
    "smettere":     {"di"},
    "cercare":      {"di"},
    "cominciare":   {"a", "di"},
    "iniziare":     {"a"},
    "continuare":   {"a"},
    "riuscire":     {"a"},
    "finire":       {"di"},
    "sperare":      {"di", "in"},
    "occuparsi":    {"di"},
    "interessarsi": {"a", "di"},
    "preoccuparsi": {"di", "per"},
    "accorgersi":   {"di"},
    "fidarsi":      {"di"},
    "trattare":     {"di"},
    "consistere":   {"in"},
}

_PREP_ALMOST_ALWAYS_ARG = {"di", "da"}
_PREP_ALMOST_ALWAYS_ADJ = {"con", "senza", "durante", "dopo", "prima", "tra", "fra"}
_UPOS_ADJ               = {"ADV"}
_NER_LOC                = {"GPE", "LOC"}
_NER_DATIVE             = {"PER", "PERSON", "ORG"}
_PREP_LOC_AMBIGUOUS     = {"a", "in", "su", "verso", "da"}


def _get_case_prep(token_id: int, tokens: list[dict]) -> Optional[str]:
    return next(
        (t["form"].lower() for t in tokens
         if t["deprel"] == "case" and t["head"] == token_id),
        None,
    )


def _surface_form(token_id: int, tokens: list[dict]) -> str:
    tok = next((t for t in tokens if t["id"] == token_id), None)
    if tok is None:
        return "?"

    def _collect_ids(tid: int) -> set[int]:
        ids = {tid}
        for t in tokens:
            if t["head"] == tid and t["deprel"] not in ("punct",):
                ids |= _collect_ids(t["id"])
        return ids

    ids = _collect_ids(token_id)
    subtree = sorted((t for t in tokens if t["id"] in ids), key=lambda t: t["id"])
    return " ".join(t["form"] for t in subtree)


def _heuristic(root_lemma: str, token: dict, tokens: list[dict],
               ner: dict[str, str]) -> tuple[str, str]:
    prep       = _get_case_prep(token["id"], tokens)
    upos       = token.get("upos", "")
    form_lower = token["form"].lower()

    # 1. Casi certi da deprel/upos
    if token["deprel"] == "advmod":
        return "aggiunto", "gli avverbi modificatori sono quasi sempre aggiunti"
    if upos in _UPOS_ADJ:
        return "aggiunto", "elemento avverbiale tipicamente aggiunto"
    if prep is None:
        return "aggiunto", "sintagma obliquo senza preposizione: probabile aggiunto"

    # 2. Preposizioni quasi sempre aggiunte
    if prep in _PREP_ALMOST_ALWAYS_ADJ:
        return "aggiunto", f"la preposizione '{prep}' introduce quasi sempre un aggiunto"

    # 3. NER per preposizioni locative ambigue
    if prep in _PREP_LOC_AMBIGUOUS and ner:
        surface   = _surface_form(token["id"], tokens).lower()
        ner_label = ner.get(form_lower) or ner.get(surface)
        if ner_label in _NER_LOC:
            return "aggiunto", (
                f"'{token['form']}' e' riconosciuto come luogo ({ner_label}): "
                f"con '{prep}' introduce quasi certamente un locativo aggiunto"
            )
        if ner_label in _NER_DATIVE:
            return "argomento", (
                f"'{token['form']}' e' riconosciuto come persona o organizzazione ({ner_label}): "
                f"con '{prep}' introduce probabilmente un dativo argomento"
            )

    # 4. Dizionario verbo + preposizione
    if root_lemma in _PREP_ARG and prep in _PREP_ARG[root_lemma]:
        return "argomento", (
            f"il verbo '{root_lemma}' seleziona tipicamente "
            f"un complemento introdotto da '{prep}'"
        )

    # 5. Preposizioni quasi sempre argomentali
    if prep in _PREP_ALMOST_ALWAYS_ARG:
        return "argomento", (
            f"la preposizione '{prep}' introduce spesso un argomento, "
            f"ma puo' anche introdurre un aggiunto"
        )

    # 6. Default
    return "aggiunto", (
        f"la preposizione '{prep}' introduce tipicamente "
        f"un modificatore locativo, temporale o strumentale"
    )


def _collect_subtree_ids(token_id: int, tokens: list[dict]) -> set[int]:
    """Restituisce tutti gli id del sottoalbero radicato in token_id."""
    ids = {token_id}
    for t in tokens:
        if t["head"] == token_id:
            ids |= _collect_subtree_ids(t["id"], tokens)
    return ids


def _sn_candidates(tokens: list[dict],
                   exclude_ids: set[int] | None = None) -> list[dict]:
    """
    Restituisce i token nominali disponibili come testa SN.
    Esclude la radice e i token in exclude_ids (sottoalbero del sintagma
    ambiguo, per evitare che un nome si proponga come proprio modificatore).
    """
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    root_id = root["id"] if root else -1
    excl = exclude_ids or set()
    return [
        t for t in tokens
        if t["upos"] in ("NOUN", "PROPN", "PRON")
        and t["id"] != root_id
        and t["id"] not in excl
    ]


def detect_ambiguous_adjuncts(tokens: list[dict],
                               frase: str = "") -> list[dict]:
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root:
        return []

    from ud_to_chomsky import is_wh_token

    ner = _ner_entities(frase) if frase else {}
    ambiguous = []

    for t in tokens:
        if t["head"] != root["id"]:
            continue

        deprel = t["deprel"]

        if deprel == "obl":
            if is_wh_token(t):
                continue
            hint, reason = _heuristic(root["lemma"], t, tokens, ner)
            prep = _get_case_prep(t["id"], tokens)
            sn_hint = prep in {"senza", "con", "di", "da", "per"} if prep else False
            # Escludi il sottoalbero del token stesso dai candidati SN
            excl = _collect_subtree_ids(t["id"], tokens)
            candidates = _sn_candidates(tokens, exclude_ids=excl)
            ambiguous.append({
                "token_id":         t["id"],
                "form":             _surface_form(t["id"], tokens),
                "deprel":           deprel,
                "heuristic":        hint,
                "heuristic_reason": reason,
                "role":             None,
                "attach":           None,
                "sn_target":        None,
                "sn_candidates":    [
                    {"token_id": c["id"], "form": c["form"]}
                    for c in candidates
                ],
                "sn_hint":          sn_hint,
            })

        elif deprel == "advmod":
            excl = _collect_subtree_ids(t["id"], tokens)
            candidates = _sn_candidates(tokens, exclude_ids=excl)
            ambiguous.append({
                "token_id":         t["id"],
                "form":             _surface_form(t["id"], tokens),
                "deprel":           deprel,
                "heuristic":        "aggiunto",
                "heuristic_reason": "gli avverbi modificatori sono quasi sempre aggiunti",
                "role":             None,
                "attach":           None,
                "sn_target":        None,
                "sn_candidates":    [
                    {"token_id": c["id"], "form": c["form"]}
                    for c in candidates
                ],
                "sn_hint":          False,
            })

    return ambiguous


def apply_adjunct_choices(adjuncts: list[dict],
                          choices: dict[int, dict]) -> list[dict]:
    result = []
    for a in adjuncts:
        a = dict(a)
        tid = a["token_id"]
        if tid in choices:
            a["role"]      = choices[tid].get("role",      a["heuristic"])
            a["attach"]    = choices[tid].get("attach",    "Sv")
            a["sn_target"] = choices[tid].get("sn_target", None)
        else:
            a["role"]      = a["heuristic"]
            a["attach"]    = "Sv"
            a["sn_target"] = None
        result.append(a)
    return result


def adjuncts_as_dict(adjuncts_with_choices: list[dict]) -> dict[int, dict]:
    return {
        a["token_id"]: {
            "role":      a["role"],
            "attach":    a["attach"],
            "sn_target": a.get("sn_target"),
        }
        for a in adjuncts_with_choices
        if a["role"] is not None
    }
