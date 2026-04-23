# -*- coding: utf-8 -*-
"""
Modulo per lo scraping degli URL e il download dei file XLS dal sito MASAF.
Utilizza un QThread per non bloccare l'interfaccia utente.
"""

import re
import urllib.request
import tempfile
import os

from qgis.PyQt.QtCore import QThread, pyqtSignal

# URL della pagina MASAF con gli elenchi regionali
MASAF_PAGE_URL = "https://www.masaf.gov.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/11260"
MASAF_BASE_URL = "https://www.masaf.gov.it"

# URL di fallback hardcoded (aggiornato al 23/10/2025 - nono aggiornamento)
FALLBACK_URLS = {
    "Abruzzo":              "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252F7%252Fa%252FD.93386ce883788e3f9746/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Basilicata":           "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252F4%252F3%252FD.44bcdd9f183a3fa31b39/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Bolzano":              "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252F8%252Ff%252FD.67474ae533736a2ecbd1/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Calabria":             "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252F9%252F7%252FD.5390e2ed5be4b5049a03/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Campania":             "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252Fe%252F0%252FD.6b4607b334ee31581747/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Emilia Romagna":       "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252Fb%252F4%252FD.35ba867bbc28b1c6d16e/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Friuli Venezia Giulia":"https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252Fe%252F3%252FD.c56435788238e7d40558/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Lazio":                "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252F1%252Ff%252FD.7d9bdc4a1138bab21b8c/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Liguria":              "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252Fc%252Fc%252FD.98b3e2c807a2fe3e8ed8/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Lombardia":            "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252F6%252Fe%252FD.fb0172e578f291c44906/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Marche":               "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252Fd%252F1%252FD.00b37c2169100c8b7dc0/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Molise":               "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252Fa%252Fd%252FD.45f28bf45b1b08c4cc4a/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Piemonte":             "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252F8%252F0%252FD.bd095fb99422ec0701c0/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Puglia":               "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252F9%252F4%252FD.5955642bb4ba3a3da9eb/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Sardegna":             "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252Ff%252F7%252FD.f2b77ac2dc1b08a85222/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Sicilia":              "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252F2%252F4%252FD.542b3f556dd64f66ec76/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Toscana":              "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252F1%252F1%252FD.377c4514097b72810142/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Trento":               "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252Fc%252F7%252FD.a6e4f85ad8726d9186ec/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Umbria":               "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252Fe%252F1%252FD.325fbd41c7313f99f13a/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Valle d'Aosta":        "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252F9%252Ff%252FD.12677e2bfe1a024e5556/P/BLOB%3AID%3D11260/E/xls?mode=download",
    "Veneto":               "https://www.masaf.gov.it/flex/cm/pages/ServeAttachment.php/L/IT/D/1%252F8%252F9%252FD.c2903a6f7cf5650ff57c/P/BLOB%3AID%3D11260/E/xls?mode=download",
}

# Nomi regioni nell'ordine corretto per la UI
REGIONI = sorted(FALLBACK_URLS.keys())


def scrape_regional_urls():
    """
    Scarica la pagina MASAF e ricava gli URL aggiornati dei file regionali.

    Returns:
        dict: {nome_regione: url_download} oppure None in caso di errore
    """
    try:
        req = urllib.request.Request(
            MASAF_PAGE_URL,
            headers={"User-Agent": "Mozilla/5.0 (QGIS plugin AlberiMonumentali/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310
            html = resp.read().decode("iso-8859-1", errors="replace")

        # Trova tutti i link ai file XLS nella sezione elenchi regionali
        pattern = (
            r'href="(/flex/cm/pages/ServeAttachment\.php[^"]+/E/xls[^"]*)"'
            r'[^>]*>([^<(]+)'
        )
        matches = re.findall(pattern, html)

        urls = {}
        for path, label in matches:
            region = label.strip().rstrip('*').strip()
            # Rimuove la data e il peso dal label (es. "Sicilia 23/10/2025")
            region = re.sub(r'\s+\d{2}/\d{2}/\d{4}.*', '', region).strip()
            if region:
                urls[region] = MASAF_BASE_URL + path

        return urls if urls else None
    except Exception:
        return None


class DownloadWorker(QThread):
    """Thread di lavoro per il download dei file XLS."""

    progress = pyqtSignal(int, str)       # (percentuale, messaggio)
    region_done = pyqtSignal(str, str)    # (nome_regione, percorso_file_temp)
    finished = pyqtSignal(list)           # lista di (regione, percorso)
    error = pyqtSignal(str)              # messaggio di errore

    def __init__(self, regions, urls, parent=None):
        """
        Args:
            regions: lista di nomi regione da scaricare
            urls: dict {regione: url}
            parent: QObject parent
        """
        super().__init__(parent)
        self.regions = regions
        self.urls = urls
        self._abort = False

    def abort(self):
        """Interrompe il download."""
        self._abort = True

    def run(self):
        """Esegue il download in background."""
        results = []
        total = len(self.regions)

        for i, region in enumerate(self.regions):
            if self._abort:
                break

            url = self.urls.get(region)
            if not url:
                self.error.emit(f"URL non trovato per: {region}")
                continue

            pct = int(i / total * 100)
            self.progress.emit(pct, f"Download {region}...")

            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (QGIS plugin AlberiMonumentali/1.0)"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
                    data = resp.read()

                # Salva in file temporaneo
                tmp = tempfile.NamedTemporaryFile(
                    suffix=f"_{region.replace(' ', '_')}.xls",
                    delete=False
                )
                tmp.write(data)
                tmp.close()

                results.append((region, tmp.name))
                self.region_done.emit(region, tmp.name)

            except Exception as e:
                self.error.emit(f"Errore download {region}: {str(e)}")

        self.progress.emit(100, "Download completato.")
        self.finished.emit(results)
