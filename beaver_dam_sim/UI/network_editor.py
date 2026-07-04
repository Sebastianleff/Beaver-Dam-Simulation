"""
Graphical River Network Editor (PySide6) - Step 18

This build turns the editor into a dedicated GRAPH EDITOR only.
All simulation execution / playback controls have been removed
(see NETWORK_EDITOR.md, "Scope change in Step 18" for the full
rationale) -- a future main application will own running the
simulation and viewing results, and will "summon" this editor to
build/edit the river network.

New in this step:
  * Tree-topology enforcement. The simulation engine
    (beaver_dam_sim.simulation.RiverNetwork, built via
    RiverNetworkBuilder.create_network) models a river as edges of
    the form add_edge(downstream, upstream): many upstream nodes
    (tributaries) can feed into one downstream node, but a node can
    only flow to ONE downstream node. The editor now enforces this
    directly: a node can be the "upstream" end of at most one edge,
    and cycles are rejected outright.
  * Editable per-edge "length" (number of cells), with a default
    used by the generator and an override in the Edge Properties
    panel.
  * Cells are drawn as small dots along each edge so the underlying
    engine structure (a chain of cells per edge, where dams/floods/
    meadows occur) is visible directly in the editor.
  * Node/edge deletion.
"""

import sys
import json
import random
from collections import defaultdict, deque
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
)
from PySide6.QtGui import (
    QPen,
    QBrush,
    QColor,
    QPainterPath,
    QPainterPathStroker,
    QPolygonF,
    QKeySequence,
    QShortcut,
)
from PySide6.QtCore import Qt, QLineF, QPointF
import math


# Node

class NodeItem(QGraphicsEllipseItem):
    """A river-network node (junction, source, or outlet).

    Nodes do not know anything about simulation state any more --
    that concept doesn't exist in a pure graph editor. The only
    "state" a node can visually have here is whether it is currently
    the outlet/root of its tree (no downstream edge), or whether it
    is the first node picked while creating an edge.
    """

    RADIUS = 20

    COLOR_DEFAULT = QColor("#00838F")
    COLOR_ROOT = QColor("#00838F")
    COLOR_PENDING = QColor("#43A047")

    BORDER_DEFAULT = QColor("#000000")
    BORDER_ROOT = QColor("#FFB300")

    def __init__(self, node_id: int, x: float, y: float):
        r = self.RADIUS
        super().__init__(-r, -r, r * 2, r * 2)

        self.node_id = node_id
        self.edges: list["EdgeItem"] = []

        self.setBrush(QBrush(self.COLOR_DEFAULT))
        self.setPen(QPen(self.BORDER_DEFAULT, 2))
        self.setZValue(10)

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
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

    def set_highlight(self, mode: str):
        """mode: 'default', 'pending', or 'root'."""
        if mode == "pending":
            self.setBrush(QBrush(self.COLOR_PENDING))
            self.setPen(QPen(self.BORDER_DEFAULT, 2))
        elif mode == "root":
            self.setBrush(QBrush(self.COLOR_ROOT))
            self.setPen(QPen(self.BORDER_ROOT, 3))
        else:
            self.setBrush(QBrush(self.COLOR_DEFAULT))
            self.setPen(QPen(self.BORDER_DEFAULT, 2))


# Edge

