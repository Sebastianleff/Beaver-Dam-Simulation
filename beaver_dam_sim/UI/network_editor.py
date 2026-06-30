"""
Graphical River Network Editor (PySide6) - Step 16
Highlights nodes that border flooded edges with a pulsing glow effect
"""

import sys
import json
import math
import random
from collections import deque, defaultdict
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from __main__ import NetworkEditor

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QMessageBox,
    QApplication,
    QFileDialog,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsItem,
    QFormLayout,
    QGridLayout,
    QDoubleSpinBox,
    QSpinBox,
    QGraphicsTextItem,
    QLabel,
    QComboBox,
    QGroupBox,
    QSlider,
)
from PySide6.QtCore import Qt, QLineF, QTimer, QPointF
from PySide6.QtGui import QPen, QBrush, QColor, QRadialGradient

from beaver_dam_sim.service import SimulationService, SimParam


# Water dot

class WaterDot(QGraphicsEllipseItem):
    RADIUS = 5

    def __init__(self, start: QPointF, end: QPointF, progress: float = 0.0):
        r = self.RADIUS
        super().__init__(-r, -r, r * 2, r * 2)

        self.start = start
        self.end = end
        self.progress = progress

        self.setBrush(QBrush(QColor("#64B5F6")))
        self.setPen(QPen(QColor("#1565C0"), 1))
        self.setZValue(100)  # draw above nodes

        self._update_pos()

    def _update_pos(self):
        x = self.start.x() + (self.end.x() - self.start.x()) * self.progress
        y = self.start.y() + (self.end.y() - self.start.y()) * self.progress
        self.setPos(x, y)

    def advance(self, delta: float) -> bool:
        self.progress += delta
        if self.progress >= 1.0:
            self.progress -= 1.0
        self._update_pos()
        return False   # never clamps; caller handles wrap


# Node

class NodeItem(QGraphicsEllipseItem):
    RADIUS = 20

    def __init__(self, node_id: int, x: float, y: float):
        r = self.RADIUS
        super().__init__(-r, -r, r * 2, r * 2)

        self.node_id = node_id
        self.edges = []
        self._state = "default"

        # Glow ring drawn behind the node
        glow_r = r + 8
        self._glow = QGraphicsEllipseItem(-glow_r, -glow_r, glow_r * 2, glow_r * 2, self)
        self._glow.setPen(QPen(Qt.GlobalColor.transparent))
        self._glow.setBrush(QBrush(Qt.GlobalColor.transparent))
        self._glow.setZValue(-1)

        # Pulse state
        self._pulse = 0.0          # 0.0 → 1.0 → 0.0
        self._pulse_dir = 1        # 1 = growing, -1 = shrinking

        self.setBrush(QBrush(Qt.GlobalColor.darkCyan))
        self.setPen(QPen(Qt.GlobalColor.black, 2))

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

        self.label = QGraphicsTextItem(str(node_id), self)
        self.label.setDefaultTextColor(Qt.GlobalColor.white)
        self.label.setPos(-6, -10)

        self.setPos(x, y)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            for e in self.edges:
                e.update_position()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        editor = cast("NetworkEditor", cast(QWidget, self.scene().views()[0].window()))
        editor.node_clicked(self)
        super().mousePressEvent(event)

    def set_state(self, state: str):
        self._state = state
        colors = {
            "default": Qt.GlobalColor.darkCyan,
            "dam":     QColor("#8B4513"),
            "flooded": QColor("#1565C0"),
            "meadow":  QColor("#2E7D32"),
        }
        self.setBrush(QBrush(colors.get(state, Qt.GlobalColor.darkCyan)))

        if state != "flooded":
            self._glow.setBrush(QBrush(Qt.GlobalColor.transparent))
            self._glow.setPen(QPen(Qt.GlobalColor.transparent))

    def pulse_tick(self, delta: float = 0.05):
        """
        Advance the pulse animation for flooded nodes.
        Call this from the flow timer (~30 fps).
        """
        if self._state != "flooded":
            return

        self._pulse += self._pulse_dir * delta
        if self._pulse >= 1.0:
            self._pulse = 1.0
            self._pulse_dir = -1
        elif self._pulse <= 0.0:
            self._pulse = 0.0
            self._pulse_dir = 1

        # Glow colour: semi-transparent blue, opacity pulses 40–180
        alpha = int(40 + self._pulse * 140)
        glow_color = QColor(100, 181, 246, alpha)   # #64B5F6 with variable alpha

        r = self.RADIUS + 8
        gradient = QRadialGradient(0, 0, r)
        gradient.setColorAt(0.0, glow_color)
        gradient.setColorAt(1.0, QColor(100, 181, 246, 0))

        self._glow.setBrush(QBrush(gradient))
        self._glow.setPen(QPen(Qt.GlobalColor.transparent))


