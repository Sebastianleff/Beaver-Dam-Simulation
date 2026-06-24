"""
Graphical River Network Editor (PySide6) - Step 12
Adds node state visualization based on simulation step data
"""

import sys
import json
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
    QLabel
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

        # label
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
        """
        Color the node based on its simulation state.
        States: 'default', 'dam', 'flooded', 'meadow'
        """
        colors = {
            "default": Qt.GlobalColor.darkCyan,
            "dam":     QColor("#8B4513"),   # brown
            "flooded": QColor("#1565C0"),   # deep blue
            "meadow":  QColor("#2E7D32"),   # green
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
        self.setLine(
            QLineF(
                self.start_node.scenePos(),
                self.end_node.scenePos()
            )
        )

    def set_state(self, state: str):
        """
        Color the edge based on the dominant cell state along it.
        Priority: flooded > dam > meadow > default
        """
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

        self.setWindowTitle("Beaver Dam Network Editor - Step 12")
        self.setMinimumSize(1000, 700)

        self.service = SimulationService()

        self.node_counter = 0
        self.nodes = {}
        self.edges = []
        self.selected_node = None
        self.simulation_history = []
        self.current_step = 0

        self._build_ui()

    # UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)

        # LEFT: controls
        control_panel = QVBoxLayout()

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

        control_panel.addLayout(form)

        run_btn = QPushButton("Run Simulation")
        run_btn.clicked.connect(self.run_simulation)

        add_node_btn = QPushButton("Add Node")
        add_node_btn.clicked.connect(self.add_node)

        # Step navigation row
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

        # Legend
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

    # Nodes
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

            self.simulation_history = self.service.run_simulation(
                params,
                river
            )

            self.current_step = 0
            self.display_step()

            QMessageBox.information(
                self,
                "Simulation Complete",
                f"Simulation finished!\nSteps: {len(self.simulation_history)}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _edge_dominant_state(self, sim_edge) -> str:
        """
        Determine the dominant visual state for an edge based on its cells.
        Priority: flooded > dam > meadow > default
        """
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
        """
        Display current simulation step and color edges by cell state.
        """
        if not self.simulation_history:
            return

        step = self.simulation_history[self.current_step]
        river = step.river_snapshot

        # Count flooded cells for the label
        flooded_count = sum(
            1
            for e in river.edges
            for c in e.cells.values()
            if c.flooded_step is not None
        )

        self.step_label.setText(
            f"Step: {step.step} | Flooded Cells: {flooded_count}"
        )

        # Reset all edges
        for edge_item in self.edges:
            edge_item.set_state("default")

        # Match each UI EdgeItem to the simulation edge by node IDs
        for sim_edge in river.edges:
            for edge_item in self.edges:
                a = edge_item.start_node.node_id
                b = edge_item.end_node.node_id
                if (a, b) == (sim_edge.down_stream_node, sim_edge.up_stream_node) or                    (b, a) == (sim_edge.down_stream_node, sim_edge.up_stream_node):
                    edge_item.set_state(self._edge_dominant_state(sim_edge))
                    break

    # Save / Load
    def save_network(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save", "", "JSON (*.json)")
        if not path:
            return

        data = {
            "nodes": [
                {
                    "id": n.node_id,
                    "x": n.scenePos().x(),
                    "y": n.scenePos().y()
                }
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

        self.scene.clear()
        self.nodes.clear()
        self.edges.clear()
        self.selected_node = None
        self.node_counter = 0

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