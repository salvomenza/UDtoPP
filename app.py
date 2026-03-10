"""
app.py
Interfaccia web Flask per il generatore di alberi chomskiani.
"""

from flask import Flask, request, jsonify, render_template_string
import requests
import json
from test_conllu import parse_conllu
from ud_to_chomsky import build_tp
from svg_render import tree_to_svg

app = Flask(__name__)

# ── Configurazione UDPipe ────────────────────────────────────────────────────

UDPIPE_URL = "https://lindat.mff.cuni.cz/services/udpipe/api/process"
UDPIPE_MODEL = "italian-isdt-ud-2.10-220711"


# ── HTML template ────────────────────────────────────────────────────────────

HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Alberi Sintattici Chomskiani</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: Georgia, serif;
      background: #f5f0e8;
      color: #2c1e0f;
      min-height: 100vh;
    }

    header {
      background: #2c1e0f;
      color: #fdfaf5;
      padding: 20px 40px;
    }

    header h1 {
      font-size: 1.5em;
      font-weight: normal;
      letter-spacing: 0.05em;
    }

    header p {
      font-size: 0.85em;
      color: #c8b99a;
      margin-top: 4px;
    }

    main {
      max-width: 1000px;
      margin: 40px auto;
      padding: 0 20px;
    }

    .input-section {
      background: #fdfaf5;
      border: 1px solid #d4c9b0;
      border-radius: 8px;
      padding: 24px;
      margin-bottom: 30px;
    }

    .input-section label {
      display: block;
      font-size: 0.9em;
      color: #5a4a3a;
      margin-bottom: 8px;
    }

    .input-row {
      display: flex;
      gap: 10px;
    }

    .input-row input {
      flex: 1;
      padding: 10px 14px;
      font-family: Georgia, serif;
      font-size: 1em;
      border: 1px solid #c8b99a;
      border-radius: 5px;
      background: #fdfaf5;
      color: #2c1e0f;
      outline: none;
    }

    .input-row input:focus {
      border-color: #7a5a3a;
    }

    .input-row button {
      padding: 10px 24px;
      background: #2c1e0f;
      color: #fdfaf5;
      border: none;
      border-radius: 5px;
      font-family: Georgia, serif;
      font-size: 1em;
      cursor: pointer;
      transition: background 0.2s;
    }

    .input-row button:hover {
      background: #5a4a3a;
    }

    .examples {
      margin-top: 12px;
      font-size: 0.82em;
      color: #7a6a5a;
    }

    .examples span {
      cursor: pointer;
      text-decoration: underline;
      margin-right: 12px;
      color: #7a5a3a;
    }

    .examples span:hover { color: #2c1e0f; }

    #status {
      font-size: 0.9em;
      color: #7a5a3a;
      margin-top: 10px;
      min-height: 20px;
      font-style: italic;
    }

    #status.error { color: #c0392b; }

    .tree-section {
      background: #fdfaf5;
      border: 1px solid #d4c9b0;
      border-radius: 8px;
      padding: 24px;
      display: none;
    }

    .tree-section h2 {
      font-size: 1em;
      font-weight: normal;
      color: #5a4a3a;
      margin-bottom: 16px;
      border-bottom: 1px solid #e8e0d0;
      padding-bottom: 8px;
    }

    #svg-container {
      overflow-x: auto;
      text-align: center;
    }

    #svg-container svg {
      max-width: 100%;
      height: auto;
    }

    .actions {
      margin-top: 16px;
      display: flex;
      gap: 10px;
      justify-content: flex-end;
    }

    .actions button {
      padding: 7px 18px;
      background: #fdfaf5;
      color: #2c1e0f;
      border: 1px solid #c8b99a;
      border-radius: 5px;
      font-family: Georgia, serif;
      font-size: 0.9em;
      cursor: pointer;
    }

    .actions button:hover {
      background: #f0e8d8;
    }

    .conllu-section {
      margin-top: 20px;
      display: none;
    }

    .conllu-section h3 {
      font-size: 0.9em;
      color: #5a4a3a;
      margin-bottom: 8px;
    }

    .conllu-section textarea {
      width: 100%;
      height: 180px;
      font-family: monospace;
      font-size: 0.8em;
      padding: 10px;
      border: 1px solid #c8b99a;
      border-radius: 5px;
      background: #f5f0e8;
      color: #2c1e0f;
      resize: vertical;
    }

    .conllu-section .reload-btn {
      margin-top: 8px;
      padding: 7px 18px;
      background: #2c1e0f;
      color: #fdfaf5;
      border: none;
      border-radius: 5px;
      font-family: Georgia, serif;
      font-size: 0.85em;
      cursor: pointer;
    }

    footer {
      text-align: center;
      padding: 30px;
      font-size: 0.78em;
      color: #a89880;
    }
  </style>
</head>
<body>

<header>
  <h1>Generatore di Alberi Sintattici Chomskiani</h1>
  <p>Inserisci una frase italiana per generare la struttura sintattica</p>
</header>

