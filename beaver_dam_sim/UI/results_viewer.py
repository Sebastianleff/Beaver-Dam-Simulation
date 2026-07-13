"""
Results Viewer - Step 21 (+ playback)

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

Playback: a QTimer (self._play_timer) advances one step at a time at
an interval driven by the speed slider. Any manual navigation (Previous
/ Next / dragging the step slider) pauses playback rather than fighting
it, so the user always has one clear "who's driving" answer. A second,
much faster QTimer (self._pulse_timer) drives a short highlight
animation on whichever cells changed state on the step that was just
rendered (newly flooded, dam created, dam broken -- see PulseState),
so state changes are noticeable even at high playback speed instead of
just silently appearing.

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
    QFrame,
    QSizePolicy,
)
from PySide6.QtGui import QPen, QBrush, QColor, QPolygonF, QKeySequence, QShortcut, QPainter
from PySide6.QtCore import Qt, QLineF, QPointF, QTimer


# Pulse state (shared, mutable; read by every ResultEdgeItem at paint
# time so a single timer can drive the highlight animation for the
# whole scene without each item needing its own timer)

class PulseState:
    """Tracks which (edge_index, cell_position) pairs changed state on
    the step that was just rendered, and how far through the brief
    highlight animation we are (0.0 = just changed, 1.0 = done)."""

    def __init__(self):
        self.active_keys: set[tuple[int, int]] = set()
        self.progress: float = 1.0  # 1.0 == nothing animating

    def is_active(self, edge_index: int, position: int) -> bool:
        return self.progress < 1.0 and (edge_index, position) in self.active_keys

    def start(self, keys: set[tuple[int, int]]):
        self.active_keys = keys
        self.progress = 0.0 if keys else 1.0

    def stop(self):
        self.active_keys = set()
        self.progress = 1.0


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
    graph editor has no concept of, plus a brief highlight ring on
    cells that just changed state (driven by the shared PulseState)."""

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

    COLOR_PULSE = QColor("#FFEB3B")
    PULSE_MAX_GROWTH = 9  # extra radius, in px, at the start of the pulse

    def __init__(self, up_pos: QPointF, down_pos: QPointF, cells: list, edge_index: int, pulse_state: PulseState):
        """cells: the RiverEdge's Cell objects for this step, ordered
        by position (1..N, upstream to downstream). edge_index: this
        edge's position in network_data["edges"] / river_snapshot.edges,
        used as the first half of a pulse key. pulse_state: shared
        object read at paint time to decide which cells are pulsing."""
        super().__init__()
        self._cells = cells
        self._edge_index = edge_index
        self._pulse_state = pulse_state
        self.setZValue(-5)
        self.setLine(QLineF(up_pos, down_pos))

    def boundingRect(self):
        rect = super().boundingRect()
        # Padded generously enough to cover the pulse ring's max growth
        # too, so animated frames don't get clipped at the item's edge.
        pad = self.CELL_RADIUS + self.PULSE_MAX_GROWTH + 6
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

            if self._pulse_state.is_active(self._edge_index, cell.position):
                self._paint_pulse_ring(painter, pt)

            fill, border = self._cell_colors(cell)
            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(border, 1))
            painter.drawEllipse(pt, self.CELL_RADIUS, self.CELL_RADIUS)

    def _paint_pulse_ring(self, painter, pt: QPointF):
        """A fading, shrinking ring around a cell that just changed
        state this step -- a lightweight stand-in for a per-cell
        animation without needing a QPropertyAnimation per cell."""
        progress = self._pulse_state.progress
        radius = self.CELL_RADIUS + self.PULSE_MAX_GROWTH * (1.0 - progress)
        color = QColor(self.COLOR_PULSE)
        color.setAlphaF(max(0.0, 1.0 - progress))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, 2))
        painter.drawEllipse(pt, radius, radius)


# Main Viewer

