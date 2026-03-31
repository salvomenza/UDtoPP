# ver. 26.2
"""
svg_render.py — v22
Animazioni SVG:
- Nodi nuovi: fade-in
- Frecce di movimento: effetto "si disegna" (stroke-dashoffset)
- Particella che risale lungo le frecce
"""

from ud_to_chomsky import Node, INDEX_COLORS
from collections import defaultdict
import math

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
HIGHLIGHT_COLOR = "rgba(255, 220, 50, 0.35)"
HIGHLIGHT_R = 10

# Durata animazioni
FADE_DUR    = "0.5s"
DRAW_DUR    = "0.8s"
PARTICLE_DUR = "1.2s"
BASE_DELAY  = 0.3   # secondi di ritardo base per elementi nuovi


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
    mtype = getattr(node, "movement_type", None)
    if mtype and node.index:
        key = (node.index, mtype)
        # Movimento sintagmatico (soggetto, sintagmatico):
        #   punto di arrivo = nodo XP (strutturale, word is None)
        #   punto di partenza = traccia (is_copy=True, word is not None)
        # Movimento di testa (verbo, testa):
        #   sia partenza che arrivo = nodi terminali (word is not None)
        is_sintagmatico = mtype in ("soggetto", "sintagmatico")
        is_testa = mtype in ("verbo", "testa")

        if is_sintagmatico:
            # Includi solo: XP strutturali (word is None) oppure tracce (is_copy)
            if node.word is None or node.is_copy:
                registry[key].append({
                    "x": node._x, "y": node._y,
                    "is_copy": node.is_copy,
                    "is_pronounced": getattr(node, "is_pronounced", False),
                    "is_xp": node.word is None,
                })
        elif is_testa:
            # Includi solo terminali (word is not None)
            if node.word is not None:
                registry[key].append({
                    "x": node._x, "y": node._y,
                    "is_copy": node.is_copy,
                    "is_pronounced": getattr(node, "is_pronounced", False),
                    "is_xp": False,
                })

    for child in node.children:
        collect_nodes(child, registry)


def path_length(x1, y1, cx, cy, x2, y2):
    """Stima la lunghezza di una curva di Bezier quadratica."""
    steps = 20
    length = 0.0
    px, py = x1, y1
    for i in range(1, steps + 1):
        t = i / steps
        qx = (1-t)**2 * x1 + 2*(1-t)*t * cx + t**2 * x2
        qy = (1-t)**2 * y1 + 2*(1-t)*t * cy + t**2 * y2
        length += math.sqrt((qx-px)**2 + (qy-py)**2)
        px, py = qx, qy
    return length


def generate_arrows(registry, animate=False):
    arrows = []
    particles = []
    move_types_used = set()
    arrow_idx = 0

    for (idx, mtype), nodes in registry.items():
        if len(nodes) < 2:
            continue
        color = MOVE_COLORS.get(mtype, "#888")
        dash = MOVE_DASH.get(mtype, "6 3")
        marker = f"arr_{mtype}"
        move_types_used.add(mtype)

        nodes_sorted = sorted(nodes, key=lambda n: -n["y"])

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
            else:
                ctrl_x = min(x1, x2) - 70
                ctrl_y = mid_y

            path_d = f'M {x1:.1f} {y1:.1f} Q {ctrl_x:.1f} {ctrl_y:.1f} {x2:.1f} {y2:.1f}'
            plen = path_length(x1, y1, ctrl_x, ctrl_y, x2, y2)
            delay = f"{arrow_idx * 0.3 + 0.5:.1f}s"
            aid = f"arrow_{arrow_idx}"

            if animate:
                # Effetto "si disegna": stroke-dasharray = lunghezza, offset da len a 0
                arrows.append(
                    f'<path id="{aid}" d="{path_d}" fill="none" stroke="{color}" '
                    f'stroke-width="1" stroke-dasharray="{plen:.0f}" '
                    f'stroke-dashoffset="{plen:.0f}" '
                    f'marker-end="url(#{marker})" opacity="0.85">'
                    f'<animate attributeName="stroke-dashoffset" '
                    f'from="{plen:.0f}" to="0" dur="{DRAW_DUR}" '
                    f'begin="{delay}" fill="freeze" calcMode="spline" '
                    f'keySplines="0.4 0 0.2 1"/>'
                    f'</path>'
                )
                # Particella che risale
                particles.append(
                    f'<circle r="3" fill="{color}" opacity="0">'
                    f'<animateMotion dur="{PARTICLE_DUR}" begin="{delay}" '
                    f'fill="freeze" calcMode="spline" '
                    f'keySplines="0.4 0 0.2 1">'
                    f'<mpath href="#{aid}" xlink:href="#{aid}"/>'
                    f'</animateMotion>'
                    f'<animate attributeName="opacity" '
                    f'values="0;0.9;0.9;0" '
                    f'keyTimes="0;0.1;0.8;1" '
                    f'dur="{PARTICLE_DUR}" begin="{delay}" fill="freeze"/>'
                    f'</circle>'
                )
            else:
                arrows.append(
                    f'<path d="{path_d}" fill="none" stroke="{color}" '
                    f'stroke-width="1" stroke-dasharray="{dash}" '
                    f'marker-end="url(#{marker})" opacity="0.85"/>'
                )

            arrow_idx += 1

    return arrows, particles, move_types_used


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


