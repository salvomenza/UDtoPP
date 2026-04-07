# ver. 26.10
"""
ud_to_chomsky.py
Converte una lista di token CoNLL-U in una struttura ad albero chomskiana.

Convenzioni:
- SD invece di NP; little v (Sv); ST invece di IP
- X' eliminata se unico figlio è la testa (no spec, no aggiunto)
- SD → D → nome proprio/pronome (senza NP)
- SD → D' → D + SN → N' → [AP spec +] N (per nomi comuni)
- Passivo: v [+pass], SAsp per participio passivo
- Aggiunti: sdoppiamento XP → XP + YP, con livello scelto dall'utente
- FR con [+wh] per interrogative; movimento wh a spec-CP
- Ditransitivi: struttura larsoneana (oggetto diretto in spec-VP esterno)
- obl/advmod: utente sceglie argomento/aggiunto e livello (SV/Sv/ST/SC/SN)
- SN: aggiunto nominale, sdoppia il SN della testa scelta dall'utente
"""

from dataclasses import dataclass, field
from typing import Optional


# ── Struttura dati ──────────────────────────────────────────────────────────

@dataclass
class Node:
    label: str
    children: list = field(default_factory=list)
    word: Optional[str] = None
    index: Optional[str] = None
    is_trace: bool = False
    is_head: bool = False
    color: Optional[str] = None
    is_copy: bool = False        # copia di movimento — mostrata con { }
    is_pronounced: bool = False  # forma pronunciata — mostrata in grassetto
    movement_type: Optional[str] = None  # "sintagmatico"|"testa"|"soggetto" per frecce
    is_new: bool = False         # nodo nuovo in questo passo — evidenziato

    def __repr__(self):
        if self.word:
            s = f"{self.label}({self.word!r}"
            if self.index: s += f"_{self.index}"
            if self.is_trace: s += " TRACE"
            s += ")"
            return s
        return f"{self.label}[{len(self.children)} figli]"


# ── Colori per indice ────────────────────────────────────────────────────────

INDEX_COLORS = {
    "i": "#c0392b",   # rosso
    "j": "#1a4fa0",   # blu
    "k": "#1a7a2a",   # verde
    "l": "#7a4a00",   # marrone
    "m": "#a0197a",   # fucsia
    "n": "#d46000",   # arancione
}


def color_for(index):
    return INDEX_COLORS.get(index, "#2c1e0f")


# ── Helpers ──────────────────────────────────────────────────────────────────

def children_of(tokens, head_id):
    return [t for t in tokens if t["head"] == head_id]


def is_passive(tokens):
    return any(t["deprel"] == "aux:pass" for t in tokens)


# Verbi che selezionano "essere" (inaccusativi e pseudo-copulativi)
VERBI_MODALI = {
    "volere", "potere", "dovere", "sapere", "riuscire", "osare",
    "solere", "cominciare", "continuare", "smettere", "cessare",
    "iniziare", "finire", "stare",
}

VERBI_INACCUSATIVI = {
    "andare", "venire", "arrivare", "partire", "uscire", "entrare",
    "nascere", "morire", "cadere", "salire", "scendere", "tornare",
    "rimanere", "restare", "diventare", "sembrare", "parere",
    "succedere", "accadere", "avvenire", "risultare", "apparire",
    "comparire", "sparire", "scomparire", "fuggire", "scappare",
    "correre", "passare", "finire", "iniziare", "cominciare",
    "affondare", "esplodere", "crescere", "durare",
}


def is_unaccusative(tokens):
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root:
        return False
    deps = [t["deprel"] for t in children_of(tokens, root["id"])]
    has_obj = "obj" in deps
    has_agent = "obl:agent" in deps
    has_aux = any(t["upos"] == "AUX" for t in children_of(tokens, root["id"]))
    if not has_obj and not has_agent and not has_aux:
        if root["lemma"] in VERBI_INACCUSATIVI:
            return True
    return False


def has_postverbal_subject(tokens):
    """True se il soggetto è postverbale (presentativo)."""
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root:
        return False
    nsubj = next((t for t in tokens
                  if t["deprel"] == "nsubj" and t["head"] == root["id"]), None)
    return nsubj is not None and nsubj["id"] > root["id"]


def is_copular(tokens):
    """True se la frase è copulare: root non-VERB con cop dipendente."""
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root:
        return False
    has_cop = any(t["deprel"] == "cop" and t["head"] == root["id"] for t in tokens)
    return has_cop and root["upos"] != "VERB"


def is_wh_token(token):
    return "PronType=Int" in token.get("feats", "")


# ── Costruzione SC per frase relativa (acl:relcl) ────────────────────────────

def _subtree_tokens(head_id, tokens):
    """
    Restituisce solo i token che appartengono al sottoalbero radicato in head_id,
    inclusa la testa. Usato per isolare i token di una frase relativa.
    """
    def _collect(tid):
        ids = {tid}
        for t in tokens:
            if t["head"] == tid:
                ids |= _collect(t["id"])
        return ids
    ids = _collect(head_id)
    return [t for t in tokens if t["id"] in ids]


