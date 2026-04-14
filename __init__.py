# -*- coding: utf-8 -*-
"""
Alberi Monumentali Italia
Plugin QGIS per scaricare e visualizzare gli alberi monumentali d'Italia
dal sito MASAF (Ministero dell'agricoltura, della sovranità alimentare e delle foreste).
"""

import sys
import subprocess


def _install_deps():
    """Installa le dipendenze mancanti (pandas, xlrd) tramite pip di QGIS."""
    required = {"pandas": "pandas", "xlrd": "xlrd"}
    missing = []

    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if not missing:
        return True

    try:
        from qgis.PyQt.QtWidgets import QMessageBox, QApplication
        parent = QApplication.activeWindow()

        risposta = QMessageBox.question(
            parent,
            "Alberi Monumentali — Dipendenze mancanti",
            (
                "Il plugin richiede i seguenti pacchetti Python non ancora installati:\n\n"
                f"  • {chr(10).join('  • ' + p for p in missing)}\n\n"
                "Vuoi installarli automaticamente adesso?\n"
                "(Potrebbe essere necessario riavviare QGIS al termine.)"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if risposta != QMessageBox.Yes:
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

        # Usa il pip associato all'interprete Python corrente (quello di QGIS)
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
        return False  # richiede riavvio: non caricare il plugin ora

    except Exception as exc:
        try:
            from qgis.PyQt.QtWidgets import QMessageBox, QApplication
            QMessageBox.critical(
                QApplication.activeWindow(),
                "Alberi Monumentali — Errore installazione",
                (
                    f"Impossibile installare le dipendenze automaticamente:\n{exc}\n\n"
                    "Installale manualmente:\n"
                    f"  pip install {' '.join(missing)}"
                ),
            )
        except Exception:
            pass
        return False


def classFactory(iface):
    """Carica la classe principale del plugin."""
    if not _install_deps():
        # Restituisce un plugin stub che non fa nulla, per evitare crash
        class _Stub:
            def __init__(self, iface): pass
            def initGui(self): pass
            def unload(self): pass
        return _Stub(iface)

    from .main import AlberiMonumentali
    return AlberiMonumentali(iface)
