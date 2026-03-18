# ver. 21
"""
step_generator.py
Genera la sequenza di passi per la costruzione passo-passo dell'albero chomskiano.
Ogni passo è un dizionario con:
  - 'tree': sottoalbero parziale (Node)
  - 'comment': testo esplicativo
  - 'title': titolo breve del passo
"""

from copy import deepcopy
from ud_to_chomsky import (
    Node, build_dp, build_pp, build_advp, build_sc,
    is_passive, is_unaccusative, is_copular, is_wh_token,
    color_for, children_of, build_pro_node, prune_single_child_bars,
    VERBI_MODALI
)


# ── Utilità ──────────────────────────────────────────────────────────────────

def lemma_of_root(tokens):
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    return root["lemma"] if root else "?"

def form_of_root(tokens):
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    return root["form"] if root else "?"

def aux_form(tokens):
    aux = next((t for t in tokens
                if t["upos"] == "AUX" and t["deprel"] in ("aux", "root")
                and t["lemma"] in ("avere", "essere")), None)
    return aux["form"] if aux else None

def has_aux_avere(tokens):
    return any(t["lemma"] == "avere" and t["upos"] == "AUX" for t in tokens)

def has_aux_essere(tokens):
    return any(t["lemma"] == "essere" and t["upos"] == "AUX"
               and t["deprel"] in ("aux", "root") for t in tokens)

def subj_form(tokens):
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root: return "il soggetto"
    s = next((t for t in tokens
               if t["deprel"] in ("nsubj", "nsubj:pass")
               and t["head"] == root["id"]), None)
    return f"'{s['form']}'" if s else "il soggetto"

def obj_form(tokens):
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root: return "l'oggetto"
    o = next((t for t in tokens
               if t["deprel"] == "obj" and t["head"] == root["id"]), None)
    return f"'{o['form']}'" if o else "l'oggetto"

def wh_form(tokens):
    obl = next((t for t in tokens
                if t["deprel"] == "obl" and is_wh_token(t)), None)
    if not obl: return "il costituente wh"
    case_t = next((t for t in tokens
                   if t["deprel"] == "case" and t["head"] == obl["id"]), None)
    if case_t:
        return f"'{case_t['form']} {obl['form']}'"
    return f"'{obl['form']}'"


# ── Test preliminare ─────────────────────────────────────────────────────────