def render_highlight(node, elements, animate=False):
    if not getattr(node, "is_new", False):
        for child in node.children:
            render_highlight(child, elements, animate)
        return
    x, y = node._x, node._y
    w, h = 54, 22
    anim = (
        f'<animate attributeName="opacity" from="0" to="1" '
        f'dur="{FADE_DUR}" begin="0.1s" fill="freeze"/>'
    ) if animate else ""
    elements.append(
        f'<rect x="{x - w/2:.1f}" y="{y - 16:.1f}" width="{w}" height="{h}" '
        f'rx="{HIGHLIGHT_R}" fill="{HIGHLIGHT_COLOR}" '
        f'{"opacity=\"0\"" if animate else ""}>{anim}</rect>'
    )
    for child in node.children:
        render_highlight(child, elements, animate)


def render_node(node, elements, animate=False, delay_counter=None):
    x, y = node._x, node._y
    color = node.color or "#2c1e0f"
    is_new = getattr(node, "is_new", False)

    # Calcola ritardo animazione fade-in per nodi nuovi
    anim_attrs = ""
    if animate and is_new:
        if delay_counter is None:
            delay_counter = [0]
        delay = f"{delay_counter[0] * 0.08:.2f}s"
        delay_counter[0] += 1
        anim_attrs = f' opacity="0"><animate attributeName="opacity" from="0" to="1" dur="{FADE_DUR}" begin="{delay}" fill="freeze"/><'
    else:
        anim_attrs = ">"

    def wrap(tag_content):
        """Avvolge un elemento SVG con animazione fade-in se il nodo è nuovo."""
        if animate and is_new:
            d = f"{(delay_counter[0] if delay_counter else 0) * 0.08:.2f}s"
            return (tag_content.rstrip("/>") +
                    f' opacity="0"><animate attributeName="opacity" '
                    f'from="0" to="1" dur="{FADE_DUR}" begin="{d}" fill="freeze"/>'
                    f'</' + tag_content.split("<")[1].split(" ")[0] + '>')
        return tag_content

    if not node.children:
        if node.is_copy:
            display = "{" + (node.word or "?") + "}"
            el = (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
                  f'font-size="{TERM_FONT}" font-style="italic" fill="{color}">'
                  f'{display}</text>')
            elements.append(el)
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
            is_silent = node.word in ("pro", "PRO", "pro_espl", "PRO_arb") \
                        and not getattr(node, "is_pronounced", True)
            if is_silent:
                # Elemento silenzioso: corsivo, colore attenuato, non grassetto
                elements.append(
                    f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
                    f'font-size="{TERM_FONT}" font-style="italic" '
                    f'font-weight="normal" fill="{color}" opacity="0.75">'
                    f'{node.word}</text>'
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
        render_node(child, elements, animate, delay_counter)


def tree_to_svg(root, title=None, animate=False):
    n_leaves = count_leaves(root)
    total_width = max(n_leaves * LEAF_WIDTH, 400)

    assign_x(root, MARGIN_X, total_width - MARGIN_X)
    assign_y(root, depth=0)

    view_w = total_width + MARGIN_X * 2
    tree_h = max_y(root) + MARGIN_Y + 20

    registry = defaultdict(list)
    collect_nodes(root, registry)
    arrows, particles, move_types_used = generate_arrows(registry, animate=animate)
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

    # CSS animazioni
    css = ""
    if animate:
        css = (
            '<style>'
            '@media (prefers-reduced-motion: no-preference) {'
            '.new-node { animation: fadein 0.5s ease both; }'
            '@keyframes fadein { from { opacity: 0; } to { opacity: 1; } }'
            '}'
            '</style>'
        )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {view_w:.0f} {view_h:.0f}" '
        f'style="background:#fdfaf5; font-family: Georgia, serif;">'
    ]
    if css:
        parts.append(css)
    if defs_items:
        parts.append('<defs>' + "".join(defs_items) + '</defs>')
    if title:
        parts.append(
            f'<text x="{view_w/2:.0f}" y="20" text-anchor="middle" '
            f'font-size="13" fill="#888" font-style="italic">{title}</text>'
        )

    elements = []
    delay_counter = [0]
    render_highlight(root, elements, animate=animate)
    render_node(root, elements, animate=animate, delay_counter=delay_counter)
    parts.extend(elements)
    parts.extend(arrows)
    parts.extend(particles)
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
        svg = tree_to_svg(tree, title=sentence, animate=True)
        fname = sentence.replace(" ", "_").lower() + "_auto.svg"
        with open(f"output_svg/{fname}", "w") as f:
            f.write(svg)
        print(f"Salvato: {fname}")
