"""
ContextOS™ PyQt5 tab widget with headless fallback.

When PyQt5 is not available (CI, headless servers), the module gracefully
degrades: all public symbols still exist but operate as no-ops or stubs.
Import this module freely — it will never crash due to a missing display.
"""

from __future__ import annotations

from typing import Any, Optional

_QT_AVAILABLE: bool = False

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QPushButton,
        QSplitter,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
    _QT_AVAILABLE = True
except ImportError:
    pass


# ─────────────────────────────── Headless stubs ───────────────────────────────

class _HeadlessTab:
    """No-op stub used when PyQt5 is not available."""

    def __init__(self, register: Any = None, resolver: Any = None, runner: Any = None) -> None:
        self._register = register
        self._resolver = resolver
        self._runner = runner

    def refresh(self) -> None:
        pass

    def is_headless(self) -> bool:
        return True


# ─────────────────────────────── Real Qt widget ───────────────────────────────

if _QT_AVAILABLE:
    class ContextOSTab(QWidget):  # type: ignore[misc]
        """
        PyQt5 tab for the FraPP main window.

        Layout:
          Left panel:  searchable list of all NKID/MKID entries
          Right panel: detail view + MKID runner output
        """

        def __init__(
            self,
            register: Any,
            resolver: Any,
            runner: Any,
            parent: Optional[Any] = None,
        ) -> None:
            super().__init__(parent)
            self._register = register
            self._resolver = resolver
            self._runner = runner
            self._setup_ui()
            self.refresh()

        def _setup_ui(self) -> None:
            root = QHBoxLayout(self)
            splitter = QSplitter(Qt.Horizontal)

            # ── Left: entry list ──────────────────────────────────────
            left = QWidget()
            lv = QVBoxLayout(left)
            lv.addWidget(QLabel("ContextOS Entries"))

            self._search = QLineEdit()
            self._search.setPlaceholderText("Search by ID or cluster…")
            self._search.textChanged.connect(self._on_search)
            lv.addWidget(self._search)

            self._list = QListWidget()
            self._list.currentTextChanged.connect(self._on_select)
            lv.addWidget(self._list)

            btn_refresh = QPushButton("Refresh")
            btn_refresh.clicked.connect(self.refresh)
            lv.addWidget(btn_refresh)

            splitter.addWidget(left)

            # ── Right: detail / runner output ─────────────────────────
            right = QWidget()
            rv = QVBoxLayout(right)
            rv.addWidget(QLabel("Entry detail"))

            self._detail = QTextEdit()
            self._detail.setReadOnly(True)
            rv.addWidget(self._detail)

            btn_run = QPushButton("Execute MKID")
            btn_run.clicked.connect(self._on_run_mkid)
            rv.addWidget(btn_run)

            splitter.addWidget(right)
            splitter.setSizes([300, 500])
            root.addWidget(splitter)

        def refresh(self) -> None:
            """Repopulate the list from the register."""
            self._list.clear()
            for e in self._register.all_ssot():
                self._list.addItem(f"NK  {e.nkid}  [{e.cluster.name}]")
            for e in self._register.all_work():
                promoted = " ✓" if e.promoted else ""
                self._list.addItem(f"MK  {e.mkid}  [{e.cluster.name}]{promoted}")

        def _on_search(self, text: str) -> None:
            for i in range(self._list.count()):
                item = self._list.item(i)
                item.setHidden(text.lower() not in item.text().lower())

        def _on_select(self, text: str) -> None:
            if not text:
                return
            parts = text.split()
            if not parts:
                return
            id_str = parts[1] if len(parts) > 1 else parts[0]
            if text.startswith("NK"):
                entry = self._register.get_ssot(id_str)
            else:
                entry = self._register.get_work(id_str)
            if entry:
                import json
                self._detail.setPlainText(
                    json.dumps(
                        {k: str(v) for k, v in entry.__dict__.items()},
                        indent=2,
                    )
                )

        def _on_run_mkid(self) -> None:
            item = self._list.currentItem()
            if item is None or not item.text().startswith("MK"):
                self._detail.setPlainText("Select a MK entry to execute.")
                return
            parts = item.text().split()
            mkid = parts[1] if len(parts) > 1 else ""
            try:
                result = self._runner.execute(mkid)
                import json
                self._detail.setPlainText(json.dumps(result, indent=2, default=str))
            except Exception as exc:
                self._detail.setPlainText(f"Error: {exc}")

        def is_headless(self) -> bool:
            return False

else:
    # Alias to the headless stub when Qt is unavailable
    ContextOSTab = _HeadlessTab  # type: ignore[assignment,misc]


def is_qt_available() -> bool:
    """Return True if PyQt5 was successfully imported."""
    return _QT_AVAILABLE
