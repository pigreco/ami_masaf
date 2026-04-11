# -*- coding: utf-8 -*-
"""
Dialogo principale del plugin Alberi Monumentali Italia.

Permette di:
- Selezionare una o più regioni (o tutta Italia)
- Scegliere il formato di output (Shapefile / GeoPackage)
- Scegliere la cartella/file di destinazione
- Avviare il download e la conversione
- Caricare il layer in QGIS con tematizzazione dedicata
"""

import os
import pandas as pd

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem,
    QComboBox, QLineEdit, QFileDialog, QProgressBar,
    QMessageBox, QGroupBox, QCheckBox, QSizePolicy,
    QAbstractItemView, QFrame, QSpacerItem,
)
from qgis.PyQt.QtCore import Qt, QThread, QSize, pyqtSignal
from qgis.PyQt.QtGui import QFont, QColor, QPalette, QIcon

from qgis.core import QgsProject

from .downloader import REGIONI, FALLBACK_URLS, DownloadWorker, scrape_regional_urls
from .converter import read_xls, dataframes_to_layer
from .symbology import apply_graduated_symbology


class AlberiDialog(QDialog):
    """Dialogo principale del plugin."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Alberi Monumentali d'Italia — MASAF")
        self.setMinimumWidth(520)
        self.setMinimumHeight(640)

        self._urls = dict(FALLBACK_URLS)      # url per regione
        self._worker = None
        self._downloaded = []                 # lista (regione, path_xls)

        self._setup_ui()
        self._refresh_urls()

    # ------------------------------------------------------------------ #
    #  UI                                                                  #
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        # Titolo
        title = QLabel("🌳 Alberi Monumentali d'Italia")
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet("color: #1B5E20;")
        root.addWidget(title)

        subtitle = QLabel(
            "Fonte: MASAF — Ministero dell'agricoltura, della sovranità\n"
            "alimentare e delle foreste — Nono aggiornamento (23/10/2025)"
        )
        subtitle.setStyleSheet("color: #555; font-size: 10px;")
        root.addWidget(subtitle)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(line)

        # ----- Selezione Regioni -----
        grp_reg = QGroupBox("Selezione Regioni")
        grp_reg.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #2D6A4F; border: 1px solid #74C69D; "
            "border-radius: 4px; margin-top: 6px; padding-top: 6px; }"
        )
        reg_layout = QVBoxLayout(grp_reg)

        btn_row = QHBoxLayout()
        self.btn_all = QPushButton("✔ Tutta Italia")
        self.btn_none = QPushButton("✘ Deseleziona tutto")
        self.btn_all.setFixedHeight(26)
        self.btn_none.setFixedHeight(26)
        self.btn_all.clicked.connect(self._select_all)
        self.btn_none.clicked.connect(self._select_none)
        btn_row.addWidget(self.btn_all)
        btn_row.addWidget(self.btn_none)
        btn_row.addStretch()
        reg_layout.addLayout(btn_row)

        self.list_regions = QListWidget()
        self.list_regions.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.list_regions.setFixedHeight(200)
        for r in REGIONI:
            item = QListWidgetItem(r)
            self.list_regions.addItem(item)
        reg_layout.addWidget(self.list_regions)

        root.addWidget(grp_reg)

        # ----- Formato output -----
        grp_fmt = QGroupBox("Formato di output")
        grp_fmt.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #2D6A4F; border: 1px solid #74C69D; "
            "border-radius: 4px; margin-top: 6px; padding-top: 6px; }"
        )
        fmt_layout = QGridLayout(grp_fmt)

        fmt_layout.addWidget(QLabel("Formato:"), 0, 0)
        self.combo_fmt = QComboBox()
        self.combo_fmt.addItems(["GeoPackage (.gpkg)", "Shapefile (.shp)"])
        self.combo_fmt.currentIndexChanged.connect(self._on_fmt_changed)
        fmt_layout.addWidget(self.combo_fmt, 0, 1)

        fmt_layout.addWidget(QLabel("Destinazione:"), 1, 0)
        dest_row = QHBoxLayout()
        self.edit_dest = QLineEdit()
        self.edit_dest.setPlaceholderText("Seleziona cartella o file…")
        self.btn_browse = QPushButton("…")
        self.btn_browse.setFixedWidth(32)
        self.btn_browse.clicked.connect(self._browse_dest)
        dest_row.addWidget(self.edit_dest)
        dest_row.addWidget(self.btn_browse)
        fmt_layout.addLayout(dest_row, 1, 1)

        fmt_layout.addWidget(QLabel("Nome layer:"), 2, 0)
        self.edit_name = QLineEdit("Alberi Monumentali")
        fmt_layout.addWidget(self.edit_name, 2, 1)

        root.addWidget(grp_fmt)

        # ----- Opzioni -----
        grp_opt = QGroupBox("Opzioni")
        grp_opt.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #2D6A4F; border: 1px solid #74C69D; "
            "border-radius: 4px; margin-top: 6px; padding-top: 6px; }"
        )
        opt_layout = QVBoxLayout(grp_opt)
        self.chk_symbology = QCheckBox("Applica tematizzazione alberi (graduata per circonferenza)")
        self.chk_symbology.setChecked(True)
        self.chk_add_map = QCheckBox("Aggiungi automaticamente il layer alla mappa")
        self.chk_add_map.setChecked(True)
        opt_layout.addWidget(self.chk_symbology)
        opt_layout.addWidget(self.chk_add_map)
        root.addWidget(grp_opt)

        # ----- Progress -----
        self.lbl_status = QLabel("Pronto.")
        self.lbl_status.setStyleSheet("color: #333; font-size: 10px;")
        root.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        # ----- Pulsanti -----
        btn_row2 = QHBoxLayout()
        btn_row2.setSpacing(6)

        self.btn_download = QPushButton("⬇  Scarica e converti")
        self.btn_download.setFixedHeight(36)
        self.btn_download.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_download.setStyleSheet(
            "QPushButton { background: #2D6A4F; color: white; border-radius: 4px; "
            "font-weight: bold; font-size: 12px; padding: 0 16px; }"
            "QPushButton:hover { background: #1B5E20; }"
            "QPushButton:disabled { background: #aaa; }"
        )
        self.btn_download.clicked.connect(self._start_download)

        self.btn_cancel = QPushButton("Annulla")
        self.btn_cancel.setFixedSize(90, 36)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_cancel.setEnabled(False)

        btn_close = QPushButton("Chiudi")
        btn_close.setFixedSize(90, 36)
        btn_close.clicked.connect(self.close)

        btn_row2.addWidget(self.btn_download)
        btn_row2.addWidget(self.btn_cancel)
        btn_row2.addWidget(btn_close)
        root.addLayout(btn_row2)

        # Credits
        credits = QLabel(
            '<a href="https://www.masaf.gov.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/11260">'
            'Dati MASAF — Licenza CC BY 4.0</a>'
        )
        credits.setOpenExternalLinks(True)
        credits.setStyleSheet("font-size: 9px; color: #888;")
        credits.setAlignment(Qt.AlignmentFlag.AlignRight)
        root.addWidget(credits)

    # ------------------------------------------------------------------ #
    #  Logica UI                                                           #
    # ------------------------------------------------------------------ #

    def _select_all(self):
        for i in range(self.list_regions.count()):
            self.list_regions.item(i).setSelected(True)

    def _select_none(self):
        self.list_regions.clearSelection()

    def _on_fmt_changed(self, idx):
        # Resetta il percorso quando si cambia formato
        self.edit_dest.clear()

    def _browse_dest(self):
        fmt = self._get_fmt()
        if fmt == "GPKG":
            path, _ = QFileDialog.getSaveFileName(
                self, "Salva GeoPackage", "", "GeoPackage (*.gpkg)"
            )
        else:
            path = QFileDialog.getExistingDirectory(
                self, "Seleziona cartella Shapefile"
            )
        if path:
            self.edit_dest.setText(path)

    def _get_fmt(self):
        return "GPKG" if self.combo_fmt.currentIndex() == 0 else "SHP"

    def _get_selected_regions(self):
        return [item.text() for item in self.list_regions.selectedItems()]

    def _set_busy(self, busy):
        self.btn_download.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)
        self.progress_bar.setVisible(busy)
        if not busy:
            self.progress_bar.setValue(0)

    # ------------------------------------------------------------------ #
    #  Aggiornamento URL da sito                                           #
    # ------------------------------------------------------------------ #

    def _refresh_urls(self):
        """Prova a recuperare URL aggiornati dalla pagina MASAF (silenzioso)."""
        self.lbl_status.setText("Aggiornamento URL dal sito MASAF…")

        class _Refresher(QThread):
            done = pyqtSignal(dict, str)   # (urls_trovati, messaggio)

            def run(self_):
                urls = scrape_regional_urls()
                if urls:
                    self_.done.emit(urls, f"URL aggiornati dal sito ({len(urls)} regioni trovate). Pronto.")
                else:
                    self_.done.emit({}, "URL da cache locale. Pronto.")

        def _on_refresh_done(urls, msg):
            if urls:
                self._urls.update(urls)
            self.lbl_status.setText(msg)

        self._refresher = _Refresher(self)
        self._refresher.done.connect(_on_refresh_done)
        self._refresher.start()

    # ------------------------------------------------------------------ #
    #  Download                                                            #
    # ------------------------------------------------------------------ #

    def _start_download(self):
        regions = self._get_selected_regions()
        if not regions:
            QMessageBox.warning(self, "Attenzione", "Seleziona almeno una regione.")
            return

        dest = self.edit_dest.text().strip()
        if not dest:
            QMessageBox.warning(self, "Attenzione", "Seleziona la destinazione di output.")
            return

        fmt = self._get_fmt()

        # Controlla che la destinazione esista / sia scrivibile
        if fmt == "SHP":
            if not os.path.isdir(dest):
                try:
                    os.makedirs(dest, exist_ok=True)
                except Exception as e:
                    QMessageBox.critical(self, "Errore", f"Impossibile creare cartella:\n{e}")
                    return
        else:
            parent_dir = os.path.dirname(dest) or "."
            if not os.path.isdir(parent_dir):
                QMessageBox.critical(self, "Errore",
                                     f"Cartella di destinazione non trovata:\n{parent_dir}")
                return

        self._downloaded = []
        self._dest = dest
        self._fmt = fmt
        self._regions_selected = regions

        self._set_busy(True)
        self.lbl_status.setText(f"Avvio download di {len(regions)} regioni…")

        self._worker = DownloadWorker(regions, self._urls, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.region_done.connect(self._on_region_done)
        self._worker.finished.connect(self._on_download_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _cancel(self):
        if self._worker:
            self._worker.abort()
        self._set_busy(False)
        self.lbl_status.setText("Operazione annullata.")

    # ------------------------------------------------------------------ #
    #  Slot worker                                                         #
    # ------------------------------------------------------------------ #

    def _on_progress(self, pct, msg):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(msg)

    def _on_region_done(self, region, filepath):
        self._downloaded.append((region, filepath))

    def _on_worker_error(self, msg):
        self.lbl_status.setText(f"⚠ {msg}")

    def _on_download_finished(self, results):
        self._set_busy(False)

        if not results:
            QMessageBox.warning(self, "Attenzione",
                                "Nessun file scaricato correttamente.")
            return

        self.lbl_status.setText("Lettura e conversione in corso…")

        # Legge i DataFrame
        df_list = []
        errors = []
        for region, path in results:
            try:
                df = read_xls(path)
                df_list.append((region, df))
            except Exception as e:
                errors.append(f"{region}: {e}")
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass

        if not df_list:
            msg = "Impossibile leggere i file scaricati."
            if errors:
                msg += "\n\nDettagli:\n" + "\n".join(errors)
            QMessageBox.critical(self, "Errore", msg)
            return

        # Converte in layer
        layer_name = self.edit_name.text().strip() or "Alberi Monumentali"
        self.lbl_status.setText("Creazione layer vettoriale…")

        try:
            layer, n_written, n_skipped = dataframes_to_layer(
                df_list, self._dest, self._fmt, layer_name
            )
        except Exception as e:
            QMessageBox.critical(self, "Errore conversione", str(e))
            self.lbl_status.setText("Errore durante la conversione.")
            return

        if not layer.isValid():
            QMessageBox.critical(self, "Errore", "Il layer creato non è valido.")
            return

        # Tematizzazione
        if self.chk_symbology.isChecked():
            apply_graduated_symbology(layer)

        # Aggiunge alla mappa
        if self.chk_add_map.isChecked():
            QgsProject.instance().addMapLayer(layer)

        # Report finale
        summary = (
            f"✅ Completato!\n\n"
            f"Alberi scritti:   {n_written}\n"
            f"Alberi saltati:   {n_skipped} (coordinate mancanti/invalide)\n"
            f"Regioni:          {len(df_list)}\n"
            f"Formato:          {'GeoPackage' if self._fmt == 'GPKG' else 'Shapefile'}\n"
            f"File:             {self._dest}"
        )
        if errors:
            summary += "\n\n⚠ Regioni con errori:\n" + "\n".join(errors)

        self.lbl_status.setText(
            f"Completato — {n_written} alberi caricati, {n_skipped} saltati."
        )
        QMessageBox.information(self, "Operazione completata", summary)
