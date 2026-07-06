"""
Simulation Controls Window - Step 20

This window ONLY handles simulation setup and execution. It does not
edit graphs, draw nodes, or animate results -- see NETWORK_EDITOR.md,
"Step 20 -- Simulation Controls".

It receives the current network as plain data from MainWindow (the
same shape as NetworkEditor.to_dict()), builds a SimParam from the
form fields, builds a RiverNetwork via SimulationService.create_river,
runs SimulationService.run_simulation, and emits the resulting
`history` via the `simulation_complete` signal so MainWindow (and,
later, the Results Viewer) can pick it up.

Works both as a package module (`python -m ui.simulation_controls` from
the project root) and as a loose script run directly from inside the
`ui/` folder (`python simulation_controls.py`) -- see the import
fallback just below.
"""

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
    QDoubleSpinBox,
    QSpinBox,
    QMessageBox,
)
from PySide6.QtCore import Signal

from beaver_dam_sim.service import SimulationService, SimParam

try:
    from .network_editor import is_valid_tree
except ImportError:
    from network_editor import is_valid_tree


# Defaults shared by the initial form values and "Reset Parameters".
DEFAULT_PARAMS = {
    "dam_creation_probability": 0.3,
    "dam_break_probability": 0.3,
    "flood_probability": 0.3,
    "flood_break_probability": 0.3,
    "meadow_probability": 0.3,
    "stabilization_time": 3,
    "random_seed": 1,
    "steps": 50,
}


def build_river(service: SimulationService, network_data: dict):
    """Build a RiverNetwork from editor-shaped network data.

    RiverNetworkBuilder.create_network assumes node ids are a
    contiguous 1..node_count range. NetworkEditor node ids are never
    reused, so after deleting nodes the remaining ids can have gaps
    (e.g. {1, 3, 4}) -- calling create_river directly with those ids
    would either misassign nodes or raise a "not in range" ValueError.
    We remap ids to a contiguous 1..N range (preserving the tree
    structure) before calling create_river.
    """
    node_ids = sorted(n["id"] for n in network_data.get("nodes", []))
    remap = {old_id: new_id for new_id, old_id in enumerate(node_ids, start=1)}

    edges = []
    for e in network_data.get("edges", []):
        if isinstance(e, dict):
            up_id, down_id = e["upstream"], e["downstream"]
        else:
            up_id, down_id = e[0], e[1]
        # service edges are (downstream, upstream) pairs.
        edges.append((remap[down_id], remap[up_id]))

    return service.create_river(len(node_ids), edges)


