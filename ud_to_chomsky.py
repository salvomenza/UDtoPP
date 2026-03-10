"""
ud_to_chomsky.py
Converte una lista di token CoNLL-U in una struttura ad albero chomskiana.

Convenzioni:
- DP invece di NP; little v (vP); TP invece di IP
- X' eliminata se unico figlio è la testa (no spec, no aggiunto)
- DP → D → nome proprio/pronome (senza NP)
- DP → D' → D + NP → N' → [AP spec +] N (per nomi comuni)
- Passivo: v [+pass], AspP per participio passivo
- Aggiunti: sdoppiamento XP → XP + YP
- CP con [+wh] per interrogative; movimento wh a spec-CP
- Ditransitivi: struttura larsoneana (oggetto diretto in spec-VP esterno)
- obl con PronType=Int → wh; obl senza → aggiunto PP
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


def is_unaccusative(tokens):
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root:
        return False
    deps = [t["deprel"] for t in children_of(tokens, root["id"])]
    has_obj = "obj" in deps
    has_agent = "obl:agent" in deps
    has_aux = any(t["upos"] == "AUX" for t in children_of(tokens, root["id"]))
    if not has_obj and not has_agent and not has_aux:
        nsubj = next((t for t in tokens
                      if t["deprel"] == "nsubj" and t["head"] == root["id"]), None)
        if nsubj:
            return True
    return False


def is_copular(tokens):
    """True se la frase è copulare: root non-VERB con cop dipendente."""
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root:
        return False
    has_cop = any(t["deprel"] == "cop" and t["head"] == root["id"] for t in tokens)
    return has_cop and root["upos"] != "VERB"


def is_wh_token(token):
    return "PronType=Int" in token.get("feats", "")


# ── Costruzione DP ───────────────────────────────────────────────────────────

def build_dp(noun_token, tokens, index=None, is_trace=False, color=None):
    dp_color = color or (color_for(index) if index else "#2c1e0f")

    if is_trace:
        # traccia: nodo t_j diretto, senza etichetta DP
        t_node = Node("t", word="t", index=index, is_trace=True,
                      is_head=True, color=dp_color)
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

    dp = Node("DP", index=index, color=dp_color)

    if noun_token["upos"] in ("PROPN", "PRON"):
        d = Node("D", is_head=True, color=dp_color)
        word = Node(noun_token["form"], word=noun_token["form"],
                    index=index, is_head=True, color=dp_color)
        d.children = [word]
        dp.children = [d]

    else:
        if det_token:
            d = Node("D", is_head=True, color="#2c1e0f")
            d_word = Node(det_token["form"], word=det_token["form"],
                          is_head=True, color="#2c1e0f")
            d.children = [d_word]

            np = Node("NP", color="#2c1e0f")

            if poss_token:
                # NP → N' → AP(poss) + N
                n_prime = Node("N'", color="#2c1e0f")
                ap = Node("AP", color="#2c1e0f")
                ap_word = Node(poss_token["form"], word=poss_token["form"],
                               is_head=True, color="#2c1e0f")
                ap.children = [ap_word]
                n = Node("N", is_head=True, color="#2c1e0f")
                n_word = Node(noun_token["form"], word=noun_token["form"],
                              is_head=True, color="#2c1e0f")
                n.children = [n_word]
                n_prime.children = [ap, n]
                np.children = [n_prime]
                # spec presente → D' necessaria
                d_prime = Node("D'", color=dp_color)
                d_prime.children = [d, np]
                dp.children = [d_prime]
            else:
                n = Node("N", is_head=True, color="#2c1e0f")
                n_word = Node(noun_token["form"], word=noun_token["form"],
                              is_head=True, color="#2c1e0f")
                n.children = [n_word]
                np.children = [n]
                # no spec → DP → D + NP direttamente
                dp.children = [d, np]

            # aggiunti al nome (nmod): sdoppiamento NP → NP + PP
            nmod_tokens = [t for t in tokens
                           if t["deprel"] == "nmod" and t["head"] == noun_token["id"]]
            for nmod_t in nmod_tokens:
                case_t = next(
                    (t for t in tokens
                     if t["deprel"] == "case" and t["head"] == nmod_t["id"]),
                    None
                )
                if case_t:
                    pp = build_pp(case_t, nmod_t, tokens)
                else:
                    pp = build_dp(nmod_t, tokens)
                # trova l'NP attuale dentro dp e sdoppia
                # cerca NP tra i figli diretti o tramite D'
                current_np = None
                for child in dp.children:
                    if child.label == "NP":
                        current_np = child
                        break
                    elif child.label == "D'":
                        for gc in child.children:
                            if gc.label == "NP":
                                current_np = gc
                                break
                if current_np is not None:
                    outer_np = Node("NP", color="#2c1e0f")
                    outer_np.children = [current_np, pp]
                    # sostituisci current_np con outer_np
                    for child in dp.children:
                        if child.label == "NP":
                            dp.children[dp.children.index(child)] = outer_np
                            break
                        elif child.label == "D'":
                            for i, gc in enumerate(child.children):
                                if gc.label == "NP":
                                    child.children[i] = outer_np
                                    break
        else:
            d = Node("D", is_head=True, color="#2c1e0f")
            word = Node(noun_token["form"], word=noun_token["form"],
                        is_head=True, color="#2c1e0f")
            d.children = [word]
            dp.children = [d]

    return dp


# ── Costruzione PP ───────────────────────────────────────────────────────────

def build_pp(case_token, noun_token, tokens, index=None, is_trace=False, color=None):
    pp_color = color or (color_for(index) if index else "#2c1e0f")

    if is_trace:
        t = Node("t", word="t", index=index, is_trace=True,
                 is_head=True, color=pp_color)
        return t

    pp = Node("PP", index=index, color=pp_color)
    p_prime = Node("P'", color=pp_color)
    p = Node("P", is_head=True, color=pp_color)
    p_word = Node(case_token["form"], word=case_token["form"],
                  is_head=True, color=pp_color)
    p.children = [p_word]
    dp = build_dp(noun_token, tokens, color="#2c1e0f")
    p_prime.children = [p, dp]
    pp.children = [p_prime]
    return pp


# ── Costruzione AdvP ─────────────────────────────────────────────────────────

def build_advp(adv_token):
    advp = Node("AdvP")
    adv = Node("Adv", is_head=True)
    adv_word = Node(adv_token["form"], word=adv_token["form"], is_head=True)
    adv.children = [adv_word]
    advp.children = [adv]
    return advp


# ── Costruzione SC (Small Clause) ───────────────────────────────────────────

def build_sc(subj_index, pred_token, tokens):
    """
    Costruisce SC → DP(t_j) + XP
    XP può essere DP (nome), AP (aggettivo), PP (preposizione)
    """
    sc = Node("SC")
    subj_color = color_for(subj_index)

    # traccia del soggetto in spec-SC: t_j diretto, senza etichetta DP
    t_subj = Node("t", word="t", index=subj_index, is_trace=True,
                  is_head=True, color=subj_color)

    # predicato
    upos = pred_token["upos"]
    if upos == "ADJ":
        # AP → A → word
        ap = Node("AP")
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


# ── Costruzione VP ───────────────────────────────────────────────────────────

def build_vp(verb_token, tokens, verb_index="i", obj_token=None,
             wh_pp=None, verb_is_trace=False):
    vp = Node("VP")
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
    else:
        vp.children = [v]

    return vp


# ── Costruzione vP shell ──────────────────────────────────────────────────────

def build_vp_shell(verb_token, tokens, subj_token, obj_token,
                   verb_index="i", subj_index="j", passive=False,
                   wh_index=None, wh_case_token=None, wh_noun_token=None,
                   has_aux=False):
    v_color = color_for(verb_index)
    subj_color = color_for(subj_index)

    larsonian = (wh_index is not None and wh_case_token is not None
                 and obj_token is not None)

    if larsonian:
        # Ditransitivo larsoneano: obj in spec-VP esterno, PP(t_k) in VP interno
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
        outer_vp = Node("VP")
        outer_vp.children = [obj_dp, v_prime_outer]

    else:
        outer_vp = build_vp(verb_token, tokens, verb_index=verb_index,
                            obj_token=obj_token, verb_is_trace=True)

    v_little = Node("v", is_head=True,
                    color=v_color if not passive else "#2c1e0f")
    if passive:
        v_word = Node("[+pass]", word="[+pass]", is_head=True, color="#2c1e0f")
    elif has_aux:
        # con ausiliare: participio sale V→v, forma fonetica in v
        v_word = Node(verb_token["form"], word=verb_token["form"],
                      index=verb_index, is_head=True, color=v_color)
    else:
        # senza ausiliare: verbo sale V→v→T, solo traccia in v
        v_word = Node("t", word="t", index=verb_index, is_trace=True,
                      is_head=True, color=v_color)
    v_little.children = [v_word]

    v_prime = Node("v'")
    v_prime.children = [v_little, outer_vp]

    vp = Node("vP")
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


# ── Avvolgi in CP ────────────────────────────────────────────────────────────

def wrap_cp(tp, wh_xp):
    cp = Node("CP")
    c_prime = Node("C'")
    c = Node("C", is_head=True)
    c_word = Node("[+wh]", word="[+wh]", is_head=True)
    c.children = [c_word]
    c_prime.children = [c, tp]
    cp.children = [wh_xp, c_prime]
    return cp


# ── Costruzione TP (punto di ingresso) ───────────────────────────────────────

def build_tp(tokens):
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root:
        raise ValueError("Nessun token root trovato")

    passive = is_passive(tokens)
    unaccusative = is_unaccusative(tokens)
    copular = is_copular(tokens)

    subj_token = next(
        (t for t in tokens
         if t["deprel"] in ("nsubj", "nsubj:pass") and t["head"] == root["id"]),
        None
    )
    obj_token = next(
        (t for t in tokens
         if t["deprel"] == "obj" and t["head"] == root["id"]),
        None
    )
    agent_token = next(
        (t for t in tokens
         if t["deprel"] == "obl:agent" and t["head"] == root["id"]),
        None
    )

    obl_tokens = [t for t in tokens
                  if t["deprel"] == "obl" and t["head"] == root["id"]]
    wh_obl = next((t for t in obl_tokens if is_wh_token(t)), None)
    adj_obl_tokens = [t for t in obl_tokens if not is_wh_token(t)]

    advmod_tokens = [t for t in tokens
                     if t["deprel"] == "advmod" and t["head"] == root["id"]]

    aux_t = next(
        (t for t in tokens
         if t["upos"] == "AUX"
         and t["deprel"] in ("aux", "root")
         and t["head"] == root["id"]
         and t["lemma"] in ("avere", "essere")),
        None
    )
    aux_pass = next((t for t in tokens if t["deprel"] == "aux:pass"), None)

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

    subj_dp = build_dp(subj_token, tokens, index=subj_index,
                       color=color_for(subj_index)) if subj_token else None

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
            # Marco è stato un medico: T(è) + AspP(stato + SC)
            asp_p = Node("AspP")
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
        v_color = color_for(verb_index)
        subj_color = color_for(subj_index)

        v_node = Node("V", is_head=True, color=v_color)
        v_word = Node(root["form"], word=root["form"],
                      is_head=True, color=v_color)
        v_node.children = [v_word]

        t_subj_inner = Node("DP", index=subj_index, is_trace=True,
                            color=subj_color)
        t_word = Node("t", word="t", index=subj_index, is_trace=True,
                      is_head=True, color=subj_color)
        t_subj_inner.children = [t_word]

        inner_vp = Node("VP")
        inner_vp.children = [v_node, t_subj_inner]

        v_little = Node("v", is_head=True)
        v_pass_word = Node("[+pass]", word="[+pass]", is_head=True)
        v_little.children = [v_pass_word]

        v_prime = Node("v'")
        v_prime.children = [v_little, inner_vp]

        inner_vp_shell = Node("vP")
        inner_vp_shell.children = [v_prime]

        if agent_token:
            case_t = next(
                (t for t in tokens
                 if t["deprel"] == "case" and t["head"] == agent_token["id"]),
                None
            )
            if case_t:
                pp = build_pp(case_t, agent_token, tokens)
                outer_vp = Node("vP")
                outer_vp.children = [inner_vp_shell, pp]
            else:
                outer_vp = inner_vp_shell
        else:
            outer_vp = inner_vp_shell

        if aux_pass:
            asp_p = Node("AspP")
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

        v_node = Node("V", is_head=True, color=v_color)
        v_word = Node(root["form"], word=root["form"],
                      index=verb_index, is_head=True, color=v_color)
        v_node.children = [v_word]

        t_subj_inner = Node("DP", index=subj_index, is_trace=True,
                            color=subj_color)
        t_word = Node("t", word="t", index=subj_index, is_trace=True,
                      is_head=True, color=subj_color)
        t_subj_inner.children = [t_word]

        vp = Node("VP")
        vp.children = [v_node, t_subj_inner]

        t_node = Node("T", is_head=True)
        t_node.children = [Node(root["form"], word=root["form"], is_head=True)]
        main_complement = vp

    elif aux_t:
        vp_shell = build_vp_shell(
            root, tokens, subj_token, obj_token,
            verb_index=verb_index, subj_index=subj_index,
            wh_index=wh_index if wh_obl else None,
            wh_case_token=wh_case_token,
            wh_noun_token=wh_noun_token,
            has_aux=True,
        )
        t_node = Node("T", is_head=True)
        t_node.children = [Node(aux_t["form"], word=aux_t["form"], is_head=True)]
        main_complement = vp_shell

    else:
        vp_shell = build_vp_shell(
            root, tokens, subj_token, obj_token,
            verb_index=verb_index, subj_index=subj_index,
            wh_index=wh_index if wh_obl else None,
            wh_case_token=wh_case_token,
            wh_noun_token=wh_noun_token,
        )
        t_node = Node("T", is_head=True, color=color_for(verb_index))
        t_node.children = [Node(root["form"], word=root["form"],
                                index=verb_index, is_head=True,
                                color=color_for(verb_index))]
        main_complement = vp_shell

    # ── Aggiunti PP da obl non-wh ────────────────────────────────────────────
    for obl_t in adj_obl_tokens:
        case_t = next(
            (t for t in tokens
             if t["deprel"] == "case" and t["head"] == obl_t["id"]),
            None
        )
        adjunct = build_pp(case_t, obl_t, tokens) if case_t else build_dp(obl_t, tokens)
        outer = Node("vP")
        outer.children = [main_complement, adjunct]
        main_complement = outer

    # ── Aggiunti avverbiali ──────────────────────────────────────────────────
    for adv_token in advmod_tokens:
        outer = Node("vP")
        outer.children = [main_complement, build_advp(adv_token)]
        main_complement = outer

    # ── Assembla T' e TP ────────────────────────────────────────────────────
    t_prime = Node("T'")
    t_prime.children = [t_node, main_complement]

    tp = Node("TP")
    tp.children = [subj_dp, t_prime] if subj_dp else [t_prime]

    if wh_xp is not None:
        return wrap_cp(tp, wh_xp)

    return tp


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