def _build_relcl(rel_token, tokens):
    """
    Costruisce una SC per una frase relativa (acl:relcl) — analisi con
    operatore (Donati/GB). Usa solo i token del sottoalbero della relativa.

    Tre casi:
    1. "che" soggetto: OP_k in spec-Sv → spec-ST → spec-SC; C°=che
    2. "che" oggetto:  OP_k in compl-V → spec-SC; C°=che
    3. Pronome obl ("a cui"): SP(a cui)_k in compl-SV → spec-SC; C°=∅
       Struttura interna larsoneana: agente spec-Sv, oggetto spec-SV est.,
       compl. termine compl-SV int.
    """
    rel_color  = "#5a3a7a"
    rel_v_idx  = "l"   # indice verbale della relativa — separato da "i" della principale
    rel_v_color = color_for(rel_v_idx)

    # Filtra i token al solo sottoalbero della relativa
    rel_tokens = _subtree_tokens(rel_token["id"], tokens)

    rel_pron = next(
        (t for t in rel_tokens
         if t["head"] == rel_token["id"]
         and "PronType=Rel" in t.get("feats", "")),
        None
    )
    aux_rel = next(
        (t for t in rel_tokens
         if t["head"] == rel_token["id"]
         and t["deprel"] in ("aux", "aux:pass")
         and t["lemma"] in ("avere", "essere")),
        None
    )
    # obj_rel: oggetto lessicale vero — esclude il pronome relativo stesso
    rel_pron_id = rel_pron["id"] if rel_pron else -1
    obj_rel = next(
        (t for t in rel_tokens
         if t["head"] == rel_token["id"]
         and t["deprel"] == "obj"
         and t["id"] != rel_pron_id),
        None
    )
    # Soggetto esplicito della relativa (diverso dal pronome relativo)
    subj_rel = next(
        (t for t in rel_tokens
         if t["head"] == rel_token["id"]
         and t["deprel"] in ("nsubj", "nsubj:pass")
         and t["id"] != rel_pron_id),
        None
    )

    is_subj_rel = (rel_pron is not None
                   and rel_pron["deprel"] in ("nsubj", "nsubj:pass"))
    is_obl_rel  = (rel_pron is not None
                   and rel_pron["deprel"] in ("obl", "iobj"))

    case_rel = None
    if is_obl_rel:
        case_rel = next(
            (t for t in rel_tokens
             if t["deprel"] == "case" and t["head"] == rel_pron["id"]),
            None
        )

    # ── Helper: costruisce spec-Sv (soggetto esplicito o pro silenzioso) ────
    def _build_rel_subj():
        if subj_rel:
            return build_dp(subj_rel, rel_tokens)
        else:
            pro_ag = Node("SD", color="#2c1e0f")
            pro_d  = Node("D", is_head=True, color="#2c1e0f")
            pro_d.children = [Node("pro", word="pro", is_head=True,
                                   color="#2c1e0f", is_pronounced=False)]
            pro_ag.children = [pro_d]
            return pro_ag

    # ── Testa verbale: traccia t_l in V (sale a T o Asp) ────────────────────
    v_rel = Node("V", is_head=True, color=rel_v_color)
    v_rel.children = [Node("t", word="t", index=rel_v_idx, is_trace=True,
                           is_head=True, color=rel_v_color)]

    # ── Costruisce la struttura verbale interna ──────────────────────────────

    if is_obl_rel:
        # Struttura larsoneana:
        # Sv → {t_k agente} + v'(v + SV_est)
        # SV_est → SD(obj) + V'(V_int + SV_int)
        # SV_int → V(t_l) + SP({t_k compl.termine})
        t_obl = Node("t", word="t", index="k", is_trace=True,
                     is_head=True, color=rel_color)

        # SV interno: V + traccia complemento di termine
        v_inner = Node("V", is_head=True, color=rel_v_color)
        v_inner.children = [Node("t", word="t", index=rel_v_idx, is_trace=True,
                                 is_head=True, color=rel_v_color)]
        sv_inner = Node("SV", color="#2c1e0f")
        sv_inner.children = [v_inner, t_obl]

        # V' esterno
        v_prime_ext = Node("V'", color="#2c1e0f")
        v_prime_ext.children = [v_rel, sv_inner]

        # SV esterno: SD(obj) in spec + V'
        sv_ext = Node("SV", color="#2c1e0f")
        if obj_rel:
            obj_dp = build_dp(obj_rel, rel_tokens)
            sv_ext.children = [obj_dp, v_prime_ext]
        else:
            sv_ext.children = [v_prime_ext]

        # v° con traccia verbale t_l
        v_little = Node("v", is_head=True, color=rel_v_color)
        v_little.children = [Node("t", word="t", index=rel_v_idx, is_trace=True,
                                  is_head=True, color=rel_v_color)]
        v_prime_rel_node = Node("v'", color="#2c1e0f")
        v_prime_rel_node.children = [v_little, sv_ext]

        # Sv: soggetto (esplicito o pro silenzioso) in spec-Sv
        sv_shell = Node("Sv", color="#2c1e0f")
        sv_shell.children = [_build_rel_subj(), v_prime_rel_node]

    elif is_subj_rel:
        # "che" soggetto: traccia {t_k} in spec-Sv
        t_sv = Node("t", word="t", index="k", is_trace=True,
                    is_head=True, color=rel_color)
        sv = Node("SV", color="#2c1e0f")
        if obj_rel:
            sv.children = [v_rel, build_dp(obj_rel, rel_tokens)]
        else:
            sv.children = [v_rel]
        v_little = Node("v", is_head=True, color=rel_v_color)
        v_little.children = [Node("t", word="t", index=rel_v_idx, is_trace=True,
                                  is_head=True, color=rel_v_color)]
        v_prime_rel_node = Node("v'", color="#2c1e0f")
        v_prime_rel_node.children = [v_little, sv]
        sv_shell = Node("Sv", color="#2c1e0f")
        sv_shell.children = [t_sv, v_prime_rel_node]

    else:
        # "che" oggetto: traccia {t_k} in posizione oggetto di V
        # Sv → SD(soggetto) + v'(v + SV(V + {t_k}))
        t_obj = Node("t", word="t", index="k", is_trace=True,
                     is_head=True, color=rel_color)
        sv = Node("SV", color="#2c1e0f")
        sv.children = [v_rel, t_obj]

        v_little = Node("v", is_head=True, color=rel_v_color)
        v_little.children = [Node("t", word="t", index=rel_v_idx, is_trace=True,
                                  is_head=True, color=rel_v_color)]
        v_prime_rel_node = Node("v'", color="#2c1e0f")
        v_prime_rel_node.children = [v_little, sv]

        sv_shell = Node("Sv", color="#2c1e0f")
        sv_shell.children = [_build_rel_subj(), v_prime_rel_node]

    # ── T' e ST ──────────────────────────────────────────────────────────────
    t_rel = Node("T", is_head=True, color=rel_v_color)
    if aux_rel:
        # Con ausiliare: T = ausiliare, Asp = participio pronunciato
        t_rel.children = [Node(aux_rel["form"], word=aux_rel["form"],
                               is_head=True, color="#2c1e0f")]
        asp_rel = Node("SAsp", color="#2c1e0f")
        asp_head = Node("Asp", is_head=True, color=rel_v_color)
        asp_word = Node(rel_token["form"], word=rel_token["form"],
                        index=rel_v_idx, is_head=True, color=rel_v_color,
                        is_pronounced=True)
        asp_head.children = [asp_word]
        asp_rel.children = [asp_head, sv_shell]
        t_prime_rel = Node("T'", color="#2c1e0f")
        t_prime_rel.children = [t_rel, asp_rel]
    else:
        # Senza ausiliare: T = forma verbale pronunciata con indice l
        t_rel.children = [Node(rel_token["form"], word=rel_token["form"],
                               index=rel_v_idx, is_head=True, color=rel_v_color,
                               is_pronounced=True)]
        t_prime_rel = Node("T'", color="#2c1e0f")
        t_prime_rel.children = [t_rel, sv_shell]

    st = Node("ST", color="#2c1e0f")
    if is_subj_rel:
        t_st = Node("t", word="t", index="k", is_trace=True,
                    is_head=True, color=rel_color)
        st.children = [t_st, t_prime_rel]
    else:
        st.children = [t_prime_rel]

    # ── spec-SC: OP o SP pieno ────────────────────────────────────────────────
    sc = Node("SC", color="#2c1e0f")

    if is_obl_rel and rel_pron and case_rel:
        # SP(a cui) in spec-SC, C°=∅
        sp_rel = Node("SP", index="k", color=rel_color)
        p_rel  = Node("P", is_head=True, color=rel_color)
        p_rel.children = [Node(case_rel["form"], word=case_rel["form"],
                               is_head=True, color=rel_color)]
        dp_cui = Node("SD", color=rel_color)
        d_cui  = Node("D", is_head=True, color=rel_color)
        d_cui.children = [Node(rel_pron["form"], word=rel_pron["form"],
                               index="k", is_head=True, color=rel_color,
                               is_pronounced=True)]
        dp_cui.children = [d_cui]
        p_prime = Node("P'", color=rel_color)
        p_prime.children = [p_rel, dp_cui]
        sp_rel.children = [p_prime]
        sp_rel.movement_type = "sintagmatico"

        c_node = Node("C", is_head=True, color="#2c1e0f")
        c_node.children = [Node("∅", word="∅", is_head=True, color="#2c1e0f")]
        c_prime = Node("C'", color="#2c1e0f")
        c_prime.children = [c_node, st]
        sc.children = [sp_rel, c_prime]

    else:
        # OP nullo in spec-SC, C°=che
        c_form = rel_pron["form"] if rel_pron else "che"
        op_node = Node("OP", word="OP", index="k",
                       is_head=True, color=rel_color,
                       is_pronounced=True,
                       movement_type="sintagmatico")

        c_node = Node("C", is_head=True, color="#2c1e0f")
        c_node.children = [Node(c_form, word=c_form,
                                is_head=True, color="#2c1e0f")]
        c_prime = Node("C'", color="#2c1e0f")
        c_prime.children = [c_node, st]
        sc.children = [op_node, c_prime]

    return sc


# ── Costruzione SD ───────────────────────────────────────────────────────────

