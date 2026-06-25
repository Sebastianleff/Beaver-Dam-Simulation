"""
Batch Simulation UI (PySide6)
Runs batch simulations from a CSV and displays results as charts.
"""

import sys
import csv

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLabel, QApplication,
    QTableWidget, QTableWidgetItem, QSplitter, QGroupBox,
    QFormLayout, QMessageBox, QTabWidget, QScrollArea,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtCharts import (
    QChart, QChartView, QLineSeries, QValueAxis, QLegend
)

from beaver_dam_sim.service import SimulationService


# Helpers

COLORS = [
    QColor("#1565C0"), QColor("#C62828"), QColor("#2E7D32"),
    QColor("#6A1B9A"), QColor("#E65100"), QColor("#00838F"),
    QColor("#4E342E"), QColor("#37474F"), QColor("#AD1457"),
]


def color_for(index: int) -> QColor:
    return COLORS[index % len(COLORS)]


def build_chart(title: str, x_label: str, y_label: str) -> QChart:
    chart = QChart()
    chart.setTitle(title)
    chart.legend().setVisible(True)
    chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
    return chart


def add_axes(chart: QChart, x_label: str, y_label: str):
    x_axis = QValueAxis()
    x_axis.setTitleText(x_label)
    x_axis.setLabelFormat("%d")
    chart.addAxis(x_axis, Qt.AlignmentFlag.AlignBottom)

    y_axis = QValueAxis()
    y_axis.setTitleText(y_label)
    y_axis.setLabelFormat("%d")
    chart.addAxis(y_axis, Qt.AlignmentFlag.AlignLeft)

    return x_axis, y_axis


# Results data class

class SimRow:
    def __init__(self, sim_id, year, cells_flooded, dams_created, dams_broken):
        self.sim_id = int(sim_id)
        self.year = int(year)
        self.cells_flooded = int(cells_flooded)
        self.dams_created = int(dams_created)
        self.dams_broken = int(dams_broken)


# Main Window

class BatchUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Beaver Dam — Batch Simulation")
        self.setMinimumSize(1200, 750)

        self.service = SimulationService()
        self.results: list[SimRow] = []

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # File picker row
        file_group = QGroupBox("Batch Files")
        file_form = QFormLayout()

        self.input_label = QLabel("No file selected")
        input_btn = QPushButton("Browse…")
        input_btn.clicked.connect(self._pick_input)
        input_row = QHBoxLayout()
        input_row.addWidget(self.input_label, 1)
        input_row.addWidget(input_btn)
        input_widget = QWidget()
        input_widget.setLayout(input_row)
        file_form.addRow("Input CSV:", input_widget)

        self.output_label = QLabel("No file selected")
        output_btn = QPushButton("Browse…")
        output_btn.clicked.connect(self._pick_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_label, 1)
        output_row.addWidget(output_btn)
        output_widget = QWidget()
        output_widget.setLayout(output_row)
        file_form.addRow("Output CSV:", output_widget)

        file_group.setLayout(file_form)
        root.addWidget(file_group)

        run_btn = QPushButton("Run Batch Simulation")
        run_btn.setFixedHeight(36)
        run_btn.clicked.connect(self._run_batch)
        root.addWidget(run_btn)

        # Tabs: Table / Flooded chart / Dams chart
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # Table tab
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Simulation", "Year", "Flooded Cells", "Dams Created", "Dams Broken"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabs.addTab(self.table, "Results Table")

        # Flooded cells chart tab
        self.flooded_chart_view = QChartView()
        self.flooded_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.tabs.addTab(self.flooded_chart_view, "Flooded Cells Over Time")

        # Dams chart tab
        self.dams_chart_view = QChartView()
        self.dams_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.tabs.addTab(self.dams_chart_view, "Dams Created vs Broken")

        self.input_path = ""
        self.output_path = ""

    # File pickers

    def _pick_input(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Input CSV", "", "CSV (*.csv)")
        if path:
            self.input_path = path
            self.input_label.setText(path)

    def _pick_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select Output CSV", "", "CSV (*.csv)")
        if path:
            self.output_path = path
            self.output_label.setText(path)

    # Run

    def _run_batch(self):
        if not self.input_path:
            QMessageBox.warning(self, "Missing Input", "Please select an input CSV file.")
            return
        if not self.output_path:
            QMessageBox.warning(self, "Missing Output", "Please select an output CSV file.")
            return

        try:
            self.service.run_simulation_batch(self.input_path, self.output_path, None)
        except Exception as e:
            QMessageBox.critical(self, "Batch Error", str(e))
            return

        try:
            self._load_results(self.output_path)
        except Exception as e:
            QMessageBox.critical(self, "Results Error", str(e))
            return

        self._populate_table()
        self._build_flooded_chart()
        self._build_dams_chart()

        self.tabs.setCurrentIndex(1)
        QMessageBox.information(
            self, "Done",
            f"Batch complete.\n{len(self.results)} rows written to output CSV."
        )

    # Load CSV

    def _load_results(self, path: str):
        self.results = []
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.results.append(SimRow(
                    row["simulation_id"],
                    row["year"],
                    row["cells_flooded"],
                    row["dams_created"],
                    row["dams_broken"],
                ))

    # Table

    def _populate_table(self):
        self.table.setRowCount(len(self.results))
        for r, row in enumerate(self.results):
            self.table.setItem(r, 0, QTableWidgetItem(str(row.sim_id)))
            self.table.setItem(r, 1, QTableWidgetItem(str(row.year)))
            self.table.setItem(r, 2, QTableWidgetItem(str(row.cells_flooded)))
            self.table.setItem(r, 3, QTableWidgetItem(str(row.dams_created)))
            self.table.setItem(r, 4, QTableWidgetItem(str(row.dams_broken)))
        self.table.resizeColumnsToContents()

    # Group rows by sim_id

    def _group_by_sim(self) -> dict[int, list[SimRow]]:
        groups: dict[int, list[SimRow]] = {}
        for row in self.results:
            groups.setdefault(row.sim_id, []).append(row)
        for rows in groups.values():
            rows.sort(key=lambda r: r.year)
        return groups

    # Flooded cells chart

    def _build_flooded_chart(self):
        chart = build_chart("Flooded Cells Over Time", "Year", "Flooded Cells")
        groups = self._group_by_sim()

        max_x = max_y = 0

        for idx, (sim_id, rows) in enumerate(sorted(groups.items())):
            series = QLineSeries()
            series.setName(f"Sim {sim_id}")
            pen = QPen(color_for(idx))
            pen.setWidth(2)
            series.setPen(pen)

            for row in rows:
                series.append(row.year, row.cells_flooded)
                max_x = max(max_x, row.year)
                max_y = max(max_y, row.cells_flooded)

            chart.addSeries(series)

        x_axis, y_axis = add_axes(chart, "Year", "Flooded Cells")
        x_axis.setRange(0, max_x)
        y_axis.setRange(0, max_y + 5)

        for series in chart.series():
            series.attachAxis(x_axis)
            series.attachAxis(y_axis)

        self.flooded_chart_view.setChart(chart)

    # Dams chart

    def _build_dams_chart(self):
        chart = build_chart("Dams Created vs Broken Over Time", "Year", "Count")
        groups = self._group_by_sim()

        max_x = max_y = 0

        for idx, (sim_id, rows) in enumerate(sorted(groups.items())):
            created_series = QLineSeries()
            created_series.setName(f"Sim {sim_id} Created")
            pen_c = QPen(color_for(idx))
            pen_c.setWidth(2)
            created_series.setPen(pen_c)

            broken_series = QLineSeries()
            broken_series.setName(f"Sim {sim_id} Broken")
            pen_b = QPen(color_for(idx))
            pen_b.setWidth(2)
            pen_b.setStyle(Qt.PenStyle.DashLine)
            broken_series.setPen(pen_b)

            for row in rows:
                created_series.append(row.year, row.dams_created)
                broken_series.append(row.year, row.dams_broken)
                max_x = max(max_x, row.year)
                max_y = max(max_y, row.dams_created, row.dams_broken)

            chart.addSeries(created_series)
            chart.addSeries(broken_series)

        x_axis, y_axis = add_axes(chart, "Year", "Count")
        x_axis.setRange(0, max_x)
        y_axis.setRange(0, max_y + 5)

        for series in chart.series():
            series.attachAxis(x_axis)
            series.attachAxis(y_axis)

        self.dams_chart_view.setChart(chart)


# Run

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = BatchUI()
    w.show()
    sys.exit(app.exec())