"""
Graphical River Network Editor (PySide6) - Step 13
Adds auto-generate network from topology + size parameters
"""

import sys
import json
import math
import random
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
    QFormLayout,
    QDoubleSpinBox,
    QSpinBox,
    QGraphicsTextItem,
    QLabel,
    QComboBox,
    QGroupBox,
)
from PySide6.QtCore import Qt, QLineF
from PySide6.QtGui import QPen, QBrush, QColor
from PySide6.QtWidgets import QGraphicsItem

from beaver_dam_sim.service import SimulationService, SimParam


# Node
class NodeItem(QGraphicsEllipseItem):
    def __init__(self, node_id: int, x: float, y: float, radius: int = 20):
        super().__init__(-radius, -radius, radius * 2, radius * 2)

        self.node_id = node_id
        self.edges = []

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
        editor = cast("NetworkEditor", self.scene().views()[0].window())
        editor.node_clicked(self)
        super().mousePressEvent(event)

    def set_state(self, state: str):
        colors = {
            "default": Qt.GlobalColor.darkCyan,
            "dam":     QColor("#8B4513"),
            "flooded": QColor("#1565C0"),
            "meadow":  QColor("#2E7D32"),
        }
        self.setBrush(QBrush(colors.get(state, Qt.GlobalColor.darkCyan)))


# Edge
class EdgeItem(QGraphicsLineItem):
    def __init__(self, start_node, end_node):
        super().__init__()

        self.start_node = start_node
        self.end_node = end_node

        self.setPen(QPen(Qt.GlobalColor.black, 2))
        self.update_position()

    def update_position(self):
        self.setLine(QLineF(self.start_node.scenePos(), self.end_node.scenePos()))

    def set_state(self, state: str):
        colors = {
            "default": Qt.GlobalColor.black,
            "dam":     QColor("#8B4513"),
            "flooded": QColor("#1565C0"),
            "meadow":  QColor("#2E7D32"),
        }
        color = colors.get(state, Qt.GlobalColor.black)
        self.setPen(QPen(color, 4 if state != "default" else 2))