def build_dp(noun_token, tokens, index=None, is_trace=False, color=None):
    dp_color = color or (color_for(index) if index else "#2c1e0f")

    if is_trace:
        t_node = Node("t", word="t", index=index, is_trace=True,
                      is_head=True, color=dp_color)
        return t_node

    # Token fittizio per traccia clitico (id negativo)
    if noun_token.get("id", 0) < 0:
        idx = None
        for f in noun_token.get("feats", "").split("|"):
            if f.startswith("Index="):
                idx = f.split("=")[1]
        idx = idx or index or "k"
        t_node = Node("t", word="t", index=idx, is_trace=True,
                      is_head=True, color=color_for(idx))
        return t_node

    det_token = next(
        (t for t in tokens
         if t["head"] == noun_token["id"] and t["deprel"] == "det"),
        None
    )
    poss_token = next(
        (t for t in tokens
         if t["head"] == noun_token["id"] and t["deprel"] == "det:poss"),
        None
    )

    dp = Node("SD", index=index, color=dp_color)

    if noun_token["upos"] in ("PROPN", "PRON"):
        d = Node("D", is_head=True, color=dp_color)
        word = Node(noun_token["form"], word=noun_token["form"],
                    index=index, is_head=True, color=dp_color)
        d.children = [word]
        dp.children = [d]

    else:
        # ── Costruzione del nucleo N' ────────────────────────────────────────
        n = Node("N", is_head=True, color="#2c1e0f")
        n_word = Node(noun_token["form"], word=noun_token["form"],
                      is_head=True, color="#2c1e0f")
        n.children = [n_word]

        n_prime = Node("N'", color="#2c1e0f")

        if poss_token:
            # Possessivo come spec di N': N' → SA(poss) + N
            ap_poss = Node("SA", color="#2c1e0f")
            ap_poss_word = Node(poss_token["form"], word=poss_token["form"],
                                is_head=True, color="#2c1e0f")
            ap_poss.children = [ap_poss_word]
            n_prime.children = [ap_poss, n]
        else:
            n_prime.children = [n]

        # SN iniziale contiene solo N'
        np = Node("SN", color="#2c1e0f")
        np.children = [n_prime]

        # ── Raccoglie tutti gli aggiunti nominali in ordine lineare ──────────
        # Aggiunti prenominali (id < noun_token["id"]): amod, nummod
        # Aggiunti postnominali (id > noun_token["id"]): amod, nmod, appos, acl:relcl
        noun_id = noun_token["id"]

        pre_modifiers  = []  # (token, tipo) id < noun_id → vanno a sinistra di SN
        post_modifiers = []  # (token, tipo) id > noun_id → vanno a destra di SN

        for t in tokens:
            if t["head"] != noun_id:
                continue
            dep = t["deprel"]
            if dep in ("det", "det:poss", "case", "punct", "cc", "conj"):
                continue  # già gestiti o irrilevanti
            if dep in ("amod", "nummod"):
                if t["id"] < noun_id:
                    pre_modifiers.append((t, "amod"))
                else:
                    post_modifiers.append((t, "amod"))
            elif dep == "advmod":
                # Avverbio focalizzatore: sdoppiamento SD esterno (gestito dopo)
                pre_modifiers.append((t, "advmod")) if t["id"] < noun_id \
                    else post_modifiers.append((t, "advmod"))
            elif dep == "nmod":
                post_modifiers.append((t, "nmod"))
            elif dep == "appos":
                post_modifiers.append((t, "appos"))
            elif dep == "acl:relcl":
                post_modifiers.append((t, "acl:relcl"))

        # Ordina per posizione lineare
        pre_modifiers.sort(key=lambda x: x[0]["id"])
        post_modifiers.sort(key=lambda x: x[0]["id"])

        # ── Prenominali: sdoppiamento SN a sinistra (più vicino al nome = più interno)
        # Invertiamo l'ordine: il più vicino al nome entra per primo (più interno)
        for (mod_t, mod_type) in reversed(pre_modifiers):
            if mod_type == "advmod":
                continue  # gestito come sdoppiamento SD esterno, non SN
            sa = Node("SA", color="#2c1e0f")
            a_node = Node("A", is_head=True, color="#2c1e0f")
            a_word = Node(mod_t["form"], word=mod_t["form"],
                          is_head=True, color="#2c1e0f")
            a_node.children = [a_word]
            sa.children = [a_node]
            outer = Node("SN", color="#2c1e0f")
            outer.children = [sa, np]
            np = outer

        # ── Postnominali: sdoppiamento SN a destra
        for (mod_t, mod_type) in post_modifiers:
            if mod_type == "amod":
                sa = Node("SA", color="#2c1e0f")
                a_node = Node("A", is_head=True, color="#2c1e0f")
                a_word = Node(mod_t["form"], word=mod_t["form"],
                              is_head=True, color="#2c1e0f")
                a_node.children = [a_word]
                sa.children = [a_node]
                xp = sa

            elif mod_type == "nmod":
                case_t = next(
                    (t for t in tokens
                     if t["deprel"] == "case" and t["head"] == mod_t["id"]),
                    None
                )
                # Gestisce anche acl:relcl dipendente dall'nmod
                xp = build_pp(case_t, mod_t, tokens) if case_t else build_dp(mod_t, tokens)

            elif mod_type == "appos":
                xp = build_dp(mod_t, tokens)

            elif mod_type == "acl:relcl":
                # Frase relativa: SC con C(∅) e ST interno (semplificato)
                xp = _build_relcl(mod_t, tokens)

            else:
                continue

            outer = Node("SN", color="#2c1e0f")
            outer.children = [np, xp]   # XP a destra
            np = outer

        # ── Assembla SD ──────────────────────────────────────────────────────
        if det_token:
            d = Node("D", is_head=True, color="#2c1e0f")
            d_word = Node(det_token["form"], word=det_token["form"],
                          is_head=True, color="#2c1e0f")
            d.children = [d_word]
            if poss_token:
                # Con possessivo: D' necessaria
                d_prime = Node("D'", color=dp_color)
                d_prime.children = [d, np]
                dp.children = [d_prime]
            else:
                dp.children = [d, np]
        else:
            # Senza determinante: D(∅)
            d = Node("D", is_head=True, color="#2c1e0f")
            d_word = Node("∅", word="∅", is_head=True, color="#2c1e0f")
            d.children = [d_word]
            dp.children = [d, np]

        # ── Sdoppiamento SD per avverbi focalizzatori (es. "soprattutto") ────
        # SD_est → SAvv + SD_int  (a sinistra del SD completo)
        adv_mods = sorted(
            [(t, typ) for (t, typ) in pre_modifiers + post_modifiers
             if typ == "advmod"],
            key=lambda x: x[0]["id"]
        )
        for (adv_t, _) in adv_mods:
            savv = build_advp(adv_t)
            outer_dp = Node("SD", color=dp_color)
            if adv_t["id"] < noun_id:
                outer_dp.children = [savv, dp]   # SAvv a sinistra
            else:
                outer_dp.children = [dp, savv]   # SAvv a destra (raro)
            dp = outer_dp

    return dp


# ── Costruzione SP ───────────────────────────────────────────────────────────

def build_pp(case_token, noun_token, tokens, index=None, is_trace=False, color=None):
    pp_color = color or (color_for(index) if index else "#2c1e0f")

    if is_trace:
        t = Node("t", word="t", index=index, is_trace=True,
                 is_head=True, color=pp_color)
        return t

    pp = Node("SP", index=index, color=pp_color)
    p_prime = Node("P'", color=pp_color)
    p = Node("P", is_head=True, color=pp_color)
    p_word = Node(case_token["form"], word=case_token["form"],
                  is_head=True, color=pp_color)
    p.children = [p_word]
    dp = build_dp(noun_token, tokens, color="#2c1e0f")
    p_prime.children = [p, dp]
    pp.children = [p_prime]
    return pp


# ── Costruzione SAvv ─────────────────────────────────────────────────────────

def build_advp(adv_token):
    advp = Node("SAvv")
    adv = Node("Adv", is_head=True)
    adv_word = Node(adv_token["form"], word=adv_token["form"], is_head=True)
    adv.children = [adv_word]
    advp.children = [adv]
    return advp


# ── Costruzione FR (Small Clause) ───────────────────────────────────────────

def build_sc(subj_index, pred_token, tokens):
    """
    Costruisce FR → SD(t_j) + XP
    XP può essere SD (nome), SA (aggettivo), SP (preposizione)
    """
    sc = Node("FR")
    subj_color = color_for(subj_index)

    # traccia del soggetto in spec-SC: t_j diretto, senza etichetta DP
    t_subj = Node("t", word="t", index=subj_index, is_trace=True,
                  is_head=True, color=subj_color)

    # predicato
    upos = pred_token["upos"]
    if upos == "ADJ":
        # SA → A → word
        ap = Node("SA")
        a = Node("A", is_head=True)
        a_word = Node(pred_token["form"], word=pred_token["form"], is_head=True)
        a.children = [a_word]
        ap.children = [a]
        pred_xp = ap
    elif upos in ("NOUN", "PROPN", "PRON"):
        # DP
        pred_xp = build_dp(pred_token, tokens)
    else:
        # fallback: XP generico
        xp = Node("XP")
        x = Node("X", is_head=True)
        x_word = Node(pred_token["form"], word=pred_token["form"], is_head=True)
        x.children = [x_word]
        xp.children = [x]
        pred_xp = xp

    sc.children = [t_subj, pred_xp]
    return sc



# ── Costruzione nodo pro/PRO ─────────────────────────────────────────────────

def build_pro_node(pro_type, index=None, color=None):
    """
    Costruisce un nodo SD per pro/PRO.
    pro_type: 'pro', 'pro_espl', 'PRO', 'PRO_arb'
    pro/PRO sono elementi silenziosi: is_pronounced=False.
    Il movement_type viene assegnato qui direttamente perché
    annotate_movements non deve trattarli come nodi pronunciati.
    """
    dp_color = color or (color_for(index) if index else "#5a4a3a")
    dp = Node("SD", index=index, color=dp_color)
    # Solo pro referenziale (non pro_espl, PRO_arb) si muove da spec-Sv a spec-ST
    if index is not None and pro_type == "pro":
        dp.movement_type = "soggetto"
    d = Node("D", is_head=True, color=dp_color)
    word = Node(pro_type, word=pro_type, index=index,
                is_head=True, color=dp_color, is_trace=False,
                is_pronounced=False)  # silenzioso: non ha forma fonetica
    d.children = [word]
    dp.children = [d]
    return dp


