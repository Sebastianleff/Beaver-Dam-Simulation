"""
Batch Simulation Dialog - Step 20

Handles running SimulationService.run_simulation_batch: a CSV of
SimParam rows (see CSVService.load_sim_params for the expected
columns: dam_creation_probability, dam_break_probability,
flood_probability, flood_break_probability, stabilization_time,
years, random_seed, meadow_probability) run against a single network,
with results written to an output CSV
(CSVService.save_sim_results).

This is intentionally a separate file from simulation_controls.py:
Simulation Controls owns single-run SimParam entry and execution,
while this dialog owns the CSV-driven batch workflow. It is opened
from SimulationControls' "Batch Simulation" button and receives the
already-validated network data from it -- it does not talk to
MainWindow or NetworkEditor directly.

Works both as a package module (`python -m ui.batch_ui` from the
project root) and as a loose script run directly from inside the
`ui/` folder (`python batch_ui.py`) -- it shows the dialog against an
empty network for layout/manual testing either way.
"""

import sys

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QFileDialog,
    QMessageBox,
)

from beaver_dam_sim.service import SimulationService


class BatchSimulationDialog(QDialog):
    """Pick an input SimParam CSV and an output results CSV, then run
    SimulationService.run_simulation_batch against the network handed
    to this dialog by SimulationControls."""

    def __init__(self, service: SimulationService, network_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Simulation")
        self.setMinimumWidth(420)

        self.service = service
        self.network_data = network_data

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            "Runs one simulation per row of the input CSV "
            "(dam_creation_probability, dam_break_probability, "
            "flood_probability, flood_break_probability, "
            "stabilization_time, years, random_seed, "
            "meadow_probability), all against the current network."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()

        self.input_path = QLineEdit()
        input_row = QHBoxLayout()
        input_row.addWidget(self.input_path)
        input_browse = QPushButton("Browse...")
        input_browse.clicked.connect(self._browse_input)
        input_row.addWidget(input_browse)
        form.addRow("Input CSV", input_row)

        self.output_path = QLineEdit()
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_path)
        output_browse = QPushButton("Browse...")
        output_browse.clicked.connect(self._browse_output)
        output_row.addWidget(output_browse)
        form.addRow("Output CSV", output_row)

        layout.addLayout(form)

        button_row = QHBoxLayout()
        run_btn = QPushButton("Run Batch")
        run_btn.clicked.connect(self._run_batch)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(run_btn)
        button_row.addWidget(cancel_btn)
        layout.addLayout(button_row)

    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Input CSV", "", "CSV (*.csv)")
        if path:
            self.input_path.setText(path)

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select Output CSV", "", "CSV (*.csv)")
        if path:
            self.output_path.setText(path)

    def _run_batch(self):
        input_path = self.input_path.text().strip()
        output_path = self.output_path.text().strip()

        if not input_path or not output_path:
            QMessageBox.warning(self, "Missing Path", "Choose both an input and output CSV file.")
            return

        # Imported here (not at module import time) to avoid a circular
        # import with simulation_controls.py, which imports this module
        # lazily too.
        try:
            from .simulation_controls import build_river
        except ImportError:
            from simulation_controls import build_river

        try:
            river = build_river(self.service, self.network_data)
            self.service.run_simulation_batch(input_path, output_path, river)
        except Exception as ex:
            QMessageBox.critical(self, "Batch Simulation Error", str(ex))
            return

        QMessageBox.information(
            self, "Batch Complete", f"Batch simulation finished.\nResults written to:\n{output_path}"
        )
        self.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    empty_network = {"version": 2, "nodes": [], "edges": []}
    dialog = BatchSimulationDialog(SimulationService(), empty_network)
    dialog.show()
    sys.exit(app.exec())