# -*- coding: utf-8 -*-
"""Modulo principale del plugin Alberi Monumentali Italia."""

import sys
import os
import subprocess
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication


def _install_deps(parent=None):
    """Verifica e installa le dipendenze mancanti (pandas, xlrd).

    Ritorna True se le dipendenze sono disponibili, False altrimenti.
    """
    required = ["pandas", "xlrd"]
    missing = [pkg for pkg in required if not _is_importable(pkg)]

    if not missing:
        return True

    # PyQt6 moved enum values to QMessageBox.StandardButton.*
    _btn = getattr(QMessageBox, "StandardButton", QMessageBox)
    YES = _btn.Yes
    NO = _btn.No

    risposta = QMessageBox.question(
        parent,
        "Alberi Monumentali — Dipendenze mancanti",
        (
            "Il plugin richiede i seguenti pacchetti Python non ancora installati:\n\n"
            + "".join(f"  • {p}\n" for p in missing)
            + "\nVuoi installarli automaticamente adesso?\n"
            "(Potrebbe essere necessario riavviare QGIS al termine.)"
        ),
        YES | NO,
        YES,
    )

    if risposta != YES:
        QMessageBox.warning(
            parent,
            "Alberi Monumentali — Installazione annullata",
            (
                "Il plugin non può funzionare senza le dipendenze.\n\n"
                "Installale manualmente dalla OSGeo4W Shell (Windows) "
                "o dal terminale:\n\n"
                f"  pip install {' '.join(missing)}"
            ),
        )
        return False

    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--user"] + missing
        )
        QMessageBox.information(
            parent,
            "Alberi Monumentali — Installazione completata",
            (
                f"Pacchetti installati: {', '.join(missing)}.\n\n"
                "Riavvia QGIS per rendere effettive le modifiche."
            ),
        )
    except Exception as exc:
        QMessageBox.critical(
            parent,
            "Alberi Monumentali — Errore installazione",
            (
                f"Impossibile installare le dipendenze automaticamente:\n{exc}\n\n"
                "Installale manualmente:\n"
                f"  pip install {' '.join(missing)}"
            ),
        )

    return False  # richiede riavvio


def _is_importable(name):
    try:
        __import__(name)
        return True
    except ImportError:
        return False


class AlberiMonumentali:
    """Classe principale del plugin Alberi Monumentali Italia."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = self.tr('&Alberi Monumentali')
        self.toolbar = None
        self.dlg = None

    def tr(self, message):
        """Traduce una stringa."""
        return QCoreApplication.translate('AlberiMonumentali', message)

    def add_action(self, icon_path, text, callback,
                   enabled=True, add_to_menu=True,
                   add_to_toolbar=True, parent=None):
        """Aggiunge icona toolbar e voce di menu."""
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent or self.iface.mainWindow())
        action.triggered.connect(callback)
        action.setEnabled(enabled)

        if add_to_toolbar and self.toolbar:
            self.toolbar.addAction(action)
        if add_to_menu:
            self.iface.addPluginToWebMenu(self.menu, action)

        self.actions.append(action)
        return action

    def initGui(self):
        """Crea voci di menu e icone toolbar."""
        self.toolbar = self.iface.addToolBar('AlberiMonumentali')
        self.toolbar.setObjectName('AlberiMonumentaliToolbar')

        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.add_action(
            icon_path,
            text=self.tr('Alberi Monumentali Italia'),
            callback=self.run,
            parent=self.iface.mainWindow()
        )

    def unload(self):
        """Rimuove voci di menu e icone toolbar."""
        for action in self.actions:
            self.iface.removePluginWebMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        if self.toolbar:
            del self.toolbar

    def run(self):
        """Apre il dialogo principale del plugin."""
        if not _install_deps(self.iface.mainWindow()):
            return
        from .dialogs import AlberiDialog
        self.dlg = AlberiDialog(self.iface, self.iface.mainWindow())
        self.dlg.show()
