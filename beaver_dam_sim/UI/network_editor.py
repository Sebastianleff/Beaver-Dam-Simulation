"""
Graphical River Network Editor (PySide6) - Step 10
Node dragging + connect + save/load + arrows
"""

import sys
import json
from math import sin, cos, radians

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
    QGraphicsPolygonItem,
)
from PySide6.QtCore import Qt, QLineF, QPointF
from PySide6.QtGui import QPen, QBrush, QPolygonF
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtWidgets import QGraphicsTextItem

from beaver_dam_sim.service import SimulationService


# Node
class NodeItem(QGraphicsEllipseItem):
    def __init__(self, node_id: int, x: float, y: float, radius: int = 20):
        super().__init__(-radius, -radius, radius * 2, radius * 2)

        self.node_id = node_id
        self.edges = []

        self.setBrush(QBrush(Qt.darkCyan))
        self.setPen(QPen(Qt.black, 2))

        self.setFlags(
            QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

        # LABEL
        self.label = QGraphicsTextItem(str(node_id), self)
        self.label.setDefaultTextColor(Qt.white)
        self.label.setPos(-6, -10)

        self.setPos(x, y)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            for e in self.edges:
                e.update_position()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        editor = self.scene().views()[0].window()
        editor.node_clicked(self)
        super().mousePressEvent(event)


# Edge
class EdgeItem(QGraphicsLineItem):
    def __init__(self, start_node, end_node):
        super().__init__()

        self.start_node = start_node
        self.end_node = end_node

        self.setPen(QPen(Qt.black, 2))

        self.arrow_head = QGraphicsPolygonItem(self)
        self.arrow_head.setBrush(QBrush(Qt.black))
        self.arrow_head.setPen(QPen(Qt.black))

        self.setZValue(1)
        self.arrow_head.setZValue(2)

        self.update_position()

    def update_position(self):
        line = QLineF(
            self.start_node.scenePos(),
            self.end_node.scenePos()
        )

        self.setLine(line)

        # Arrow head (fixed & stable)
        angle = radians(-line.angle())
        arrow_size = 10

        p = self.end_node.scenePos()

        p1 = QPointF(
            p.x() + arrow_size * cos(angle),
            p.y() + arrow_size * sin(angle)
        )
        p2 = QPointF(
            p.x() + arrow_size * cos(angle + 2.5),
            p.y() + arrow_size * sin(angle + 2.5)
        )
        p3 = QPointF(
            p.x() + arrow_size * cos(angle - 2.5),
            p.y() + arrow_size * sin(angle - 2.5)
        )

        self.arrow_head.setPolygon(QPolygonF([p1, p2, p3]))


# Editor
class NetworkEditor(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Beaver Dam Network Editor - Step 10")
        self.setMinimumSize(900, 600)

        self.service = SimulationService()

        self.node_counter = 0
        self.nodes = {}
        self.edges = []
        self.selected_node = None

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        row = QHBoxLayout()

        add_btn = QPushButton("Add Node")
        add_btn.clicked.connect(self.add_node)

        del_btn = QPushButton("Delete Selected")
        del_btn.clicked.connect(self.delete_selected)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_network)

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self.load_network)

        build_btn = QPushButton("Build")
        build_btn.clicked.connect(self.build_network)

        row.addWidget(add_btn)
        row.addWidget(del_btn)
        row.addWidget(save_btn)
        row.addWidget(load_btn)
        row.addWidget(build_btn)

        layout.addLayout(row)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setSceneRect(0, 0, 1000, 800)

        layout.addWidget(self.view)

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

    # Connect logic
    def node_clicked(self, node):
        if self.selected_node is None:
            self.selected_node = node
            node.setBrush(QBrush(Qt.green))
            return

        if self.selected_node == node:
            node.setBrush(QBrush(Qt.darkCyan))
            self.selected_node = None
            return

        for e in self.edges:
            if e.start_node == self.selected_node and e.end_node == node:
                QMessageBox.warning(self, "Duplicate", "Edge exists")
                self.selected_node.setBrush(QBrush(Qt.darkCyan))
                self.selected_node = None
                return

        edge = EdgeItem(self.selected_node, node)
        self.scene.addItem(edge)

        self.edges.append(edge)

        self.selected_node.edges.append(edge)
        node.edges.append(edge)

        self.selected_node.setBrush(QBrush(Qt.darkCyan))
        self.selected_node = None

    # Delete
    def delete_selected(self):
        for item in self.scene.selectedItems():

            if isinstance(item, NodeItem):
                for e in item.edges[:]:
                    if e in self.edges:
                        self.edges.remove(e)
                    self.scene.removeItem(e)

                self.scene.removeItem(item)

                if item.node_id in self.nodes:
                    del self.nodes[item.node_id]

            elif isinstance(item, EdgeItem):
                if item in self.edges:
                    self.edges.remove(item)
                self.scene.removeItem(item)

    # Build backend
    def build_network(self):
        edges = [
            (e.start_node.node_id, e.end_node.node_id)
            for e in self.edges
        ]

        try:
            river = self.service.create_river(len(self.nodes), edges)

            QMessageBox.information(
                self,
                "Success",
                f"Nodes: {len(river.nodes)} | Edges: {len(river.edges)}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

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


# Run
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = NetworkEditor()
    w.show()
    sys.exit(app.exec())