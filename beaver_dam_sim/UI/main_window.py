"""
Beaver Dam Simulator - Main Application Window - Step 21

This is the shell that hosts the whole application:

    Main Window
        |
        +-- Graph Editor        (ui.network_editor.NetworkEditor)
        |
        +-- Simulation Controls (ui.simulation_controls.SimulationControls)
        |
        +-- Results Viewer      (ui.results_viewer.ResultsViewer)

Package layout:

    ui/
    |-- __init__.py
    |-- main_window.py          (this file)
    |-- network_editor.py       (Step 18/19 -- graph editing only)
    |-- simulation_controls.py  (Step 20 -- SimParam + run a single sim)
    |-- batch_ui.py             (Step 20 -- CSV batch runs)
    |-- results_viewer.py       (Step 21 -- step through a run's history)

The Main Window owns the *canonical* current network as plain data
(the same shape as NetworkEditor.to_dict()) rather than owning any
QGraphicsScene itself. It "summons" NetworkEditor when the user wants
to build/edit a network, and it "summons" SimulationControls when the
user wants to run a simulation against that network -- handing it the
current network data and picking up the resulting `history` (together
with the exact network_data that run used) via a signal, the same
pattern used for the editor's `closed` signal. "View Results" then
summons ResultsViewer with that same pair.
"""

import sys
import json

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QGroupBox,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtGui import QAction, QKeySequence

# Relative import when this file is used as part of the `ui` package
# (python -m ui.main_window, or `from ui.main_window import MainWindow`);
# falls back to a flat sibling import when run directly as a loose
# script from inside the ui/ folder (python main_window.py). Both
# branches are ordinary imports, so IDEs can resolve whichever one
# matches how the project is actually opened.
try:
    from .network_editor import NetworkEditor, is_valid_tree
    from .simulation_controls import SimulationControls
    from .results_viewer import ResultsViewer
except ImportError:
    from network_editor import NetworkEditor, is_valid_tree
    from simulation_controls import SimulationControls
    from results_viewer import ResultsViewer

EMPTY_NETWORK: dict = {"version": NetworkEditor.SAVE_FORMAT_VERSION, "nodes": [], "edges": []}


