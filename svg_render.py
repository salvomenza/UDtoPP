# ver. 19
"""
svg_render.py — v18
Frecce di movimento tratteggiate colorate + { } copie + grassetto pronunciati.
"""

from ud_to_chomsky import Node, INDEX_COLORS
from collections import defaultdict

LEVEL_HEIGHT = 60
LEAF_WIDTH   = 100
MARGIN_X     = 60
MARGIN_Y     = 50
FONT_SIZE    = 15
TERM_FONT    = 14
INDEX_FONT   = 10

MOVE_COLORS = {
    "sintagmatico": "#1a7a2a",
    "testa":        "#1a7a2a",
    "soggetto":     "#1a4fa0",
    "verbo":        "#c0392b",
}
MOVE_DASH = {
    "sintagmatico": "6 3",
    "testa":        "3 3",
    "soggetto":     "6 3",
    "verbo":        "6 3",
}


def count_leaves(node):
    if not node.children:
        return 1
    return sum(count_leaves(c) for c in node.children)


def assign_x(node, x_start, x_end):
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
    node._y = MARGIN_Y + depth * LEVEL_HEIGHT
    for child in node.children:
        assign_y(child, depth + 1)


def max_y(node):
    y = node._y
    for child in node.children:
        y = max(y, max_y(child))
    return y


def collect_nodes(node, registry):
    """Raccoglie nodi con movement_type per generare frecce."""
    if getattr(node, "movement_type", None) and node.index:
        key = (node.index, node.movement_type)
        registry[key].append({
            "x": node._x, "y": node._y,
            "is_copy": node.is_copy,
            "is_pronounced": getattr(node, "is_pronounced", False),
        })
    for child in node.children:
        collect_nodes(child, registry)


def generate_arrows(registry):
    arrows = []
    move_types_used = set()

    for (idx, mtype), nodes in registry.items():
        if len(nodes) < 2:
            continue
        color = MOVE_COLORS.get(mtype, "#888")
        dash = MOVE_DASH.get(mtype, "6 3")
        marker = f"arr_{mtype}"
        move_types_used.add(mtype)

        # Ordina per y decrescente: base = più in basso (y più alta)
        nodes_sorted = sorted(nodes, key=lambda n: -n["y"])

        # Frecce successive: A→B, B→C (non A→B e A→C)
        for i in range(len(nodes_sorted) - 1):
            src = nodes_sorted[i]
            tgt = nodes_sorted[i + 1]
            x1, y1 = src["x"], src["y"]
            x2, y2 = tgt["x"], tgt["y"]
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2

            if mtype == "testa":
                ctrl_x = mid_x
                ctrl_y = max(y1, y2) + 55
                path = f'M {x1:.1f} {y1:.1f} Q {ctrl_x:.1f} {ctrl_y:.1f} {x2:.1f} {y2:.1f}'
            else:
                ctrl_x = min(x1, x2) - 70
                ctrl_y = mid_y
                path = f'M {x1:.1f} {y1:.1f} Q {ctrl_x:.1f} {ctrl_y:.1f} {x2:.1f} {y2:.1f}'

            arrows.append(
                f'<path d="{path}" fill="none" stroke="{color}" '
                f'stroke-width="1" stroke-dasharray="{dash}" '
                f'marker-end="url(#{marker})" opacity="0.85"/>'
            )

    return arrows, move_types_used


def generate_legend(move_types_used, view_w, y_start):
    if not move_types_used:
        return [], 0
    labels = {
        "sintagmatico": "mvt sintagmatico",
        "testa":        "mvt di testa",
        "soggetto":     "mvt soggetto",
        "verbo":        "mvt testa verbo",
    }
    items = []
    x, y = 30, y_start + 24
    for mtype in sorted(move_types_used):
        color = MOVE_COLORS.get(mtype, "#888")
        dash = MOVE_DASH.get(mtype, "6 3")
        label = labels.get(mtype, mtype)
        items.append(
            f'<line x1="{x}" y1="{y}" x2="{x+28}" y2="{y}" '
            f'stroke="{color}" stroke-width="1" stroke-dasharray="{dash}"/>'
            f'<text x="{x+34}" y="{y+4}" font-size="11" fill="#666" '
            f'font-family="Georgia,serif">{label}</text>'
        )
        x += 160
        if x > view_w - 80:
            x = 30
            y += 18
    return items, (y - y_start + 18)


HIGHLIGHT_COLOR = "rgba(255, 220, 50, 0.35)"  # giallo evidenziatore semitrasparente
HIGHLIGHT_R = 10  # raggio angoli rettangolo evidenziatore


