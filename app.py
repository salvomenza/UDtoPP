"""
app.py
Interfaccia web Flask per il generatore di alberi chomskiani.
"""

from flask import Flask, request, jsonify, render_template_string
import requests
import json
from datetime import datetime

VERSION = "0.3"
BUILD_DATE = datetime.now().strftime("%d/%m/%Y")
from test_conllu import parse_conllu
from ud_to_chomsky import build_tp
from svg_render import tree_to_svg
from step_generator import generate_steps

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
  <title>Analizzatore sintattico · UniCT</title>
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

    .header-top {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    header h1 {
      font-size: 1.5em;
      font-weight: normal;
      letter-spacing: 0.05em;
    }

    .badge-beta {
      font-size: 0.6em;
      background: #c0392b;
      color: #fff;
      padding: 2px 8px;
      border-radius: 3px;
      letter-spacing: 0.1em;
      font-family: sans-serif;
      vertical-align: middle;
      text-transform: uppercase;
    }

    .badge-didattico {
      font-size: 0.6em;
      background: #7a5a3a;
      color: #fdfaf5;
      padding: 2px 8px;
      border-radius: 3px;
      letter-spacing: 0.08em;
      font-family: sans-serif;
      vertical-align: middle;
    }

    header p {
      font-size: 0.82em;
      color: #c8b99a;
      margin-top: 6px;
      line-height: 1.6;
    }

    header p a {
      color: #e8d8c0;
    }

    header .version {
      font-size: 0.75em;
      color: #a89070;
      margin-top: 3px;
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



    /* ── Tab alberi ── */
    .tab-row {
      display: flex;
      border-bottom: 2px solid #d4c9b0;
      margin-bottom: 16px;
    }

    .tab-btn {
      padding: 8px 22px;
      background: none;
      border: none;
      border-bottom: 3px solid transparent;
      margin-bottom: -2px;
      font-family: Georgia, serif;
      font-size: 0.88em;
      color: #7a6a5a;
      cursor: pointer;
    }

    .tab-btn:hover { color: #2c1e0f; }

    .tab-btn.active {
      color: #2c1e0f;
      border-bottom: 3px solid #2c1e0f;
    }

    .tab-pane { display: none; }
    .tab-pane.active { display: block; }

    /* ── Passo-passo ── */
    .toggle-row {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid #e8e0d0;
    }

    .toggle-label {
      font-size: 0.88em;
      color: #5a4a3a;
    }

    .toggle-switch {
      position: relative;
      width: 42px;
      height: 22px;
    }

    .toggle-switch input { opacity: 0; width: 0; height: 0; }

    .slider {
      position: absolute;
      cursor: pointer;
      top: 0; left: 0; right: 0; bottom: 0;
      background: #c8b99a;
      border-radius: 22px;
      transition: 0.3s;
    }

    .slider:before {
      position: absolute;
      content: "";
      height: 16px; width: 16px;
      left: 3px; bottom: 3px;
      background: white;
      border-radius: 50%;
      transition: 0.3s;
    }

    input:checked + .slider { background: #2c1e0f; }
    input:checked + .slider:before { transform: translateX(20px); }

    #step-panel {
      margin-top: 20px;
      display: none;
      border-top: 1px solid #e8e0d0;
      padding-top: 20px;
    }

    .step-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;
    }

    .step-title {
      font-size: 1em;
      color: #2c1e0f;
      font-weight: bold;
    }

    .step-counter {
      font-size: 0.82em;
      color: #7a6a5a;
    }

    .step-nav {
      display: flex;
      gap: 8px;
      justify-content: center;
      margin-bottom: 16px;
    }

    .step-nav button {
      padding: 6px 20px;
      background: #2c1e0f;
      color: #fdfaf5;
      border: none;
      border-radius: 5px;
      font-family: Georgia, serif;
      font-size: 0.9em;
      cursor: pointer;
    }

    .step-nav button:disabled {
      background: #c8b99a;
      cursor: default;
    }

    .step-nav button:hover:not(:disabled) { background: #5a4a3a; }

    .step-comment {
      background: #f5f0e8;
      border-left: 3px solid #7a5a3a;
      padding: 12px 16px;
      font-size: 0.88em;
      line-height: 1.6;
      color: #2c1e0f;
      margin-bottom: 16px;
      border-radius: 0 5px 5px 0;
    }

    #step-svg-container {
      overflow-x: auto;
      text-align: center;
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
  <div class="header-top">
    <h1>Analizzatore sintattico</h1>
    <span class="badge-beta">beta</span>
    <span class="badge-didattico">strumento didattico</span>
  </div>
  <p>Fatto da Claude con la consulenza e l'insistenza di S. Menza, DiSUm, UniCT &middot;
     <a href="mailto:salvatore.menza@unict.it">salvatore.menza@unict.it</a></p>
  <div class="version">v{{ version }} &middot; aggiornato il {{ build_date }}</div>
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
    <div class="tab-row">
      <button class="tab-btn active" id="tab-chomsky" onclick="switchTab('chomsky')">Albero chomskiano</button>
      <button class="tab-btn" id="tab-ud" onclick="switchTab('ud')">Albero UD</button>
    </div>
    <div class="tab-pane active" id="pane-chomsky">
      <div id="svg-container"></div>
    </div>
    <div class="tab-pane" id="pane-ud">
      <div id="ud-container" style="text-align:center; padding: 10px 0;"></div>
    </div>
    <div class="actions">
      <button onclick="toggleConllu()">Mostra/modifica analisi</button>
      <button onclick="scaricaSVG()">Scarica SVG</button>
    </div>
    <div class="toggle-row">
      <label class="toggle-switch">
        <input type="checkbox" id="toggle-passi" onchange="togglePassi()">
        <span class="slider"></span>
      </label>
      <span class="toggle-label">Modalità passo-passo</span>
    </div>

    <div id="step-panel">
      <div class="step-header">
        <span class="step-title" id="step-title"></span>
        <span class="step-counter" id="step-counter"></span>
      </div>
      <div class="step-comment" id="step-comment"></div>
      <div class="step-nav">
        <button onclick="stepPrev()" id="btn-prev">← Indietro</button>
        <button onclick="stepNext()" id="btn-next">Avanti →</button>
      </div>
      <div id="step-svg-container"></div>
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
  let currentUDSVG = "";
  let currentTab = "chomsky";

  function switchTab(tab) {
    currentTab = tab;
    document.getElementById("pane-chomsky").classList.toggle("active", tab === "chomsky");
    document.getElementById("pane-ud").classList.toggle("active", tab === "ud");
    document.getElementById("tab-chomsky").classList.toggle("active", tab === "chomsky");
    document.getElementById("tab-ud").classList.toggle("active", tab === "ud");
    // nasconde step-panel se si va su UD
    if (tab === "ud") {
      document.getElementById("step-panel").style.display = "none";
      document.getElementById("toggle-passi").checked = false;
    }
  }

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
      currentUDSVG = data.ud_svg || "";
      document.getElementById("tree-title").textContent = "«" + frase + "»";
      document.getElementById("svg-container").innerHTML = data.svg;
      document.getElementById("ud-container").innerHTML = currentUDSVG;
      document.getElementById("conllu-text").value = data.conllu;
      document.getElementById("tree-section").style.display = "block";
      document.getElementById("conllu-section").style.display = "none";
      switchTab("chomsky");

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


  let steps = [];
  let currentStep = 0;

  function togglePassi() {
    const on = document.getElementById("toggle-passi").checked;
    document.getElementById("step-panel").style.display = on ? "block" : "none";
    document.getElementById("svg-container").style.display = on ? "none" : "block";
    if (on && steps.length === 0) {
      caricaPassi();
    } else if (on) {
      mostraStep(currentStep);
    }
  }

  async function caricaPassi() {
    const conllu = document.getElementById("conllu-text").value;
    const frase = currentFrase;
    try {
      const resp = await fetch("/passi", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({conllu: conllu, frase: frase})
      });
      const data = await resp.json();
      if (data.error) { setStatus("Errore passi: " + data.error, true); return; }
      steps = data.steps;
      currentStep = 0;
      mostraStep(0);
    } catch(e) {
      setStatus("Errore: " + e.message, true);
    }
  }

  function mostraStep(i) {
    if (!steps.length) return;
    const s = steps[i];
    document.getElementById("step-title").textContent = s.title;
    document.getElementById("step-comment").innerHTML = s.comment;
    document.getElementById("step-counter").textContent =
      "Passo " + (i + 1) + " di " + steps.length;
    document.getElementById("step-svg-container").innerHTML = s.svg;
    document.getElementById("btn-prev").disabled = i === 0;
    document.getElementById("btn-next").disabled = i === steps.length - 1;
  }

  function stepNext() {
    if (currentStep < steps.length - 1) {
      currentStep++;
      mostraStep(currentStep);
    }
  }

  function stepPrev() {
    if (currentStep > 0) {
      currentStep--;
      mostraStep(currentStep);
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


def build_ud_svg(tokens):
    """Genera un SVG dell'albero di dipendenza UD."""
    if not tokens:
        return ""

    NODE_W = 90
    TOP_MARGIN = 150
    PAD = 20

    n = len(tokens)
    width = max(600, n * NODE_W + PAD * 2)
    height = TOP_MARGIN + 60 + 50

    cx = [PAD + NODE_W // 2 + i * NODE_W for i in range(n)]
    cy = TOP_MARGIN

    out = []
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" style="font-family:Georgia,serif;background:#fdfaf5;">')
    out.append('<defs><marker id="arr" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" fill="#7a5a3a"/></marker></defs>')

    # archi
    for tok in tokens:
        head = tok["head"]
        if head == 0:
            continue
        si = tok["id"] - 1
        di = head - 1
        x1, x2 = cx[si], cx[di]
        mid = (x1 + x2) / 2
        dist = abs(x2 - x1)
        ctrl_y = cy - 30 - dist * 0.35
        ctrl_y = max(ctrl_y, 8)
        dep = tok["deprel"]
        out.append(f'<path d="M {x1} {cy} Q {mid} {ctrl_y} {x2} {cy}" fill="none" stroke="#7a5a3a" stroke-width="1.4" marker-end="url(#arr)"/>')
        out.append(f'<text x="{mid}" y="{ctrl_y - 4}" text-anchor="middle" font-size="10" fill="#5a4a3a">{dep}</text>')

    # nodi
    for i, tok in enumerate(tokens):
        x = cx[i]
        out.append(f'<rect x="{x-38}" y="{cy}" width="76" height="46" rx="5" fill="#f5f0e8" stroke="#c8b99a" stroke-width="1.2"/>')
        out.append(f'<text x="{x}" y="{cy + 18}" text-anchor="middle" font-size="13" fill="#2c1e0f">{tok["form"]}</text>')
        out.append(f'<text x="{x}" y="{cy + 33}" text-anchor="middle" font-size="10" fill="#7a5a3a" font-style="italic">{tok["upos"]}</text>')
        out.append(f'<text x="{x}" y="{cy + 56}" text-anchor="middle" font-size="9" fill="#a89880">{tok["id"]}</text>')

    out.append("</svg>")
    return "\n".join(out)


# ── API endpoints ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML, version=VERSION, build_date=BUILD_DATE)


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
        ud_svg = build_ud_svg(tokens)
        return jsonify({"svg": svg, "conllu": conllu, "ud_svg": ud_svg})
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



@app.route("/passi", methods=["POST"])
def passi():
    """Genera la sequenza di passi passo-passo."""
    data = request.get_json()
    conllu = data.get("conllu", "")
    frase = data.get("frase", "")
    try:
        tokens = parse_conllu(conllu)
        steps = generate_steps(tokens)
        result = []
        for s in steps:
            if s["tree"].word == "…":
                # passo test preliminare: nessun SVG, solo commento
                svg = "<div style=\'text-align:center;padding:40px;color:#7a6a5a;font-style:italic;\'>Leggi il commento prima di procedere.</div>"
            else:
                svg = tree_to_svg(s["tree"], title=None)
            result.append({"title": s["title"], "comment": s["comment"], "svg": svg})
        return jsonify({"steps": result})
    except Exception as e:
        import traceback
        return jsonify({"error": str(e) + "\n" + traceback.format_exc()})


# ── Avvio ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Avvio server su http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
