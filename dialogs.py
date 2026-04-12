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
import re
import pandas as pd
from datetime import datetime

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem,
    QComboBox, QLineEdit, QFileDialog, QProgressBar,
    QMessageBox, QGroupBox, QCheckBox, QSizePolicy,
    QAbstractItemView, QFrame, QSpacerItem, QTabWidget,
    QWidget, QTextBrowser,
)
from qgis.PyQt.QtCore import Qt, QThread, QSize, pyqtSignal
from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtGui import QFont, QColor, QPalette, QIcon

import traceback

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsVectorFileWriter,
    QgsCoordinateTransformContext,
    QgsMessageLog,
    Qgis,
)

from .downloader import REGIONI, FALLBACK_URLS, DownloadWorker, scrape_regional_urls
from .converter import read_xls, dataframes_to_layer
from .symbology import apply_graduated_symbology, apply_choropleth_regions, apply_choropleth_symbology


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
        self._update_layer_name()   # nome iniziale (nessuna selezione → "")
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
        font.setFamilies(["Segoe UI Emoji", "Noto Color Emoji", "Apple Color Emoji", ""])
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

        # ----- Tab widget -----
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        self.tabs.addTab(self._build_main_tab(), "Scarica")
        self.tabs.addTab(self._build_guide_tab(), "Guida")

        # ----- Progress (fuori dai tab, sempre visibile) -----
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

    def _build_main_tab(self) -> QWidget:
        """Costruisce il tab principale con regioni, formato e opzioni."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 8, 0, 0)

        grp_style = (
            "QGroupBox { font-weight: bold; color: #2D6A4F; border: 1px solid #74C69D; "
            "border-radius: 4px; margin-top: 6px; padding-top: 6px; }"
        )

        # ----- Selezione Regioni -----
        grp_reg = QGroupBox("Selezione Regioni")
        grp_reg.setStyleSheet(grp_style)
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
        self.list_regions.setFixedHeight(180)
        self.list_regions.setStyleSheet(
            "QListWidget::item:selected { background-color: #2D6A4F; color: white; }"
            "QListWidget::item:selected:!active { background-color: #2D6A4F; color: white; }"
        )
        for r in REGIONI:
            item = QListWidgetItem(r)
            self.list_regions.addItem(item)
        self.list_regions.itemSelectionChanged.connect(self._update_layer_name)
        reg_layout.addWidget(self.list_regions)

        layout.addWidget(grp_reg)

        # ----- Formato output -----
        grp_fmt = QGroupBox("Formato di output")
        grp_fmt.setStyleSheet(grp_style)
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
        self.edit_name = QLineEdit()
        fmt_layout.addWidget(self.edit_name, 2, 1)

        layout.addWidget(grp_fmt)

        # ----- Opzioni -----
        grp_opt = QGroupBox("Opzioni")
        grp_opt.setStyleSheet(grp_style)
        opt_layout = QVBoxLayout(grp_opt)
        self.chk_symbology = QCheckBox("Applica tematizzazione alberi (graduata per circonferenza)")
        self.chk_symbology.setChecked(True)
        self.chk_add_map = QCheckBox("Aggiungi automaticamente il layer alla mappa")
        self.chk_add_map.setChecked(True)
        opt_layout.addWidget(self.chk_symbology)
        opt_layout.addWidget(self.chk_add_map)
        layout.addWidget(grp_opt)

        layout.addStretch()
        return tab

    def _build_guide_tab(self) -> QWidget:
        """Costruisce il tab Guida caricando help/guida.html dalla cartella del plugin."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)

        # Ricava i colori direttamente dalla palette Qt — funziona con qualsiasi tema
        pal = QApplication.palette()
        is_dark = pal.window().color().lightness() < 128
        text    = pal.windowText().color().name()   # colore testo principale
        bg      = pal.window().color().name()        # colore sfondo

        if is_dark:
            h2_col, h3_col, accent = "#81C784", "#A5D6A7", "#81C784"
            code_bg  = pal.mid().color().name()      # grigio adattivo scuro
            note_bg  = "#1B3A1F"
        else:
            h2_col, h3_col, accent = "#1B5E20", "#2D6A4F", "#2D6A4F"
            code_bg  = "#f0f0f0"
            note_bg  = "#E8F5E9"

        # Colori iniettati nel <head> — sovrascrivono il CSS strutturale del file
        theme_css = (
            f"body  {{ color: {text}; }}"
            f"h2    {{ color: {h2_col}; }}"
            f"h3    {{ color: {h3_col}; }}"
            f"code  {{ background: {code_bg}; color: {text}; }}"
            f".note {{ background: {note_bg}; border-left-color: {accent}; }}"
            f"a     {{ color: {accent}; }}"
        )

        # Sfondo del widget allineato alla palette (evita il mismatch bianco/scuro)
        browser.setStyleSheet(f"QTextBrowser {{ background-color: {bg}; }}")

        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        guide_path = os.path.join(plugin_dir, "help", "guida.html")
        try:
            with open(guide_path, encoding="utf-8") as fh:
                html = fh.read()
            html = html.replace("</head>", f"<style>{theme_css}</style></head>", 1)
            browser.setHtml(html)
        except OSError:
            browser.setHtml(
                f"<p style='color:{text}'>File di guida non trovato: "
                f"<code>help/guida.html</code></p>"
            )

        layout.addWidget(browser)
        return tab

    # ------------------------------------------------------------------ #
    #  Logica UI                                                           #
    # ------------------------------------------------------------------ #

    def _select_all(self):
        for i in range(self.list_regions.count()):
            self.list_regions.item(i).setSelected(True)

    def _select_none(self):
        self.list_regions.clearSelection()

    def _update_layer_name(self):
        """Aggiorna automaticamente il nome layer in base alla selezione."""
        selected = self._get_selected_regions()
        if len(selected) == 1:
            name = re.sub(r"[^\w\-]", "_", selected[0])
        elif selected:
            name = "ami_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        else:
            name = ""
        self.edit_name.setText(name)

    @staticmethod
    def _region_to_filename(region_name: str) -> str:
        """Converte il nome regione in una stringa usabile come nome file."""
        return re.sub(r"[^\w\-]", "_", region_name)

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
            if not dest.lower().endswith(".gpkg"):
                dest = dest + ".gpkg"
                self.edit_dest.setText(dest)
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

        # Aggiunge il layer punti alla mappa prima di tematizzare:
        # su Linux, addMapLayer può caricare lo stile predefinito sovrascrivendo
        # il renderer già impostato.
        root = QgsProject.instance().layerTreeRoot()
        if self.chk_add_map.isChecked():
            QgsProject.instance().addMapLayer(layer, False)
            root.insertLayer(0, layer)

        # Tematizzazione (dopo addMapLayer per evitare override del renderer su Linux)
        regions_layer = None
        if self.chk_symbology.isChecked():
            try:
                apply_graduated_symbology(layer)
            except Exception:
                QgsMessageLog.logMessage(
                    traceback.format_exc(),
                    "AlberiMonumentali",
                    Qgis.MessageLevel.Critical,
                )
            if len(self._regions_selected) == len(REGIONI):
                plugin_dir = os.path.dirname(os.path.abspath(__file__))
                regions_layer = apply_choropleth_regions(layer, plugin_dir)

                if regions_layer and self._fmt == "GPKG":
                    # Salva il layer regioni nello stesso GeoPackage dei punti
                    opts = QgsVectorFileWriter.SaveVectorOptions()
                    opts.driverName = "GPKG"
                    opts.layerName = "regioni_densita_alberi"
                    opts.actionOnExistingFile = (
                        QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
                    )
                    QgsVectorFileWriter.writeAsVectorFormatV3(
                        regions_layer, self._dest,
                        QgsCoordinateTransformContext(), opts
                    )
                    reloaded = QgsVectorLayer(
                        f"{self._dest}|layername=regioni_densita_alberi",
                        "Regioni — densità alberi monumentali", "ogr"
                    )
                    if reloaded.isValid():
                        apply_choropleth_symbology(reloaded)
                        regions_layer = reloaded

        # Aggiunge il layer regioni sotto i punti (regioni sotto, punti sopra)
        if self.chk_add_map.isChecked() and regions_layer is not None:
            QgsProject.instance().addMapLayer(regions_layer, False)
            root.insertLayer(1, regions_layer)

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