def render_highlight(node, elements):
    """Disegna un rettangolo evidenziatore giallo sotto i nodi nuovi."""
    if not getattr(node, "is_new", False):
        for child in node.children:
            render_highlight(child, elements)
        return
    x, y = node._x, node._y
    w, h = 54, 22
    elements.append(
        f'<rect x="{x - w/2:.1f}" y="{y - 16:.1f}" width="{w}" height="{h}" '
        f'rx="{HIGHLIGHT_R}" fill="{HIGHLIGHT_COLOR}"/>'
    )
    for child in node.children:
        render_highlight(child, elements)


def render_node(node, elements):
    x, y = node._x, node._y
    color = node.color or "#2c1e0f"

    if not node.children:
        if node.is_copy:
            display = "{" + (node.word or "?") + "}"
            elements.append(
                f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
                f'font-size="{TERM_FONT}" font-style="italic" fill="{color}">'
                f'{display}</text>'
            )
            if node.index:
                elements.append(
                    f'<text x="{x+8:.1f}" y="{y+8:.1f}" text-anchor="start" '
                    f'font-size="{INDEX_FONT}" font-style="italic" fill="{color}">'
                    f'{node.index}</text>'
                )
        elif node.is_trace:
            elements.append(
                f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
                f'font-size="{TERM_FONT}" font-style="italic" fill="{color}">t</text>'
            )
            if node.index:
                elements.append(
                    f'<text x="{x+6:.1f}" y="{y+8:.1f}" text-anchor="start" '
                    f'font-size="{INDEX_FONT}" font-style="italic" fill="{color}">'
                    f'{node.index}</text>'
                )
        else:
            weight = "bold" if getattr(node, "is_pronounced", False) else "normal"
            elements.append(
                f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
                f'font-size="{TERM_FONT}" font-style="italic" '
                f'font-weight="{weight}" fill="{color}">{node.word}</text>'
            )
    else:
        label = node.label
        elements.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
            f'font-size="{FONT_SIZE}" font-weight="bold" fill="{color}">'
            f'{label}</text>'
        )
        if node.index and not node.is_trace:
            label_w = len(label) * FONT_SIZE * 0.6
            elements.append(
                f'<text x="{x + label_w/2 + 2:.1f}" y="{y + 8:.1f}" '
                f'text-anchor="start" font-size="{INDEX_FONT}" '
                f'font-style="italic" fill="{color}">{node.index}</text>'
            )

    for child in node.children:
        cx, cy = child._x, child._y
        y_from = y + 6
        y_to   = cy - 16 if child.children else cy - 14
        elements.append(
            f'<line x1="{x:.1f}" y1="{y_from:.1f}" '
            f'x2="{cx:.1f}" y2="{y_to:.1f}" '
            f'stroke="#5a4a3a" stroke-width="1.5"/>'
        )
        render_node(child, elements)


def tree_to_svg(root, title=None):
    n_leaves = count_leaves(root)
    total_width = max(n_leaves * LEAF_WIDTH, 400)

    assign_x(root, MARGIN_X, total_width - MARGIN_X)
    assign_y(root, depth=0)

    view_w = total_width + MARGIN_X * 2
    tree_h = max_y(root) + MARGIN_Y + 20

    registry = defaultdict(list)
    collect_nodes(root, registry)
    arrows, move_types_used = generate_arrows(registry)
    legend_items, legend_h = generate_legend(move_types_used, view_w, tree_h)
    view_h = tree_h + legend_h + (10 if legend_items else 0)

    defs_items = []
    for mtype in move_types_used:
        color = MOVE_COLORS.get(mtype, "#888")
        mid = f"arr_{mtype}"
        defs_items.append(
            f'<marker id="{mid}" viewBox="0 0 10 10" refX="8" refY="5" '
            f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            f'<path d="M2 1L8 5L2 9" fill="none" stroke="{color}" '
            f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
            f'</marker>'
        )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {view_w:.0f} {view_h:.0f}" '
        f'style="background:#fdfaf5; font-family: Georgia, serif;">'
    ]
    if defs_items:
        parts.append('<defs>' + "".join(defs_items) + '</defs>')
    if title:
        parts.append(
            f'<text x="{view_w/2:.0f}" y="20" text-anchor="middle" '
            f'font-size="13" fill="#888" font-style="italic">{title}</text>'
        )
    elements = []
    render_highlight(root, elements)  # evidenziatori sotto i nodi nuovi
    render_node(root, elements)
    parts.extend(elements)
    parts.extend(arrows)
    parts.extend(legend_items)
    parts.append('</svg>')
    return "\n".join(parts)


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
        with open(f"output_svg/{fname}", "w") as f:
            f.write(svg)
        print(f"Salvato: {fname}")
