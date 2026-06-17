from PySide6.QtWidgets import QApplication, QMainWindow
import sys


class NetworkEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("River Network Editor")
        self.resize(800, 600)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = NetworkEditor()
    window.show()

    sys.exit(app.exec())