"""
Beaver Dam Simulation — Main Window (PySide6)
"""

from beaver_dam_sim.service import SimulationService
from beaver_dam_sim.simulation import SimParam, SimulationStep

import sys
import math

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QDoubleSpinBox, QSpinBox, QPushButton, QFrame,
    QSizePolicy, QMessageBox, QGraphicsView, QGraphicsScene,
    QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsTextItem,
    QScrollArea,
)
from PySide6.QtCore import Qt, QThread, Signal, QRectF, QPointF
from PySide6.QtGui import QPen, QBrush, QColor, QFont
#- Color codes
WHITE = "#FFFFFF"
LIGHT_GRAY = "#F0F0F0"
SIDEBAR_BG = "#888888"
RIVER_GREEN = "#5A9E4A"
RIVER_BLUE = "#4A90D9"

# Cell node states
NODE_EMPTY = QColor("#D6C8A8")  # clear — no dam
NODE_DAM = QColor("#6B3A1F")  # brown — dam present
NODE_MEADOW = QColor("#F5C518")  # yellow — beaver meadow
NODE_FLOODED = QColor("#4A90D9")  # blue  — flooded
NODE_OUTLINE = QColor("#2C1A0E")

STYLESHEET = f"""
QMainWindow {{ background: {WHITE}; }}
QWidget#root {{ background: {WHITE}; }}

/* Title */
QLabel#title {{
    font-size: 32px;
    font-weight: 800;
    color: #111111;
}}

/* Sidebar */
QWidget#sidebar {{
    background: {SIDEBAR_BG};
}}
QLabel#sidebar_section {{
    color: {WHITE};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#sidebar_field {{
    color: {WHITE};
    font-size: 11px;
}}
QDoubleSpinBox, QSpinBox {{
    background: {WHITE};
    border: 1px solid #CCCCCC;
    border-radius: 3px;
    padding: 4px 6px;
    font-size: 12px;
    color: #111;
}}

/* Centre info panel */
QWidget#info_panel {{
    background: {LIGHT_GRAY};
    border-right: 1px solid #CCCCCC;
}}
QLabel#info_section {{
    font-size: 13px;
    font-weight: 700;
    color: #333;
}}
QLabel#info_stat_label {{
    font-size: 12px;
    color: #444;
}}
QLabel#info_stat_value {{
    font-size: 12px;
    font-weight: 700;
    color: #111;
    min-width: 28px;
}}
QLabel#seed_label {{
    font-size: 11px;
    color: #666;
    margin-top: 8px;
}}
QLabel#seed_value {{
    font-size: 12px;
    font-weight: 600;
    color: #222;
    background: {WHITE};
    border: 1px solid #CCC;
    border-radius: 3px;
    padding: 3px 6px;
}}

/* Year counter */
QLabel#year_label {{
    font-size: 13px;
    color: #444;
}}
QLabel#year_value {{
    font-size: 13px;
    font-weight: 700;
    color: #111;
}}

/* Buttons */
QPushButton#simulate_btn {{
    background: {WHITE};
    border: 2px solid #333;
    border-radius: 4px;
    padding: 6px 18px;
    font-size: 13px;
    font-weight: 600;
    color: #111;
}}
QPushButton#simulate_btn:hover {{ background: #EFEFEF; }}
QPushButton#simulate_btn:disabled {{ color: #999; border-color: #BBB; }}

QPushButton#nav_btn {{
    background: {WHITE};
    border: 2px solid #333;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 16px;
    font-weight: 800;
    color: #111;
    min-width: 36px;
}}
QPushButton#nav_btn:hover {{ background: #EFEFEF; }}
QPushButton#nav_btn:disabled {{ color: #BBB; border-color: #CCC; }}

/* Legend */
QLabel#legend_dot {{
    min-width: 14px;
    max-width: 14px;
    min-height: 14px;
    max-height: 14px;
    border-radius: 7px;
    border: 1px solid #555;
}}
QLabel#legend_text {{
    font-size: 11px;
    color: #EEE;
}}
"""

