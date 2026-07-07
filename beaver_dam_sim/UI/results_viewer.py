"""
Results Viewer - Step 21

A read-only, step-through viewer for a completed simulation run. It
does not edit graphs (network_editor.py) and does not configure or run
simulations (simulation_controls.py) -- it only displays the history
a run already produced.

It is opened by MainWindow after a simulation completes, and receives:
  * network_data -- the same plain-data shape as NetworkEditor.to_dict(),
    captured by SimulationControls at the moment the run was launched
    (see simulation_controls.py's simulation_complete signal). Node x/y
    positions come from here.
  * history -- the list[SimulationStep] returned by
    SimulationService.run_simulation. Each SimulationStep holds a full
    deep-copied snapshot of the RiverNetwork at that step
    (beaver_dam_sim.simulation.models.SimulationStep.river_snapshot),
    not just a delta, so every step can be rendered independently.

Matching a river_snapshot's edges back to the original network_data
edges (and from there to node x/y positions) relies on list order
rather than node ids: RiverNetworkBuilder.create_network (called via
SimulationControls.build_river) iterates network_data["edges"] in
order and appends to RiverNetwork.edges in that same order, and
Simulation._save_step() only ever deep-copies that RiverNetwork -- so
river_snapshot.edges[i] is always the simulation counterpart of
network_data["edges"][i]. (Node-id remapping to a contiguous 1..N
range only matters for build_river's call into
RiverNetworkBuilder.create_network -- it doesn't affect this file.)

Works both as a package module (`python -m ui.results_viewer` from the
project root) and as a loose script run directly from inside the
`ui/` folder (`python results_viewer.py`) -- see the bottom of the
file for a self-contained demo run.
"""

import math
import sys

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QPushButton,
    QLabel,
    QGroupBox,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsTextItem,
    QSlider,
)
from PySide6.QtGui import QPen, QBrush, QColor, QPolygonF
from PySide6.QtCore import Qt, QLineF, QPointF


# Node

class ResultNodeItem(QGraphicsEllipseItem):
    """Static (non-interactive) rendering of a river-network node for
    playback. Visually mirrors NodeItem in network_editor.py, minus
    the editing affordances (movable/selectable/click handling) that
    don't apply to a read-only viewer."""

    RADIUS = 20

    COLOR_DEFAULT = QColor("#00838F")
    BORDER_DEFAULT = QColor("#000000")
    BORDER_OUTLET = QColor("#FFB300")

    def __init__(self, node_id: int, x: float, y: float, is_outlet: bool):
        r = self.RADIUS
        super().__init__(-r, -r, r * 2, r * 2)

        self.setBrush(QBrush(self.COLOR_DEFAULT))
        self.setPen(QPen(self.BORDER_OUTLET if is_outlet else self.BORDER_DEFAULT, 3 if is_outlet else 2))
        self.setZValue(10)
        self.setPos(x, y)

        label = QGraphicsTextItem(str(node_id), self)
        label.setDefaultTextColor(Qt.GlobalColor.white)
        label.setPos(-6, -10)


# Edge