class SimulationControls(QMainWindow):
    """Set SimParam values and run a simulation against a network
    handed to it by MainWindow. Does not touch graph editing at all."""

    # Emitted with the resulting list[SimulationStep] once a run (or
    # each batch run) finishes, so a host window / future Results
    # Viewer can pick it up.
    simulation_complete = Signal(list)

    def __init__(self, network_data: dict | None = None):
        super().__init__()

        self.setWindowTitle("Simulation Controls")
        self.setMinimumSize(420, 480)

        self.service = SimulationService()
        self.network_data: dict | None = None
        self.simulation_history: list | None = None

        self._build_ui()
        self.set_network_data(network_data)


    # UI

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)

        # Network status (read-only; this window never edits the graph)
        network_group = QGroupBox("Network")
        network_layout = QVBoxLayout()
        self.network_label = QLabel()
        self.network_label.setWordWrap(True)
        network_layout.addWidget(self.network_label)
        network_group.setLayout(network_layout)
        layout.addWidget(network_group)

        # Simulation parameters
        params_group = QGroupBox("Simulation Parameters")
        form = QFormLayout()
        form.setVerticalSpacing(4)

        def _prob_spin():
            box = QDoubleSpinBox()
            box.setRange(0.0, 1.0)
            box.setSingleStep(0.05)
            box.setDecimals(2)
            return box

        self.dam_creation = _prob_spin()
        self.dam_break = _prob_spin()
        self.flood_prob = _prob_spin()
        self.flood_break = _prob_spin()
        self.meadow = _prob_spin()

        self.stabilization = QSpinBox()
        self.stabilization.setRange(1, 1000)

        self.seed = QSpinBox()
        self.seed.setRange(0, 999999)

        self.steps = QSpinBox()
        self.steps.setRange(1, 100000)

        form.addRow("Dam Creation Probability", self.dam_creation)
        form.addRow("Dam Break Probability", self.dam_break)
        form.addRow("Flood Probability", self.flood_prob)
        form.addRow("Flood Break Probability", self.flood_break)
        form.addRow("Meadow Probability", self.meadow)
        form.addRow("Stabilization Time", self.stabilization)
        form.addRow("Random Seed", self.seed)
        form.addRow("Steps", self.steps)

        params_group.setLayout(form)
        layout.addWidget(params_group)

        self._reset_params()

        # Buttons
        button_row = QHBoxLayout()

        self.run_btn = QPushButton("Run Simulation")
        self.run_btn.clicked.connect(self.run_simulation)

        self.batch_btn = QPushButton("Batch Simulation")
        self.batch_btn.clicked.connect(self.open_batch_dialog)

        reset_btn = QPushButton("Reset Parameters")
        reset_btn.clicked.connect(self._reset_params)

        for btn in (self.run_btn, self.batch_btn, reset_btn):
            button_row.addWidget(btn)
        layout.addLayout(button_row)

        # Result summary
        result_group = QGroupBox("Last Result")
        result_layout = QVBoxLayout()
        self.result_label = QLabel("No simulation run yet.")
        self.result_label.setWordWrap(True)
        result_layout.addWidget(self.result_label)
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)

        layout.addStretch(1)

    def _reset_params(self):
        self.dam_creation.setValue(DEFAULT_PARAMS["dam_creation_probability"])
        self.dam_break.setValue(DEFAULT_PARAMS["dam_break_probability"])
        self.flood_prob.setValue(DEFAULT_PARAMS["flood_probability"])
        self.flood_break.setValue(DEFAULT_PARAMS["flood_break_probability"])
        self.meadow.setValue(DEFAULT_PARAMS["meadow_probability"])
        self.stabilization.setValue(DEFAULT_PARAMS["stabilization_time"])
        self.seed.setValue(DEFAULT_PARAMS["random_seed"])
        self.steps.setValue(DEFAULT_PARAMS["steps"])


    # Network data (received from MainWindow; never edited here)

    def set_network_data(self, network_data: dict | None):
        self.network_data = network_data
        self._refresh_network_label()

    def _network_is_valid(self) -> tuple[bool, str]:
        if not self.network_data or not self.network_data.get("nodes"):
            return False, "No network loaded."
        return is_valid_tree(self.network_data)

    def _refresh_network_label(self):
        if not self.network_data or not self.network_data.get("nodes"):
            self.network_label.setText("No network loaded. Build one in the Network Editor first.")
            self.run_btn.setEnabled(False)
            self.batch_btn.setEnabled(False)
            return

        n_nodes = len(self.network_data.get("nodes", []))
        n_edges = len(self.network_data.get("edges", []))
        valid, reason = self._network_is_valid()
        self.network_label.setText(f"{n_nodes} node(s), {n_edges} edge(s) \u2014 {reason}")
        self.run_btn.setEnabled(valid)
        self.batch_btn.setEnabled(valid)


    # SimParam

    def build_params(self) -> SimParam:
        return SimParam(
            dam_creation_probability=self.dam_creation.value(),
            dam_break_probability=self.dam_break.value(),
            flood_probability=self.flood_prob.value(),
            flood_break_probability=self.flood_break.value(),
            stabilization_time=self.stabilization.value(),
            steps=self.steps.value(),
            random_seed=self.seed.value(),
            meadow_probability=self.meadow.value(),
        )


    # Run

    def run_simulation(self):
        valid, reason = self._network_is_valid()
        if not valid:
            QMessageBox.warning(self, "Invalid Network", f"Cannot run simulation:\n{reason}")
            return

        params = self.build_params()

        try:
            river = build_river(self.service, self.network_data)
            history = self.service.run_simulation(params, river)
        except Exception as ex:
            QMessageBox.critical(self, "Simulation Error", str(ex))
            return

        self.simulation_history = history
        self._show_summary(history)
        self.simulation_complete.emit(history)

    def _show_summary(self, history: list):
        total_flooded = sum(len(s.cells_flooded) for s in history)
        total_dams_created = sum(len(s.dams_created) for s in history)
        total_dams_broken = sum(len(s.dams_broken) for s in history)

        summary = (
            f"Steps: {len(history)}\n"
            f"Flooded cell-events: {total_flooded}\n"
            f"Dams created: {total_dams_created}\n"
            f"Dams broken: {total_dams_broken}"
        )
        self.result_label.setText(summary)
        QMessageBox.information(self, "Simulation Complete", summary)


    # Batch

    def open_batch_dialog(self):
        # Imported lazily to avoid a hard dependency at module import
        # time for callers that only need single-run simulation.
        try:
            from .batch_ui import BatchSimulationDialog
        except ImportError:
            from batch_ui import BatchSimulationDialog

        valid, reason = self._network_is_valid()
        if not valid:
            QMessageBox.warning(self, "Invalid Network", f"Cannot run a batch:\n{reason}")
            return

        dialog = BatchSimulationDialog(self.service, self.network_data, self)
        dialog.exec()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SimulationControls()
    window.show()
    sys.exit(app.exec())