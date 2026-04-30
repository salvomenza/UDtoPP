# HANDOFF — UDtoPP nuova architettura derivazionale
## Per uso all'inizio di una nuova chat

---

## Stato attuale del progetto

- **App corrente**: UDtoPP v26.15 / app v26.6
- **Repository**: github.com/salvomenza/UDtoPP
- **Deploy**: Railway
- **Moduli principali attuali**:
  - `ud_to_chomsky.py` — costruzione albero da parse UD
  - `svg_render.py` — rendering SVG con frecce di movimento
  - `adjunct_detector.py` — rilevamento aggiunti
  - `app.py` — interfaccia Flask

---

## Cosa abbiamo progettato in questa sessione

### Nuova versione — architettura derivazionale

Una nuova versione dell'app (da tenere affiancata alla 26.x) che:

1. **Parte comunque da UDPipe** per ottenere tutte le informazioni morfosintattiche sui token (POS, tratti morfologici, dipendenze). UDPipe è insostituibile come fonte di informazioni.

2. **Costruisce la struttura sintattica bottom-up** tramite un motore derivazionale (`deriv_engine.py`) invece di mappare i dipendenti UD direttamente.

3. **Rappresentazione canonica**: ogni stato della derivazione è un JSON ricorsivo:
```python
{
  "label": "TP",
  "head": {
    "form": "mangia",
    "traits": {"finito": True, "uCl": True, "phi": {"num": "sg", "per": 3}},
    "checked": []
  },
  "spec": {
    "label": "DP",
    "form": "pro",
    "traits": {"phi": {"num": "sg", "per": 3}},
    "case": "nom"
  },
  "compl": { "label": "VP", ... },
  "phase": False,
  "checked": [],
  "chain": []
}
```

4. **Tutti i moduli operano su questa struttura**:
   - Il motore derivazionale la costruisce merge per merge
   - Il renderer SVG la interpreta graficamente
   - Il verbalizzatore la racconta in linguaggio naturale
   - Il verificatore la interroga per controllare la derivazione

5. **Serializzazione alternativa** — parentesi etichettate:
```python
def to_bracketed(node):
    # [TP [DP pro] [T' mangia [VP ...]]]
```

6. **Navigazione**: la derivazione viene costruita tutta in automatico, poi l'utente può navigarla avanti/indietro passo per passo (un frame per ogni Merge/Agree/Spell-Out).

---

## Le operazioni derivazionali

```python
def merge_esterno(alfa, beta):
    """Merge di due oggetti distinti dalla workspace"""
    # labeling, assegnazione ruolo theta,
    # controllo subcategorizzazione

def merge_interno(alfa, posizione):
    """Movimento: alfa già nella struttura"""
    # crea copia in posizione di partenza
    # verifica minimalità relativizzata
    # aggiorna catena

def agree(probe, goal):
    """Valorizzazione tratti tra probe e goal"""
    # verifica accessibilità del goal (PIC)
    # valorizza tratti non interpretabili

def spell_out(fase):
    """Trasferimento a PF della fase"""
    # verifica condizione (11) D&R per accordo participiale
    # verifica che tutti i tratti siano valorizzati
    # congela la fase
```

---

## Il verificatore derivazionale

```python
def verify_derivation(root, log):
    checks = [
        check_case_assignment,        # ogni DP ha caso?
        check_epp,                    # Spec,TP occupato?
        check_agree_phi,              # tratti phi valorizzati?
        check_theta_roles,            # tutti i ruoli theta assegnati?
        check_participle_agreement,   # condizione (11) D&R
        check_relativized_minimality, # nessuna violazione RM
        check_pic,                    # PIC rispettata?
        check_pro_licensing,          # pro licenziato da T° finito?
        check_PRO_control,            # PRO ha controllore?
    ]
```

---

## La funzione build_clause (ricorsiva)