# ── Rilevamento e aggiunta di pro/PRO ai token ───────────────────────────────

def _get_feats(token):
    """Estrae il campo feats come stringa."""
    return token.get("feats", "") or ""


def _person(token):
    feats = _get_feats(token)
    for f in feats.split("|"):
        if f.startswith("Person="):
            return f.split("=")[1]
    return None


def _number(token):
    feats = _get_feats(token)
    for f in feats.split("|"):
        if f.startswith("Number="):
            return f.split("=")[1]
    return None


def _verbform(token):
    feats = _get_feats(token)
    for f in feats.split("|"):
        if f.startswith("VerbForm="):
            return f.split("=")[1]
    return None


def _mood(token):
    feats = _get_feats(token)
    for f in feats.split("|"):
        if f.startswith("Mood="):
            return f.split("=")[1]
    return None


def enrich_with_silent_subjects(tokens):
    """
    Aggiunge token sintetici per pro/PRO mancanti.
    Restituisce una lista di token arricchita + dizionario
    {token_id: Node} per i nodi silenziosi già costruiti.
    """
    silent_nodes = {}  # root_id → Node SD(pro/PRO)

    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root:
        return tokens, silent_nodes

    # ── 1. pro/pro_espl in frase finita ─────────────────────────────────────
    has_nsubj = any(t["deprel"] in ("nsubj", "nsubj:pass")
                    and t["head"] == root["id"] for t in tokens)

    # La frase è finita se il root è finito OPPURE ha un ausiliare/modale finito
    aux_finite = any(
        t["head"] == root["id"]
        and _mood(t) in ("Ind", "Sub", "Cnd", "Imp")
        for t in tokens
        if t["upos"] in ("AUX", "VERB")
    )
    root_finite = _mood(root) in ("Ind", "Sub", "Cnd", "Imp")

    if not has_nsubj and (root_finite or aux_finite):
        # Determina il tipo:
        # pro_espl: verbi meteorologici (piove, nevica, ecc.) o
        #           inaccusativi presentativi (arriva un treno)
        #           = nessun obj, nessun obl:agent, nessun nsubj, ma c'è un
        #             SD postverbale identificabile come "soggetto logico"
        is_weather = root["lemma"] in (
            "piovere", "nevicare", "grandinare", "tuonare",
            "lampeggiare", "diluviare", "pioviggare"
        )
        has_obj = any(t["deprel"] == "obj" and t["head"] == root["id"]
                      for t in tokens)
        # inaccusativo presentativo: c'è un nsubj postverbale oppure un
        # SD che funge da soggetto logico (UDPipe spesso lo analizza come
        # nsubj comunque, ma per sicurezza controlliamo)
        is_presentative = (not has_obj and not is_weather
                           and root["upos"] == "VERB"
                           and _verbform(root) == "Fin")

        if is_weather or is_presentative:
            pro_type = "pro_espl"
        else:
            pro_type = "pro"

        node = build_pro_node(pro_type, index="j", color=color_for("j"))
        silent_nodes[root["id"]] = ("subj", node, pro_type)

    # ── 2. PRO / PRO_arb per verbi all'infinito ─────────────────────────────
    for t in tokens:
        if _verbform(t) != "Inf":
            continue
        if t["deprel"] == "root":
            # Soggettiva infinitiva: PRO_arb
            # MA non se c'è un modale finito (es. "voglio andare" → pro, non PRO_arb)
            has_nsubj_inf = any(tk["deprel"] == "nsubj"
                                and tk["head"] == t["id"] for tk in tokens)
            has_modal = any(
                tk["head"] == t["id"]
                and _mood(tk) in ("Ind", "Sub", "Cnd", "Imp")
                for tk in tokens
            )
            if not has_nsubj_inf and not has_modal:
                node = build_pro_node("PRO_arb", index="j",
                                      color=color_for("j"))
                silent_nodes[t["id"]] = ("subj", node, "PRO_arb")
        else:
            # Infinito dipendente: cerca controllore
            has_nsubj_inf = any(tk["deprel"] in ("nsubj", "nsubj:pass")
                                and tk["head"] == t["id"] for tk in tokens)
            if has_nsubj_inf:
                continue
            # Cerca controllore: il soggetto della frase matrice
            matrix_root_id = t["head"]
            controller = next(
                (tk for tk in tokens
                 if tk["deprel"] in ("nsubj", "nsubj:pass")
                 and tk["head"] == matrix_root_id),
                None
            )
            if controller:
                # Controllore esplicito (es. Maria vuole uscire → PRO_j)
                pro_type = "PRO"
                pro_index = "j"   # stesso indice del soggetto matrice
            else:
                # Nessun soggetto esplicito: il controllore è pro stesso
                # (es. vuole uscire → pro_j vuole [PRO_j uscire])
                # Non è PRO_arb — è comunque controllato da pro_j
                pro_type = "PRO"
                pro_index = "j"
            node = build_pro_node(pro_type, index=pro_index,
                                  color=color_for(pro_index))
            silent_nodes[t["id"]] = ("subj", node, pro_type)

    return tokens, silent_nodes


# ── Rilevamento clitici ───────────────────────────────────────────────────────

def get_clitic_tokens(tokens, head_id):
    """
    Restituisce i token clitici (accusativo/riflessivo) dipendenti da head_id.
    UDPipe marca i clitici come:
      - obj / expl:pv  con upos=PRON e posizione preverbale
      - expl:refl      per riflessivi
    """
    clitics = []
    for t in tokens:
        if t["head"] != head_id:
            continue
        if t["upos"] != "PRON":
            continue
        deprel = t["deprel"]
        feats = _get_feats(t)
        # clitico accusativo: obj o iobj con forma breve
        if deprel in ("obj", "iobj", "expl:pv"):
            if "Clitic=Yes" in feats or t["form"].lower() in (
                    "lo", "la", "li", "le", "mi", "ti", "ci", "vi",
                    "gli", "ne", "me", "te", "ce", "ve", "glielo",
                    "gliela", "glieli", "gliele"):
                clitics.append(("acc", t))
        # riflessivo
        elif deprel in ("expl:refl", "expl"):
            clitics.append(("refl", t))
    return clitics


# ── Costruzione SV ───────────────────────────────────────────────────────────

def build_vp(verb_token, tokens, verb_index="i", obj_token=None,
             wh_pp=None, verb_is_trace=False, xcomp_node=None):
    vp = Node("SV")
    v_color = color_for(verb_index)

    v = Node("V", is_head=True, color=v_color)
    if verb_is_trace:
        t = Node("t", word="t", index=verb_index, is_trace=True,
                 is_head=True, color=v_color)
        v.children = [t]
    else:
        v_word = Node(verb_token["form"], word=verb_token["form"],
                      index=verb_index, is_head=True, color=v_color)
        v.children = [v_word]

    if wh_pp is not None:
        vp.children = [v, wh_pp]
    elif obj_token:
        obj_dp = build_dp(obj_token, tokens)
        vp.children = [v, obj_dp]
    elif xcomp_node is not None:
        vp.children = [v, xcomp_node]
    else:
        vp.children = [v]

    return vp


# ── Costruzione Sv shell ──────────────────────────────────────────────────────