# Edge

class EdgeItem(QGraphicsLineItem):
    DOT_COUNT = 3
    DOT_SPEED = 0.015

    def __init__(self, start_node: NodeItem, end_node: NodeItem):
        super().__init__()

        self.start_node = start_node
        self.end_node = end_node
        self._state = "default"
        self._dots: list[WaterDot] = []

        # Flow direction: set by display_step from sim edge ordering
        # dots travel from flow_start → flow_end
        self.flow_start: NodeItem = start_node
        self.flow_end: NodeItem = end_node

        self.setPen(QPen(Qt.GlobalColor.black, 2))
        self.update_position()

    def update_position(self):
        self.setLine(QLineF(self.start_node.scenePos(), self.end_node.scenePos()))
        for dot in self._dots:
            dot.start = self.start_node.scenePos()
            dot.end = self.end_node.scenePos()

    def set_state(self, state: str, respawn_dots: bool = False):
        if self._state == state and not respawn_dots:
            return
        self._state = state

        colors = {
            "default": Qt.GlobalColor.black,
            "dam":     QColor("#8B4513"),
            "flooded": QColor("#1565C0"),
            "meadow":  QColor("#2E7D32"),
        }
        color = colors.get(state, Qt.GlobalColor.black)
        self.setPen(QPen(color, 4 if state != "default" else 2))

        if state == "flooded":
            self._spawn_dots()
        else:
            self._remove_dots()

    def _spawn_dots(self):
        self._remove_dots()
        scene = self.scene()
        if scene is None:
            return
        start = self.flow_start.scenePos()
        end = self.flow_end.scenePos()
        for i in range(self.DOT_COUNT):
            dot = WaterDot(start, end, i / self.DOT_COUNT)
            scene.addItem(dot)
            self._dots.append(dot)

    def _remove_dots(self):
        scene = self.scene()
        for dot in self._dots:
            if scene:
                scene.removeItem(dot)
        self._dots.clear()

    def advance_dots(self):
        start = self.flow_start.scenePos()
        end = self.flow_end.scenePos()
        for dot in self._dots:
            dot.start = start
            dot.end = end
            dot.progress += self.DOT_SPEED
            if dot.progress >= 1.0:
                dot.progress -= 1.0   # wrap instead of reset so speed stays consistent
            dot._update_pos()


# Main Editor

