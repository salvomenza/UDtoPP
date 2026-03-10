"""
svg_render.py
Genera SVG da un albero chomskiano (Node).

Layout:
- Ogni nodo occupa una larghezza proporzionale al numero di foglie nel suo sottoalbero
- I livelli sono separati da un'altezza fissa (LEVEL_HEIGHT)
- Le etichette strutturali sono in bold, i terminali in italic
- Indici in pedice (offset y +8, font-size 10)
- Convenzioni colori da INDEX_COLORS
"""

from ud_to_chomsky import Node, INDEX_COLORS

# ── Parametri di layout ──────────────────────────────────────────────────────

LEVEL_HEIGHT = 60       # distanza verticale tra livelli
LEAF_WIDTH   = 100      # larghezza minima per foglia terminale
MARGIN_X     = 60       # margine orizzontale
MARGIN_Y     = 50       # margine verticale
FONT_SIZE    = 15       # dimensione font nodi strutturali
TERM_FONT    = 14       # dimensione font terminali
INDEX_FONT   = 10       # dimensione font indici


# ── Calcolo larghezze ────────────────────────────────────────────────────────

def count_leaves(node):
    """Conta le foglie terminali nel sottoalbero."""
    if not node.children:
        return 1
    return sum(count_leaves(c) for c in node.children)


def assign_x(node, x_start, x_end):
    """
    Assegna la coordinata x centrale a ogni nodo
    distribuendo lo spazio proporzionalmente alle foglie.
    """
    node._x = (x_start + x_end) / 2
    if not node.children:
        return
    total_leaves = count_leaves(node)
    cursor = x_start
    for child in node.children:
        child_leaves = count_leaves(child)
        child_width = (child_leaves / total_leaves) * (x_end - x_start)
        assign_x(child, cursor, cursor + child_width)
        cursor += child_width


def assign_y(node, depth=0):
    """Assegna la coordinata y in base alla profondità."""
    node._y = MARGIN_Y + depth * LEVEL_HEIGHT
    for child in node.children:
        assign_y(child, depth + 1)


def max_y(node):
    """Trova la y massima nell'albero."""
    y = node._y
    for child in node.children:
        y = max(y, max_y(child))
    return y


def max_x(node):
    """Trova la x massima nell'albero."""
    x = node._x
    for child in node.children:
        x = max(x, max_x(child))
    return x


# ── Rendering SVG ────────────────────────────────────────────────────────────

def render_node(node, elements):
    """
    Genera gli elementi SVG per un nodo e i suoi rami verso i figli.
    Riempie la lista `elements` con stringhe SVG.
    """
    x, y = node._x, node._y
    color = node.color or "#2c1e0f"

    # ── Etichetta nodo ───────────────────────────────────────────────────────
    if not node.children:
        # Terminale: italic
        if node.is_trace:
            # Traccia: t in italic + pedice indice
            elements.append(
                f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
                f'font-size="{TERM_FONT}" font-style="italic" fill="{color}">'
                f't</text>'
            )
            if node.index:
                elements.append(
                    f'<text x="{x+8:.1f}" y="{y+8:.1f}" text-anchor="start" '
                    f'font-size="{INDEX_FONT}" font-style="italic" fill="{color}">'
                    f'{node.index}</text>'
                )
        else:
            # Terminale normale
            elements.append(
                f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
                f'font-size="{TERM_FONT}" font-style="italic" fill="{color}">'
                f'{node.word}</text>'
            )
    else:
        # Nodo strutturale: bold
        # Label principale
        label = node.label
        elements.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
            f'font-size="{FONT_SIZE}" font-weight="bold" fill="{color}">'
            f'{label}</text>'
        )
        # Indice in pedice se presente
        if node.index and not node.is_trace:
            # stima larghezza label per posizionare pedice
            label_w = len(label) * FONT_SIZE * 0.6
            elements.append(
                f'<text x="{x + label_w/2 + 2:.1f}" y="{y + 8:.1f}" '
                f'text-anchor="start" font-size="{INDEX_FONT}" '
                f'font-style="italic" fill="{color}">'
                f'{node.index}</text>'
            )

    # ── Linee verso i figli ──────────────────────────────────────────────────
    for child in node.children:
        cx, cy = child._x, child._y
        # offset: parti sotto il testo del padre, arriva sopra il testo del figlio
        y_from = y + 6
        y_to   = cy - 16 if child.children else cy - 14

        elements.append(
            f'<line x1="{x:.1f}" y1="{y_from:.1f}" '
            f'x2="{cx:.1f}" y2="{y_to:.1f}" '
            f'stroke="#5a4a3a" stroke-width="1.5"/>'
        )
        render_node(child, elements)


def tree_to_svg(root, title=None):
    """
    Prende un Node radice e restituisce una stringa SVG completa.
    """
    # 1. Calcola larghezza totale dalle foglie
    n_leaves = count_leaves(root)
    total_width = max(n_leaves * LEAF_WIDTH, 400)

    # 2. Assegna coordinate
    assign_x(root, MARGIN_X, total_width - MARGIN_X)
    assign_y(root, depth=0)

    # 3. Calcola viewBox
    view_w = total_width + MARGIN_X * 2
    view_h = max_y(root) + MARGIN_Y + 30

    # 4. Genera elementi
    elements = []
    render_node(root, elements)

    # 5. Assembla SVG
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {view_w:.0f} {view_h:.0f}" '
        f'style="background:#fdfaf5; font-family: Georgia, serif;">'
    ]
    if title:
        svg_parts.append(
            f'<text x="{view_w/2:.0f}" y="20" text-anchor="middle" '
            f'font-size="13" fill="#888" font-style="italic">{title}</text>'
        )
    svg_parts.extend(elements)
    svg_parts.append('</svg>')

    return "\n".join(svg_parts)


# ── Test ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    from test_conllu import CONLLU_SAMPLES, parse_conllu
    from ud_to_chomsky import build_tp

    os.makedirs("output_svg", exist_ok=True)

    for sentence, conllu in CONLLU_SAMPLES.items():
        tokens = parse_conllu(conllu)
        tree = build_tp(tokens)
        svg = tree_to_svg(tree, title=sentence)
        fname = sentence.replace(" ", "_").lower() + "_auto.svg"
        fpath = f"output_svg/{fname}"
        with open(fpath, "w") as f:
            f.write(svg)
        print(f"Salvato: {fpath}")