def build_vp_shell(verb_token, tokens, subj_token, obj_token,
                   verb_index="i", subj_index="j", passive=False,
                   wh_index=None, wh_case_token=None, wh_noun_token=None,
                   has_aux=False,
                   cl_acc=None, cl_refl=None, cl_index="k",
                   has_clitic_obj=False, has_clitic_refl=False,
                   xcomp_node=None):
    _xcomp_node = xcomp_node  # passato a build_vp nel ramo else
    v_color = color_for(verb_index)
    subj_color = color_for(subj_index)
    cl_color = color_for(cl_index)

    larsonian = (wh_index is not None and wh_case_token is not None
                 and obj_token is not None and not has_clitic_obj)

    if larsonian:
        wh_trace_pp = build_pp(wh_case_token, wh_noun_token, tokens,
                               index=wh_index, is_trace=True,
                               color=color_for(wh_index))
        inner_vp = build_vp(verb_token, tokens, verb_index=verb_index,
                            wh_pp=wh_trace_pp, verb_is_trace=True)
        v_inner = Node("V", is_head=True, color=v_color)
        t_v = Node("t", word="t", index=verb_index, is_trace=True,
                   is_head=True, color=v_color)
        v_inner.children = [t_v]
        v_prime_outer = Node("V'")
        v_prime_outer.children = [v_inner, inner_vp]
        obj_dp = build_dp(obj_token, tokens)
        outer_vp = Node("SV")
        outer_vp.children = [obj_dp, v_prime_outer]

    elif has_clitic_obj:
        # Clitico acc: traccia t_k in posizione oggetto
        t_cl = Node("t", word="t", index=cl_index, is_trace=True,
                    is_head=True, color=cl_color)
        vp_with_trace = Node("SV")
        v_node = Node("V", is_head=True, color=v_color)
        v_node.children = [Node("t", word="t", index=verb_index, is_trace=True,
                                is_head=True, color=v_color)]
        vp_with_trace.children = [v_node, t_cl]
        outer_vp = vp_with_trace

    elif has_clitic_refl:
        # Riflessivo: traccia t_k in posizione oggetto
        t_cl = Node("t", word="t", index=cl_index, is_trace=True,
                    is_head=True, color=cl_color)
        vp_with_trace = Node("SV")
        v_node = Node("V", is_head=True, color=v_color)
        v_node.children = [Node("t", word="t", index=verb_index, is_trace=True,
                                is_head=True, color=v_color)]
        vp_with_trace.children = [v_node, t_cl]
        outer_vp = vp_with_trace

    else:
        outer_vp = build_vp(verb_token, tokens, verb_index=verb_index,
                            obj_token=obj_token, verb_is_trace=True,
                            xcomp_node=_xcomp_node)

    # Costruzione v con eventuale clitico incorporato
    v_little = Node("v", is_head=True,
                    color=v_color if not passive else "#2c1e0f")
    if passive:
        v_word = Node("[+pass]", word="[+pass]", is_head=True, color="#2c1e0f")
    elif has_clitic_obj and cl_acc:
        cl_form = cl_acc["form"]
        if has_aux:
            v_label = f"{cl_form}+{verb_token['form']}"
        else:
            v_label = f"{cl_form}+t_{verb_index}"
        v_word = Node(v_label, word=v_label, index=cl_index,
                      is_head=True, color=cl_color)
    elif has_clitic_refl and cl_refl:
        cl_form = cl_refl["form"]
        if has_aux:
            v_label = f"{cl_form}+{verb_token['form']}"
        else:
            v_label = f"{cl_form}+t_{verb_index}"
        v_word = Node(v_label, word=v_label, index=cl_index,
                      is_head=True, color=cl_color)
    elif has_aux:
        # Il participio sale a Asp, non resta in v°: v° contiene la traccia t_i
        v_word = Node("t", word="t", index=verb_index, is_trace=True,
                      is_head=True, color=v_color)
    else:
        v_word = Node("t", word="t", index=verb_index, is_trace=True,
                      is_head=True, color=v_color)
    v_little.children = [v_word]

    v_prime = Node("v'")
    v_prime.children = [v_little, outer_vp]

    vp = Node("Sv")
    if passive:
        vp.children = [v_prime]
    else:
        t_subj = build_dp(subj_token, tokens, index=subj_index,
                          is_trace=True, color=subj_color) if subj_token else None
        if t_subj:
            vp.children = [t_subj, v_prime]
        else:
            vp.children = [v_prime]

    return vp


# ── Avvolgi in FR ────────────────────────────────────────────────────────────

def wrap_cp(tp, wh_xp):
    cp = Node("SC")
    c_prime = Node("C'")
    c = Node("C", is_head=True)
    c_word = Node("[+wh]", word="[+wh]", is_head=True)
    c.children = [c_word]
    c_prime.children = [c, tp]
    cp.children = [wh_xp, c_prime]
    return cp



# ── Costruzione SV con complemento xcomp (infinito) ─────────────────────────

def build_xcomp_vp(verb_token_id, xcomp_token, tokens,
                   verb_index="i", silent_nodes=None):
    """
    Costruisce ST_inf (o SV_inf) per un complemento xcomp infinito.
    verb_token_id: ignorato, tenuto per compatibilità firma.
    silent_nodes: dizionario {token_id: ("subj", Node, tipo)} per pro/PRO.
    """
    v_color = color_for(verb_index)
    xcomp_index = "l"  # indice separato per il verbo infinito
    xcomp_color = color_for(xcomp_index)

    # SV infinito: solo V (intransitivo) o V + obj se xcomp ha obj
    xcomp_obj = next(
        (t for t in tokens if t["deprel"] == "obj" and t["head"] == xcomp_token["id"]),
        None
    )
    inner_vp = Node("SV")
    v_inf = Node("V", is_head=True, color=xcomp_color)
    v_inf_word = Node(xcomp_token["form"], word=xcomp_token["form"],
                      index=xcomp_index, is_head=True, color=xcomp_color)
    v_inf.children = [v_inf_word]
    if xcomp_obj:
        obj_dp = build_dp(xcomp_obj, tokens)
        inner_vp.children = [v_inf, obj_dp]
    else:
        inner_vp.children = [v_inf]

    # PRO soggetto dell'infinito
    pro_node = None
    if silent_nodes and xcomp_token["id"] in silent_nodes:
        _, pro_node, _ = silent_nodes[xcomp_token["id"]]

    # Sv dell'infinito: se c'è PRO → Sv → PRO + v'(V+t) + SV
    # Per semplicità: ST_inf ridotto → PRO + T'(T[Inf] + SV)
    if pro_node:
        t_inf = Node("T", is_head=True, color=xcomp_color)
        t_inf_word = Node("[Inf]", word="[Inf]", is_head=True, color=xcomp_color)
        t_inf.children = [t_inf_word]
        t_prime_inf = Node("T'")
        t_prime_inf.children = [t_inf, inner_vp]
        st_inf = Node("ST")
        st_inf.children = [pro_node, t_prime_inf]
        return st_inf
    else:
        return inner_vp


# ── Post-processing: elimina proiezioni intermedie con figlio unico ──────────

def prune_single_child_bars(node):
    """
    Post-order: applica la regola X-barra in modo uniforme.

    Regola unica: X' con figlio unico → collassa X'.
    Le proiezioni massimali (SN, SA, SAvv, SD, SP, ecc.) non vengono
    mai collassate — hanno valore strutturale indipendente.
    """
    # Ricorsione prima (bottom-up)
    node.children = [prune_single_child_bars(c) for c in node.children]

    # Regola: XP → X' (figlio unico intermedio) → collassa X'
    if (len(node.children) == 1 and
            node.children[0].label.endswith("'") and
            not node.children[0].label.endswith("''") and
            node.children[0].word is None):
        node.children = node.children[0].children

    return node

# ── Costruzione ST (punto di ingresso) ───────────────────────────────────────