# Main Editor
class NetworkEditor(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Beaver Dam Network Editor - Step 13")
        self.setMinimumSize(1100, 700)

        self.service = SimulationService()

        self.node_counter = 0
        self.nodes = {}
        self.edges = []
        self.selected_node = None
        self.simulation_history = []
        self.current_step = 0

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)

        control_panel = QVBoxLayout()

        # Generate Network group
        gen_group = QGroupBox("Generate Network")
        gen_form = QFormLayout()

        self.gen_node_count = QSpinBox()
        self.gen_node_count.setRange(2, 50)
        self.gen_node_count.setValue(6)

        self.gen_edge_count = QSpinBox()
        self.gen_edge_count.setRange(1, 100)
        self.gen_edge_count.setValue(5)

        self.gen_topology = QComboBox()
        self.gen_topology.addItems(["Linear", "Branching", "Random"])
        self.gen_topology.currentTextChanged.connect(self._update_edge_hint)

        gen_form.addRow("Nodes", self.gen_node_count)
        gen_form.addRow("Edges", self.gen_edge_count)
        gen_form.addRow("Topology", self.gen_topology)

        self.edge_hint = QLabel("")
        self.edge_hint.setStyleSheet("color: gray; font-size: 10px;")
        gen_form.addRow("", self.edge_hint)

        gen_group.setLayout(gen_form)

        gen_btn = QPushButton("Generate Network")
        gen_btn.clicked.connect(self.generate_network)

        control_panel.addWidget(gen_group)
        control_panel.addWidget(gen_btn)

        # Simulation params group
        sim_group = QGroupBox("Simulation Parameters")
        form = QFormLayout()

        self.dam_creation = QDoubleSpinBox()
        self.dam_creation.setRange(0, 1)
        self.dam_creation.setSingleStep(0.1)
        self.dam_creation.setValue(0.3)

        self.dam_break = QDoubleSpinBox()
        self.dam_break.setRange(0, 1)
        self.dam_break.setValue(0.3)

        self.flood_prob = QDoubleSpinBox()
        self.flood_prob.setRange(0, 1)
        self.flood_prob.setValue(0.3)

        self.flood_break = QDoubleSpinBox()
        self.flood_break.setRange(0, 1)
        self.flood_break.setValue(0.3)

        self.meadow = QDoubleSpinBox()
        self.meadow.setRange(0, 1)
        self.meadow.setValue(0.3)

        self.steps = QSpinBox()
        self.steps.setRange(1, 10000)
        self.steps.setValue(50)

        self.seed = QSpinBox()
        self.seed.setRange(0, 999999)
        self.seed.setValue(1)

        self.stabilization = QSpinBox()
        self.stabilization.setRange(0, 1000)
        self.stabilization.setValue(3)

        form.addRow("Dam Creation", self.dam_creation)
        form.addRow("Dam Break", self.dam_break)
        form.addRow("Flood Prob", self.flood_prob)
        form.addRow("Flood Break", self.flood_break)
        form.addRow("Meadow Prob", self.meadow)
        form.addRow("Steps", self.steps)
        form.addRow("Seed", self.seed)
        form.addRow("Stabilization", self.stabilization)

        sim_group.setLayout(form)
        control_panel.addWidget(sim_group)

        # Buttons
        run_btn = QPushButton("Run Simulation")
        run_btn.clicked.connect(self.run_simulation)

        add_node_btn = QPushButton("Add Node")
        add_node_btn.clicked.connect(self.add_node)

        simulation_row = QHBoxLayout()
        prev_btn = QPushButton("◀ Prev")
        prev_btn.clicked.connect(self.previous_step)
        next_btn = QPushButton("Next ▶")
        next_btn.clicked.connect(self.next_step)
        self.step_label = QLabel("Step: 0")
        simulation_row.addWidget(prev_btn)
        simulation_row.addWidget(next_btn)
        simulation_row.addWidget(self.step_label)

        save_btn = QPushButton("Save Network")
        save_btn.clicked.connect(self.save_network)
        load_btn = QPushButton("Load Network")
        load_btn.clicked.connect(self.load_network)

        control_panel.addWidget(run_btn)
        control_panel.addLayout(simulation_row)
        control_panel.addWidget(add_node_btn)
        control_panel.addWidget(save_btn)
        control_panel.addWidget(load_btn)

        legend_label = QLabel(
            "<b>Legend</b><br>"
            "<span style='color:#00838F'>■</span> Default &nbsp;"
            "<span style='color:#8B4513'>■</span> Dam &nbsp;"
            "<span style='color:#1565C0'>■</span> Flooded &nbsp;"
            "<span style='color:#2E7D32'>■</span> Meadow"
        )
        legend_label.setTextFormat(Qt.TextFormat.RichText)
        control_panel.addWidget(legend_label)
        control_panel.addStretch()

        # RIGHT: scene
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setSceneRect(0, 0, 1000, 800)

        main_layout.addLayout(control_panel, 1)
        main_layout.addWidget(self.view, 3)

        self._update_edge_hint(self.gen_topology.currentText())

    # Network generation

    def _update_edge_hint(self, topology: str):
        n = self.gen_node_count.value()
        if topology == "Linear":
            self.edge_hint.setText(f"Linear uses exactly {n - 1} edges")
        elif topology == "Branching":
            self.edge_hint.setText(f"Branching uses exactly {n - 1} edges")
        else:
            self.edge_hint.setText(f"Random uses the edge count you set")

    def _clear_scene(self):
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

        cx, cy = 500, 400   # scene centre
        radius = min(300, 60 * n)

        if topology == "Linear":
            self._generate_linear(n, cx, cy)
        elif topology == "Branching":
            self._generate_branching(n, cx, cy, radius)
        else:
            e = self.gen_edge_count.value()
            self._generate_random(n, e, cx, cy, radius)

    def _generate_linear(self, n: int, cx: float, cy: float):
        """Nodes spaced evenly across the scene width, connected in a chain."""
        spacing = 800 / (n + 1)
        nodes = []
        for i in range(n):
            x = spacing * (i + 1)
            y = cy + (20 if i % 2 else -20)   # slight zigzag
            nodes.append(self._add_node_at(x, y))

        for i in range(len(nodes) - 1):
            self._add_edge_between(nodes[i], nodes[i + 1])

    def _generate_branching(self, n: int, cx: float, cy: float, radius: float):
        """
        Tree layout: root at top-centre, children spread below.
        Mimics a river branching upstream.
        """
        nodes = [self._add_node_at(cx, 80)]   # root = downstream outlet

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
        """
        Nodes placed on a circle, edges added randomly.
        Guarantees connectivity via a spanning chain first,
        then adds extra edges up to the requested count.
        """
        rng = random.Random(self.seed.value())
        nodes = []

        for i in range(n):
            angle = 2 * math.pi * i / n
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            nodes.append(self._add_node_at(x, y))

        # Guarantee connectivity: random spanning chain
        order = list(range(n))
        rng.shuffle(order)
        existing = set()
        for i in range(len(order) - 1):
            a, b = order[i], order[i + 1]
            key = (min(a, b), max(a, b))
            if key not in existing:
                self._add_edge_between(nodes[a], nodes[b])
                existing.add(key)

        # Add extra random edges up to requested count
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

    # Connect nodes by clicking

    def node_clicked(self, node):
        if self.selected_node is None:
            self.selected_node = node
            node.setBrush(QBrush(Qt.GlobalColor.green))
            return

        if self.selected_node == node:
            node.setBrush(QBrush(Qt.GlobalColor.darkCyan))
            self.selected_node = None
            return

        edge = EdgeItem(self.selected_node, node)
        self.scene.addItem(edge)
        self.edges.append(edge)
        self.selected_node.edges.append(edge)
        node.edges.append(edge)
        self.selected_node.setBrush(QBrush(Qt.GlobalColor.darkCyan))
        self.selected_node = None

    # Simulation

    def run_simulation(self):
        if len(self.nodes) < 2:
            QMessageBox.warning(self, "Error", "Need at least 2 nodes")
            return

        edges = [
            (e.start_node.node_id, e.end_node.node_id)
            for e in self.edges
        ]

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
            river = self.service.create_river(len(self.nodes), edges)
            self.simulation_history = self.service.run_simulation(params, river)
            self.current_step = 0
            self.display_step()

            QMessageBox.information(
                self,
                "Simulation Complete",
                f"Simulation finished!\nSteps: {len(self.simulation_history)}"
            )

        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))

    def _edge_dominant_state(self, sim_edge) -> str:
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

        flooded_count = sum(
            1
            for e in river.edges
            for c in e.cells.values()
            if c.flooded_step is not None
        )

        self.step_label.setText(
            f"Step: {step.step} | Flooded Cells: {flooded_count}"
        )

        for edge_item in self.edges:
            edge_item.set_state("default")

        for sim_edge in river.edges:
            for edge_item in self.edges:
                a = edge_item.start_node.node_id
                b = edge_item.end_node.node_id
                if (a, b) == (sim_edge.down_stream_node, sim_edge.up_stream_node) or \
                   (b, a) == (sim_edge.down_stream_node, sim_edge.up_stream_node):
                    edge_item.set_state(self._edge_dominant_state(sim_edge))
                    break

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
    w.show()
    sys.exit(app.exec())