def preliminary_comment(tokens, tipo_verbo=None):
    """Genera il commento del test preliminare sul tipo di predicato."""
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root: return ""
    verb = f"'{root['form']}'"
    lemma = f"'{root['lemma']}'"

    passive = is_passive(tokens)
    unaccusative = is_unaccusative(tokens)
    copular = is_copular(tokens)

    # Sovrascrittura da scelta utente
    if tipo_verbo == "transitivo":
        unaccusative = False
    elif tipo_verbo == "inaccusativo":
        unaccusative = True

    has_obj = any(t["deprel"] == "obj" and t["head"] == root["id"] for t in tokens)
    has_wh = any(t["deprel"] == "obl" and is_wh_token(t) for t in tokens)
    has_iobj = any(t["deprel"] == "obl" and not is_wh_token(t)
                   and t["head"] == root["id"] for t in tokens)

    if copular:
        pred = next((t for t in tokens
                     if t["id"] == root["id"]), None)
        upos = pred["upos"] if pred else ""
        tipo = "aggettivale" if upos == "ADJ" else "nominale"
        return (
            f"<b>Test preliminare.</b> Il predicato {verb} è una copula con predicato {tipo}. "
            f"La copula 'essere' occupa la testa T e non è un vero verbo lessicale: "
            f"non seleziona né 'avere' né 'essere' come ausiliare proprio, "
            f"e non ammette il clitico accusativo 'la'. "
            f"La struttura è: ST → SD + T'(T(essere) + FR(t_sogg + XP))."
        )

    if passive:
        return (
            f"<b>Test preliminare.</b> Il predicato {verb} è passivo. "
            f"Seleziona l'ausiliare 'essere'. "
            f"v è defettivo [+pass]: sopprime l'argomento esterno, "
            f"quindi nessun agente viene introdotto in spec-Sv. "
            f"L'argomento interno salirà a spec-ST per valutare uNum su T. "
            f"Avremo bisogno di: SV + Sv(defettivo) + SAsp + ST."
        )

    if unaccusative:
        lemma_inf = root["lemma"]
        part = lemma_inf.replace("are", "ato").replace("ere", "uto").replace("ire", "ito")
        return (
            f"<b>Test preliminare.</b> Il predicato {verb} è inaccusativo. "
            f"Dimostrazione: (1) seleziona l'ausiliare 'essere' "
            f"(es. '{subj_form(tokens).strip(chr(39))} è {part}'); "
            f"(2) ammette il clitico partitivo 'ne' riferito al soggetto "
            f"(es. 'ne sono {part}i/e tre'). "
            f"Poiché non c'è argomento esterno, <b>non avremo Sv</b>: "
            f"la struttura è ST → SD + T'(T + SV(V + t_sogg))."
        )

    # transitivo (semplice o ditransitivo o con wh)
    # Forma del test clitico: se c'è ausiliare uso "la hanno accettata",
    # altrimenti uso il presente "la accetta"
    aux_avere = next((t for t in tokens
                      if t["lemma"] == "avere" and t["upos"] == "AUX"), None)
    if aux_avere:
        # participio dal lemma
        lemma_str = root["lemma"]
        if lemma_str.endswith("are"):
            part_f = lemma_str[:-3] + "ata"
        elif lemma_str.endswith("ere"):
            part_f = lemma_str[:-3] + "uta"
        elif lemma_str.endswith("ire"):
            part_f = lemma_str[:-3] + "ita"
        else:
            part_f = root["form"]
        clitico_ex = f"'la {aux_avere['form']} {part_f}'"
    else:
        # presente 3a persona: uso la forma attuale del verbo se sembra al presente
        # altrimenti ricado sul lemma con -a finale
        lemma_str = root["lemma"]
        if lemma_str.endswith("are"):
            pres = lemma_str[:-3] + "a"
        elif lemma_str.endswith("ere"):
            pres = lemma_str[:-3] + "e"
        elif lemma_str.endswith("ire"):
            pres = lemma_str[:-3] + "e"
        else:
            pres = root["form"]
        clitico_ex = f"'la {pres}'"

    ditrans = has_obj and has_iobj and not has_wh
    wh_trans = has_wh and has_obj

    if wh_trans:
        return (
            f"<b>Test preliminare.</b> Il predicato {verb} è transitivo ditransitivo "
            f"con elemento wh. Seleziona 'avere' e ammette il clitico accusativo 'la' "
            f"(es. {clitico_ex}). "
            f"Attenzione: non usare 'lo' come test, perché 'lo' funziona anche "
            f"come proforma per predicati nominali ('è medico → lo è'). "
            f"La struttura interna è larsoneana (due SV annidati). "
            f"Inoltre c'è un elemento wh che si sposterà a spec-SC. "
            f"Avremo: SC → SP_wh + C'(C[+wh] + ST)."
        )
    if ditrans:
        return (
            f"<b>Test preliminare.</b> Il predicato {verb} è ditransitivo. "
            f"Seleziona 'avere' e ammette il clitico accusativo 'la' "
            f"(es. {clitico_ex}). "
            f"Attenzione: non usare 'lo' come test, perché 'lo' funziona anche "
            f"come proforma per predicati nominali ('è medico → lo è'). "
            f"Essendo ditransitivo, la struttura interna è <b>larsoneana</b>: "
            f"SV esterno (con l'oggetto diretto in spec) annida un SV interno "
            f"(con l'oggetto indiretto). L'oggetto diretto c-comanda quello indiretto. "
            f"Avremo: ST → SD + T'(T + Sv(t_sogg + v'(v + SV_larsoneano)))."
        )
    if has_obj:
        return (
            f"<b>Test preliminare.</b> Il predicato {verb} è transitivo. "
            f"Seleziona 'avere' e ammette il clitico accusativo 'la' "
            f"(es. {clitico_ex}). "
            f"Attenzione: non usare 'lo' come test, perché 'lo' funziona anche "
            f"come proforma per predicati nominali ('è medico → lo è'). "
            f"Avremo bisogno di SV (dove V assegna il ruolo tematico interno) "
            f"e Sv (dove v assegna il ruolo di agente)."
        )
    # intransitivo con avere
    return (
        f"<b>Test preliminare.</b> Il predicato {verb} è intransitivo "
        f"e seleziona 'avere'. "
        f"Avremo Sv (v assegna il ruolo di agente) e SV (senza complemento)."
    )


# ── Costruzione passi ────────────────────────────────────────────────────────

def node_signatures(node, sigs=None):
    """Raccoglie le firme di tutti i nodi (label+word+index) in un set."""
    if sigs is None:
        sigs = set()
    sig = (node.label, node.word or "", node.index or "")
    sigs.add(sig)
    for child in node.children:
        node_signatures(child, sigs)
    return sigs


def mark_new_nodes(node, prev_sigs):
    """Marca is_new=True sui nodi non presenti nel passo precedente."""
    sig = (node.label, node.word or "", node.index or "")
    node.is_new = sig not in prev_sigs
    for child in node.children:
        mark_new_nodes(child, prev_sigs)


_prev_step_sigs = set()


def make_step(title, comment, tree):
    global _prev_step_sigs
    t = deepcopy(tree)
    if t.word != "…":
        prune_single_child_bars(t)
        mark_new_nodes(t, _prev_step_sigs)
        _prev_step_sigs = node_signatures(t)
    return {"title": title, "comment": comment, "tree": t}


def reset_step_state():
    """Resetta lo stato tra frasi diverse."""
    global _prev_step_sigs
    _prev_step_sigs = set()