```python
def build_clause(tokens, params):
    """
    Parametri ricevuti dal chiamante:
    - finito: bool
    - tipo: 'dichiarativa'|'relativa'|'interrogativa'|
             'completiva'|'infinitiva'|'gerundiva'|'scissa'
    - controllore_PRO: SO | None
    - forza: 'dichiarativa'|'interrogativa'|'esclamativa'
    - operatore: token | None  (per relative)
    - fase_superiore: SO | None  (per PIC)
    """
    # 1. Merge bottom-up: VP prima
    # 2. ApplP se necessario
    # 3. PartP se forma composta
    # 4. NegP2 se mica/affatto
    # 5. ClP se clitici
    # 6. TP con pro/PRO in Spec
    # 7. NegP1 se non
    # 8. FinP
    # 9. FocP se necessario
    # 10. TopP* se necessario
    # 11. ForceP
    # Per ogni subordinata: chiamata ricorsiva con params aggiornati
    verify_derivation(workspace, derivation_log)
    return workspace.root, derivation_log
```

---

## La spine della geometria

```
ForceP
  TopP*              ← topic (se presente)
    FocP_alta        ← focus contrastivo / wh- (se presente)
      FinP
        NegP1        ← "non" in Neg1° (testa; Zanuttini 1997)
          TP
            Spec,TP  ← pro (sempre; Moro 1997) o PRO (infinitive/gerundive)
            T°       ← verbo flesso; ausiliare; copula (da V°); [uCl] se finito
            ClP      ← se presente clitico
              Spec,ClP
              Cl°
              PartP  ← solo forme composte; defettiva se V° non ha [+acc]
                Part°
                NegP2  ← "mica" in Spec,Neg2P (Zanuttini 1997)
                  FocP_bassa ← solo strutture copulari (se presente)
                    VP
                      V°  ← verbo lessicale / copula / V[+pass]
                      XP  ← complemento (DP, FR, small-CP, ApplP...)
```

**Regola generale**: ogni proiezione si attiva solo se c'è materiale che la necessita.

---

## Decisioni teoriche chiave (riferimento rapido)

- **pro in Spec,TP sempre** (Moro 1997, principio 113)
- **PRO in Spec,TP** delle frasi non finite (infinitive, gerundive)
- **Accordo participiale**: condizione (11) D'Alessandro & Roberts (2008) — Spec,PartP eliminata
- **Copula nasce in V°** e sale a T° — crea FocP basso nella periferia vP
- **Inaccusativi/inergativi**: distinzione nei tratti di V°[+acc], non nella posizione
- **Dislocazione**: unico meccanismo, base-generation in TopP, resumptivo pro o clitico
- **Scisse**: small-CP ridotta (Force assente, "che" in Fin°); focalizzato in FocP basso o alto
- **NegP1**: "non" testa sopra TP; **NegP2**: "mica" specificatore sotto PartP (Zanuttini 1997)
- **Si**: tre tipi — impersonale/passivante (aspettuale, D'Alessandro 2007), riflessivo/dativo (argomentale), inerente/lessicale (incorporato in V°)
- **Ausiliare**: tratto lessicale di V° — V°[+essere] / V°[+avere]
- **Selezione dell'ausiliare**: tratto lessicale di V°
- **Clitico**: nasce in VP come XP, Spec,ClP, poi head movement a T°[uCl]
- **Enclisi**: T°-inf/ger privo di [uCl] — clitico resta in Spec,ClP
- **Aggiunti**: posizione sempre decisa interattivamente dall'utente (regola invariante dell'app)

---

## Documenti di riferimento disponibili

- `geometria_frase_italiana.md` — documento teorico completo consolidato
- `ud_to_chomsky_v26.15.py` — modulo attuale da tenere come riferimento
- `app_v26.6.py` — app Flask attuale

---

## Specifiche sul rendering e sulla ricorsività

### Il rendering è una derivazione continua navigabile

- La derivazione è **una sola sequenza continua di operazioni** — merge per merge, Agree per Agree, Spell-Out per Spell-Out — dalla prima foglia lessicale fino alla ForceP finale
- L'utente può **navigare avanti e indietro** tra i frame (come un video con controlli)
- Non esistono "albero parziale" e "albero finale" come oggetti separati: sono semplicemente frame diversi della stessa derivazione
- Ogni frame mostra lo stato corrente dell'albero + le operazioni appena avvenute