def build_tp(tokens, tipo_verbo=None, adjunct_choices=None):
    """
    adjunct_choices: dict {token_id: {"role": "argomento"|"aggiunto",
                                       "attach": "SV"|"Sv"|"ST"|"SC"|"SN",
                                       "sn_target": int|None}}
    Se attach=="SN", sn_target indica il token_id del nome a cui agganciare
    l'aggiunto come sdoppiamento di SN.
    Se None o vuoto, comportamento identico alla ver. 24.
    """
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root:
        raise ValueError("Nessun token root trovato")

    # Correzione tipo_verbo PRIMA di enrich (così pro viene aggiunto correttamente)
    if tipo_verbo == "transitivo":
        for t in tokens:
            if (t["deprel"] == "nsubj" and t["head"] == root["id"]
                    and t["id"] > root["id"]):
                t["deprel"] = "obj"
                break

    # Arricchimento con pro/PRO
    tokens, silent_nodes = enrich_with_silent_subjects(tokens)

    passive = is_passive(tokens)
    copular = is_copular(tokens)
    # Rilevamento clitici anticipato (serve per is_unaccusative)
    _clitics_pre = get_clitic_tokens(tokens, root["id"])
    _has_refl_pre = any(typ == "refl" for typ, _ in _clitics_pre)
    _unacc_auto = is_unaccusative(tokens) and not _has_refl_pre

    if tipo_verbo == "transitivo":
        unaccusative = False
    elif tipo_verbo == "inaccusativo":
        unaccusative = True
    elif tipo_verbo == "inergativo":
        unaccusative = False
    else:
        unaccusative = _unacc_auto

    subj_token = next(
        (t for t in tokens
         if t["deprel"] in ("nsubj", "nsubj:pass") and t["head"] == root["id"]),
        None
    )
    # nodo pro/PRO se soggetto esplicito assente
    silent_subj_node = None
    if not subj_token and root["id"] in silent_nodes:
        _, silent_subj_node, _ = silent_nodes[root["id"]]

    # Rilevamento clitici (prima di obj_token, per escluderli)
    clitics = get_clitic_tokens(tokens, root["id"])
    cl_acc  = next((t for typ, t in clitics if typ == "acc"), None)
    cl_refl = next((t for typ, t in clitics if typ == "refl"), None)
    cl_index = "k"
    # cl_ids: id dei token clitici, da escludere da obj_token
    cl_ids = {t["id"] for _, t in clitics}

    obj_token = next(
        (t for t in tokens
         if t["deprel"] == "obj" and t["head"] == root["id"]
         and t["id"] not in cl_ids),
        None
    )
    has_clitic_obj  = (cl_acc  is not None)
    has_clitic_refl = (cl_refl is not None)

    # Rilevamento xcomp (infinito controllato)
    xcomp_token = next(
        (t for t in tokens
         if t["deprel"] == "xcomp" and t["head"] == root["id"]
         and _verbform(t) == "Inf"),
        None
    )
    xcomp_node = None
    if xcomp_token:
        xcomp_node = build_xcomp_vp(
            xcomp_token["id"], xcomp_token, tokens,
            silent_nodes=silent_nodes
        )
    agent_token = next(
        (t for t in tokens
         if t["deprel"] == "obl:agent" and t["head"] == root["id"]),
        None
    )

    obl_tokens = [t for t in tokens
                  if t["deprel"] == "obl" and t["head"] == root["id"]]
    wh_obl = next((t for t in obl_tokens if is_wh_token(t)), None)
    # adj_obl_tokens: tutti gli obl non-wh (verranno classificati sotto)
    adj_obl_tokens = [t for t in obl_tokens if not is_wh_token(t)]

    advmod_tokens = [t for t in tokens
                     if t["deprel"] == "advmod" and t["head"] == root["id"]]

    # ── Classificazione argomenti/aggiunti per livello (ver. 26) ────────────
    adjunct_choices = adjunct_choices or {}

    arg_obl_tokens = []
    adj_by_attach  = {"SV": [], "Sv": [], "ST": [], "SC": [], "SN": []}

    for t in adj_obl_tokens:
        choice = adjunct_choices.get(t["id"], {})
        role   = choice.get("role", "aggiunto")
        attach = choice.get("attach", "Sv")
        if role == "argomento":
            arg_obl_tokens.append(t)
        else:
            adj_by_attach.setdefault(attach, []).append(
                (t, choice.get("sn_target"))
            )

    for t in advmod_tokens:
        choice = adjunct_choices.get(t["id"], {})
        role   = choice.get("role", "aggiunto")
        attach = choice.get("attach", "Sv")
        if role == "aggiunto":
            adj_by_attach.setdefault(attach, []).append(
                (t, choice.get("sn_target"))
            )
        else:
            arg_obl_tokens.append(t)

    aux_t = next(
        (t for t in tokens
         if t["upos"] == "AUX"
         and t["deprel"] in ("aux", "root")
         and t["head"] == root["id"]
         and t["lemma"] in ("avere", "essere")),
        None
    )
    aux_pass = next((t for t in tokens if t["deprel"] == "aux:pass"), None)

    # Modale: root è infinito con aux modale (volere, potere, dovere…)
    # In UDPipe: root=infinito, aux=modale finito
    # Struttura: T=modale, V=infinito (sale a v), xcomp eventuale
    modal_aux = None
    if _verbform(root) == "Inf" and not aux_t:
        modal_aux = next(
            (t for t in tokens
             if t["deprel"] == "aux" and t["head"] == root["id"]
             and t["lemma"] in VERBI_MODALI),
            None
        )
        # Se non trovato come AUX, prova VERB (UDPipe a volte marca i modali come VERB)
        if not modal_aux:
            modal_aux = next(
                (t for t in tokens
                 if t["deprel"] in ("aux", "ccomp", "xcomp")
                 and t["head"] == root["id"]
                 and t["lemma"] in VERBI_MODALI),
                None
            )

    verb_index = "i"
    subj_index = "j"
    wh_index   = "k"

    wh_case_token = None
    wh_noun_token = None
    wh_xp = None

    if wh_obl:
        wh_case_token = next(
            (t for t in tokens
             if t["deprel"] == "case" and t["head"] == wh_obl["id"]),
            None
        )
        wh_noun_token = wh_obl
        if wh_case_token:
            wh_xp = build_pp(wh_case_token, wh_noun_token, tokens,
                             index=wh_index, color=color_for(wh_index))
        else:
            wh_xp = build_dp(wh_noun_token, tokens, index=wh_index,
                             color=color_for(wh_index))

    # Soggetto: token esplicito oppure nodo pro/PRO silenzioso
    if subj_token:
        subj_dp = build_dp(subj_token, tokens, index=subj_index,
                           color=color_for(subj_index))
    elif silent_subj_node:
        subj_dp = silent_subj_node
    else:
        subj_dp = None

    # Se c'è clitico oggetto, costruiamo la traccia t_k in SV
    # e il clitico viene incorporato in v (etichetta composta)
    cl_index = "k"
    cl_color = color_for(cl_index)
    if has_clitic_obj:
        # la traccia sarà l'oggetto in SV
        cl_trace_token = {"id": -1, "form": "t", "lemma": "t",
                          "upos": "PRON", "feats": "", "head": root["id"],
                          "deprel": "obj"}
    if has_clitic_refl:
        cl_refl_trace_token = {"id": -2, "form": "t", "lemma": "t",
                               "upos": "PRON", "feats": "", "head": root["id"],
                               "deprel": "obj"}

    if copular:
        # Copulare con Small Clause
        # cop_token: *è* semplice oppure *stato* (participio)
        # aux_cop: *è* quando c'è anche *stato*
        cop_token = next(
            (t for t in tokens if t["deprel"] == "cop" and t["head"] == root["id"]),
            None
        )
        aux_cop = next(
            (t for t in tokens if t["deprel"] == "aux" and t["head"] == root["id"]
             and t["lemma"] == "essere"),
            None
        )

        sc = build_sc(subj_index, root, tokens)

        if cop_token and cop_token["upos"] == "AUX" and aux_cop:
            # Marco è stato un medico: T(è) + SAsp(stato + SC)
            asp_p = Node("SAsp")
            asp = Node("Asp", is_head=True)
            asp_word = Node(cop_token["form"], word=cop_token["form"], is_head=True)
            asp.children = [asp_word]
            asp_p.children = [asp, sc]
            main_complement = asp_p

            t_node = Node("T", is_head=True)
            t_word = Node(aux_cop["form"], word=aux_cop["form"], is_head=True)
            t_node.children = [t_word]
        else:
            # Marco è un medico / Marco è stanco: T(è) + SC
            t_node = Node("T", is_head=True)
            t_word = Node(cop_token["form"] if cop_token else "∅",
                          word=cop_token["form"] if cop_token else "∅", is_head=True)
            t_node.children = [t_word]
            main_complement = sc

    elif passive:
        # Passivo = niente Sv: v°[−ag] è assorbito come tratto su V°[+pass]
        # Struttura: SV(V°[+pass] + {SD_j}) — soggetto nasce come complemento di V
        v_color = color_for(verb_index)
        subj_color = color_for(subj_index)

        # V°[+pass] con tratto morfologico
        v_node = Node("V", is_head=True, color=v_color)
        v_word = Node(root["form"], word=root["form"],
                      is_head=True, color=v_color)
        v_node.children = [v_word]
        # tratto [+pass] come label aggiuntiva su V — usiamo etichetta composta
        v_node.label = "V[+pass]"

        # Traccia soggetto in posizione interna (complemento di V)
        t_subj_inner = Node("SD", index=subj_index, is_trace=True,
                            color=subj_color)
        t_word = Node("t", word="t", index=subj_index, is_trace=True,
                      is_head=True, color=subj_color)
        t_subj_inner.children = [t_word]

        inner_vp = Node("SV")
        inner_vp.children = [v_node, t_subj_inner]

        # Aggiunto agentivo (se presente) come sdoppiamento di SV
        if agent_token:
            case_t = next(
                (t for t in tokens
                 if t["deprel"] == "case" and t["head"] == agent_token["id"]),
                None
            )
            if case_t:
                pp = build_pp(case_t, agent_token, tokens)
                outer_vp = Node("SV")
                outer_vp.children = [inner_vp, pp]
            else:
                outer_vp = inner_vp
        else:
            outer_vp = inner_vp

        if aux_pass:
            asp_p = Node("SAsp")
            asp = Node("Asp", is_head=True)
            asp_word = Node(aux_pass["form"], word=aux_pass["form"], is_head=True)
            asp.children = [asp_word]
            asp_p.children = [asp, outer_vp]
            main_complement = asp_p
        else:
            main_complement = outer_vp

        t_node = Node("T", is_head=True)
        t_word2 = Node(aux_t["form"] if aux_t else "∅",
                       word=aux_t["form"] if aux_t else "∅", is_head=True)
        t_node.children = [t_word2]

    elif unaccusative:
        v_color = color_for(verb_index)
        subj_color = color_for(subj_index)

        # V contiene la traccia del verbo (sale a T)
        v_node = Node("V", is_head=True, color=v_color)
        t_verb = Node("t", word="t", index=verb_index, is_trace=True,
                      is_head=True, color=v_color)
        v_node.children = [t_verb]

        # T riceve la forma fonetica del verbo
        t_node = Node("T", is_head=True, color=v_color)
        t_node.children = [Node(root["form"], word=root["form"],
                                index=verb_index, is_head=True, color=v_color)]

        if has_postverbal_subject(tokens):
            # Presentativo: pro_espl in spec-ST, soggetto resta in situ in SV
            sd_subj = build_dp(subj_token, tokens) if subj_token else None
            vp = Node("SV")
            if sd_subj:
                vp.children = [v_node, sd_subj]
            else:
                vp.children = [v_node]
            # pro_espl in spec-ST — non porta movement_type (non si muove)
            subj_dp = build_pro_node("pro_espl", index=subj_index,
                                     color=subj_color)
        else:
            # Soggetto preverbale: nasce in SV come complemento di V,
            # sale a spec-ST (traccia t_j in SV)
            t_subj = Node("SD", index=subj_index, is_trace=True, color=subj_color)
            t_subj_word = Node("t", word="t", index=subj_index, is_trace=True,
                               is_head=True, color=subj_color)
            t_subj.children = [t_subj_word]
            vp = Node("SV")
            vp.children = [v_node, t_subj]
            # soggetto sale a spec-ST
            subj_dp = build_dp(subj_token, tokens, index=subj_index,
                               color=subj_color) if subj_token else None

        main_complement = vp

    elif modal_aux:
        # Struttura modale: T = modale, V = infinito con PRO soggetto
        # PRO è controllato da pro_j / soggetto esplicito (stesso indice j)
        pro_index = subj_index  # "j"
        pro_color = color_for(pro_index)
        pro_node = build_pro_node("PRO", index=pro_index, color=pro_color)

        eff_obj = None
        if has_clitic_obj:
            eff_obj = {"id": -1, "form": f"t_{cl_index}", "lemma": "t",
                       "upos": "PRON", "feats": f"Index={cl_index}",
                       "head": root["id"], "deprel": "obj"}
        elif obj_token:
            eff_obj = obj_token

        # Costruiamo Sv con PRO come spec esplicito
        # build_vp_shell mette la traccia t_j in spec-Sv — ma qui vogliamo
        # PRO, non una traccia. Costruiamo Sv manualmente.
        v_color = color_for(verb_index)

        inner_vp = build_vp(root, tokens, verb_index=verb_index,
                            obj_token=eff_obj, verb_is_trace=True)

        v_little = Node("v", is_head=True, color=v_color)
        v_word = Node(root["form"], word=root["form"],
                      index=verb_index, is_head=True, color=v_color)
        v_little.children = [v_word]

        v_prime = Node("v'")
        v_prime.children = [v_little, inner_vp]

        sv_modal = Node("Sv")
        sv_modal.children = [pro_node, v_prime]

        # Aggiunti SP/Avv come sdoppiamento Sv attorno a sv_modal
        main_complement = sv_modal

        t_node = Node("T", is_head=True, color=v_color)
        t_node.children = [Node(modal_aux["form"], word=modal_aux["form"],
                                is_head=True, color=v_color)]

    elif aux_t:
        eff_obj = None
        if has_clitic_obj:
            eff_obj = {"id": -1, "form": f"t_{cl_index}", "lemma": "t",
                       "upos": "PRON", "feats": f"Index={cl_index}",
                       "head": root["id"], "deprel": "obj"}
        elif obj_token:
            eff_obj = obj_token

        # Fix 26.1: se il soggetto è pro/PRO silenzioso, creiamo un token
        # fittizio con id negativo così build_vp_shell genera t_j in spec-Sv.
        # subj_dp (il nodo pro pieno) andrà in spec-ST come di consueto.
        eff_subj = subj_token
        if eff_subj is None and silent_subj_node is not None:
            eff_subj = {"id": -3, "form": "pro", "lemma": "pro",
                        "upos": "PRON", "feats": "", "head": root["id"],
                        "deprel": "nsubj"}

        vp_shell = build_vp_shell(
            root, tokens, eff_subj, eff_obj,
            verb_index=verb_index, subj_index=subj_index,
            wh_index=wh_index if wh_obl else None,
            wh_case_token=wh_case_token,
            wh_noun_token=wh_noun_token,
            has_aux=True,
            cl_acc=cl_acc, cl_refl=cl_refl,
            cl_index=cl_index, has_clitic_obj=has_clitic_obj,
            has_clitic_refl=has_clitic_refl,
            xcomp_node=xcomp_node,
        )
        t_node = Node("T", is_head=True)
        t_node.children = [Node(aux_t["form"], word=aux_t["form"], is_head=True)]

        # Fix 26.3: avvolgi vp_shell in SAsp per il participio passato.
        # is_pronounced=True esplicito perché annotate_movements non può
        # inferirlo (il default del dataclass è False).
        asp_p = Node("SAsp")
        asp = Node("Asp", is_head=True)
        asp_word = Node(root["form"], word=root["form"],
                        index=verb_index, is_head=True,
                        color=color_for(verb_index), is_pronounced=True)
        asp.children = [asp_word]
        asp_p.children = [asp, vp_shell]
        main_complement = asp_p

    else:
        eff_obj = None
        if has_clitic_obj:
            eff_obj = {"id": -1, "form": f"t_{cl_index}", "lemma": "t",
                       "upos": "PRON", "feats": f"Index={cl_index}",
                       "head": root["id"], "deprel": "obj"}
        elif obj_token:
            eff_obj = obj_token

        # Fix 26.1: token fittizio per pro silenzioso (vedi ramo elif aux_t)
        eff_subj = subj_token
        if eff_subj is None and silent_subj_node is not None:
            eff_subj = {"id": -3, "form": "pro", "lemma": "pro",
                        "upos": "PRON", "feats": "", "head": root["id"],
                        "deprel": "nsubj"}

        vp_shell = build_vp_shell(
            root, tokens, eff_subj, eff_obj,
            verb_index=verb_index, subj_index=subj_index,
            wh_index=wh_index if wh_obl else None,
            wh_case_token=wh_case_token,
            wh_noun_token=wh_noun_token,
            cl_acc=cl_acc, cl_refl=cl_refl,
            cl_index=cl_index, has_clitic_obj=has_clitic_obj,
            has_clitic_refl=has_clitic_refl,
            xcomp_node=xcomp_node,
        )
        t_node = Node("T", is_head=True, color=color_for(verb_index))
        t_node.children = [Node(root["form"], word=root["form"],
                                index=verb_index, is_head=True,
                                color=color_for(verb_index))]
        main_complement = vp_shell

    # ── Argomenti obl (PP argomento, es. "parlare a qn") — ver. 26.1 ─────────
    for obl_t in arg_obl_tokens:
        case_t = next(
            (t for t in tokens
             if t["deprel"] == "case" and t["head"] == obl_t["id"]),
            None
        )
        pp = build_pp(case_t, obl_t, tokens) if case_t else build_dp(obl_t, tokens)

        # Struttura larsoneana: SV_est → SD(obj) + V'(V_int + SV_int(PP))
        # Trova il SV più interno e lo ristruttura
        def _find_innermost_sv(node):
            best = None
            if node.label == "SV":
                best = node
            for child in node.children:
                inner = _find_innermost_sv(child)
                if inner is not None:
                    best = inner
            return best

        innermost = _find_innermost_sv(main_complement)
        if innermost is not None:
            # Estrai la testa V e i figli esistenti
            v_head = next((c for c in innermost.children if c.label == "V"), None)
            other_children = [c for c in innermost.children if c.label != "V"]

            if v_head and other_children:
                # SV già ha oggetto diretto: struttura larsoneana corretta
                # SV → SD(obj) + V'(V + PP)
                # L'oggetto sta in spec-SV, il PP è complemento di V
                v_prime = Node("V'", color="#2c1e0f")
                v_prime.children = [v_head, pp]
                innermost.children = other_children + [v_prime]
            else:
                # SV senza oggetto: PP come complemento diretto di V
                innermost.children.append(pp)

    # ── Aggiunti SP/Avv per livello (ver. 26) ───────────────────────────────

    def _build_adjunct_xp(obl_t):
        """Costruisce il nodo XP per un aggiunto (SP, SAvv o SD)."""
        case_t = next(
            (t for t in tokens
             if t["deprel"] == "case" and t["head"] == obl_t["id"]),
            None
        )
        if obl_t.get("upos") == "ADV":
            return build_advp(obl_t)
        elif case_t:
            return build_pp(case_t, obl_t, tokens)
        else:
            return build_dp(obl_t, tokens)

    def _attach_to_sn(root_node, sn_target_id, xp):
        """
        Cerca il SN che contiene il token sn_target_id come discendente
        e lo sdoppia: SN → SN + XP.
        Restituisce True se trovato e modificato.
        """
        target_tok = next((t for t in tokens if t["id"] == sn_target_id), None)
        if target_tok is None:
            return False
        target_form = target_tok["form"]

        def _node_contains_form(node, form):
            """True se il sottoalbero contiene un nodo foglia con word==form."""
            if node.word == form:
                return True
            return any(_node_contains_form(c, form) for c in node.children)

        def _find_and_attach(node):
            for i, child in enumerate(node.children):
                if child.label == "SN" and _node_contains_form(child, target_form):
                    outer = Node("SN", color="#2c1e0f")
                    outer.children = [child, xp]
                    node.children[i] = outer
                    return True
                if _find_and_attach(child):
                    return True
            return False

        return _find_and_attach(root_node)

    # Livello SN (aggiunto nominale — ver. 26)
    for (obl_t, sn_target_id) in adj_by_attach.get("SN", []):
        xp = _build_adjunct_xp(obl_t)
        found = False
        if sn_target_id:
            if subj_dp:
                found = _attach_to_sn(subj_dp, sn_target_id, xp)
            if not found:
                found = _attach_to_sn(main_complement, sn_target_id, xp)
        if not found:
            # Fallback: aggancia a Sv
            outer = Node("Sv")
            outer.children = [main_complement, xp]
            main_complement = outer

    # Livello Sv (default)
    for (obl_t, _) in adj_by_attach.get("Sv", []):
        xp = _build_adjunct_xp(obl_t)
        outer = Node("Sv")
        outer.children = [main_complement, xp]
        main_complement = outer

    # Livello SV (basso — per ora sdoppia come Sv)
    for (obl_t, _) in adj_by_attach.get("SV", []):
        xp = _build_adjunct_xp(obl_t)
        outer = Node("Sv")
        outer.children = [main_complement, xp]
        main_complement = outer

    # ── Assembla T' e ST ────────────────────────────────────────────────────
    t_prime = Node("T'")
    t_prime.children = [t_node, main_complement]

    tp = Node("ST")
    tp.children = [subj_dp, t_prime] if subj_dp else [t_prime]

    # Livello ST (sopra il soggetto)
    for (obl_t, _) in adj_by_attach.get("ST", []):
        xp = _build_adjunct_xp(obl_t)
        outer_st = Node("ST")
        outer_st.children = [tp, xp]
        tp = outer_st

    if wh_xp is not None:
        # Livello SC (sopra SC wh, se presente)
        pre_cp = tp
        for (obl_t, _) in adj_by_attach.get("SC", []):
            xp = _build_adjunct_xp(obl_t)
            outer_sc = Node("SC")
            outer_sc.children = [pre_cp, xp]
            pre_cp = outer_sc
        result = prune_single_child_bars(wrap_cp(pre_cp, wh_xp))
        annotate_movements(result)
        return result

    # Livello SC (senza movimento wh)
    for (obl_t, _) in adj_by_attach.get("SC", []):
        xp = _build_adjunct_xp(obl_t)
        outer_sc = Node("SC")
        outer_sc.children = [tp, xp]
        tp = outer_sc

    result = prune_single_child_bars(tp)
    annotate_movements(result)
    return result