class ResultEdgeItem(QGraphicsLineItem):
    """Static rendering of one river edge's cells for a single
    simulation step. The line/arrowhead styling mirrors EdgeItem in
    network_editor.py; the cell dots additionally encode simulation
    state (flooded / active dam / broken dam / meadow) which the pure
    graph editor has no concept of."""

    CELL_RADIUS = 5

    COLOR_LINE = QColor("#555555")

    COLOR_EMPTY_FILL = QColor("#D7CCC8")
    COLOR_EMPTY_BORDER = QColor("#6D4C41")

    COLOR_FLOODED_FILL = QColor("#1976D2")
    COLOR_FLOODED_BORDER = QColor("#0D47A1")

    COLOR_DAM_FILL = QColor("#5D4037")
    COLOR_DAM_BORDER = QColor("#3E2723")

    COLOR_DAM_BROKEN_FILL = QColor("#9E9E9E")
    COLOR_DAM_BROKEN_BORDER = QColor("#616161")

    COLOR_MEADOW_FILL = QColor("#7CB342")
    COLOR_MEADOW_BORDER = QColor("#33691E")

    def __init__(self, up_pos: QPointF, down_pos: QPointF, cells: list):
        """cells: the RiverEdge's Cell objects for this step, ordered
        by position (1..N, upstream to downstream)."""
        super().__init__()
        self._cells = cells
        self.setZValue(-5)
        self.setLine(QLineF(up_pos, down_pos))

    def boundingRect(self):
        rect = super().boundingRect()
        pad = self.CELL_RADIUS + 6
        return rect.adjusted(-pad, -pad, pad, pad)

    def paint(self, painter, option, widget=None):
        line = self.line()
        painter.setPen(QPen(self.COLOR_LINE, 2))
        painter.drawLine(line)
        self._paint_arrowhead(painter, line)
        self._paint_cells(painter, line)

    def _paint_arrowhead(self, painter, line: QLineF):
        mid = line.pointAt(0.5)
        angle = math.atan2(line.dy(), line.dx())
        size = 7
        p1 = QPointF(
            mid.x() - size * math.cos(angle - math.pi / 7),
            mid.y() - size * math.sin(angle - math.pi / 7),
        )
        p2 = QPointF(
            mid.x() - size * math.cos(angle + math.pi / 7),
            mid.y() - size * math.sin(angle + math.pi / 7),
        )
        painter.setBrush(QBrush(self.COLOR_LINE))
        painter.setPen(QPen(self.COLOR_LINE, 1))
        painter.drawPolygon(QPolygonF([mid, p1, p2]))

    def _cell_colors(self, cell) -> tuple[QColor, QColor]:
        # Flooded takes priority in display even if the cell also has a
        # (broken) dam -- a cascade break can flood a cell in the same
        # step its dam breaks (see Simulation._propagate_floods).
        if cell.flooded:
            return self.COLOR_FLOODED_FILL, self.COLOR_FLOODED_BORDER
        if cell.dam is not None:
            if cell.dam.broken:
                if cell.dam.meadow:
                    return self.COLOR_MEADOW_FILL, self.COLOR_MEADOW_BORDER
                return self.COLOR_DAM_BROKEN_FILL, self.COLOR_DAM_BROKEN_BORDER
            return self.COLOR_DAM_FILL, self.COLOR_DAM_BORDER
        return self.COLOR_EMPTY_FILL, self.COLOR_EMPTY_BORDER

    def _paint_cells(self, painter, line: QLineF):
        n = len(self._cells)
        if n == 0:
            return
        for cell in self._cells:
            t = cell.position / (n + 1)
            pt = line.pointAt(t)
            fill, border = self._cell_colors(cell)
            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(border, 1))
            painter.drawEllipse(pt, self.CELL_RADIUS, self.CELL_RADIUS)


# Main Viewer

class ResultsViewer(QMainWindow):
    """Step-through viewer for a completed simulation run.

    Takes the network_data used for the run (for node layout) and the
    resulting history, and lets the user step forward/backward through
    it, seeing per-step statistics and the river's flood/dam/meadow
    state rendered on the network layout.
    """

    def __init__(self, network_data: dict, history: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Results Viewer")
        self.setMinimumSize(900, 640)
        self.resize(1100, 700)

        self.network_data = network_data
        self.history = history
        self.current_index = 0

        self._outlet_ids = self._compute_outlet_ids()

        self._build_ui()
        self._render_step()

    def _compute_outlet_ids(self) -> set:
        """A node is an outlet if it never appears as the upstream end
        of an edge (mirrors the "roots" logic in
        network_editor.is_valid_tree), purely for the gold-ring visual
        -- it has no effect on simulation state."""
        def edge_pair(e):
            if isinstance(e, dict):
                return e["upstream"], e["downstream"]
            return e[0], e[1]

        upstream_ids = {edge_pair(e)[0] for e in self.network_data.get("edges", [])}
        all_ids = {n["id"] for n in self.network_data.get("nodes", [])}
        return all_ids - upstream_ids


    # UI

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        layout.addWidget(self.view, 1)

        side = QVBoxLayout()
        side.setAlignment(Qt.AlignmentFlag.AlignTop)
        side.setSpacing(10)

        # Step navigation
        nav_group = QGroupBox("Step")
        nav_layout = QVBoxLayout()

        self.step_label = QLabel()
        self.step_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self.step_label)

        nav_btn_row = QHBoxLayout()
        self.prev_btn = QPushButton("\u25c0 Previous")
        self.prev_btn.clicked.connect(self.previous_step)
        self.next_btn = QPushButton("Next \u25b6")
        self.next_btn.clicked.connect(self.next_step)
        nav_btn_row.addWidget(self.prev_btn)
        nav_btn_row.addWidget(self.next_btn)
        nav_layout.addLayout(nav_btn_row)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(max(0, len(self.history) - 1))
        self.slider.valueChanged.connect(self._on_slider_changed)
        nav_layout.addWidget(self.slider)

        nav_group.setLayout(nav_layout)
        side.addWidget(nav_group)

        # Statistics
        stats_group = QGroupBox("Statistics")
        stats_form = QFormLayout()
        self.flooded_label = QLabel()
        self.dams_created_label = QLabel()
        self.dams_broken_label = QLabel()
        stats_form.addRow("Currently flooded cells", self.flooded_label)
        stats_form.addRow("Dams created this step", self.dams_created_label)
        stats_form.addRow("Dams broken this step", self.dams_broken_label)
        stats_group.setLayout(stats_form)
        side.addWidget(stats_group)

        # Legend
        legend_group = QGroupBox("Legend")
        legend_layout = QVBoxLayout()
        legend_label = QLabel(
            "<span style='color:#1976D2'>\u25cf</span> Flooded cell<br>"
            "<span style='color:#5D4037'>\u25cf</span> Active dam<br>"
            "<span style='color:#9E9E9E'>\u25cf</span> Broken dam<br>"
            "<span style='color:#7CB342'>\u25cf</span> Meadow<br>"
            "<span style='color:#D7CCC8'>\u25cf</span> Empty cell<br>"
            "<span style='color:#FFB300'>\u25ce</span> Outlet"
        )
        legend_label.setTextFormat(Qt.TextFormat.RichText)
        legend_label.setWordWrap(True)
        legend_layout.addWidget(legend_label)
        legend_group.setLayout(legend_layout)
        side.addWidget(legend_group)

        side.addStretch(1)
        layout.addLayout(side)


    # Navigation

    def previous_step(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.slider.blockSignals(True)
            self.slider.setValue(self.current_index)
            self.slider.blockSignals(False)
            self._render_step()

    def next_step(self):
        if self.current_index < len(self.history) - 1:
            self.current_index += 1
            self.slider.blockSignals(True)
            self.slider.setValue(self.current_index)
            self.slider.blockSignals(False)
            self._render_step()

    def _on_slider_changed(self, value: int):
        self.current_index = value
        self._render_step()


    # Rendering

    def _render_step(self):
        self.scene.clear()

        if not self.history:
            self.step_label.setText("No steps to display")
            return

        step = self.history[self.current_index]
        node_positions = {n["id"]: (n["x"], n["y"]) for n in self.network_data.get("nodes", [])}

        for node_id, (x, y) in node_positions.items():
            self.scene.addItem(ResultNodeItem(node_id, x, y, node_id in self._outlet_ids))

        def edge_pair(e):
            if isinstance(e, dict):
                return e["upstream"], e["downstream"]
            return e[0], e[1]

        edges_data = self.network_data.get("edges", [])
        river_edges = step.river_snapshot.edges
        for edge_data, river_edge in zip(edges_data, river_edges):
            up_id, down_id = edge_pair(edge_data)
            up_x, up_y = node_positions[up_id]
            down_x, down_y = node_positions[down_id]
            cells = [river_edge.cells[pos] for pos in sorted(river_edge.cells.keys())]
            self.scene.addItem(ResultEdgeItem(QPointF(up_x, up_y), QPointF(down_x, down_y), cells))

        bounds = self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self.scene.setSceneRect(bounds)
        self.view.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)

        last_step = len(self.history) - 1
        self.step_label.setText(f"Step {step.step} of {last_step}")
        self.flooded_label.setText(str(len(step.cells_flooded)))
        self.dams_created_label.setText(str(len(step.dams_created)))
        self.dams_broken_label.setText(str(len(step.dams_broken)))

        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < last_step)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene.itemsBoundingRect().isValid():
            self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