class MainWindow(QMainWindow):
    """Application shell. Holds the current network as data and
    summons NetworkEditor / SimulationControls / ResultsViewer on
    demand."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Beaver Dam Simulator")
        self.resize(720, 420)

        # Canonical current network, independent of whether the editor
        # is currently open. None means "nothing loaded yet" (distinct
        # from an intentionally empty network).
        self.network_data: dict | None = None
        self.network_file_path: str | None = None

        # Kept alive here so it isn't garbage-collected while open, and
        # so re-clicking "Open Network Editor" can just raise it.
        self._editor: NetworkEditor | None = None

        # Same pattern for Simulation Controls.
        self._sim_controls: SimulationControls | None = None
        self.simulation_history: list | None = None
        # The network_data a completed run actually used -- kept
        # separate from self.network_data because the editor may be
        # reopened and changed after a run finishes; ResultsViewer
        # needs the network as it was at run time, not "now".
        self.simulation_network_data: dict | None = None

        # Same pattern for Results Viewer.
        self._results_viewer: ResultsViewer | None = None

        self._build_menus()
        self._build_ui()
        self._refresh_status()


    # UI

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("&File")

        new_action = QAction("&New Network", self)
        new_action.triggered.connect(self.new_network)

        open_action = QAction("&Open Network...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_network_file)

        save_action = QAction("&Save Network", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_network_file)

        save_as_action = QAction("Save Network &As...", self)
        save_as_action.triggered.connect(self.save_network_file_as)

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Beaver Dam River Simulator")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        status_group = QGroupBox("Current Network")
        status_layout = QVBoxLayout()
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        button_row = QHBoxLayout()

        self.open_editor_btn = QPushButton("Open Network Editor")
        self.open_editor_btn.clicked.connect(self.open_network_editor)

        self.run_sim_btn = QPushButton("Run Simulation")
        self.run_sim_btn.clicked.connect(self.open_simulation_controls)

        self.view_results_btn = QPushButton("View Results")
        self.view_results_btn.clicked.connect(self.view_results)

        for btn in (self.open_editor_btn, self.run_sim_btn, self.view_results_btn):
            button_row.addWidget(btn)
        layout.addLayout(button_row)

        layout.addStretch(1)


    # Status

    def _refresh_status(self):
        if self.network_data is None:
            self.status_label.setText(
                "No network loaded yet. Use \u201cOpen Network Editor\u201d to build one, "
                "or File \u2192 New / Open."
            )
            self.run_sim_btn.setEnabled(False)
            self.view_results_btn.setEnabled(False)
            return

        n_nodes = len(self.network_data.get("nodes", []))
        n_edges = len(self.network_data.get("edges", []))
        location = self.network_file_path or "(unsaved)"

        if n_nodes == 0:
            validity = "empty"
        else:
            valid, reason = is_valid_tree(self.network_data)
            validity = reason if valid else f"invalid \u2014 {reason}"

        self.status_label.setText(
            f"{n_nodes} node(s), {n_edges} edge(s) \u2014 {location}\n{validity}"
            + (
                f"\nLast simulation: {len(self.simulation_history)} steps."
                if self.simulation_history
                else ""
            )
        )

        self.run_sim_btn.setEnabled(n_nodes > 0)
        self.view_results_btn.setEnabled(bool(self.simulation_history))


    # Summoning the Graph Editor

    def open_network_editor(self):
        if self._editor is not None and self._editor.isVisible():
            self._editor.raise_()
            self._editor.activateWindow()
            return

        self._editor = NetworkEditor(initial_data=self.network_data)
        self._editor.closed.connect(self._on_editor_closed)
        self._editor.show()

    def _on_editor_closed(self, data: dict):
        self.network_data = data
        self._refresh_status()
        self._sync_open_sim_controls()

    def _pull_latest_from_editor_if_open(self):
        """If the editor is currently open, sync its live graph back
        into self.network_data before we act on network_data (e.g.
        saving), instead of waiting for it to close."""
        if self._editor is not None and self._editor.isVisible():
            self.network_data = self._editor.to_dict()

    def _sync_open_sim_controls(self):
        """Push the current network_data into an already-open
        Simulation Controls window, mirroring the live-refresh pattern
        used for the editor."""
        if self._sim_controls is not None and self._sim_controls.isVisible():
            self._sim_controls.set_network_data(self.network_data)


    # Summoning Simulation Controls

    def open_simulation_controls(self):
        self._pull_latest_from_editor_if_open()

        if not self.network_data or not self.network_data.get("nodes"):
            QMessageBox.information(
                self, "No Network", "Build or load a network first (Open Network Editor)."
            )
            return

        if self._sim_controls is not None and self._sim_controls.isVisible():
            self._sim_controls.set_network_data(self.network_data)
            self._sim_controls.raise_()
            self._sim_controls.activateWindow()
            return

        self._sim_controls = SimulationControls(self.network_data)
        self._sim_controls.simulation_complete.connect(self._on_simulation_complete)
        self._sim_controls.show()

    def _on_simulation_complete(self, history: list, network_data: dict):
        self.simulation_history = history
        self.simulation_network_data = network_data
        self._refresh_status()
        # If Results Viewer is already open from a previous run, refresh
        # it in place rather than leaving it showing stale history.
        if self._results_viewer is not None and self._results_viewer.isVisible():
            self._results_viewer.close()
            self._results_viewer = None
            self.view_results()


    # File menu actions

    def new_network(self):
        self.network_data = dict(EMPTY_NETWORK)
        self.network_file_path = None
        self.simulation_history = None
        self.simulation_network_data = None
        self._refresh_status()
        if self._editor is not None and self._editor.isVisible():
            self._editor.load_from_dict(self.network_data)
        self._sync_open_sim_controls()

    def open_network_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Network", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Error", f"Could not open network:\n{exc}")
            return

        self.network_data = data
        self.network_file_path = path
        self.simulation_history = None
        self.simulation_network_data = None
        self._refresh_status()
        if self._editor is not None and self._editor.isVisible():
            self._editor.load_from_dict(data)
        self._sync_open_sim_controls()

    def save_network_file(self):
        if self.network_file_path:
            self._pull_latest_from_editor_if_open()
            self._write_network(self.network_file_path)
        else:
            self.save_network_file_as()

    def save_network_file_as(self):
        self._pull_latest_from_editor_if_open()
        if self.network_data is None:
            QMessageBox.information(self, "Nothing to Save", "There is no network loaded yet.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save Network As", "", "JSON (*.json)")
        if not path:
            return
        self.network_file_path = path
        self._write_network(path)

    def _write_network(self, path: str):
        try:
            with open(path, "w") as f:
                json.dump(self.network_data, f, indent=4)
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"Could not save network:\n{exc}")
            return
        self._refresh_status()


    # Summoning the Results Viewer

    def view_results(self):
        if not self.simulation_history or not self.simulation_network_data:
            QMessageBox.information(
                self, "No Results", "Run a simulation first (Run Simulation)."
            )
            return

        if self._results_viewer is not None and self._results_viewer.isVisible():
            self._results_viewer.raise_()
            self._results_viewer.activateWindow()
            return

        self._results_viewer = ResultsViewer(self.simulation_network_data, self.simulation_history)
        self._results_viewer.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())