# -*- coding: utf-8 -*-
"""
Alberi Monumentali Italia
Plugin QGIS per scaricare e visualizzare gli alberi monumentali d'Italia
dal sito MASAF (Ministero dell'agricoltura, della sovranità alimentare e delle foreste).
"""


def classFactory(iface):
    """Carica la classe principale del plugin."""
    from .main import AlberiMonumentali
    return AlberiMonumentali(iface)
