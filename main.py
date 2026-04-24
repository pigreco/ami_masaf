# -*- coding: utf-8 -*-
"""Modulo principale del plugin Alberi Monumentali Italia."""

import sys
import os
import subprocess
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QApplication, QPushButton, QMessageBox 
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication
from qgis.utils import iface
from qgis.core import Qgis


class AlberiMonumentali:
    """Classe principale del plugin Alberi Monumentali Italia."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = self.tr('&Alberi Monumentali')
        self.toolbar = None
        self.dlg = None
        
        self.required_modules = {
            "pandas": "pandas",
            "xlrd": "xlrd"
        }

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
        
        moduli_richiesti = ["pandas", "requests", "scipy"]
        
        self.check_dependencies()
        
        self.toolbar = self.iface.addToolBar('AlberiMonumentali')
        self.toolbar.setObjectName('AlberiMonumentaliToolbar')

        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.add_action(
            icon_path,
            text=self.tr('Alberi Monumentali Italia'),
            callback=self.run,
            parent=self.iface.mainWindow()
            )

    def check_dependencies(self):
        """Verifica i moduli e gestisce i messaggi all'utente."""
        missing_import_names = []
        missing_pip_names = []

        for imp_name, pip_name in self.required_modules.items():
            try:
                __import__(imp_name)
            except ImportError:
                missing_import_names.append(imp_name)
                missing_pip_names.append(pip_name)

        if missing_pip_names:
            self.ask_permission_to_install(missing_pip_names)
        else:
            self.iface.messageBar().pushMessage(
                "Plugin Pronto", 
                "Tutte le dipendenze Python sono soddisfatte.", 
                level=Qgis.MessageLevel.Success, 
                duration=3
            )

    def ask_permission_to_install(self, pip_packages):
        """Crea la barra con il pulsante di consenso."""
        msg = f"Il plugin Alberi Monumentali richiede moduli extra: {', '.join(pip_packages)}. Vuoi installarli?"
        msg_bar = self.iface.messageBar().createMessage("Dipendenze Mancanti", msg)
        
        btn = QPushButton(f"Installa ora ({len(pip_packages)})")
        # Connettiamo il click alla funzione di installazione reale
        btn.clicked.connect(lambda: [
            self.iface.messageBar().clearWidgets(), 
            self.run_installation(pip_packages)
        ])
        
        msg_bar.layout().addWidget(btn)
        self.iface.messageBar().pushWidget(msg_bar, Qgis.MessageLevel.Warning)

    def run_installation(self, pip_packages):
        """Esegue l'installazione tecnica."""
        try:
            # Individua l'eseguibile corretto per Windows/OSGeo4W
            python_exe = sys.executable.replace("qgis-bin.exe", "python-qgis.bat")
            if not os.path.exists(python_exe):
                python_exe = sys.executable
            
            is_windows = os.name == 'nt'

            # Installazione via pip
            subprocess.check_call(
                [python_exe, "-m", "pip", "install", "--user"] + pip_packages, 
                shell=is_windows
            )

            QMessageBox.information(
                None, 
                "Completato", 
                "Moduli installati. Riavvia QGIS per poter utilizzare il plugin."
            )
        except Exception as e:
            QMessageBox.critical(
                None, 
                "Errore", 
                f"L'installazione automatica è fallita:\n{str(e)}\n\n"
                "Prova ad avviare la Shell OSGeo4W come amministratore e digita:\n"
                f"pip install {' '.join(pip_packages)}"
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
        # if not _install_deps(self.iface.mainWindow()):
            # return
        from .dialogs import AlberiDialog
        self.dlg = AlberiDialog(self.iface, self.iface.mainWindow())
        self.dlg.show()