def generate_steps(tokens, tipo_verbo=None):
    """
    Genera la lista di passi per la costruzione dell'albero.
    Restituisce lista di dict: {title, comment, tree}
    """
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root:
        return []

    passive   = is_passive(tokens)
    unaccus   = is_unaccusative(tokens)
    copular   = is_copular(tokens)

    # Sovrascrittura da scelta utente
    if tipo_verbo == "transitivo":
        unaccus = False
    elif tipo_verbo == "inaccusativo":
        unaccus = True

    # Modale: passo-passo non ancora disponibile
    modal_aux = next((t for t in tokens
                      if t["upos"] in ("AUX", "VERB")
                      and t["lemma"] in VERBI_MODALI), None)
    if modal_aux:
        placeholder = Node("?", word="…")
        return [make_step(
            "Struttura modale",
            f"<b>Nota.</b> La modalità passo-passo per le frasi con verbo modale "
            f"(<i>{modal_aux['form']}</i>) non è ancora disponibile. "
            f"Puoi consultare la rappresentazione completa nel tab Generative.",
            placeholder
        )]

    verb_index = "i"
    subj_index = "j"
    wh_index   = "k"

    v_color    = color_for(verb_index)
    subj_color = color_for(subj_index)
    wh_color   = color_for(wh_index)

    subj_token = next((t for t in tokens
                       if t["deprel"] in ("nsubj","nsubj:pass")
                       and t["head"] == root["id"]), None)
    obj_token  = next((t for t in tokens
                       if t["deprel"] == "obj"
                       and t["head"] == root["id"]), None)
    agent_token = next((t for t in tokens
                        if t["deprel"] == "obl:agent"
                        and t["head"] == root["id"]), None)
    aux_t = next((t for t in tokens
                  if t["upos"] == "AUX"
                  and t["deprel"] in ("aux","root")
                  and t["head"] == root["id"]
                  and t["lemma"] in ("avere","essere")), None)
    aux_pass = next((t for t in tokens if t["deprel"] == "aux:pass"), None)
    cop_token = next((t for t in tokens
                      if t["deprel"] == "cop"
                      and t["head"] == root["id"]), None)
    aux_cop = next((t for t in tokens
                    if t["deprel"] == "aux"
                    and t["head"] == root["id"]
                    and t["lemma"] == "essere"), None)

    obl_tokens = [t for t in tokens
                  if t["deprel"] == "obl" and t["head"] == root["id"]]
    wh_obl = next((t for t in obl_tokens if is_wh_token(t)), None)
    adj_obl_tokens = [t for t in obl_tokens if not is_wh_token(t)]
    advmod_tokens = [t for t in tokens
                     if t["deprel"] == "advmod" and t["head"] == root["id"]]

    wh_case_token = None
    wh_noun_token = None
    if wh_obl:
        wh_case_token = next((t for t in tokens
                              if t["deprel"] == "case"
                              and t["head"] == wh_obl["id"]), None)
        wh_noun_token = wh_obl

    reset_step_state()  # resetta stato tra frasi
    steps = []
    verb_form = root["form"]
    verb_lemma = root["lemma"]
    subj_str = subj_form(tokens)
    obj_str  = obj_form(tokens)

    # ── PASSO 0: test preliminare ────────────────────────────────────────────
    # Non ha albero — mostriamo solo il commento con un nodo radice vuoto
    root_placeholder = Node("?", word="…")
    steps.append(make_step(
        "Test preliminare",
        preliminary_comment(tokens, tipo_verbo=tipo_verbo),
        root_placeholder
    ))

    # ── COPULARE ─────────────────────────────────────────────────────────────
    if copular:
        pred_token = root
        upos = pred_token["upos"]
        pred_str = f"'{pred_token['form']}'"

        # Passo 1: predicato XP
        if upos == "ADJ":
            xp = Node("SA")
            a = Node("A", is_head=True)
            a_word = Node(pred_token["form"], word=pred_token["form"], is_head=True)
            a.children = [a_word]
            xp.children = [a]
            xp_label = "SA"
        else:
            xp = build_dp(pred_token, tokens)
            xp_label = "SD"

        steps.append(make_step(
            f"Merge: predicato {xp_label}",
            f"Costruiamo il predicato {pred_str}. "
            f"Questo elemento formerà il nucleo della Frase Ridotta (FR).",
            xp
        ))

        # Passo 2: SD soggetto
        subj_dp = build_dp(subj_token, tokens, index=subj_index,
                           color=subj_color) if subj_token else None
        if subj_dp:
            steps.append(make_step(
                f"Merge: SD soggetto",
                f"Costruiamo SD({subj_str}). "
                f"Questo elemento sarà il soggetto della predicazione.",
                subj_dp
            ))

        # Passo 3: FR
        fr = Node("FR")
        t_subj_fr = Node("t", word="t", index=subj_index, is_trace=True,
                         is_head=True, color=subj_color)
        fr.children = [t_subj_fr, xp]
        steps.append(make_step(
            "Merge esterno: FR",
            f"Merge esterno: formiamo la Frase Ridotta (FR). "
            f"FR unisce t_{subj_index} (posizione del soggetto) e {xp_label}({pred_str}). "
            f"Il predicato {pred_str} assegna il ruolo tematico al soggetto "
            f"nella posizione di spec-FR.",
            fr
        ))

        # Passo 4: T + FR (con o senza AspP)
        if cop_token and aux_cop:
            # è stato: AspP
            asp_p = Node("SAsp")
            asp = Node("Asp", is_head=True)
            asp_word = Node(cop_token["form"], word=cop_token["form"], is_head=True)
            asp.children = [asp_word]
            asp_p.children = [asp, fr]
            steps.append(make_step(
                "Merge: SAsp",
                f"'{cop_token['form']}' occupa la testa Asp e introduce "
                f"l'aspetto perfettivo. SAsp domina FR.",
                asp_p
            ))
            t_node = Node("T", is_head=True)
            t_word = Node(aux_cop["form"], word=aux_cop["form"], is_head=True)
            t_node.children = [t_word]
            t_prime = Node("T'")
            t_prime.children = [t_node, asp_p]
        else:
            cop_form = cop_token["form"] if cop_token else "è"
            t_node = Node("T", is_head=True)
            t_word = Node(cop_form, word=cop_form, is_head=True)
            t_node.children = [t_word]
            t_prime = Node("T'")
            t_prime.children = [t_node, fr]

        st_no_spec = Node("ST")
        st_no_spec.children = [t_prime]
        steps.append(make_step(
            "Merge: T + FR → ST",
            f"La copula '{cop_token['form'] if cop_token else 'è'}' occupa la testa T "
            f"e porta i tratti di tempo e accordo (uNum). "
            f"T ha bisogno di un elemento con iNum che lo c-comandi da spec-ST.",
            st_no_spec
        ))

        # Passo 5: soggetto sale a spec-ST
        if subj_dp:
            st_full = Node("ST")
            st_full.children = [deepcopy(subj_dp), t_prime]
            steps.append(make_step(
                f"Merge interno: {subj_str} → spec-ST",
                f"SD({subj_str}) viene copiato in spec-ST per valutare "
                f"il tratto di numero non interpretabile (uNum) su T. "
                f"SD porta iNum, che soddisfa uNum. "
                f"Come effetto collaterale SD riceve Caso nominativo. "
                f"Rimane una traccia t_{subj_index} in spec-FR.",
                st_full
            ))

        return steps

    # ── INACCUSATIVO ─────────────────────────────────────────────────────────
    if unaccus:
        # Passo 1: SD oggetto/soggetto superficiale
        subj_dp = build_dp(subj_token, tokens, index=subj_index,
                           color=subj_color) if subj_token else None
        if subj_dp:
            steps.append(make_step(
                f"Merge: SD argomento",
                f"Costruiamo SD({subj_str}). "
                f"Nell'inaccusativo questo elemento nasce come argomento interno di V, "
                f"non come soggetto — lo vedremo salire più tardi.",
                subj_dp
            ))

        # Passo 2: SV con argomento interno
        v_node = Node("V", is_head=True, color=v_color)
        v_word = Node(verb_form, word=verb_form, index=verb_index,
                      is_head=True, color=v_color)
        v_node.children = [v_word]
        t_subj_inner = Node("t", word="t", index=subj_index, is_trace=True,
                            is_head=True, color=subj_color)
        sv = Node("SV")
        sv.children = [v_node, t_subj_inner]
        steps.append(make_step(
            f"Merge esterno: V + SD → SV",
            f"V('{verb_form}') si unisce a SD({subj_str}) come argomento interno. "
            f"V assegna il ruolo tematico di <b>tema</b> a SD. "
            f"Non c'è Sv perché non c'è argomento esterno/agente.",
            sv
        ))

        # Passo 3: T + SV
        t_node = Node("T", is_head=True, color=v_color)
        t_word2 = Node(verb_form, word=verb_form, is_head=True, color=v_color)
        t_node.children = [t_word2]
        t_prime = Node("T'")
        t_prime.children = [t_node, sv]
        st_no_spec = Node("ST")
        st_no_spec.children = [t_prime]
        steps.append(make_step(
            "Movimento di testa: V → T",
            f"Il verbo '{verb_form}' sale da V a T (movimento di testa). "
            f"T porta i tratti di tempo e accordo (uNum) e attende "
            f"un elemento con iNum in spec-ST.",
            st_no_spec
        ))

        # Passo 4: soggetto sale a spec-ST
        if subj_dp:
            st_full = Node("ST")
            t_prime2 = Node("T'")
            t_prime2.children = [t_node, sv]
            st_full.children = [deepcopy(subj_dp), t_prime2]
            steps.append(make_step(
                f"Merge interno: {subj_str} → spec-ST",
                f"T porta uNum. L'unico elemento con iNum disponibile "
                f"(c-comandato da T e il più vicino per Minimalità) è "
                f"SD({subj_str}), l'argomento interno di V. "
                f"Viene copiato in spec-ST: come effetto collaterale riceve "
                f"Caso nominativo, ma conserva il ruolo di <b>tema</b> "
                f"assegnatogli da V.",
                st_full
            ))

        return steps

    # ── PASSIVO ──────────────────────────────────────────────────────────────
    if passive:
        subj_dp = build_dp(subj_token, tokens, index=subj_index,
                           color=subj_color) if subj_token else None

        # Passo 1: SD argomento interno
        if subj_dp:
            steps.append(make_step(
                "Merge: SD argomento interno",
                f"Costruiamo SD({subj_str}). "
                f"Nel passivo questo elemento nasce come argomento interno di V "
                f"e riceve subito il ruolo tematico di <b>paziente</b>.",
                deepcopy(subj_dp)
            ))

        # Passo 2: SV
        v_node = Node("V", is_head=True, color=v_color)
        v_word = Node(verb_form, word=verb_form, is_head=True, color=v_color)
        v_node.children = [v_word]
        t_subj_inner = Node("t", word="t", index=subj_index, is_trace=True,
                            is_head=True, color=subj_color)
        sv = Node("SV")
        sv.children = [v_node, t_subj_inner]
        steps.append(make_step(
            "Merge esterno: V + SD → SV",
            f"V('{verb_form}') si unisce a SD({subj_str}). "
            f"V assegna il ruolo tematico di <b>paziente</b> a SD.",
            sv
        ))

        # Passo 3: Sv defettivo
        v_little = Node("v", is_head=True)
        v_pass = Node("[+pass]", word="[+pass]", is_head=True)
        v_little.children = [v_pass]
        v_prime = Node("v'")
        v_prime.children = [v_little, sv]
        sv_shell = Node("Sv")
        sv_shell.children = [v_prime]

        agent_str = f"'{agent_token['form']}'" if agent_token else "un agente"
        steps.append(make_step(
            "Merge: v[+pass] + SV → Sv",
            f"v porta il tratto [+pass] che <b>sopprime l'argomento esterno</b>: "
            f"spec-Sv rimane vuoto e nessun ruolo di agente viene assegnato. "
            f"L'eventuale agente ({agent_str}) entrerà solo come aggiunto opzionale.",
            sv_shell
        ))

        # Passo 4: aggiunto agentivo
        if agent_token:
            case_t = next((t for t in tokens
                           if t["deprel"] == "case"
                           and t["head"] == agent_token["id"]), None)
            if case_t:
                pp_agent = build_pp(case_t, agent_token, tokens)
                sv_outer = Node("Sv")
                sv_outer.children = [sv_shell, pp_agent]
                steps.append(make_step(
                    f"Merge: aggiunto agentivo SP",
                    f"SP('{case_t['form']} {agent_token['form']}') entra come "
                    f"<b>aggiunto</b> a Sv (non come argomento): "
                    f"struttura a sdoppiamento Sv → Sv + SP. "
                    f"L'agente non riceve il ruolo da v (che è defettivo) "
                    f"ma è introdotto dalla preposizione.",
                    sv_outer
                ))
                sv_shell = sv_outer

        # Passo 5: SAsp
        if aux_pass:
            asp_p = Node("SAsp")
            asp = Node("Asp", is_head=True)
            asp_word = Node(aux_pass["form"], word=aux_pass["form"], is_head=True)
            asp.children = [asp_word]
            asp_p.children = [asp, sv_shell]
            steps.append(make_step(
                f"Merge: Asp('{aux_pass['form']}') + Sv → SAsp",
                f"'{aux_pass['form']}' occupa la testa Asp e introduce "
                f"l'aspetto perfettivo passivo.",
                asp_p
            ))
            main_compl = asp_p
        else:
            main_compl = sv_shell

        # Passo 6: T
        t_node = Node("T", is_head=True)
        t_w = Node(aux_t["form"] if aux_t else "∅",
                   word=aux_t["form"] if aux_t else "∅", is_head=True)
        t_node.children = [t_w]
        t_prime = Node("T'")
        t_prime.children = [t_node, main_compl]
        st_no_spec = Node("ST")
        st_no_spec.children = [t_prime]
        steps.append(make_step(
            "Merge: T + SAsp → ST",
            f"T('{aux_t['form'] if aux_t else 'è'}') porta uNum. "
            f"spec-ST è ancora vuoto: T cerca l'elemento con iNum "
            f"più vicino che lo c-comandi.",
            st_no_spec
        ))

        # Passo 7: soggetto sale a spec-ST
        if subj_dp:
            st_full = Node("ST")
            st_full.children = [deepcopy(subj_dp), deepcopy(t_prime)]
            steps.append(make_step(
                f"Merge interno: {subj_str} → spec-ST",
                f"T porta uNum. L'elemento con iNum più vicino e c-comandato da T "
                f"è SD({subj_str}), l'argomento interno. "
                f"Viene copiato in spec-ST per valutare uNum: "
                f"come effetto collaterale riceve Caso nominativo, "
                f"ma conserva il ruolo di <b>paziente</b> assegnatogli da V "
                f"nella posizione tematica.",
                st_full
            ))

        return steps

    # ── TRANSITIVO (semplice, con ausiliare, ditransitivo, wh) ───────────────

    # Se tipo_verbo=="transitivo" il soggetto esplicito mancava (era postverbale
    # ed è stato convertito in obj): usiamo pro referenziale come soggetto
    if tipo_verbo == "transitivo" and subj_token is None:
        subj_dp = build_pro_node("pro", index=subj_index, color=subj_color)
        subj_str = "'pro'"
    else:
        subj_dp = build_dp(subj_token, tokens, index=subj_index,
                           color=subj_color) if subj_token else None

    larsonian = (wh_obl is not None and wh_case_token is not None
                 and obj_token is not None)

    # Passo 1: SD soggetto
    if subj_dp:
        steps.append(make_step(
            f"Merge: SD soggetto",
            f"Costruiamo SD({subj_str}). "
            f"Questo elemento sarà l'argomento esterno e riceverà "
            f"il ruolo tematico di <b>agente</b> da v.",
            deepcopy(subj_dp)
        ))

    # Passo 2: SD oggetto (se presente)
    if obj_token:
        obj_dp = build_dp(obj_token, tokens)
        steps.append(make_step(
            f"Merge: SD oggetto",
            f"Costruiamo SD({obj_str}). "
            f"Questo elemento sarà l'argomento interno di V "
            f"e riceverà il ruolo tematico di <b>tema/paziente</b>.",
            obj_dp
        ))

    # Passo 3: SV
    v_node = Node("V", is_head=True, color=v_color)
    v_word_node = Node(verb_form, word=verb_form, index=verb_index,
                       is_head=True, color=v_color)
    v_node.children = [v_word_node]

    if larsonian:
        # SV interno: V + t_k
        wh_trace = Node("t", word="t", index=wh_index, is_trace=True,
                        is_head=True, color=wh_color)
        sv_inner = Node("SV")
        sv_inner.children = [v_node, wh_trace]
        steps.append(make_step(
            "Merge esterno: V + t_k → SV interno",
            f"V('{verb_form}') si unisce alla traccia t_k del costituente wh "
            f"(posizione dell'argomento indiretto). "
            f"V assegna il ruolo tematico di <b>meta/beneficiario</b>.",
            sv_inner
        ))
        # V' esterno (testa con traccia + SV interno)
        v_inner2 = Node("V", is_head=True, color=v_color)
        t_v2 = Node("t", word="t", index=verb_index, is_trace=True,
                    is_head=True, color=v_color)
        v_inner2.children = [t_v2]
        v_prime_out = Node("V'")
        v_prime_out.children = [v_inner2, sv_inner]
        steps.append(make_step(
            "Proiezione: V' esterno",
            f"V' si forma unendo la testa V (con traccia t_i) e il SV interno. "
            f"V' è la proiezione intermedia che domina i due SV annidati.",
            v_prime_out
        ))
        # SV esterno con spec
        obj_dp2 = build_dp(obj_token, tokens)
        sv_outer = Node("SV")
        sv_outer.children = [obj_dp2, v_prime_out]
        steps.append(make_step(
            "Merge esterno: SD(obj) in spec-SV → SV larsoneano",
            f"SD({obj_str}) entra in spec-SV esterno tramite Merge esterno. "
            f"SD({obj_str}) c-comanda l'argomento indiretto nel SV interno. "
            f"V assegna il ruolo di <b>tema</b> a SD({obj_str}).",
            sv_outer
        ))
        sv_for_shell = sv_outer

    elif obj_token:
        sv = Node("SV")
        sv.children = [v_node, build_dp(obj_token, tokens)]
        steps.append(make_step(
            f"Merge esterno: V + SD → SV",
            f"V('{verb_form}') si unisce a SD({obj_str}). "
            f"V assegna il ruolo tematico di <b>tema/paziente</b> a SD({obj_str}). "
            f"V ha però ancora un ruolo tematico da assegnare — il ruolo di <b>agente</b> — "
            f"quindi la proiezione non si ferma qui: continuerà verso Sv.",
            sv
        ))
        sv_for_shell = sv
    else:
        sv = Node("SV")
        sv.children = [v_node]
        steps.append(make_step(
            "Merge: V → SV",
            f"V('{verb_form}') proietta SV. Non c'è argomento interno.",
            sv
        ))
        sv_for_shell = sv

    # Passo: V sale a v — prima mostriamo v' da solo
    v_little = Node("v", is_head=True, color=v_color)
    # In questo passo il verbo è appena arrivato in v: mostriamo sempre
    # la forma fonetica (la traccia in v appare solo quando sale a T)
    v_word2 = Node(verb_form, word=verb_form, index=verb_index,
                   is_head=True, color=v_color)
    v_little.children = [v_word2]

    # SV con traccia di V
    sv_with_v_trace = Node("SV")
    if obj_token and not larsonian:
        v_t = Node("V", is_head=True, color=v_color)
        v_t.children = [Node("t", word="t", index=verb_index, is_trace=True,
                             is_head=True, color=v_color)]
        sv_with_v_trace.children = [v_t, build_dp(obj_token, tokens)]
    elif larsonian:
        sv_with_v_trace = sv_for_shell
    else:
        v_t = Node("V", is_head=True, color=v_color)
        v_t.children = [Node("t", word="t", index=verb_index, is_trace=True,
                             is_head=True, color=v_color)]
        sv_with_v_trace.children = [v_t]

    # Prima mostriamo v' (proiezione intermedia, senza spec)
    v_prime = Node("v'")
    v_prime.children = [v_little, sv_with_v_trace]
    steps.append(make_step(
        "Movimento di testa V → v: v'",
        f"Il verbo sale da V a v (movimento di testa). "
        f"Si forma prima la proiezione intermedia v', che unisce la testa v "
        f"{'(con la forma fonetica del participio)' if aux_t else '(con la forma fonetica del verbo)'} "
        f"e SV come complemento. La traccia t_i rimane in V. "
        f"v porta il tratto agentivo [+ag]: potrà assegnare il ruolo di <b>agente</b> "
        f"all'elemento che entrerà in spec-Sv.",
        v_prime
    ))

    # Merge esterno del soggetto in spec-Sv
    sv_shell = Node("Sv")
    if subj_dp:
        sv_shell.children = [deepcopy(subj_dp), deepcopy(v_prime)]
        steps.append(make_step(
            f"Merge esterno: {subj_str} → spec-Sv",
            f"SD({subj_str}) entra in spec-Sv tramite Merge esterno. "
            f"v assegna il ruolo tematico di <b>agente</b> a SD({subj_str}). "
            f"Questo è il punto in cui l'argomento esterno nasce strutturalmente. "
            f"La derivazione non può fermarsi qui: l'espressione è ancora priva "
            f"di informazioni sulla collocazione temporale dell'evento.",
            sv_shell
        ))
    else:
        sv_shell.children = [deepcopy(v_prime)]

    # Aggiunti a Sv
    current = sv_shell
    for obl_t in adj_obl_tokens:
        case_t2 = next((t for t in tokens
                        if t["deprel"] == "case" and t["head"] == obl_t["id"]), None)
        pp = build_pp(case_t2, obl_t, tokens) if case_t2 else build_dp(obl_t, tokens)
        outer = Node("Sv")
        outer.children = [current, pp]
        steps.append(make_step(
            f"Merge: aggiunto SP → Sv",
            f"SP('{obl_t['form']}') entra come aggiunto a Sv: "
            f"struttura a sdoppiamento Sv → Sv + SP.",
            outer
        ))
        current = outer

    for adv_t in advmod_tokens:
        advp = build_advp(adv_t)
        outer = Node("Sv")
        outer.children = [current, advp]
        steps.append(make_step(
            f"Merge: aggiunto SAvv → Sv",
            f"SAvv('{adv_t['form']}') entra come aggiunto a Sv: "
            f"struttura a sdoppiamento Sv → Sv + SAvv.",
            outer
        ))
        current = outer

    sv_final = current

    # T' prima (proiezione intermedia), poi ST senza spec
    # Quando il verbo sale a T, v° deve mostrare la traccia (il verbo è partito)
    def sv_with_v_in_t(sv_node):
        """Sostituisce la forma fonetica in v° con la traccia t_i."""
        sv_copy = deepcopy(sv_node)
        def replace_v_form(node):
            for child in node.children:
                if (child.label == "v" and child.is_head and
                        child.children and child.children[0].word == verb_form
                        and not child.children[0].is_trace):
                    child.children[0] = Node("t", word="t", index=verb_index,
                                             is_trace=True, is_head=True, color=v_color)
                    return True
                if replace_v_form(child):
                    return True
            return False
        replace_v_form(sv_copy)
        return sv_copy

    t_node = Node("T", is_head=True)
    if aux_t:
        t_w = Node(aux_t["form"], word=aux_t["form"], is_head=True)
        t_comment_prime = (f"Si forma T': la testa T('{aux_t['form']}') si unisce a Sv come complemento. "
                           f"Il participio '{verb_form}' è già in v e non sale ulteriormente.")
        t_comment_full  = (f"T' proietta ST. La testa T° porta informazione "
                           f"temporale e il tratto uNum non ancora valorizzato. "
                           f"spec-ST è vuoto: attende il soggetto.")
        sv_for_t = sv_final  # con aux il verbo non è in v°
    else:
        t_w = Node(verb_form, word=verb_form, index=verb_index,
                   is_head=True, color=v_color)
        t_comment_prime = (f"Poiché il verbo deve salire almeno fino a T° "
                           f"(è una caratteristica parametrica dell'italiano), "
                           f"'{verb_form}' sale da v a T (V→v→T). "
                           f"Il risultato di questo merge è il nuovo insieme T', "
                           f"costituito appunto dal verbo che si è risaldato "
                           f"(internal merge) all'insieme precedente (Sv).")
        t_comment_full  = (f"T' proietta ST. La testa T° porta informazione "
                           f"temporale e il tratto uNum non ancora valorizzato. "
                           f"spec-ST è vuoto: attende il soggetto.")
        sv_for_t = sv_with_v_in_t(sv_final)  # v° mostra traccia
    t_node.children = [t_w]

    # T' da sola (senza spec — il passo ST senza spec è eliminato)
    t_prime = Node("T'")
    t_prime.children = [t_node, sv_for_t]
    steps.append(make_step(
        "Movimento di testa → T: T'",
        t_comment_prime,
        t_prime
    ))

    # Passo 7: soggetto sale a spec-ST
    # In sv_final spec-Sv ha ancora il SD vero — sostituiamo con traccia
    if subj_dp:
        # Costruiamo sv_final_with_trace: spec-Sv = traccia
        t_subj_trace = Node("t", word="t", index=subj_index, is_trace=True,
                            is_head=True, color=subj_color)
        sv_with_trace = deepcopy(sv_for_t)
        # Il primo figlio di sv_final (o del suo primo figlio se ci sono aggiunti)
        # è il SD soggetto — lo sostituiamo con la traccia
        def replace_subj_with_trace(node, done=[False]):
            if done[0]: return
            for i, child in enumerate(node.children):
                if (not child.is_trace and child.index == subj_index
                        and child.label in ("SD", "D")):
                    node.children[i] = t_subj_trace
                    done[0] = True
                    return
                replace_subj_with_trace(child, done)
        replace_subj_with_trace(sv_with_trace)

        t_prime_with_trace = Node("T'")
        t_prime_with_trace.children = [t_node, sv_with_trace]
        st_full = Node("ST")
        st_full.children = [deepcopy(subj_dp), t_prime_with_trace]
        steps.append(make_step(
            f"Merge interno: {subj_str} → spec-ST",
            f"SD({subj_str}) viene ricopiato (internal merge) e risaldato a T'. "
            f"Il merge di SD({subj_str}) e T' forma ST. "
            f"Questo merge valuta il tratto uNum su T°: "
            f"da spec-ST SD c-comanda T e i loro tratti di numero si valorizzano a vicenda. "
            f"Come effetto collaterale SD riceve Caso nominativo.",
            st_full
        ))

    # Se non c'era subj_dp ma è transitivo → pro sale comunque a spec-ST
    if not subj_dp and tipo_verbo == "transitivo":
        pro_dp = build_pro_node("pro", index=subj_index, color=subj_color)
        t_prime_pro = Node("T'")
        t_prime_pro.children = [t_node, sv_for_t]
        st_full = Node("ST")
        st_full.children = [pro_dp, t_prime_pro]
        steps.append(make_step(
            f"Merge interno: pro → spec-ST",
            f"T porta uNum. pro porta iNum (soggetto nullo referenziale). "
            f"pro viene copiato in spec-ST per valutare uNum tramite Agree.",
            st_full
        ))

    st_for_cp = st_full if (subj_dp or tipo_verbo == "transitivo") else t_prime

    # Passo 8: movimento wh a spec-SC
    if wh_obl:
        wh_xp = None
        if wh_case_token:
            wh_xp = build_pp(wh_case_token, wh_noun_token, tokens,
                             index=wh_index, color=wh_color)
        else:
            wh_xp = build_dp(wh_noun_token, tokens, index=wh_index,
                             color=wh_color)

        c = Node("C", is_head=True)
        c_word = Node("[+wh]", word="[+wh]", is_head=True)
        c.children = [c_word]
        c_prime = Node("C'")
        c_prime.children = [c, deepcopy(st_for_cp)]
        steps.append(make_step(
            "Proiezione: C'",
            f"C[+wh] si unisce a ST come complemento e forma C'. "
            f"La posizione spec-SC è ancora vuota.",
            c_prime
        ))

        sc = Node("SC")
        sc.children = [wh_xp, deepcopy(c_prime)]
        wh_str = wh_form(tokens)
        steps.append(make_step(
            f"Merge interno: {wh_str} → spec-SC",
            f"C porta il tratto [+wh] non interpretabile (u[wh]). "
            f"Per valutarlo, {wh_str} viene copiato in spec-SC tramite Merge interno. "
            f"Da spec-SC {wh_str} c-comanda C e valuta u[wh]. "
            f"Come effetto collaterale la frase riceve interpretazione interrogativa. "
            f"Rimane una traccia t_{wh_index} nella posizione originaria.",
            sc
        ))

    return steps