# ── Annotazione movimenti per frecce SVG ────────────────────────────────────

def annotate_movements(node, parent_label=None):
    """
    Post-order: converte is_trace in is_copy con movement_type appropriato,
    e assegna movement_type anche ai nodi di ARRIVO (pronunciati con indice).
    - Indice j = movimento soggetto
    - Indice i = movimento verbo
    - Indice k = movimento sintagmatico clitico
    """
    for child in node.children:
        annotate_movements(child, node.label)

    if node.word is not None:
        if node.is_trace:
            idx = node.index or ""
            if idx == "j":
                node.is_copy = True
                node.movement_type = "soggetto"
            elif idx == "i":
                node.is_copy = True
                node.movement_type = "verbo"
            elif idx == "k":
                node.is_copy = True
                node.movement_type = "sintagmatico"
            node.is_trace = False
        elif not node.is_copy:
            # Nodi silenziosi (pro, PRO, ecc.): is_pronounced rimane False,
            # movement_type già impostato in build_pro_node se necessario
            _is_silent = node.word in ("pro", "PRO", "pro_espl", "PRO_arb")
            if not _is_silent:
                node.is_pronounced = True
            # Assegna movement_type solo se non già impostato alla costruzione
            # (es. OP, SP relativo hanno movement_type preimpostato)
            if node.is_pronounced and not node.movement_type:
                idx = node.index or ""
                if idx == "j":
                    node.movement_type = "soggetto"
                elif idx == "i":
                    node.movement_type = "verbo"
                elif idx == "k":
                    node.movement_type = "sintagmatico"
    else:
        # Nodo strutturale con indice: propaga movement_type
        # ma NON per pro_espl (non si muove — è già in posizione finale)
        idx = node.index or ""
        is_pro_espl = any(
            c.word in ("pro_espl", "pro", "PRO", "PRO_arb")
            for c in node.children
            if c.word is not None
        ) or any(
            any(gc.word in ("pro_espl",) for gc in c.children if gc.word is not None)
            for c in node.children
        )
        if not is_pro_espl:
            if idx == "j":
                node.movement_type = "soggetto"
                if node.is_trace:
                    node.is_copy = True
                    node.is_trace = False
            elif idx == "k":
                node.movement_type = "sintagmatico"
                if node.is_trace:
                    node.is_copy = True
                    node.is_trace = False

