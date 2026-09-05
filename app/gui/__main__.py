import sys

from PySide6.QtWidgets import QApplication

from app.core.session import AnalyzerSession
from app.gui.main_window import MainWindow
from app.gui.theme import apply_theme


def main(argv=None) -> int:
    app = QApplication(sys.argv if argv is None else argv)
    apply_theme(app)
    session = AnalyzerSession.from_config()
    win = MainWindow(session)
    win.resize(1900, 1000)
    win.show()
    code = app.exec()
    session.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
