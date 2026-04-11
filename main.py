# -*- coding: utf-8 -*-
"""Modulo principale del plugin Alberi Monumentali Italia."""

import os
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication


class AlberiMonumentali:
    """Classe principale del plugin Alberi Monumentali Italia."""

    def __init__(self, iface):
        """Inizializza il plugin.

        Args:
            iface: istanza dell'interfaccia QGIS
        """
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
        from .dialogs import AlberiDialog
        self.dlg = AlberiDialog(self.iface, self.iface.mainWindow())
        self.dlg.show()
