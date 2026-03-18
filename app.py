# ver. 21
"""
app.py
Interfaccia web Flask per il generatore di alberi chomskiani.
"""

from flask import Flask, request, jsonify, render_template_string
import requests
import json
from datetime import datetime

VERSION = "0.21"
BUILD_DATE = datetime.now().strftime("%d/%m/%Y")
BUILD_TIME = datetime.now().strftime("%H:%M")
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
  <title>Analizzatore sintattico · UniCT · v{{ version }}</title>
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

    .descrizione {
      font-size: 0.88em;
      color: #5a4a3a;
      margin-bottom: 14px;
      line-height: 1.6;
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
  <div class="version">v{{ version }} &middot; aggiornato il {{ build_date }} alle {{ build_time }}</div>
</header>

<main>
  <div class="input-section">
    <p class="descrizione">Inserisci una frase: UDPipe la analizza secondo Universal Dependencies, poi lo strumento converte l'analisi in una rappresentazione di tipo generativista.</p>
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

  <!-- Dialogo inergativo/inaccusativo -->
  <div id="modal-iner" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%;
       background:rgba(0,0,0,0.45); z-index:1000; align-items:center; justify-content:center;">
    <div style="background:#fff8f0; border-radius:8px; padding:28px 32px; max-width:420px;
                box-shadow:0 4px 24px rgba(0,0,0,0.18); font-family:Georgia,serif;">
      <p style="margin:0 0 20px; font-size:1.05em; color:#2c1e0f; line-height:1.6;">
        Il verbo <strong id="modal-iner-verbo"></strong> è inaccusativo?
      </p>
      <p style="margin:0 0 20px; font-size:0.9em; color:#5a4a3a; line-height:1.5;">
        <em>Inaccusativo</em>: soggetto = tema/paziente, seleziona <em>essere</em> (es. <em>arrivare, cadere, nascere</em>).<br>
        <em>Inergativo</em>: soggetto = agente, seleziona <em>avere</em> (es. <em>correre, dormire, parlare</em>).
      </p>
      <div style="display:flex; gap:12px; flex-wrap:wrap;">
        <button onclick="scegliInerg('inaccusativo')"
          style="flex:1; padding:12px; background:#3a5a7a; color:#fff; border:none;
                 border-radius:5px; cursor:pointer; font-size:1em;">
          Sì, inaccusativo
        </button>
        <button onclick="scegliInerg('inergativo')"
          style="flex:1; padding:12px; background:#7a5a3a; color:#fff; border:none;
                 border-radius:5px; cursor:pointer; font-size:1em;">
          No, inergativo
        </button>
      </div>
    </div>
  </div>

  <!-- Dialogo transitivo/inaccusativo -->
  <div id="modal-tipo" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%;
       background:rgba(0,0,0,0.45); z-index:1000; align-items:center; justify-content:center;">
    <div style="background:#fff8f0; border-radius:8px; padding:28px 32px; max-width:420px;
                box-shadow:0 4px 24px rgba(0,0,0,0.18); font-family:Georgia,serif;">
      <p style="margin:0 0 20px; font-size:1.05em; color:#2c1e0f; line-height:1.6;">
        Il verbo <strong id="modal-verbo"></strong> è transitivo?
      </p>
      <div style="display:flex; gap:12px; flex-wrap:wrap;">
        <button onclick="scegliTipo('transitivo')"
          style="flex:1; padding:12px; background:#7a5a3a; color:#fff; border:none;
                 border-radius:5px; cursor:pointer; font-size:1em;">
          Sì
        </button>
        <button onclick="scegliTipo('inaccusativo')"
          style="flex:1; padding:12px; background:#3a5a7a; color:#fff; border:none;
                 border-radius:5px; cursor:pointer; font-size:1em;">
          No
        </button>
      </div>
    </div>
  </div>

  <div class="tree-section" id="tree-section">
    <h2 id="tree-title"></h2>
    <div class="tab-row">
      <button class="tab-btn active" id="tab-chomsky" onclick="switchTab('chomsky')">Generative</button>
      <button class="tab-btn" id="tab-ud" onclick="switchTab('ud')">UDPipe</button>
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

  let _pendingConllu = null;
  let currentTipoVerbo = null;
  let _pendingIner = null;

  async function genera(tipoVerbo) {
    const frase = document.getElementById("frase").value.trim();
    if (!frase) return;
    currentFrase = frase;
    currentTipoVerbo = tipoVerbo || null;
    steps = [];
    currentStep = 0;
    setStatus("Analisi in corso...");
    document.getElementById("tree-section").style.display = "none";

    try {
      const payload = {frase: frase};
      if (tipoVerbo) payload.tipo_verbo = tipoVerbo;
      if (_pendingConllu) payload.conllu = _pendingConllu;

      const resp = await fetch("/analizza", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      const data = await resp.json();

      if (data.error) {
        setStatus("Errore: " + data.error, true);
        return;
      }

      // Il server chiede di disambiguare inergativo/inaccusativo
      if (data.chiedi_iner) {
        _pendingIner = data.conllu;
        setStatus("");
        document.getElementById("modal-iner-verbo").textContent = data.verbo;
        const modal = document.getElementById("modal-iner");
        modal.style.display = "flex";
        return;
      }

      // Il server chiede di disambiguare transitivo/inaccusativo
      if (data.chiedi_tipo) {
        _pendingConllu = data.conllu;
        setStatus("");
        document.getElementById("modal-verbo").textContent = data.verbo;
        const modal = document.getElementById("modal-tipo");
        modal.style.display = "flex";
        return;
      }

      _pendingConllu = null;
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

  function scegliInerg(tipo) {
    document.getElementById("modal-iner").style.display = "none";
    currentTipoVerbo = tipo;
    steps = [];
    currentStep = 0;
    genera(tipo, _pendingIner);
    _pendingIner = null;
  }

  function scegliTipo(tipo) {
    document.getElementById("modal-tipo").style.display = "none";
    currentTipoVerbo = tipo;
    steps = [];  // resetta passi precedenti
    genera(tipo);
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
        body: JSON.stringify({conllu: conllu, frase: frase, tipo_verbo: currentTipoVerbo})
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
    """
    Genera un SVG ad albero di dipendenza top-down dal CoNLL-U.
    Root in alto, figli sotto, etichette deprel sugli archi.
    """
    if not tokens:
        return ""

    # ── Costruzione struttura ad albero ──────────────────────────────────────
    children = {t["id"]: [] for t in tokens}
    children[0] = []  # root virtuale
    for t in tokens:
        children[t["head"]].append(t["id"])

    root_id = next(t["id"] for t in tokens if t["deprel"] == "root")
    tok_by_id = {t["id"]: t for t in tokens}

    # ── Layout: calcola x per ogni nodo con DFS ───────────────────────────────
    NODE_W = 90
    NODE_H = 44
    LEVEL_H = 80
    PAD = 30

    # Assegna posizioni x a ogni nodo in base ai figli (in-order)
    x_pos = {}
    leaf_counter = [0]

    def assign_x(nid):
        kids = children.get(nid, [])
        if not kids:
            x_pos[nid] = leaf_counter[0] * NODE_W + NODE_W // 2 + PAD
            leaf_counter[0] += 1
        else:
            for kid in kids:
                assign_x(kid)
            x_pos[nid] = (x_pos[kids[0]] + x_pos[kids[-1]]) / 2

    assign_x(root_id)

    # Calcola profondità di ogni nodo
    depth = {}
    def assign_depth(nid, d):
        depth[nid] = d
        for kid in children.get(nid, []):
            assign_depth(kid, d + 1)
    assign_depth(root_id, 0)

    max_depth = max(depth.values()) if depth else 0
    n_leaves = leaf_counter[0]
    width  = max(500, n_leaves * NODE_W + PAD * 2)
    height = (max_depth + 1) * LEVEL_H + NODE_H + PAD * 2 + 30

    out = []
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" ')
    out.append('style="font-family:Georgia,serif;background:#fdfaf5;" overflow="visible">')
    out.append('<defs><marker id="udarr" markerWidth="7" markerHeight="7" refX="3.5" refY="3.5" orient="auto">')
    out.append('<circle cx="3.5" cy="3.5" r="2.5" fill="#7a5a3a"/></marker></defs>')

    def nx(nid): return x_pos[nid]
    def ny(nid): return PAD + depth[nid] * LEVEL_H + NODE_H // 2

    # ── Archi ────────────────────────────────────────────────────────────────
    all_ids = list(depth.keys())
    for nid in all_ids:
        for kid in children.get(nid, []):
            x1, y1 = nx(nid), ny(nid) + NODE_H // 2
            x2, y2 = nx(kid), ny(kid) - NODE_H // 2
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            deprel = tok_by_id[kid]["deprel"]
            out.append(f'<line x1="{x1:.1f}" y1="{y1}" x2="{x2:.1f}" y2="{y2}" ')
            out.append(f'stroke="#b0956a" stroke-width="1.5" marker-end="url(#udarr)"/>')
            out.append(f'<text x="{mx:.1f}" y="{my - 3}" text-anchor="middle" ')
            out.append(f'font-size="10" fill="#7a5a3a" font-style="italic">{deprel}</text>')

    # ── Nodi ────────────────────────────────────────────────────────────────
    for nid in all_ids:
        tok = tok_by_id[nid]
        x, y = nx(nid), ny(nid)
        is_root = (tok["deprel"] == "root")
        fill   = "#e8f0e8" if is_root else "#f5f0e8"
        stroke = "#6a9a6a" if is_root else "#c8b99a"
        sw     = "2"       if is_root else "1.2"
        out.append(f'<rect x="{x - NODE_W//2 + 5:.1f}" y="{y - NODE_H//2}" ')
        out.append(f'width="{NODE_W - 10}" height="{NODE_H}" rx="5" ')
        out.append(f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
        out.append(f'<text x="{x:.1f}" y="{y + 5}" text-anchor="middle" ')
        out.append(f'font-size="13" fill="#2c1e0f" font-weight="bold">{tok["form"]}</text>')
        out.append(f'<text x="{x:.1f}" y="{y + 19}" text-anchor="middle" ')
        out.append(f'font-size="10" fill="#7a5a3a" font-style="italic">{tok["upos"]}</text>')

    # ── Parola lineare in basso ───────────────────────────────────────────────
    base_y = height - 20
    for i, tok in enumerate(tokens):
        x = PAD + i * NODE_W + NODE_W // 2
        out.append(f'<text x="{x}" y="{base_y}" text-anchor="middle" ')
        out.append(f'font-size="11" fill="#a89880">{tok["form"]}</text>')

    out.append("</svg>")
    return "".join(out)


def detect_inergativo_inaccusativo(tokens):
    """
    Rileva ambiguità inergativo/inaccusativo per verbi intransitivi
    con soggetto preverbale e nessun oggetto.
    Restituisce {"verbo": ...} se ambiguo, None altrimenti.
    """
    from ud_to_chomsky import VERBI_INACCUSATIVI, _mood, _get_feats
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root:
        return None
    # Solo verbi finiti
    feats = _get_feats(root)
    mood = next((f.split("=")[1] for f in feats.split("|")
                 if f.startswith("Mood=")), None)
    if mood not in ("Ind","Sub","Cnd","Imp"):
        return None
    # Deve avere soggetto preverbale
    nsubj = next(
        (t for t in tokens
         if t["deprel"] in ("nsubj",) and t["head"] == root["id"]
         and t["id"] < root["id"]),
        None
    )
    if not nsubj:
        return None
    # Non deve avere oggetto
    has_obj = any(t["deprel"] == "obj" and t["head"] == root["id"] for t in tokens)
    if has_obj:
        return None
    # Non deve essere passivo
    if any(t["deprel"] == "aux:pass" for t in tokens):
        return None
    # Non deve avere modale
    from ud_to_chomsky import VERBI_MODALI
    if any(t["lemma"] in VERBI_MODALI for t in tokens):
        return None
    # Se già nella lista inaccusativi certi, non chiediamo
    if root["lemma"] in VERBI_INACCUSATIVI:
        return None
    return {"verbo": root["form"]}


def detect_transitivo_inaccusativo(tokens):
    """
    Rileva ambiguità transitivo/inaccusativo.
    Restituisce {"verbo": ..., "sd": ...} se ambiguo, None altrimenti.
    Il caso ambiguo: verbo finito senza nsubj preverbale, con un SD
    postverbale che UDPipe ha marcato come nsubj, e lemma NON nella
    lista inaccusativi certi.
    """
    from ud_to_chomsky import VERBI_INACCUSATIVI, _mood, _get_feats
    root = next((t for t in tokens if t["deprel"] == "root"), None)
    if not root:
        return None
    # Solo verbi finiti
    feats = _get_feats(root)
    mood = next((f.split("=")[1] for f in feats.split("|")
                 if f.startswith("Mood=")), None)
    aux_mood = next(
        (next((f.split("=")[1] for f in _get_feats(t).split("|")
               if f.startswith("Mood=")), None)
         for t in tokens
         if t["upos"] == "AUX" and t["head"] == root["id"]),
        None
    )
    if mood not in ("Ind","Sub","Cnd","Imp") and aux_mood not in ("Ind","Sub","Cnd","Imp"):
        return None
    # Cerca nsubj postverbale
    nsubj = next(
        (t for t in tokens
         if t["deprel"] == "nsubj" and t["head"] == root["id"]
         and t["id"] > root["id"]),
        None
    )
    if not nsubj:
        return None
    # Se il lemma è nella lista inaccusativi certi, non è ambiguo
    if root["lemma"] in VERBI_INACCUSATIVI:
        return None
    # Nessun soggetto preverbale
    has_pre_nsubj = any(
        t["deprel"] == "nsubj" and t["head"] == root["id"] and t["id"] < root["id"]
        for t in tokens
    )
    if has_pre_nsubj:
        return None
    return {"verbo": root["form"], "sd": nsubj["form"]}


# ── API endpoints ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML, version=VERSION, build_date=BUILD_DATE, build_time=BUILD_TIME)


@app.route("/analizza", methods=["POST"])
def analizza():
    data = request.get_json()
    frase = data.get("frase", "").strip()
    tipo_verbo = data.get("tipo_verbo", None)   # "transitivo" | "inaccusativo" | None
    conllu_pre = data.get("conllu", None)        # CoNLL-U già calcolato (secondo round)
    if not frase:
        return jsonify({"error": "Frase vuota"})

    # Usa il CoNLL-U pre-calcolato oppure chiama UDPipe
    ud_svg_native = ""
    if conllu_pre:
        conllu = conllu_pre
    else:
        try:
            resp = requests.post(UDPIPE_URL, data={
                "data": frase,
                "model": UDPIPE_MODEL,
                "tokenizer": "",
                "tagger": "",
                "parser": "",
                "output": "conllu",
            }, timeout=10)
            result = resp.json()
            conllu = result.get("result", "")
            if not conllu:
                return jsonify({"error": "UDPipe non ha restituito risultati"})
        except Exception as e:
            return jsonify({"error": f"Errore UDPipe: {str(e)}"})

        # Seconda chiamata per SVG nativo UDPipe
        try:
            resp_svg = requests.post(UDPIPE_URL, data={
                "data": frase,
                "model": UDPIPE_MODEL,
                "tokenizer": "",
                "tagger": "",
                "parser": "",
                "output": "svg",
            }, timeout=10)
            svg_result = resp_svg.json()
            ud_svg_native = svg_result.get("result", "")
        except Exception:
            ud_svg_native = ""  # fallback silenzioso

    # Converti e renderizza
    try:
        tokens = parse_conllu(conllu)

        # Rilevamento ambiguità inergativo/inaccusativo (soggetto preverbale, no obj)
        if tipo_verbo is None:
            iner_ambiguity = detect_inergativo_inaccusativo(tokens)
            if iner_ambiguity:
                return jsonify({
                    "chiedi_iner": True,
                    "conllu": conllu,
                    "verbo": iner_ambiguity["verbo"],
                })

        # Rilevamento ambiguità transitivo/inaccusativo (soggetto postverbale)
        if tipo_verbo is None:
            ambiguity = detect_transitivo_inaccusativo(tokens)
            if ambiguity:
                return jsonify({
                    "chiedi_tipo": True,
                    "conllu": conllu,
                    "verbo": ambiguity["verbo"],
                    "sd": ambiguity["sd"],
                })

        tree = build_tp(tokens, tipo_verbo=tipo_verbo)
        svg = tree_to_svg(tree, title=frase)
        # Usa SVG nativo UDPipe se disponibile, altrimenti fallback artigianale
        ud_svg = ud_svg_native if ud_svg_native else build_ud_svg(tokens)
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
    tipo_verbo = data.get("tipo_verbo", None)
    try:
        tokens = parse_conllu(conllu)
        # Applica correzione tipo_verbo come in /analizza
        if tipo_verbo == "transitivo":
            root = next((t for t in tokens if t["deprel"] == "root"), None)
            if root:
                for t in tokens:
                    if (t["deprel"] == "nsubj" and t["head"] == root["id"]
                            and t["id"] > root["id"]):
                        t["deprel"] = "obj"
                        break
        steps = generate_steps(tokens, tipo_verbo=tipo_verbo)
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
