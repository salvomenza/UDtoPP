# Output CoNLL-U simulato per frasi di test
# Formato: id, form, lemma, upos, xpos, feats, head, deprel, deps, misc

CONLLU_SAMPLES = {

    "Marco ama Laura": """
# sent_id = 1
# text = Marco ama Laura
1	Marco	Marco	PROPN	SP	_	2	nsubj	_	_
2	ama	amare	VERB	V	Mood=Ind|Number=Sing|Person=3|Tense=Pres	0	root	_	_
3	Laura	Laura	PROPN	SP	_	2	obj	_	SpaceAfter=No
""",

    "La nave affonda": """
# sent_id = 1
# text = La nave affonda
1	La	il	DET	RD	Definite=Def|Gender=Fem|Number=Sing|PronType=Art	2	det	_	_
2	nave	nave	NOUN	S	Gender=Fem|Number=Sing	3	nsubj	_	_
3	affonda	affondare	VERB	V	Mood=Ind|Number=Sing|Person=3|Tense=Pres	0	root	_	SpaceAfter=No
""",

    "I pirati affondano la nave": """
# sent_id = 1
# text = I pirati affondano la nave
1	I	il	DET	RD	Definite=Def|Gender=Masc|Number=Plur|PronType=Art	2	det	_	_
2	pirati	pirata	NOUN	S	Gender=Masc|Number=Plur	3	nsubj	_	_
3	affondano	affondare	VERB	V	Mood=Ind|Number=Plur|Person=3|Tense=Pres	0	root	_	_
4	la	il	DET	RD	Definite=Def|Gender=Fem|Number=Sing|PronType=Art	5	det	_	_
5	nave	nave	NOUN	S	Gender=Fem|Number=Sing	3	obj	_	SpaceAfter=No
""",

    "I pirati hanno affondato la nave": """
# sent_id = 1
# text = I pirati hanno affondato la nave
1	I	il	DET	RD	Definite=Def|Gender=Masc|Number=Plur|PronType=Art	2	det	_	_
2	pirati	pirata	NOUN	S	Gender=Masc|Number=Plur	3	nsubj	_	_
3	hanno	avere	AUX	VA	Mood=Ind|Number=Plur|Person=3|Tense=Pres	0	root	_	_
4	affondato	affondare	VERB	V	Tense=Past|VerbForm=Part	3	aux	_	_
5	la	il	DET	RD	Definite=Def|Gender=Fem|Number=Sing|PronType=Art	6	det	_	_
6	nave	nave	NOUN	S	Gender=Fem|Number=Sing	3	obj	_	SpaceAfter=No
""",

    "La nave è stata affondata dai pirati": """
# sent_id = 1
# text = La nave è stata affondata dai pirati
1	La	il	DET	RD	Definite=Def|Gender=Fem|Number=Sing|PronType=Art	2	det	_	_
2	nave	nave	NOUN	S	Gender=Fem|Number=Sing	5	nsubj:pass	_	_
3	è	essere	AUX	VA	Mood=Ind|Number=Sing|Person=3|Tense=Pres	5	aux	_	_
4	stata	essere	AUX	VA	Gender=Fem|Number=Sing|Tense=Past|VerbForm=Part	5	aux:pass	_	_
5	affondata	affondare	VERB	V	Gender=Fem|Number=Sing|Tense=Past|VerbForm=Part	0	root	_	_
6	da	da	ADP	E	_	8	case	_	_
7	i	il	DET	RD	Definite=Def|Gender=Masc|Number=Plur|PronType=Art	8	det	_	_
8	pirati	pirata	NOUN	S	Gender=Masc|Number=Plur	5	obl:agent	_	SpaceAfter=No
""",
}


def parse_conllu(text):
    """Parsa un blocco CoNLL-U e restituisce lista di token dict."""
    tokens = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 8:
            continue
        # salta i token multi-word (es. 1-2)
        if "-" in fields[0] or "." in fields[0]:
            continue
        tokens.append({
            "id":     int(fields[0]),
            "form":   fields[1],
            "lemma":  fields[2],
            "upos":   fields[3],
            "feats":  fields[5],
            "head":   int(fields[6]),
            "deprel": fields[7],
        })
    return tokens


if __name__ == "__main__":
    for sentence, conllu in CONLLU_SAMPLES.items():
        print(f"\n=== {sentence} ===")
        tokens = parse_conllu(conllu)
        for t in tokens:
            print(f"  {t['id']:2}  {t['form']:12} {t['upos']:6} head={t['head']}  deprel={t['deprel']}")
