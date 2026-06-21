"""Graphical River Network Editor (PySide6) - Step 3: Node dragging"""

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
)
from PySide6.QtCore import Qt, QLineF
from PySide6.QtGui import QPen, QBrush
from PySide6.QtWidgets import QGraphicsItem
import sys
import json

from beaver_dam_sim.service import SimulationService


# Draggable Node Item
class NodeItem(QGraphicsEllipseItem):
    def __init__(self, node_id: int, x: float, y: float, radius: float = 20):
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

        self.setPos(x, y)

    def itemChange(self, change, value):

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            for edge in self.edges:
                edge.update_position()

        return super().itemChange(change, value)

    def mousePressEvent(self, event):

        editor = self.scene().views()[0].window()

        editor.node_clicked(self)

        super().mousePressEvent(event)

# Main Editor Window
class EdgeItem(QGraphicsLineItem):
    def __init__(self, start_node, end_node):
        super().__init__()

        self.start_node = start_node
        self.end_node = end_node

        self.setPen(QPen(Qt.black, 2))
        self.update_position()

    def update_position(self):
        self.setLine(
            QLineF(
                self.start_node.scenePos(),
                self.end_node.scenePos()
            )
        )
class NetworkEditor(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Beaver Dam Network Editor - Drag Nodes")
        self.setMinimumSize(800, 600)

        self.service = SimulationService()

        self.node_counter = 0
        self.nodes = {}
        self.edges = []
        self.selected_node = None
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout()
        central.setLayout(layout)

        # Buttons
        button_row = QHBoxLayout()

        add_node_btn = QPushButton("Add Node")
        add_node_btn.clicked.connect(self.add_node)

        save_btn = QPushButton("Save Network")
        save_btn.clicked.connect(self.save_network)

        button_row.addWidget(save_btn)

        build_btn = QPushButton("Build Network (Test)")
        build_btn.clicked.connect(self.build_network)

        button_row.addWidget(add_node_btn)
        button_row.addWidget(build_btn)

        layout.addLayout(button_row)

        # Graphics Scene
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)

        self.view.setRenderHint(self.view.renderHints())
        self.view.setSceneRect(0, 0, 1000, 800)

        layout.addWidget(self.view)

    # Node creation
    def add_node(self):
        """Create a draggable node on canvas"""

        self.node_counter += 1
        node_id = self.node_counter

        x = 100 + (node_id * 30)
        y = 100 + (node_id * 20)

        node = NodeItem(node_id, x, y)
        self.scene.addItem(node)

        self.nodes[node_id] = node

    # Convert UI to backend graph
    def node_clicked(self, node):
        """
        Click first node -> select it
        Click second node -> create edge
        """

        if self.selected_node is None:
            self.selected_node = node
            node.setBrush(QBrush(Qt.green))
            return

        if self.selected_node == node:
            node.setBrush(QBrush(Qt.darkCyan))
            self.selected_node = None
            return

        edge = EdgeItem(self.selected_node, node)

        self.scene.addItem(edge)

        self.edges.append(edge)

        self.selected_node.edges.append(edge)
        node.edges.append(edge)

        self.selected_node.setBrush(QBrush(Qt.darkCyan))
        self.selected_node = None

    def build_network(self):
        """
        Temporary bridge:
        builds a simple chain based on node order.
        (Next step will add real edge drawing)
        """

        if len(self.nodes) < 2:
            QMessageBox.warning(self, "Error", "Need at least 2 nodes.")
            return

        edges = []

        for edge in self.edges:
            edges.append(
                (
                    edge.start_node.node_id,
                    edge.end_node.node_id
                )
            )

        try:
            river = self.service.create_river(
                len(self.nodes),
                edges
            )

            QMessageBox.information(
                self,
                "Success",
                f"Network built!\nNodes: {len(river.nodes)}\nEdges: {len(river.edges)}",
            )

        except ValueError as e:
            QMessageBox.critical(self, "Error", str(e))

    def save_network(self):
        """
        Export network to JSON file.
        """

        edges = []

        for edge in self.edges:
            edges.append(
                [
                    edge.start_node.node_id,
                    edge.end_node.node_id
                ]
            )

        data = {
            "node_count": len(self.nodes),
            "edges": edges
        }

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Network",
            "",
            "JSON Files (*.json)"
        )

        if not filename:
            return

        with open(filename, "w") as f:
            json.dump(data, f, indent=4)

        QMessageBox.information(
            self,
            "Saved",
            f"Network saved to:\n{filename}"
        )


# Run standalone
if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = NetworkEditor()
    window.show()

    sys.exit(app.exec())