### Le linee blu per le relazioni teoriche

In aggiunta alle frecce rosse/arancioni di movimento già presenti, aggiungere **linee blu** che mostrano:
- **Assegnazione del caso**: da T° o V° o P° al DP che riceve il caso — appare nel frame in cui T° o V° entra nella derivazione
- **Agree phi**: tra probe e goal — appare nel frame in cui l'Agree scatta
- **Valorizzazione dei tratti**: [uCl], [uNum], [uPers], [uGen] — appare nel frame corretto
- **Condizione (11) D&R**: tra Part° e il suo goal — appare al momento dello Spell-Out della fase
- Le linee blu appaiono **esattamente nel momento della derivazione in cui la teoria le predice** — non tutte insieme alla fine

### La ricorsività delle subordinate

- `build_clause` è l'unica funzione per costruire qualsiasi clausola — principale o subordinata
- Le relative, le completive, le infinitive, le gerundive, le scisse chiamano **la stessa funzione** con parametri diversi passati dal chiamante
- Parametri chiave passati dal chiamante:
  - `finito`: bool — determina pro vs PRO, proclisi vs enclisi, T°[uCl] o no
  - `tipo`: 'dichiarativa'|'relativa'|'interrogativa'|'completiva'|'infinitiva'|'gerundiva'|'scissa'
  - `controllore_PRO`: SO | None — per le infinitive/gerundive
  - `operatore`: token | None — per le relative (operatore e sua funzione grammaticale)
  - `forza`: 'dichiarativa'|'interrogativa'|'esclamativa'
  - `fase_superiore`: SO | None — per la PIC
- Il rendering delle subordinate è **continuo** — non è un sotto-albero separato ma una parte della stessa derivazione principale

## Prossimi passi concreti (priorità)

1. **Struttura dati**: definire il JSON canonico per i nodi dell'albero e la classe `SO` (oggetto sintattico)
2. **Lexicon**: costruire il modulo lessicale che arricchisce i token UDPipe con tratti teorici
3. **Motore derivazionale**: implementare `merge_esterno`, `merge_interno`, `agree`, `spell_out`
4. **build_clause ricorsiva**: implementare la funzione principale con i parametri
5. **Verificatore**: implementare i check derivazionali
6. **Renderer**: adattare `svg_render.py` per interpretare il JSON canonico passo per passo
7. **Verbalizzatore**: modulo che racconta la derivazione in linguaggio naturale
8. **Interfaccia**: navigazione avanti/indietro tra i frame della derivazione

---

## Convenzioni di nomenclatura

- Etichette proiezioni: `TP`, `VP`, `ClP`, `PartP`, `NegP1`, `NegP2`, `FocP_alta`, `FocP_bassa`, `TopP`, `ForceP`, `FinP`, `ApplP`, `FR`, `small_CP`
- Tratti: dizionari Python con chiavi stringa — `{'finito': True, 'uCl': True, 'acc': True, ...}`
- Nodi: dizionari ricorsivi con chiavi `label`, `head`, `spec`, `compl`, `traits`, `checked`, `phase`, `chain`
- Versione nuova: `deriv_engine.py` + `app_deriv.py` — affiancati alla versione 26.x

---

## Note importanti per il prossimo Claude

- Salvo ha profonda expertise in sintassi minimalista e cartografia — corregge sempre le assunzioni teoriche errate. Non pre-decidere scelte teoriche che spettano a lui.
- La regola invariante: gli aggiunti vengono sempre classificati interattivamente dall'utente (argomento vs aggiunto, posizione di base).
- Il riferimento teorico primario è Donati per la grammatica generativa, con la geometria sviluppata in questa sessione.
- Tenere sempre presente `ud_to_chomsky.py` attuale — molte decisioni implementative lì discusse rimangono valide.
- Lo sviluppo è iterativo con versioni numerate esplicite ad ogni step.