class ResultsViewer(QMainWindow):
    """Step-through viewer for a completed simulation run.

    Takes the network_data used for the run (for node layout) and the
    resulting history, and lets the user step forward/backward through
    it -- manually, or via Play/Pause at an adjustable speed -- seeing
    per-step statistics and the river's flood/dam/meadow state rendered
    on the network layout, with a brief highlight on whatever just
    changed.
    """

    # Playback speed presets, in steps per second. Index 2 ("1x") is
    # the default.
    SPEED_STEPS_PER_SEC = [0.5, 1, 2, 4, 8]
    DEFAULT_SPEED_INDEX = 2

    PULSE_DURATION_MS = 500
    PULSE_TICK_MS = 30

    def __init__(self, network_data: dict, history: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Results Viewer")
        self.setMinimumSize(940, 660)
        self.resize(1150, 720)

        self.network_data = network_data
        self.history = history
        self.current_index = 0

        self._outlet_ids = self._compute_outlet_ids()
        self._pulse_state = PulseState()

        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._on_play_tick)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(self.PULSE_TICK_MS)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
        self._pulse_elapsed_ms = 0

        self._build_ui()
        self._render_step(pulse=False)

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
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Scene / view
        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QBrush(QColor("#FAFAFA")))

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setFrameShape(QFrame.Shape.StyledPanel)
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.view, 1)

        side = QVBoxLayout()
        side.setAlignment(Qt.AlignmentFlag.AlignTop)
        side.setSpacing(10)
        side_container = QWidget()
        side_container.setLayout(side)
        side_container.setFixedWidth(280)
        layout.addWidget(side_container)

        side.addWidget(self._build_playback_group())
        side.addWidget(self._build_stats_group())
        side.addWidget(self._build_legend_group())
        side.addStretch(1)

        # Keyboard shortcuts: space to play/pause, arrows to step,
        # Home/End to jump to the first/last step.
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.toggle_play)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=self.previous_step)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=self.next_step)
        QShortcut(QKeySequence(Qt.Key.Key_Home), self, activated=self.jump_to_start)
        QShortcut(QKeySequence(Qt.Key.Key_End), self, activated=self.jump_to_end)

    def _build_playback_group(self) -> QGroupBox:
        group = QGroupBox("Playback")
        outer = QVBoxLayout()
        outer.setSpacing(8)

        self.step_label = QLabel()
        self.step_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.step_label)

        self.timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setMinimum(0)
        self.timeline_slider.setMaximum(max(0, len(self.history) - 1))
        self.timeline_slider.setToolTip("Scrub to a step")
        self.timeline_slider.valueChanged.connect(self._on_timeline_dragged)
        outer.addWidget(self.timeline_slider)

        # Transport controls: |<  <  Play/Pause  >  >|
        transport_row = QHBoxLayout()
        transport_row.setSpacing(4)

        self.start_btn = QPushButton("\u23ee")
        self.start_btn.setToolTip("Jump to first step (Home)")
        self.start_btn.setFixedWidth(36)
        self.start_btn.clicked.connect(self.jump_to_start)

        self.prev_btn = QPushButton("\u25c0")
        self.prev_btn.setToolTip("Previous step (\u2190)")
        self.prev_btn.setFixedWidth(36)
        self.prev_btn.clicked.connect(self.previous_step)

        self.play_btn = QPushButton("\u25b6  Play")
        self.play_btn.setToolTip("Play / pause (Space)")
        self.play_btn.setMinimumWidth(96)
        self.play_btn.clicked.connect(self.toggle_play)

        self.next_btn = QPushButton("\u25b6")
        self.next_btn.setToolTip("Next step (\u2192)")
        self.next_btn.setFixedWidth(36)
        self.next_btn.clicked.connect(self.next_step)

        self.end_btn = QPushButton("\u23ed")
        self.end_btn.setToolTip("Jump to last step (End)")
        self.end_btn.setFixedWidth(36)
        self.end_btn.clicked.connect(self.jump_to_end)

        for btn in (self.start_btn, self.prev_btn, self.play_btn, self.next_btn, self.end_btn):
            transport_row.addWidget(btn)
        outer.addLayout(transport_row)

        # Speed control
        speed_row = QHBoxLayout()
        speed_row.setSpacing(6)
        speed_row.addWidget(QLabel("Speed"))

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setMinimum(0)
        self.speed_slider.setMaximum(len(self.SPEED_STEPS_PER_SEC) - 1)
        self.speed_slider.setValue(self.DEFAULT_SPEED_INDEX)
        self.speed_slider.setToolTip("Playback speed")
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_row.addWidget(self.speed_slider, 1)

        self.speed_label = QLabel()
        self.speed_label.setMinimumWidth(38)
        speed_row.addWidget(self.speed_label)

        outer.addLayout(speed_row)
        self._update_speed_label()

        group.setLayout(outer)
        return group

    def _build_stats_group(self) -> QGroupBox:
        group = QGroupBox("Statistics")
        form = QFormLayout()
        form.setVerticalSpacing(6)

        self.flooded_label = QLabel()
        self.dams_created_label = QLabel()
        self.dams_broken_label = QLabel()
        for lbl in (self.flooded_label, self.dams_created_label, self.dams_broken_label):
            lbl.setStyleSheet("font-weight: bold;")

        form.addRow("Currently flooded cells", self.flooded_label)
        form.addRow("Dams created this step", self.dams_created_label)
        form.addRow("Dams broken this step", self.dams_broken_label)
        group.setLayout(form)
        return group

    def _build_legend_group(self) -> QGroupBox:
        group = QGroupBox("Legend")
        legend_layout = QVBoxLayout()
        legend_label = QLabel(
            "<span style='color:#1976D2'>\u25cf</span> Flooded cell<br>"
            "<span style='color:#5D4037'>\u25cf</span> Active dam<br>"
            "<span style='color:#9E9E9E'>\u25cf</span> Broken dam<br>"
            "<span style='color:#7CB342'>\u25cf</span> Meadow<br>"
            "<span style='color:#D7CCC8'>\u25cf</span> Empty cell<br>"
            "<span style='color:#FFB300'>\u25ce</span> Outlet<br>"
            "<span style='color:#FBC02D'>\u25cb</span> Just changed"
        )
        legend_label.setTextFormat(Qt.TextFormat.RichText)
        legend_label.setWordWrap(True)
        legend_layout.addWidget(legend_label)
        group.setLayout(legend_layout)
        return group


    # Playback speed

    def _current_interval_ms(self) -> int:
        steps_per_sec = self.SPEED_STEPS_PER_SEC[self.speed_slider.value()]
        return max(1, int(1000 / steps_per_sec))

    def _update_speed_label(self):
        steps_per_sec = self.SPEED_STEPS_PER_SEC[self.speed_slider.value()]
        text = f"{steps_per_sec:g}x"
        self.speed_label.setText(text)

    def _on_speed_changed(self, _value: int):
        self._update_speed_label()
        if self._play_timer.isActive():
            self._play_timer.setInterval(self._current_interval_ms())


    # Play / pause

    def toggle_play(self):
        if self._play_timer.isActive():
            self.pause_playback()
        else:
            self.start_playback()

    def start_playback(self):
        if not self.history:
            return
        if self.current_index >= len(self.history) - 1:
            self.current_index = 0
            self._render_step(pulse=False)
        self._play_timer.start(self._current_interval_ms())
        self.play_btn.setText("\u23f8  Pause")

    def pause_playback(self):
        self._play_timer.stop()
        self.play_btn.setText("\u25b6  Play")

    def _on_play_tick(self):
        last = len(self.history) - 1
        if self.current_index >= last:
            self.pause_playback()
            return
        self.current_index += 1
        self._sync_timeline_slider()
        self._render_step(pulse=True)


    # Manual navigation (always pauses playback first)

    def previous_step(self):
        self.pause_playback()
        if self.current_index > 0:
            self.current_index -= 1
            self._sync_timeline_slider()
            self._render_step(pulse=False)

    def next_step(self):
        self.pause_playback()
        if self.current_index < len(self.history) - 1:
            self.current_index += 1
            self._sync_timeline_slider()
            self._render_step(pulse=False)

    def jump_to_start(self):
        self.pause_playback()
        if self.current_index != 0:
            self.current_index = 0
            self._sync_timeline_slider()
            self._render_step(pulse=False)

    def jump_to_end(self):
        self.pause_playback()
        last = len(self.history) - 1
        if self.current_index != last:
            self.current_index = last
            self._sync_timeline_slider()
            self._render_step(pulse=False)

    def _sync_timeline_slider(self):
        self.timeline_slider.blockSignals(True)
        self.timeline_slider.setValue(self.current_index)
        self.timeline_slider.blockSignals(False)

    def _on_timeline_dragged(self, value: int):
        # Only fires for genuine user interaction: every programmatic
        # slider update above blocks signals first.
        self.pause_playback()
        self.current_index = value
        self._render_step(pulse=False)


    # Pulse (highlight) animation

    def _on_pulse_tick(self):
        self._pulse_elapsed_ms += self.PULSE_TICK_MS
        progress = self._pulse_elapsed_ms / self.PULSE_DURATION_MS
        if progress >= 1.0:
            self._pulse_state.stop()
            self._pulse_timer.stop()
        else:
            self._pulse_state.progress = progress
        self.scene.update()

    def _changed_cell_keys(self, step) -> set[tuple[int, int]]:
        """(edge_index, position) pairs for cells whose state changed
        on exactly this step -- newly flooded, dam just created, or dam
        just broken -- so the pulse only highlights what's new."""
        keys: set[tuple[int, int]] = set()
        for edge_index, edge in enumerate(step.river_snapshot.edges):
            for cell in edge.cells.values():
                changed = (
                    (cell.flooded and cell.flooded_step == step.step)
                    or (cell.dam is not None and cell.dam.created_step == step.step)
                    or (cell.dam is not None and cell.dam.broken and cell.dam.broken_step == step.step)
                )
                if changed:
                    keys.add((edge_index, cell.position))
        return keys


    # Rendering

    def _render_step(self, pulse: bool):
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
        for edge_index, (edge_data, river_edge) in enumerate(zip(edges_data, river_edges)):
            up_id, down_id = edge_pair(edge_data)
            up_x, up_y = node_positions[up_id]
            down_x, down_y = node_positions[down_id]
            cells = [river_edge.cells[pos] for pos in sorted(river_edge.cells.keys())]
            self.scene.addItem(
                ResultEdgeItem(QPointF(up_x, up_y), QPointF(down_x, down_y), cells, edge_index, self._pulse_state)
            )

        bounds = self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self.scene.setSceneRect(bounds)
        self.view.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)

        last_step = len(self.history) - 1
        self.step_label.setText(f"Step {step.step} of {last_step}")
        self.flooded_label.setText(str(len(step.cells_flooded)))
        self.dams_created_label.setText(str(len(step.dams_created)))
        self.dams_broken_label.setText(str(len(step.dams_broken)))

        self.start_btn.setEnabled(self.current_index > 0)
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < last_step)
        self.end_btn.setEnabled(self.current_index < last_step)
        self.play_btn.setEnabled(last_step > 0)

        if pulse:
            self._pulse_elapsed_ms = 0
            self._pulse_state.start(self._changed_cell_keys(step))
            if self._pulse_state.active_keys:
                self._pulse_timer.start()
        else:
            self._pulse_timer.stop()
            self._pulse_state.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene.itemsBoundingRect().isValid():
            self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def closeEvent(self, event):
        self._play_timer.stop()
        self._pulse_timer.stop()
        super().closeEvent(event)


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