#- Background simulation
class SimWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, service, params, parent=None):
        super().__init__(parent)
        self.service = service
        self.params = params

    def run(self):
        try:
            self.finished.emit(self.service.run_simulation(self.params))
        except Exception as e:
            self.error.emit(str(e))

#- River network graphics
class CellNode(QGraphicsEllipseItem):
    RADIUS = 10

    def __init__(self, x, y):
        r = self.RADIUS
        super().__init__(-r, -r, r * 2, r * 2)
        self.setPos(x, y)
        self._set_state("empty")
        self.setPen(QPen(NODE_OUTLINE, 1.5))

    def _set_state(self, state: str):
        colours = {
            "empty": NODE_EMPTY,
            "dam": NODE_DAM,
            "meadow": NODE_MEADOW,
            "flooded": NODE_FLOODED,
        }
        self.setBrush(QBrush(colours.get(state, NODE_EMPTY)))

    def update_from_cell(self, cell):
        if cell.flooded:
            self._set_state("flooded")
        elif cell.dam and cell.dam.meadow:
            self._set_state("meadow")
        elif cell.dam and not cell.dam.broken:
            self._set_state("dam")
        else:
            self._set_state("empty")


class RiverNetworkView(QGraphicsView):
    """Green canvas that draws the river network and animates cell states."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setBackgroundBrush(QBrush(QColor(RIVER_GREEN)))
        self.setRenderHint(self.renderHints())
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._cell_nodes: list[tuple] = []  # (cell_node_item, edge_idx, cell_pos)

#- Public
    def draw_network(self, river_network):
        """Draw the network topology from a RiverNetwork object."""
        self._scene.clear()
        self._cell_nodes = []

        edges = river_network.edges
        n_edges = len(edges)
        if n_edges == 0:
            return

        W = max(self.width(), 600)
        H = max(self.height(), 400)

        node_positions = self._compute_layout(river_network, W, H)

        edge_pen = QPen(QColor(RIVER_BLUE), 3)

        for edge in edges:
            down_id = edge.down_stream_node
            up_id = edge.up_stream_node
            p1 = node_positions.get(down_id)
            p2 = node_positions.get(up_id)
            if p1 is None or p2 is None:
                continue

            # River line
            line = QGraphicsLineItem(p1[0], p1[1], p2[0], p2[1])
            line.setPen(edge_pen)
            line.setZValue(0)
            self._scene.addItem(line)

            # Cell nodes along the edge
            n_cells = len(edge.cells)
            for i, (pos_key, cell) in enumerate(sorted(edge.cells.items())):
                t = (i + 1) / (n_cells + 1)
                cx = p1[0] + t * (p2[0] - p1[0])
                cy = p1[1] + t * (p2[1] - p1[1])
                node = CellNode(cx, cy)
                node.update_from_cell(cell)
                node.setZValue(2)
                self._scene.addItem(node)
                self._cell_nodes.append((node, cell))

        # Draw junction on top
        junction_pen = QPen(NODE_OUTLINE, 1.5)
        junction_brush = QBrush(QColor("#8B5E3C"))
        R = 12
        for node_id, (x, y) in node_positions.items():
            circle = QGraphicsEllipseItem(-R, -R, R * 2, R * 2)
            circle.setPos(x, y)
            circle.setBrush(junction_brush)
            circle.setPen(junction_pen)
            circle.setZValue(3)
            self._scene.addItem(circle)

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)

    def update_step(self, step):
        """Recolour cell nodes from a SimulationStep."""
        # Build fast lookup: edge_id → {pos → cell}
        cell_map = {}
        for edge in step.river_snapshot.edges:
            cell_map[edge.id] = edge.cells

        # Match stored nodes back to updated cells by order
        all_cells = []
        for edge in step.river_snapshot.edges:
            for pos_key in sorted(edge.cells.keys()):
                all_cells.append(edge.cells[pos_key])

        for i, (node_item, _) in enumerate(self._cell_nodes):
            if i < len(all_cells):
                node_item.update_from_cell(all_cells[i])


# ─ Main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Beaver Dam Simulations")
        self.setMinimumSize(1100, 680)

        self._history = []
        self._current = -1
        self._worker = None
        self._default_river = None

        try:
            from beaver_dam_sim.service import SimulationService, RiverNetworkFactory
            self._service = SimulationService()
            self._default_river = RiverNetworkFactory.create_default_network()
        except ImportError:
            self._service = None

        self._build_ui()

        # Draw the default network on startup
        if self._default_river:
            self._river_view.draw_network(self._default_river)

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(12)

        # ─ Title row
        title_row = QHBoxLayout()

        title = QLabel("Beaver Dam Simulations")
        title.setObjectName("title")
        title_row.addWidget(title)
        title_row.addStretch()

        # Year counter + buttons (top-right)
        self._year_lbl = QLabel("Year Count:")
        self._year_lbl.setObjectName("year_label")
        self._year_val = QLabel("0")
        self._year_val.setObjectName("year_value")

        self._simulate_btn = QPushButton("Simulate")
        self._simulate_btn.setObjectName("simulate_btn")
        self._simulate_btn.clicked.connect(self._run)

        self._prev_btn = QPushButton("◀")
        self._prev_btn.setObjectName("nav_btn")
        self._prev_btn.clicked.connect(self._go_prev)

        self._next_btn = QPushButton("▶")
        self._next_btn.setObjectName("nav_btn")
        self._next_btn.clicked.connect(self._go_next)

        title_row.addWidget(self._year_lbl)
        title_row.addWidget(self._year_val)
        title_row.addSpacing(12)
        title_row.addWidget(self._simulate_btn)
        title_row.addWidget(self._prev_btn)
        title_row.addWidget(self._next_btn)

        outer.addLayout(title_row)

        # ─ Main content row
        content = QHBoxLayout()
        content.setSpacing(0)

        # Left: sidebar
        self._sidebar = SidebarForm()
        content.addWidget(self._sidebar)

        # Info panel
        self._info_panel = InfoPanel()
        self._info_panel.update_seed(self._sidebar.get_seed())
        content.addWidget(self._info_panel)

        # Right: river network
        self._river_view = RiverNetworkView()
        content.addWidget(self._river_view)

        outer.addLayout(content)

        self._set_nav_state()

        # ─ Layout
        def _compute_layout(self, river, W, H):
            """
            Tree layout. The node with no downstream edge is the root.
            Nodes are laid out top→bottom (root at bottom of scene, leaves at top).
            """
            # Build adjacency: down → [up, up, ect]
            children = {}  # up_node = child of down_node (upstream)
            parents = {}  # down_node is parent of up_node
            all_nodes = set()

            for edge in river.edges:
                d = edge.down_stream_node
                u = edge.up_stream_node
                all_nodes.add(d)
                all_nodes.add(u)
                children.setdefault(d, []).append(u)
                parents[u] = d

            # Root = node that is nobody's child (no parent)
            roots = [n for n in all_nodes if n not in parents]
            root = roots[0] if roots else next(iter(all_nodes))

            # BFS to assign depths
            from collections import deque
            depth = {root: 0}
            queue = deque([root])
            max_depth = 0
            while queue:
                n = queue.popleft()
                for c in children.get(n, []):
                    depth[c] = depth[n] + 1
                    max_depth = max(max_depth, depth[c])
                    queue.append(c)

            # Group nodes by depth
            by_depth = {}
            for n, d in depth.items():
                by_depth.setdefault(d, []).append(n)

            # Assign x positions by leaf-count
            positions = {}
            leaf_count = self._count_leaves(root, children)

            MARGIN_X = 60
            MARGIN_Y = 50
            usable_W = W - 2 * MARGIN_X
            usable_H = H - 2 * MARGIN_Y

            def assign_x(node, left, right):
                kids = children.get(node, [])
                if not kids:
                    positions[node] = ((left + right) / 2, None)
                    return
                total_leaves = sum(self._count_leaves(k, children) for k in kids)
                cursor = left
                for k in kids:
                    share = (self._count_leaves(k, children) / total_leaves) * (right - left)
                    assign_x(k, cursor, cursor + share)
                    cursor += share
                positions[node] = ((left + right) / 2, None)

            assign_x(root, 0, 1)

            # Convert to pixel coords; root at bottom
            result = {}
            for node, (xfrac, _) in positions.items():
                d = depth.get(node, 0)
                x = MARGIN_X + xfrac * usable_W
                # depth 0 = root at bottom; deeper = higher up
                y_frac = d / max(max_depth, 1)
                y = (MARGIN_Y + usable_H) - y_frac * usable_H
                result[node] = (x, y)

            return result

        def _count_leaves(self, node, children):
            kids = children.get(node, [])
            if not kids:
                return 1
            return sum(self._count_leaves(k, children) for k in kids)

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if self._scene.items():
                self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)

    #─ Sidebar param form
    class SidebarForm(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("sidebar")
            self.setFixedWidth(200)

            lay = QVBoxLayout(self)
            lay.setContentsMargins(12, 14, 12, 14)
            lay.setSpacing(6)

            hdr = QLabel("User controls")
            hdr.setObjectName("sidebar_section")
            lay.addWidget(hdr)

            fields = [
                ("Probability of Beaver Dam Construction", "dam_creation", QDoubleSpinBox, 0.0, 1.0, 0.01, 0.10),
                ("Probability of Dam Failure", "dam_break", QDoubleSpinBox, 0.0, 1.0, 0.01, 0.05),
                ("Probability of Catastrophic Flood", "flood", QDoubleSpinBox, 0.0, 1.0, 0.01, 0.05),
                ("Time for River to Stabilize", "stab_time", QSpinBox, 1, 500, 1, 3),
                ("Number of Years", "steps", QSpinBox, 1, 10000, 1, 20),
                ("How many dams will break from flood", "flood_break", QDoubleSpinBox, 0.0, 1.0, 0.01, 0.10),
                ("Meadow probability", "meadow", QDoubleSpinBox, 0.0, 1.0, 0.01, 0.05),
                ("Random seed", "seed", QSpinBox, -2147483648, 2147483647, 1, 0),
            ]

            self._inputs = {}
            for label_text, key, SpinClass, lo, hi, step, default in fields:
                lbl = QLabel(label_text)
                lbl.setObjectName("sidebar_field")
                lbl.setWordWrap(True)
                lay.addWidget(lbl)

                sb = SpinClass()
                sb.setRange(lo, hi)
                if isinstance(sb, QDoubleSpinBox):
                    sb.setDecimals(2)
                    sb.setSingleStep(step)
                else:
                    sb.setSingleStep(step)
                sb.setValue(default)
                lay.addWidget(sb)
                self._inputs[key] = sb

            lay.addStretch()

            # Legend
            lay.addWidget(self._divider())
            legend_title = QLabel("Cell legend")
            legend_title.setObjectName("sidebar_section")
            lay.addWidget(legend_title)

            legend_items = [
                ("#D6C8A8", "Empty"),
                ("#6B3A1F", "Dam"),
                ("#F5C518", "Meadow"),
                ("#4A90D9", "Flooded"),
            ]
            for color, label in legend_items:
                row = QHBoxLayout()
                row.setSpacing(6)
                dot = QLabel()
                dot.setObjectName("legend_dot")
                dot.setFixedSize(14, 14)
                dot.setStyleSheet(f"background: {color}; border-radius: 7px; border: 1px solid #444;")
                txt = QLabel(label)
                txt.setObjectName("legend_text")
                row.addWidget(dot)
                row.addWidget(txt)
                row.addStretch()
                lay.addLayout(row)

        def _divider(self):
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet("color: #777;")
            return line

        def get_params(self):
            from beaver_dam_sim.simulation import SimParam
            i = self._inputs
            return SimParam(
                dam_creation_probability=i["dam_creation"].value(),
                dam_break_probability=i["dam_break"].value(),
                flood_probability=i["flood"].value(),
                flood_break_probability=i["flood_break"].value(),
                stabilization_time=i["stab_time"].value(),
                steps=i["steps"].value(),
                random_seed=i["seed"].value(),
                meadow_probability=i["meadow"].value(),
            )

        def get_seed(self):
            return self._inputs["seed"].value()

    #─ Centre info panel
    class InfoPanel(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("info_panel")
            self.setFixedWidth(180)

            lay = QVBoxLayout(self)
            lay.setContentsMargins(14, 14, 14, 14)
            lay.setSpacing(8)

            hdr = QLabel("Step Info")
            hdr.setObjectName("info_section")
            lay.addWidget(hdr)

            self._stats = {}
            for key, display in [
                ("dam_breaks", "Dam Breaks"),
                ("dams_created", "Dams Created"),
                ("segs_flooded", "Segments Flooded"),
            ]:
                row = QHBoxLayout()
                lbl = QLabel(display)
                lbl.setObjectName("info_stat_label")
                val = QLabel("0")
                val.setObjectName("info_stat_value")
                row.addWidget(lbl)
                row.addStretch()
                row.addWidget(val)
                lay.addLayout(row)
                self._stats[key] = val

            lay.addSpacing(12)

            seed_lbl = QLabel("Seed")
            seed_lbl.setObjectName("info_section")
            lay.addWidget(seed_lbl)

            self._seed_val = QLabel("#000000000")
            self._seed_val.setObjectName("seed_value")
            lay.addWidget(self._seed_val)

            lay.addStretch()

        def update_step(self, step):
            self._stats["dam_breaks"].setText(str(len(step.dams_broken)))
            self._stats["dams_created"].setText(str(len(step.dams_created)))
            self._stats["segs_flooded"].setText(str(len(step.cells_flooded)))

        def update_seed(self, seed: int):
            self._seed_val.setText(f"#{seed:09d}")

        def reset(self):
            for v in self._stats.values():
                v.setText("0")

        #─ Main content row
        content = QHBoxLayout()
        content.setSpacing(0)

        # Left: sidebar
        self._sidebar = SidebarForm()
        content.addWidget(self._sidebar)

        # Centre: info panel
        self._info_panel = InfoPanel()
        self._info_panel.update_seed(self._sidebar.get_seed())
        content.addWidget(self._info_panel)

        # Right: river network canvas
        self._river_view = RiverNetworkView()
        content.addWidget(self._river_view)

        outer.addLayout(content)

        self._set_nav_state()

    #─ Slots
    def _run(self):
        if self._service is None:
            QMessageBox.critical(self, "Import Error",
                                 "Could not import beaver_dam_sim.\n"
                                 "Make sure the package is on your PYTHONPATH.")
            return

        try:
            params = self._sidebar.get_params()
        except Exception as e:
            QMessageBox.warning(self, "Invalid Parameters", str(e))
            return

        self._simulate_btn.setEnabled(False)
        self._simulate_btn.setText("Running…")
        self._info_panel.update_seed(params.random_seed)

        self._worker = SimWorker(self._service, params, parent=self)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, history):
        self._simulate_btn.setEnabled(True)
        self._simulate_btn.setText("Simulate")
        self._history = history
        self._current = 0

        # Redraw network layout from first step's river snapshot
        if history:
            self._river_view.draw_network(history[0].river_snapshot)

        self._show_step(0)

    def _on_error(self, msg):
        self._simulate_btn.setEnabled(True)
        self._simulate_btn.setText("Simulate")
        QMessageBox.critical(self, "Simulation Error", msg)

    def _go_prev(self):
        if self._current > 0:
            self._show_step(self._current - 1)

    def _go_next(self):
        if self._current < len(self._history) - 1:
            self._show_step(self._current + 1)

    def _show_step(self, idx):
        self._current = idx
        step = self._history[idx]
        self._year_val.setText(str(step.step))
        self._info_panel.update_step(step)
        self._river_view.update_step(step)
        self._set_nav_state()

    def _set_nav_state(self):
        has = len(self._history) > 0
        self._prev_btn.setEnabled(has and self._current > 0)
        self._next_btn.setEnabled(has and self._current < len(self._history) - 1)


#─ Entry point
def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