class NetworkEditor(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Beaver Dam Network Editor - Step 16")
        self.setMinimumSize(1100, 700)

        self.service = SimulationService()

        self.node_counter = 0
        self.nodes: dict[int, NodeItem] = {}
        self.edges: list[EdgeItem] = []
        self.selected_node = None
        self._add_edge_mode = False
        self.simulation_history = []
        self.current_step = 0

        self._sim_timer = QTimer(self)
        self._sim_timer.timeout.connect(self._simulation_tick)

        # Single flow timer drives both dots and node pulse
        self._flow_timer = QTimer(self)
        self._flow_timer.timeout.connect(self._flow_tick)
        self._flow_timer.start(33)

        self.resize(1280, 720)
        self._build_ui()

    # UI

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(4)
        main_layout.setContentsMargins(6, 6, 6, 6)

        control_panel = QVBoxLayout()
        control_panel.setSpacing(4)

        # Row 1: Generate Network + Simulation Parameters side by side
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        def _spin(widget, width=72):
            widget.setMinimumWidth(width)
            return widget

        # Generate Network (left column)
        gen_group = QGroupBox("Generate Network")
        gen_form = QFormLayout()
        gen_form.setVerticalSpacing(2)
        gen_form.setHorizontalSpacing(4)
        gen_form.setContentsMargins(4, 4, 4, 4)

        self.gen_node_count = _spin(QSpinBox())
        self.gen_node_count.setRange(2, 50)
        self.gen_node_count.setValue(6)

        self.gen_edge_count = _spin(QSpinBox())
        self.gen_edge_count.setRange(1, 100)
        self.gen_edge_count.setValue(5)

        self.gen_topology = QComboBox()
        self.gen_topology.addItems(["Linear", "Branching", "Random"])
        self.gen_topology.currentTextChanged.connect(self._update_edge_hint)
        self.gen_node_count.valueChanged.connect(lambda _: self._update_edge_hint(self.gen_topology.currentText()))

        self.edge_hint = QLabel("")
        self.edge_hint.setStyleSheet("color: gray; font-size: 9px;")
        self.edge_hint.setWordWrap(True)

        gen_form.addRow("Nodes", self.gen_node_count)
        gen_form.addRow("Edges", self.gen_edge_count)
        gen_form.addRow("Topology", self.gen_topology)
        gen_form.addRow("", self.edge_hint)
        gen_group.setLayout(gen_form)

        # Simulation Parameters (right column)
        sim_group = QGroupBox("Simulation Parameters")
        sim_form = QFormLayout()
        sim_form.setVerticalSpacing(2)
        sim_form.setHorizontalSpacing(4)
        sim_form.setContentsMargins(4, 4, 4, 4)

        self.dam_creation = _spin(QDoubleSpinBox())
        self.dam_creation.setRange(0, 1)
        self.dam_creation.setSingleStep(0.1)
        self.dam_creation.setValue(0.3)

        self.dam_break = _spin(QDoubleSpinBox())
        self.dam_break.setRange(0, 1)
        self.dam_break.setValue(0.3)

        self.flood_prob = _spin(QDoubleSpinBox())
        self.flood_prob.setRange(0, 1)
        self.flood_prob.setValue(0.3)

        self.flood_break = _spin(QDoubleSpinBox())
        self.flood_break.setRange(0, 1)
        self.flood_break.setValue(0.3)

        self.meadow = _spin(QDoubleSpinBox())
        self.meadow.setRange(0, 1)
        self.meadow.setValue(0.3)

        self.steps = _spin(QSpinBox())
        self.steps.setRange(1, 10000)
        self.steps.setValue(50)

        self.seed = _spin(QSpinBox())
        self.seed.setRange(0, 999999)
        self.seed.setValue(1)

        self.stabilization = _spin(QSpinBox())
        self.stabilization.setRange(0, 1000)
        self.stabilization.setValue(3)

        sim_form.addRow("Dam Creation", self.dam_creation)
        sim_form.addRow("Dam Break", self.dam_break)
        sim_form.addRow("Flood Prob", self.flood_prob)
        sim_form.addRow("Flood Break", self.flood_break)
        sim_form.addRow("Meadow Prob", self.meadow)
        sim_form.addRow("Steps", self.steps)
        sim_form.addRow("Seed", self.seed)
        sim_form.addRow("Stabilization", self.stabilization)
        sim_group.setLayout(sim_form)

        top_row.addWidget(gen_group, 0, Qt.AlignmentFlag.AlignTop)
        top_row.addWidget(sim_group, 0, Qt.AlignmentFlag.AlignTop)
        control_panel.addLayout(top_row)

        # Row 2: action buttons in one line
        action_row = QHBoxLayout()
        action_row.setSpacing(4)

        gen_btn = QPushButton("Generate")
        gen_btn.clicked.connect(self.generate_network)

        run_btn = QPushButton("Run Sim")
        run_btn.clicked.connect(self.run_simulation)

        layout_btn = QPushButton("Auto-Layout")
        layout_btn.clicked.connect(self.auto_layout_by_flow)

        add_node_btn = QPushButton("Add Node")
        add_node_btn.clicked.connect(self.add_node)

        self.add_edge_btn = QPushButton("Add Edge")
        self.add_edge_btn.setCheckable(True)
        self.add_edge_btn.clicked.connect(self._toggle_add_edge_mode)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_network)

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self.load_network)

        for btn in (gen_btn, run_btn, layout_btn, add_node_btn, self.add_edge_btn, save_btn, load_btn):
            action_row.addWidget(btn)

        control_panel.addLayout(action_row)

        # Row 3: Playback
        anim_group = QGroupBox("Playback")
        anim_layout = QVBoxLayout()
        anim_layout.setSpacing(3)

        playback_row = QHBoxLayout()
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.clicked.connect(self.toggle_play)
        self.play_btn.setEnabled(False)

        stop_btn = QPushButton("■ Stop")
        stop_btn.clicked.connect(self.stop_animation)

        prev_btn = QPushButton("◀")
        prev_btn.clicked.connect(self.previous_step)

        next_btn = QPushButton("▶|")
        next_btn.clicked.connect(self.next_step)

        playback_row.addWidget(prev_btn)
        playback_row.addWidget(self.play_btn)
        playback_row.addWidget(stop_btn)
        playback_row.addWidget(next_btn)

        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Slow"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 10)
        self.speed_slider.setValue(5)
        self.speed_slider.setTickInterval(1)
        self.speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.speed_slider.valueChanged.connect(self._update_timer_interval)
        speed_row.addWidget(self.speed_slider)
        speed_row.addWidget(QLabel("Fast"))

        self.step_label = QLabel("Step: 0")
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        anim_layout.addLayout(playback_row)
        anim_layout.addLayout(speed_row)
        anim_layout.addWidget(self.step_label)
        anim_group.setLayout(anim_layout)
        control_panel.addWidget(anim_group)

        # Row 4: Legend
        legend_label = QLabel(
            "<b>Legend</b> &nbsp;"
            "<span style='color:#00838F'>■</span> Default &nbsp;"
            "<span style='color:#8B4513'>■</span> Dam &nbsp;"
            "<span style='color:#1565C0'>■</span> Flooded &nbsp;"
            "<span style='color:#2E7D32'>■</span> Meadow &nbsp;"
            "<span style='color:#64B5F6'>●</span> Flow &nbsp;"
            "<span style='color:#64B5F6'>◎</span> Flooded node"
        )
        legend_label.setTextFormat(Qt.TextFormat.RichText)
        legend_label.setWordWrap(True)
        control_panel.addWidget(legend_label)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setSceneRect(0, 0, 1000, 800)

        main_layout.addLayout(control_panel)
        main_layout.addWidget(self.view, 1)

        self._update_edge_hint(self.gen_topology.currentText())

    # Flow + pulse tick

    def _flow_tick(self):
        for edge in self.edges:
            if edge._state == "flooded":
                edge.advance_dots()
        for node in self.nodes.values():
            node.pulse_tick()

    # Playback

    def _timer_interval_ms(self) -> int:
        return int(1100 - self.speed_slider.value() * 100)

    def _update_timer_interval(self):
        if self._sim_timer.isActive():
            self._sim_timer.setInterval(self._timer_interval_ms())

    def toggle_play(self):
        if self._sim_timer.isActive():
            self._sim_timer.stop()
            self.play_btn.setText("▶ Play")
        else:
            if self.current_step >= len(self.simulation_history) - 1:
                self.current_step = 0
                self.display_step()
            self._sim_timer.start(self._timer_interval_ms())
            self.play_btn.setText("⏸ Pause")

    def stop_animation(self):
        self._sim_timer.stop()
        self.play_btn.setText("▶ Play")
        self.current_step = 0
        self.display_step()

    def _simulation_tick(self):
        if self.current_step < len(self.simulation_history) - 1:
            self.current_step += 1
            self.display_step()
        else:
            self._sim_timer.stop()
            self.play_btn.setText("▶ Play")

    # Network generation

    def _update_edge_hint(self, topology: str):
        n = self.gen_node_count.value()
        if topology == "Linear":
            self.edge_hint.setText(f"Linear uses exactly {n - 1} edges")
            self.gen_edge_count.setValue(n - 1)
            self.gen_edge_count.setEnabled(False)
        elif topology == "Branching":
            self.edge_hint.setText(f"Branching uses exactly {n - 1} edges")
            self.gen_edge_count.setValue(n - 1)
            self.gen_edge_count.setEnabled(False)
        else:
            self.edge_hint.setText("Random: set edge count freely")
            self.gen_edge_count.setEnabled(True)

    def _clear_scene(self):
        self._sim_timer.stop()
        self.play_btn.setText("▶ Play")
        for edge in self.edges:
            edge._remove_dots()
        self.scene.clear()
        self.nodes.clear()
        self.edges.clear()
        self.selected_node = None
        self.node_counter = 0
        self.simulation_history = []
        self.step_label.setText("Step: 0")

    def _add_node_at(self, x: float, y: float) -> NodeItem:
        self.node_counter += 1
        node = NodeItem(self.node_counter, x, y)
        self.scene.addItem(node)
        self.nodes[self.node_counter] = node
        return node

    def _add_edge_between(self, a: NodeItem, b: NodeItem):
        edge = EdgeItem(a, b)
        self.scene.addItem(edge)
        self.edges.append(edge)
        a.edges.append(edge)
        b.edges.append(edge)

    def generate_network(self):
        n = self.gen_node_count.value()
        topology = self.gen_topology.currentText()
        self._clear_scene()
        cx, cy = 500, 400
        radius = min(300, 60 * n)

        if topology == "Linear":
            self._generate_linear(n, cx, cy)
        elif topology == "Branching":
            self._generate_branching(n, cx, cy, radius)
        else:
            self._generate_random(n, self.gen_edge_count.value(), cx, cy, radius)

    def _generate_linear(self, n: int, cx: float, cy: float):
        """Linear chain laid out top-to-bottom like a single-branch tree."""
        y_step = 700 / (n + 1)
        nodes = []
        for i in range(n):
            x = cx + (30 if i % 2 else -30)   # slight zigzag so it doesn't look like a ruler
            y = 80 + y_step * i
            nodes.append(self._add_node_at(x, y))
        for i in range(len(nodes) - 1):
            self._add_edge_between(nodes[i], nodes[i + 1])

    def _generate_branching(self, n: int, cx: float, cy: float, radius: float):
        nodes = [self._add_node_at(cx, 80)]
        rng = random.Random(self.seed.value())
        level_y = 80
        current_level = [nodes[0]]

        while len(nodes) < n:
            next_level = []
            level_y += 140
            slots = min(len(current_level) * 2, n - len(nodes))
            x_positions = [
                cx + (i - slots / 2 + 0.5) * (700 / max(slots, 1))
                for i in range(slots)
            ]
            rng.shuffle(x_positions)

            for i, parent in enumerate(current_level):
                if len(nodes) >= n:
                    break
                child = self._add_node_at(x_positions[i % len(x_positions)], level_y)
                nodes.append(child)
                next_level.append(child)
                self._add_edge_between(parent, child)

                if len(nodes) < n and i + len(current_level) < slots:
                    child2 = self._add_node_at(
                        x_positions[(i + len(current_level)) % len(x_positions)],
                        level_y
                    )
                    nodes.append(child2)
                    next_level.append(child2)
                    self._add_edge_between(parent, child2)

            current_level = next_level if next_level else current_level

    def _generate_random(self, n: int, e: int, cx: float, cy: float, radius: float):
        """Random edges, but nodes laid out in branching-style levels top-to-bottom."""
        rng = random.Random(self.seed.value())

        # Assign nodes to levels randomly (like a rough tree depth)
        max_level = max(2, n // 3)
        level_assign: dict[int, list[int]] = defaultdict(list)
        level_assign[0].append(0)
        for i in range(1, n):
            level_assign[rng.randint(1, max_level)].append(i)

        # Position by level
        scene_w, scene_h = 900, 720
        levels = sorted(level_assign.keys())
        y_step = scene_h / (len(levels) + 1)
        nodes = [None] * n
        for lvl in levels:
            ids = level_assign[lvl]
            x_step = scene_w / (len(ids) + 1)
            y = 80 + y_step * lvl
            for j, node_idx in enumerate(ids):
                nodes[node_idx] = self._add_node_at(x_step * (j + 1), y)

        # Ensure connectivity with a random spanning path, then add extra edges
        order = list(range(n))
        rng.shuffle(order)
        existing: set[tuple[int, int]] = set()
        for i in range(len(order) - 1):
            a, b = order[i], order[i + 1]
            key = (min(a, b), max(a, b))
            if key not in existing:
                self._add_edge_between(nodes[a], nodes[b])
                existing.add(key)

        attempts = 0
        while len(self.edges) < e and attempts < 500:
            a, b = rng.sample(range(n), 2)
            key = (min(a, b), max(a, b))
            if key not in existing:
                self._add_edge_between(nodes[a], nodes[b])
                existing.add(key)
            attempts += 1

    # Manual node

    def add_node(self):
        self.node_counter += 1
        node = NodeItem(
            self.node_counter,
            100 + self.node_counter * 20,
            100 + self.node_counter * 20
        )
        self.scene.addItem(node)
        self.nodes[self.node_counter] = node

    # Connect nodes

    def _toggle_add_edge_mode(self, checked: bool):
        self._add_edge_mode = checked
        self.add_edge_btn.setText("Add Edge" if checked else "Add Edge")
        # Cancel any pending node selection when toggling off
        if not checked and self.selected_node:
            self.selected_node.set_state(self.selected_node._state)
            self.selected_node = None

    def node_clicked(self, node):
        if not self._add_edge_mode:
            return

        if self.selected_node is None:
            self.selected_node = node
            node.setBrush(QBrush(Qt.GlobalColor.green))
            return

        if self.selected_node == node:
            node.set_state(node._state)
            self.selected_node = None
            return

        edge = EdgeItem(self.selected_node, node)
        self.scene.addItem(edge)
        self.edges.append(edge)
        self.selected_node.edges.append(edge)
        node.edges.append(edge)
        self.selected_node.set_state(self.selected_node._state)
        self.selected_node = None

    # Auto-layout

    def auto_layout_by_flow(self):
        """Position nodes so upstream nodes appear higher (smaller y) than downstream ones."""
        if not self.simulation_history:
            QMessageBox.warning(self, "No Simulation", "Run a simulation first to determine flow direction.")
            return

        river = self.simulation_history[self.current_step].river_snapshot

        # Build downstream adjacency and in-degree from sim edges
        downstream: dict[int, list[int]] = {nid: [] for nid in self.nodes}
        in_degree: dict[int, int] = {nid: 0 for nid in self.nodes}

        for sim_edge in river.edges:
            u = sim_edge.up_stream_node
            d = sim_edge.down_stream_node
            if u in downstream and d in downstream:
                downstream[u].append(d)
                in_degree[d] += 1

        # Kahn's algorithm to assign depth levels
        depth: dict[int, int] = {}
        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        while queue:
            nid = queue.popleft()
            for child in downstream[nid]:
                depth[child] = max(depth.get(child, 0), depth.get(nid, 0) + 1)
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        # Group nodes by depth level
        levels: dict[int, list[int]] = defaultdict(list)
        for nid in self.nodes:
            levels[depth.get(nid, 0)].append(nid)

            # Position nodes: depth 0 (most upstream) at top, deeper = lower y
            scene_width = self.view.sceneRect().width()
            scene_height = self.view.sceneRect().height()
            max_depth = max(levels.keys()) if levels else 0
            y_step = scene_height / (max_depth + 2)

            # Seeded RNG so the layout is reproducible but not a straight line,
            # even when each level only contains a single node (e.g. Linear topology).
            rng = random.Random(self.seed.value())
            jitter_amplitude = min(80.0, scene_width * 0.12)

            for level, node_ids in levels.items():
                y = y_step * (level + 1)
                x_step = scene_width / (len(node_ids) + 1)
                for i, nid in enumerate(sorted(node_ids)):
                    base_x = x_step * (i + 1)
                    # Zigzag bias alternates left/right by level so chains snake
                    # back and forth instead of forming a vertical line.
                    zigzag = jitter_amplitude * (1 if level % 2 == 0 else -1)
                    random_offset = rng.uniform(-jitter_amplitude * 0.5, jitter_amplitude * 0.5)
                    x = base_x + zigzag * 0.6 + random_offset
                    x = max(40.0, min(scene_width - 40.0, x))
                    self.nodes[nid].setPos(x, y)

            for edge in self.edges:
                edge.update_position()

    # Simulation

    def run_simulation(self):
        if len(self.nodes) < 2:
            QMessageBox.warning(self, "Error", "Need at least 2 nodes")
            return

        self._sim_timer.stop()
        self.play_btn.setText("▶ Play")

        params = SimParam(
            dam_creation_probability=self.dam_creation.value(),
            dam_break_probability=self.dam_break.value(),
            flood_probability=self.flood_prob.value(),
            flood_break_probability=self.flood_break.value(),
            stabilization_time=self.stabilization.value(),
            steps=self.steps.value(),
            random_seed=self.seed.value(),
            meadow_probability=self.meadow.value(),
        )

        try:
            edges = [
                (e.start_node.node_id, e.end_node.node_id)
                for e in self.edges
            ]
            river = self.service.create_river(len(self.nodes), edges)
            self.simulation_history = self.service.run_simulation(params, river)
            self.current_step = 0
            self.play_btn.setEnabled(True)
            self.display_step()

            QMessageBox.information(
                self,
                "Simulation Complete",
                f"Simulation finished!\nSteps: {len(self.simulation_history)}\n"
                "Press ▶ Play to animate."
            )

        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))

    @staticmethod
    def _edge_dominant_state(sim_edge) -> str:
        has_dam = False
        has_meadow = False

        for cell in sim_edge.cells.values():
            if cell.flooded_step is not None:
                return "flooded"
            if cell.dam and not cell.dam.broken_step:
                has_dam = True
            if cell.dam and cell.dam.meadow:
                has_meadow = True

        if has_dam:
            return "dam"
        if has_meadow:
            return "meadow"
        return "default"

    def display_step(self):
        if not self.simulation_history:
            return

        step = self.simulation_history[self.current_step]
        river = step.river_snapshot

        self.step_label.setText(
            f"Step: {step.step} / {len(self.simulation_history) - 1}  |  "
            f"Flooded: {len(step.cells_flooded)}  |  "
            f"Dams: +{len(step.dams_created)} / -{len(step.dams_broken)}"
        )

        # Reset all edges and nodes
        for edge_item in self.edges:
            edge_item.set_state("default")
        for node in self.nodes.values():
            node.set_state("default")

        # Track which nodes border a flooded edge
        flooded_node_ids: set[int] = set()

        for sim_edge in river.edges:
            state = self._edge_dominant_state(sim_edge)
            for edge_item in self.edges:
                a = edge_item.start_node.node_id
                b = edge_item.end_node.node_id
                if (a, b) == (sim_edge.down_stream_node, sim_edge.up_stream_node) or \
                   (b, a) == (sim_edge.down_stream_node, sim_edge.up_stream_node):
                    # Set flow direction: upstream → downstream
                    if sim_edge.up_stream_node in self.nodes and sim_edge.down_stream_node in self.nodes:
                        edge_item.flow_start = self.nodes[sim_edge.up_stream_node]
                        edge_item.flow_end = self.nodes[sim_edge.down_stream_node]
                    edge_item.set_state(state, respawn_dots=(state == "flooded"))
                    if state == "flooded":
                        flooded_node_ids.add(a)
                        flooded_node_ids.add(b)
                    break

        # Highlight nodes that border flooded edges
        for node_id in flooded_node_ids:
            if node_id in self.nodes:
                self.nodes[node_id].set_state("flooded")

    # Save / Load

    def save_network(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save", "", "JSON (*.json)")
        if not path:
            return

        data = {
            "nodes": [
                {"id": n.node_id, "x": n.scenePos().x(), "y": n.scenePos().y()}
                for n in self.nodes.values()
            ],
            "edges": [
                (e.start_node.node_id, e.end_node.node_id)
                for e in self.edges
            ]
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=4)

    def load_network(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load", "", "JSON (*.json)")
        if not path:
            return

        with open(path, "r") as f:
            data = json.load(f)

        self._clear_scene()

        for n in data["nodes"]:
            node = NodeItem(n["id"], n["x"], n["y"])
            self.scene.addItem(node)
            self.nodes[n["id"]] = node
            self.node_counter = max(self.node_counter, n["id"])

        for a, b in data["edges"]:
            e = EdgeItem(self.nodes[a], self.nodes[b])
            self.scene.addItem(e)
            self.edges.append(e)
            self.nodes[a].edges.append(e)
            self.nodes[b].edges.append(e)

    # Step navigation

    def next_step(self):
        if not self.simulation_history:
            return
        if self.current_step < len(self.simulation_history) - 1:
            self.current_step += 1
            self.display_step()

    def previous_step(self):
        if not self.simulation_history:
            return
        if self.current_step > 0:
            self.current_step -= 1
            self.display_step()


# Run

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = NetworkEditor()
    w.showMaximized()
    sys.exit(app.exec())