<main>
  <div class="input-section">
    <label for="frase">Frase da analizzare:</label>
    <div class="input-row">
      <input type="text" id="frase" placeholder="Es. I pirati affondano la nave"
             onkeydown="if(event.key==='Enter') genera()">
      <button onclick="genera()">Genera albero</button>
    </div>
    <div class="examples">
      Esempi:
      <span onclick="usa('Marco ama Laura')">Marco ama Laura</span>
      <span onclick="usa('La nave affonda')">La nave affonda</span>
      <span onclick="usa('I pirati affondano la nave')">I pirati affondano la nave</span>
      <span onclick="usa('I pirati hanno affondato la nave')">I pirati hanno affondato la nave</span>
      <span onclick="usa('La nave è stata affondata dai pirati')">La nave è stata affondata dai pirati</span>
    </div>
    <div id="status"></div>
  </div>

  <div class="tree-section" id="tree-section">
    <h2 id="tree-title"></h2>
    <div id="svg-container"></div>
    <div class="actions">
      <button onclick="toggleConllu()">Mostra/modifica analisi</button>
      <button onclick="scaricaSVG()">Scarica SVG</button>
    </div>
    <div class="conllu-section" id="conllu-section">
      <h3>Analisi CoNLL-U (modificabile):</h3>
      <textarea id="conllu-text"></textarea>
      <button class="reload-btn" onclick="rigenera()">Rigenera albero da analisi</button>
    </div>
  </div>
</main>

<footer>
  Strutture chomskiane · X-barra · DP · little v · TP
</footer>

<script>
  let currentSVG = "";
  let currentFrase = "";

  function usa(frase) {
    document.getElementById("frase").value = frase;
    genera();
  }

  function setStatus(msg, error=false) {
    const el = document.getElementById("status");
    el.textContent = msg;
    el.className = error ? "error" : "";
  }

  async function genera() {
    const frase = document.getElementById("frase").value.trim();
    if (!frase) return;
    currentFrase = frase;
    setStatus("Analisi in corso...");
    document.getElementById("tree-section").style.display = "none";

    try {
      const resp = await fetch("/analizza", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({frase: frase})
      });
      const data = await resp.json();

      if (data.error) {
        setStatus("Errore: " + data.error, true);
        return;
      }

      setStatus("");
      currentSVG = data.svg;
      document.getElementById("tree-title").textContent = "«" + frase + "»";
      document.getElementById("svg-container").innerHTML = data.svg;
      document.getElementById("conllu-text").value = data.conllu;
      document.getElementById("tree-section").style.display = "block";
      document.getElementById("conllu-section").style.display = "none";

    } catch(e) {
      setStatus("Errore di connessione: " + e.message, true);
    }
  }

  function toggleConllu() {
    const el = document.getElementById("conllu-section");
    el.style.display = el.style.display === "none" ? "block" : "none";
  }

  async function rigenera() {
    const conllu = document.getElementById("conllu-text").value;
    setStatus("Rigenerazione in corso...");
    try {
      const resp = await fetch("/da_conllu", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({conllu: conllu, frase: currentFrase})
      });
      const data = await resp.json();
      if (data.error) {
        setStatus("Errore: " + data.error, true);
        return;
      }
      setStatus("");
      currentSVG = data.svg;
      document.getElementById("svg-container").innerHTML = data.svg;
    } catch(e) {
      setStatus("Errore: " + e.message, true);
    }
  }

  function scaricaSVG() {
    if (!currentSVG) return;
    const blob = new Blob([currentSVG], {type: "image/svg+xml"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = currentFrase.replace(/ /g, "_") + ".svg";
    a.click();
    URL.revokeObjectURL(url);
  }
</script>
</body>
</html>
"""


# ── API endpoints ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/analizza", methods=["POST"])
def analizza():
    data = request.get_json()
    frase = data.get("frase", "").strip()
    if not frase:
        return jsonify({"error": "Frase vuota"})

    # Chiama UDPipe
    try:
        resp = requests.post(UDPIPE_URL, data={
            "data": frase,
            "model": UDPIPE_MODEL,
            "tokenizer": "",
            "tagger": "",
            "parser": "",
        }, timeout=10)
        result = resp.json()
        conllu = result.get("result", "")
        if not conllu:
            return jsonify({"error": "UDPipe non ha restituito risultati"})
    except Exception as e:
        return jsonify({"error": f"Errore UDPipe: {str(e)}"})

    # Converti e renderizza
    try:
        tokens = parse_conllu(conllu)
        tree = build_tp(tokens)
        svg = tree_to_svg(tree, title=frase)
        return jsonify({"svg": svg, "conllu": conllu})
    except Exception as e:
        return jsonify({"error": f"Errore conversione: {str(e)}"})


@app.route("/da_conllu", methods=["POST"])
def da_conllu():
    """Rigenera l'albero da un CoNLL-U modificato manualmente."""
    data = request.get_json()
    conllu = data.get("conllu", "")
    frase = data.get("frase", "")
    try:
        tokens = parse_conllu(conllu)
        tree = build_tp(tokens)
        svg = tree_to_svg(tree, title=frase)
        return jsonify({"svg": svg})
    except Exception as e:
        return jsonify({"error": str(e)})


# ── Avvio ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Avvio server su http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