# ── Pretty print per debug ───────────────────────────────────────────────────

def print_tree(node, indent=0):
    prefix = "  " * indent
    if node.word:
        idx = f"_{node.index}" if node.index else ""
        trace = " [TRACE]" if node.is_trace else ""
        print(f"{prefix}{node.label}{idx}: «{node.word}»{trace}")
    else:
        idx = f"_{node.index}" if node.index else ""
        print(f"{prefix}{node.label}{idx}")
    for child in node.children:
        print_tree(child, indent + 1)


# ── Test ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from test_conllu import CONLLU_SAMPLES, parse_conllu

    for sentence, conllu in CONLLU_SAMPLES.items():
        print(f"\n{'='*60}\n  {sentence}\n{'='*60}")
        tokens = parse_conllu(conllu)
        tree = build_tp(tokens)
        print_tree(tree)

    print(f"\n{'='*60}\n  A chi hai regalato la tua penna nel cortile?\n{'='*60}")
    conllu_wh = """
1\tA\ta\tADP\tE\t_\t2\tcase\t_\t_
2\tchi\tchi\tPRON\tPQ\tPronType=Int\t4\tobl\t_\t_
3\thai\tavere\tAUX\tVA\tMood=Ind|Number=Sing|Person=2|Tense=Pres\t4\taux\t_\t_
4\tregalato\tregalare\tVERB\tV\tGender=Masc|Number=Sing|Tense=Past|VerbForm=Part\t0\troot\t_\t_
5\tla\til\tDET\tRD\tDefinite=Def|Gender=Fem|Number=Sing|PronType=Art\t7\tdet\t_\t_
6\ttua\ttuo\tDET\tAP\tGender=Fem|Number=Sing|Poss=Yes|PronType=Prs\t7\tdet:poss\t_\t_
7\tpenna\tpenna\tNOUN\tS\tGender=Fem|Number=Sing\t4\tobj\t_\t_
8\tin\tin\tADP\tE\t_\t10\tcase\t_\t_
9\til\til\tDET\tRD\tDefinite=Def|Gender=Masc|Number=Sing|PronType=Art\t10\tdet\t_\t_
10\tcortile\tcortile\tNOUN\tS\tGender=Masc|Number=Sing\t4\tobl\t_\tSpaceAfter=No
"""
    tokens = parse_conllu(conllu_wh)
    tree = build_tp(tokens)
    print_tree(tree)