# Run (self-contained demo: builds a small network + runs a sim so this
# file can be exercised directly, e.g. `python results_viewer.py`)

if __name__ == "__main__":
    from beaver_dam_sim.service import SimulationService

    app = QApplication(sys.argv)

    # Mirrors RiverNetworkFactory.create_default_network's topology
    # (8 nodes; edges as (downstream, upstream) pairs: (5,1) (5,2)
    # (6,3) (6,4) (7,5) (7,6) (8,7)) but as NetworkEditor-shaped data
    # with layout positions, so ResultsViewer has something to draw.
    network_data = {
        "version": 2,
        "nodes": [
            {"id": 1, "x": 100, "y": 520},
            {"id": 2, "x": 240, "y": 520},
            {"id": 3, "x": 480, "y": 520},
            {"id": 4, "x": 620, "y": 520},
            {"id": 5, "x": 170, "y": 360},
            {"id": 6, "x": 550, "y": 360},
            {"id": 7, "x": 360, "y": 200},
            {"id": 8, "x": 360, "y": 60},
        ],
        "edges": [
            {"upstream": 1, "downstream": 5, "length": 5},
            {"upstream": 2, "downstream": 5, "length": 5},
            {"upstream": 3, "downstream": 6, "length": 5},
            {"upstream": 4, "downstream": 6, "length": 5},
            {"upstream": 5, "downstream": 7, "length": 5},
            {"upstream": 6, "downstream": 7, "length": 5},
            {"upstream": 7, "downstream": 8, "length": 5},
        ],
    }

    service = SimulationService()
    river = service.create_river(
        node_count=8,
        edges=[(5, 1), (5, 2), (6, 3), (6, 4), (7, 5), (7, 6), (8, 7)],
    )

    from beaver_dam_sim.simulation import SimParam

    params = SimParam(
        dam_creation_probability=0.3,
        dam_break_probability=0.3,
        flood_probability=0.3,
        flood_break_probability=0.3,
        stabilization_time=3,
        steps=30,
        random_seed=1,
        meadow_probability=0.3,
    )
    demo_history = service.run_simulation(params, river)

    viewer = ResultsViewer(network_data, demo_history)
    viewer.show()
    sys.exit(app.exec())