# Generatore di Alberi Sintattici Chomskiani

App didattica per la generazione automatica di alberi sintattici chomskiani a partire da frasi in italiano.

## Funzionalità

- Analisi sintattica via API UDPipe
- Conversione da Universal Dependencies a struttura chomskiana
- Rendering SVG automatico con layout proporzionale
- Supporto per: transitivi, inaccusativi, passivi, interrogative wh, ditransitivi (Larson)
- Aggiunti avverbiali e PP con struttura a sdoppiamento
- Possessivi come specificatori di NP
- Download SVG
- Correzione manuale via CoNLL-U

## Convenzioni teoriche

- X-barra con eliminazione delle proiezioni intermedie a figlio unico
- DP invece di NP (ipotesi del DP)
- little v (vP) tra TP e VP
- TP invece di IP
- Nomi propri e pronomi: DP → D → forma
- Nomi comuni: DP → D' → D + NP → N' → [AP +] N
- Passivo: v [+pass], AspP per participio, aggiunto PP con sdoppiamento vP
- Ditransitivi: struttura larsoneana, oggetto diretto c-comanda oggetto indiretto

## Avvio locale

```bash
pip install -r requirements.txt
python app.py
```

Poi apri http://127.0.0.1:5000

## Struttura

- `app.py` — interfaccia web Flask
- `ud_to_chomsky.py` — convertitore UD → struttura chomskiana
- `svg_render.py` — generatore SVG con layout automatico
- `test_conllu.py` — dati di test e parser CoNLL-U