class EdgeItem(QGraphicsLineItem):
    """A directed river-network edge: water flows from upstream_node
    into downstream_node. Internally the engine represents this edge
    as a chain of `length` cells; we draw that chain as evenly spaced
    dots so the structure is visible while editing.
    """

    CELL_RADIUS = 4
    MIN_LENGTH = 1
    MAX_LENGTH = 50
    DEFAULT_LENGTH = 5

    COLOR_DEFAULT = QColor("#555555")
    COLOR_SELECTED = QColor("#2E7D32")
    COLOR_CELL_FILL = QColor("#D7CCC8")
    COLOR_CELL_BORDER = QColor("#6D4C41")

    def __init__(self, upstream_node: NodeItem, downstream_node: NodeItem, length: int = DEFAULT_LENGTH):
        super().__init__()

        self.upstream_node = upstream_node
        self.downstream_node = downstream_node
        self.length = max(self.MIN_LENGTH, min(self.MAX_LENGTH, length))

        self.setZValue(-5)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.update_position()

    def update_position(self):
        self.prepareGeometryChange()
        self.setLine(QLineF(self.upstream_node.scenePos(), self.downstream_node.scenePos()))

    def set_length(self, length: int):
        self.length = max(self.MIN_LENGTH, min(self.MAX_LENGTH, length))
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self):
        rect = super().boundingRect()
        pad = self.CELL_RADIUS + 6
        return rect.adjusted(-pad, -pad, pad, pad)

    def shape(self) -> QPainterPath:
        # Fatten the clickable area around the thin line so edges are
        # easy to select with the mouse.
        path = QPainterPath()
        path.moveTo(self.line().p1())
        path.lineTo(self.line().p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(14)
        return stroker.createStroke(path)

    def paint(self, painter, option, widget=None):
        line = self.line()
        selected = self.isSelected()

        pen = QPen(self.COLOR_SELECTED if selected else self.COLOR_DEFAULT, 3 if selected else 2)
        painter.setPen(pen)
        painter.drawLine(line)

        self._paint_arrowhead(painter, line)
        self._paint_cells(painter, line)

    def _paint_arrowhead(self, painter, line: QLineF):
        """Small triangle at the midpoint pointing upstream -> downstream."""
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
        arrow_color = self.COLOR_SELECTED if self.isSelected() else self.COLOR_DEFAULT
        painter.setBrush(QBrush(arrow_color))
        painter.setPen(QPen(arrow_color, 1))
        painter.drawPolygon(QPolygonF([mid, p1, p2]))

    def _paint_cells(self, painter, line: QLineF):
        painter.setPen(QPen(self.COLOR_CELL_BORDER, 1))
        painter.setBrush(QBrush(self.COLOR_CELL_FILL))
        n = self.length
        for i in range(n):
            t = (i + 1) / (n + 1)
            pt = line.pointAt(t)
            painter.drawEllipse(pt, self.CELL_RADIUS, self.CELL_RADIUS)


# Main Editor

class NetworkEditor(QMainWindow):
    """A dedicated graph-editing tool for building river networks.

    Responsibilities: create/delete nodes, create/delete edges (with
    tree-topology enforcement matching the simulation engine), set
    per-edge length, auto-layout, and save/load. Running a simulation
    against the resulting network is explicitly out of scope here --
    see NETWORK_EDITOR.md.
    """

    SAVE_FORMAT_VERSION = 2

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Beaver Dam Network Editor - Step 18")
        self.setMinimumSize(1000, 650)

        self.node_counter = 0
        self.nodes: dict[int, NodeItem] = {}
        self.edges: list[EdgeItem] = []
        self.selected_node: NodeItem | None = None
        self._add_edge_mode = False
        self._editing_edge: EdgeItem | None = None

        self.resize(1200, 700)
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
        control_panel.setAlignment(Qt.AlignmentFlag.AlignTop)

        def _spin(widget, width=72):
            widget.setMinimumWidth(width)
            return widget

        # Generate Network
        gen_group = QGroupBox("Generate Network")
        gen_form = QFormLayout()
        gen_form.setVerticalSpacing(3)
        gen_form.setHorizontalSpacing(6)
        gen_form.setContentsMargins(6, 6, 6, 6)

        self.gen_node_count = _spin(QSpinBox())
        self.gen_node_count.setRange(1, 200)
        self.gen_node_count.setValue(6)

        self.gen_topology = QComboBox()
        self.gen_topology.addItems(["Linear", "Branching", "Random"])

        self.default_edge_length = _spin(QSpinBox())
        self.default_edge_length.setRange(EdgeItem.MIN_LENGTH, EdgeItem.MAX_LENGTH)
        self.default_edge_length.setValue(EdgeItem.DEFAULT_LENGTH)

        self.seed = _spin(QSpinBox())
        self.seed.setRange(0, 999999)
        self.seed.setValue(1)

        gen_form.addRow("Node Count", self.gen_node_count)
        gen_form.addRow("Topology", self.gen_topology)
        gen_form.addRow("Default Edge Length", self.default_edge_length)
        gen_form.addRow("Random Seed", self.seed)

        gen_hint = QLabel(
            "A generated network is always a single valid tree: "
            "N nodes → N−1 edges, one outlet."
        )
        gen_hint.setStyleSheet("color: gray; font-size: 9px;")
        gen_hint.setWordWrap(True)
        gen_form.addRow("", gen_hint)

        gen_group.setLayout(gen_form)
        control_panel.addWidget(gen_group)

        # Actions
        gen_btn = QPushButton("Generate")
        gen_btn.clicked.connect(self.generate_network)

        add_node_btn = QPushButton("Add Node")
        add_node_btn.clicked.connect(self.add_node)

        self.add_edge_btn = QPushButton("Add Edge")
        self.add_edge_btn.setCheckable(True)
        self.add_edge_btn.clicked.connect(self._toggle_add_edge_mode)

        delete_btn = QPushButton("Delete Selected")
        delete_btn.clicked.connect(self.delete_selected)

        layout_btn = QPushButton("Auto-Layout")
        layout_btn.clicked.connect(self.auto_layout)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_network)

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self.load_network)

        action_grid = QGridLayout()
        action_grid.setSpacing(4)
        action_buttons = [gen_btn, add_node_btn, self.add_edge_btn, delete_btn, layout_btn, save_btn, load_btn]
        cols = 2
        for i, btn in enumerate(action_buttons):
            action_grid.addWidget(btn, i // cols, i % cols)
        control_panel.addLayout(action_grid)

        # Edge Properties
        edge_group = QGroupBox("Edge Properties")
        edge_layout = QVBoxLayout()
        edge_layout.setSpacing(3)

        self.edge_props_label = QLabel("No edge selected")
        self.edge_props_label.setWordWrap(True)

        length_row = QFormLayout()
        self.edge_length_spin = QSpinBox()
        self.edge_length_spin.setRange(EdgeItem.MIN_LENGTH, EdgeItem.MAX_LENGTH)
        self.edge_length_spin.setEnabled(False)
        self.edge_length_spin.valueChanged.connect(self._on_edge_length_changed)
        length_row.addRow("Length (cells)", self.edge_length_spin)

        edge_layout.addWidget(self.edge_props_label)
        edge_layout.addLayout(length_row)
        edge_group.setLayout(edge_layout)
        control_panel.addWidget(edge_group)

        # Status
        self.status_label = QLabel("Empty network")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 10px;")
        control_panel.addWidget(self.status_label)

        # Legend
        legend_group = QGroupBox("Legend")
        legend_layout = QVBoxLayout()
        legend_layout.setSpacing(2)
        legend_label = QLabel(
            "<span style='color:#00838F'>●</span> Node<br>"
            "<span style='color:#FFB300'>◎</span> Outlet (no downstream edge)<br>"
            "<span style='color:#43A047'>●</span> Pending (creating edge)<br>"
            "<span style='color:#555555'>―▶</span> Edge (flow direction)<br>"
            "<span style='color:#6D4C41'>○</span> Cell along edge"
        )
        legend_label.setTextFormat(Qt.TextFormat.RichText)
        legend_label.setWordWrap(True)
        legend_layout.addWidget(legend_label)
        legend_group.setLayout(legend_layout)
        control_panel.addWidget(legend_group)

        # Scene / View
        self.scene = QGraphicsScene()
        self.scene.selectionChanged.connect(self._on_selection_changed)
        self.view = QGraphicsView(self.scene)
        self.view.setSceneRect(0, 0, 1000, 800)

        main_layout.addLayout(control_panel)
        main_layout.addWidget(self.view, 1)

        # Delete key shortcut
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self.delete_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self, activated=self.delete_selected)


    # Tree-topology validation

    def _downstream_edge_of(self, node_id: int) -> EdgeItem | None:
        """The single edge (if any) for which node_id is the upstream end."""
        for e in self.edges:
            if e.upstream_node.node_id == node_id:
                return e
        return None

    def _would_create_cycle(self, upstream_id: int, downstream_id: int) -> bool:
        """True if following downstream_id's chain of downstream edges
        eventually reaches upstream_id (which would close a loop once
        upstream_id -> downstream_id is added)."""
        current = downstream_id
        visited = set()
        while current is not None:
            if current == upstream_id:
                return True
            if current in visited:
                break
            visited.add(current)
            e = self._downstream_edge_of(current)
            current = e.downstream_node.node_id if e else None
        return False

    def can_add_edge(self, upstream: NodeItem, downstream: NodeItem) -> tuple[bool, str]:
        if upstream.node_id == downstream.node_id:
            return False, "A node cannot connect to itself."

        if self._downstream_edge_of(upstream.node_id) is not None:
            return False, (
                f"Node {upstream.node_id} already flows into another node.\n"
                "Each node can only have one downstream connection "
                "(matching the simulation engine's tree structure)."
            )

        for e in self.edges:
            if {e.upstream_node.node_id, e.downstream_node.node_id} == {upstream.node_id, downstream.node_id}:
                return False, "That connection already exists."

        if self._would_create_cycle(upstream.node_id, downstream.node_id):
            return False, (
                "That connection would create a cycle. Rivers must flow "
                "to a single outlet without looping back."
            )

        return True, ""

    def _is_connected(self) -> bool:
        if not self.nodes:
            return True
        adjacency: dict[int, list[int]] = defaultdict(list)
        for e in self.edges:
            a, b = e.upstream_node.node_id, e.downstream_node.node_id
            adjacency[a].append(b)
            adjacency[b].append(a)
        start = next(iter(self.nodes))
        visited = {start}
        queue = deque([start])
        while queue:
            nid = queue.popleft()
            for neighbor in adjacency[nid]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return len(visited) == len(self.nodes)

    def _roots(self) -> list[NodeItem]:
        return [n for n in self.nodes.values() if self._downstream_edge_of(n.node_id) is None]

    def _update_tree_status(self):
        if not self.nodes:
            self.status_label.setText("Empty network")
            return

        roots = self._roots()
        if len(self.edges) != len(self.nodes) - 1:
            self.status_label.setText(
                f"⚠ {len(self.nodes)} nodes, {len(self.edges)} edges — "
                "not yet a single connected tree."
            )
        elif len(roots) == 1 and self._is_connected():
            self.status_label.setText(f"✓ Valid tree — outlet at Node {roots[0].node_id}")
        else:
            self.status_label.setText(
                f"⚠ {len(roots)} separate outlet(s)/components — "
                "connect them into a single tree."
            )

    def _refresh_node_highlights(self):
        root_ids = {n.node_id for n in self._roots()}
        for node in self.nodes.values():
            node.set_highlight("root" if node.node_id in root_ids else "default")


    # Node / edge creation & deletion

    def _add_node_at(self, x: float, y: float) -> NodeItem:
        self.node_counter += 1
        node = NodeItem(self.node_counter, x, y)
        self.scene.addItem(node)
        self.nodes[self.node_counter] = node
        return node

    def add_node(self):
        x = 100 + (self.node_counter * 37) % 800
        y = 100 + (self.node_counter * 53) % 600
        self._add_node_at(x, y)
        self._refresh_node_highlights()
        self._update_tree_status()

    def _add_edge_between(self, upstream: NodeItem, downstream: NodeItem, length: int | None = None) -> EdgeItem:
        if length is None:
            length = self.default_edge_length.value()
        edge = EdgeItem(upstream, downstream, length)
        self.scene.addItem(edge)
        self.edges.append(edge)
        upstream.edges.append(edge)
        downstream.edges.append(edge)
        return edge

    def _toggle_add_edge_mode(self, checked: bool):
        self._add_edge_mode = checked
        if not checked and self.selected_node:
            self.selected_node.set_highlight("default")
            self.selected_node = None
        self._refresh_node_highlights()

    def node_clicked(self, node: NodeItem):
        if not self._add_edge_mode:
            return

        if self.selected_node is None:
            self.selected_node = node
            node.set_highlight("pending")
            return

        if self.selected_node is node:
            self.selected_node.set_highlight("default")
            self.selected_node = None
            self._refresh_node_highlights()
            return

        ok, reason = self.can_add_edge(self.selected_node, node)
        if not ok:
            QMessageBox.warning(self, "Invalid Connection", reason)
        else:
            self._add_edge_between(self.selected_node, node)

        self.selected_node.set_highlight("default")
        self.selected_node = None
        self._refresh_node_highlights()
        self._update_tree_status()

    def _delete_edge(self, edge: EdgeItem):
        if edge not in self.edges:
            return
        self.edges.remove(edge)
        for n in (edge.upstream_node, edge.downstream_node):
            if edge in n.edges:
                n.edges.remove(edge)
        self.scene.removeItem(edge)

    def _delete_node(self, node: NodeItem):
        for e in list(node.edges):
            self._delete_edge(e)
        self.nodes.pop(node.node_id, None)
        self.scene.removeItem(node)
        if self.selected_node is node:
            self.selected_node = None

    def delete_selected(self):
        items = self.scene.selectedItems()
        if not items:
            return
        for item in items:
            if isinstance(item, NodeItem):
                self._delete_node(item)
            elif isinstance(item, EdgeItem):
                self._delete_edge(item)
        self._refresh_node_highlights()
        self._update_tree_status()

    def _clear_scene(self):
        self.scene.clear()
        self.nodes.clear()
        self.edges.clear()
        self.selected_node = None
        self.node_counter = 0
        self.status_label.setText("Empty network")

    # Edge properties panel

    def _on_selection_changed(self):
        edges_selected = [i for i in self.scene.selectedItems() if isinstance(i, EdgeItem)]
        if len(edges_selected) == 1:
            edge = edges_selected[0]
            self._editing_edge = edge
            self.edge_props_label.setText(
                f"Edge: Node {edge.upstream_node.node_id} → Node {edge.downstream_node.node_id}"
            )
            self.edge_length_spin.blockSignals(True)
            self.edge_length_spin.setValue(edge.length)
            self.edge_length_spin.blockSignals(False)
            self.edge_length_spin.setEnabled(True)
        else:
            self._editing_edge = None
            self.edge_props_label.setText("No edge selected")
            self.edge_length_spin.setEnabled(False)

    def _on_edge_length_changed(self, value: int):
        if self._editing_edge is not None:
            self._editing_edge.set_length(value)


    # Network generation (always produces a single valid tree)

    def generate_network(self):
        n = self.gen_node_count.value()
        topology = self.gen_topology.currentText()
        length = self.default_edge_length.value()

        self._clear_scene()
        if n <= 0:
            return

        if topology == "Linear":
            self._generate_linear(n, length)
        elif topology == "Branching":
            self._generate_branching(n, length)
        else:
            self._generate_random(n, length)

        self._refresh_node_highlights()
        self._update_tree_status()
        self.auto_layout()

    def _generate_linear(self, n: int, length: int):
        """A single chain: node_n -> node_(n-1) -> ... -> node_1 (outlet)."""
        root = self._add_node_at(0, 0)
        previous = root
        for _ in range(1, n):
            node = self._add_node_at(0, 0)
            self._add_edge_between(node, previous, length)
            previous = node

    def _generate_branching(self, n: int, length: int):
        """Each new node attaches to a random existing node, biased to
        spread out (max children per node) so the tree visibly branches."""
        MAX_CHILDREN = 3
        rng = random.Random(self.seed.value())
        root = self._add_node_at(0, 0)
        children_count = {root.node_id: 0}

        for _ in range(1, n):
            candidates = [nid for nid, c in children_count.items() if c < MAX_CHILDREN]
            target_id = rng.choice(candidates) if candidates else rng.choice(list(children_count.keys()))
            target = self.nodes[target_id]
            node = self._add_node_at(0, 0)
            self._add_edge_between(node, target, length)
            children_count[node.node_id] = 0
            children_count[target_id] += 1

    def _generate_random(self, n: int, length: int):
        """Each new node attaches to a uniformly random existing node."""
        rng = random.Random(self.seed.value())
        root = self._add_node_at(0, 0)
        existing_ids = [root.node_id]

        for _ in range(1, n):
            target_id = rng.choice(existing_ids)
            target = self.nodes[target_id]
            node = self._add_node_at(0, 0)
            self._add_edge_between(node, target, length)
            existing_ids.append(node.node_id)


    # Auto-layout (purely structural -- no simulation needed)

    def _compute_depths(self) -> dict[int, int]:
        """Depth = number of hops to this node's outlet, following its
        chain of downstream edges. Leaves/sources have the largest
        depth; outlets have depth 0."""
        depth: dict[int, int] = {}

        def get_depth(nid: int) -> int:
            if nid in depth:
                return depth[nid]
            e = self._downstream_edge_of(nid)
            if e is None:
                depth[nid] = 0
            else:
                depth[nid] = 1 + get_depth(e.downstream_node.node_id)
            return depth[nid]

        for nid in self.nodes:
            get_depth(nid)
        return depth

    def auto_layout(self):
        """Position nodes so upstream (source) nodes render higher and
        each tree's outlet renders at the bottom, with zigzag/jitter so
        chains don't render as perfectly straight lines."""
        if not self.nodes:
            return

        depths = self._compute_depths()
        max_depth = max(depths.values()) if depths else 0

        levels: dict[int, list[int]] = defaultdict(list)
        for nid, d in depths.items():
            levels[d].append(nid)

        scene_width = self.view.sceneRect().width()
        scene_height = self.view.sceneRect().height()
        y_step = scene_height / (max_depth + 2)

        rng = random.Random(self.seed.value())
        jitter_amplitude = min(80.0, scene_width * 0.12)

        for depth_level, node_ids in levels.items():
            y = y_step * (max_depth - depth_level + 1)
            x_step = scene_width / (len(node_ids) + 1)
            for i, nid in enumerate(sorted(node_ids)):
                base_x = x_step * (i + 1)
                zigzag = jitter_amplitude * (1 if depth_level % 2 == 0 else -1)
                random_offset = rng.uniform(-jitter_amplitude * 0.5, jitter_amplitude * 0.5)
                x = base_x + zigzag * 0.6 + random_offset
                x = max(40.0, min(scene_width - 40.0, x))
                self.nodes[nid].setPos(x, y)

        for edge in self.edges:
            edge.update_position()

    # Save / Load

    def save_network(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save", "", "JSON (*.json)")
        if not path:
            return

        data = {
            "version": self.SAVE_FORMAT_VERSION,
            "nodes": [
                {"id": n.node_id, "x": n.scenePos().x(), "y": n.scenePos().y()}
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "upstream": e.upstream_node.node_id,
                    "downstream": e.downstream_node.node_id,
                    "length": e.length,
                }
                for e in self.edges
            ],
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

        for edge_data in data["edges"]:
            # Support both the current dict format and the legacy
            # Step-17 [a, b] pair format (treated as upstream, downstream
            # with the default cell length).
            if isinstance(edge_data, dict):
                up_id = edge_data["upstream"]
                down_id = edge_data["downstream"]
                length = edge_data.get("length", EdgeItem.DEFAULT_LENGTH)
            else:
                up_id, down_id = edge_data
                length = EdgeItem.DEFAULT_LENGTH

            edge = EdgeItem(self.nodes[up_id], self.nodes[down_id], length)
            self.scene.addItem(edge)
            self.edges.append(edge)
            self.nodes[up_id].edges.append(edge)
            self.nodes[down_id].edges.append(edge)

        self._refresh_node_highlights()
        self._update_tree_status()


# Run

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = NetworkEditor()
    w.showMaximized()
    sys.exit(app.exec())