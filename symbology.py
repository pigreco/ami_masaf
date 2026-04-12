# -*- coding: utf-8 -*-
"""
Modulo per la tematizzazione del layer degli alberi monumentali.

Strategia visiva multi-scala:
- Zoom out (denominatore ≥ 200.000): coroplete regionale — intensità ∝ numero alberi.
- Zoom in (denominatore < 200.000): punti individuali con renderer graduated per
  circonferenza del fusto.
- Etichette con nome volgare della specie, visibili a scale medie/grandi.
"""

import os
import unicodedata

from qgis.core import (
    QgsSymbol,
    QgsMarkerSymbol,
    QgsSimpleMarkerSymbolLayer,
    QgsSimpleMarkerSymbolLayerBase,
    QgsProperty,
    QgsGraduatedSymbolRenderer,
    QgsRendererRange,
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling,
    QgsTextFormat,
    QgsTextBufferSettings,
    QgsFillSymbol,
    QgsSimpleFillSymbolLayer,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    Qgis,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont


# ── Coroplete regionale ────────────────────────────────────────────────────────
# Palette 5 verdi per densità alberi (pochi → molti)
CHOROPLETH_PALETTE = [
    "#D4EDDA",  # verde chiarissimo
    "#A8D5A2",  # verde chiaro
    "#6BBF5E",  # verde medio
    "#3A7D44",  # verde foresta
    "#0D3311",  # verde scuro / abete
]

# Scala-soglia: il coroplete è visibile solo con denominatore ≥ questa soglia
CHOROPLETH_MAX_SCALE = 200_000

# ── Punti individuali ──────────────────────────────────────────────────────────
# Palette di 5 verdi naturali (dal chiaro al scuro)
GREEN_PALETTE = [
    "#A8D5A2",  # verde chiaro / menta
    "#6BBF5E",  # verde medio
    "#3A7D44",  # verde foresta
    "#1B5E20",  # verde bosco
    "#0D3311",  # verde scuro / abete
]

# Colori bordo abbinati
BORDER_PALETTE = [
    "#6BBF5E",
    "#3A7D44",
    "#1B5E20",
    "#0D3311",
    "#050F09",
]

# Dimensioni in pixel per le 5 classi (da piccola a grande)
SIZE_PALETTE = [4.0, 6.0, 8.0, 11.0, 15.0]

# Etichette classi
CLASS_LABELS = [
    "Piccolo (< 200 cm circ.)",
    "Medio (200–400 cm circ.)",
    "Grande (400–600 cm circ.)",
    "Molto grande (600–900 cm circ.)",
    "Monumentale (> 900 cm circ.)",
]

# Soglie classificazione manuale circonferenza [cm]
CLASS_BREAKS = [0, 200, 400, 600, 900, 99999]


def _make_marker(color_hex, border_hex, size_pt):
    """Crea un simbolo marker circolare con le proprietà fornite."""
    symbol = QgsMarkerSymbol()
    # Rimuove eventuali layer di default
    while symbol.symbolLayerCount() > 0:
        symbol.deleteSymbolLayer(0)

    sl = QgsSimpleMarkerSymbolLayer(
        QgsSimpleMarkerSymbolLayerBase.Shape.Circle,
        size_pt,
        0.0,  # angolo
    )
    sl.setColor(QColor(color_hex))
    sl.setStrokeColor(QColor(border_hex))
    sl.setStrokeWidth(0.4)

    # Imposta unità come punti (Points) per coerenza visiva
    sl.setSizeUnit(Qgis.RenderUnit.Points)

    symbol.appendSymbolLayer(sl)
    return symbol


def _find_field(layer, candidates):
    """Trova il primo campo disponibile tra i candidati (case-insensitive)."""
    field_names = {f.name().upper(): f.name() for f in layer.fields()}
    for c in candidates:
        if c.upper() in field_names:
            return field_names[c.upper()]
    return None


def apply_graduated_symbology(layer):
    """
    Applica un renderer graduated basato sulla circonferenza del fusto.

    Se il campo circonferenza non è presente, usa un renderer singolo verde.

    Args:
        layer: QgsVectorLayer
    """
    circ_field = _find_field(
        layer,
        ["CIRCF_CM", "CIRCONFERENZA_FUSTO_CM", "CIRCCONF", "CIRCONF"]
    )

    if circ_field:
        _apply_graduated(layer, circ_field)
    else:
        _apply_single(layer)

    _apply_labels(layer)
    layer.triggerRepaint()


def _apply_graduated(layer, field_name):
    """Renderer graduated manuale a 5 classi."""
    ranges = []
    for i in range(5):
        lower = CLASS_BREAKS[i]
        upper = CLASS_BREAKS[i + 1]
        symbol = _make_marker(GREEN_PALETTE[i], BORDER_PALETTE[i], SIZE_PALETTE[i])
        label = CLASS_LABELS[i]
        rng = QgsRendererRange(lower, upper, symbol, label)
        ranges.append(rng)

    renderer = QgsGraduatedSymbolRenderer(field_name, ranges)
    renderer.setMode(QgsGraduatedSymbolRenderer.Mode.Custom)
    layer.setRenderer(renderer)


def _apply_single(layer):
    """Renderer a simbolo singolo (fallback se manca il campo circonferenza)."""
    symbol = _make_marker("#3A7D44", "#1B5E20", 6.0)
    from qgis.core import QgsSingleSymbolRenderer
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def _apply_labels(layer):
    """
    Configura le etichette con il nome volgare della specie.
    Visibili dalla scala 1:50.000 in su (zoom ravvicinato).
    """
    sp_field = _find_field(
        layer,
        ["SP_VOLG", "SPECIE_VOLGARE", "SPECIE_NOME_VOLGARE"]
    )
    if not sp_field:
        return

    settings = QgsPalLayerSettings()
    settings.fieldName = sp_field
    settings.enabled = True

    # Formato testo
    txt_fmt = QgsTextFormat()
    font = QFont("Arial", 7)
    font.setItalic(True)
    txt_fmt.setFont(font)
    txt_fmt.setSize(7)
    txt_fmt.setColor(QColor("#1B5E20"))

    # Buffer bianco leggero per leggibilità
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.5)
    buf.setColor(QColor(255, 255, 255, 200))
    txt_fmt.setBuffer(buf)

    settings.setFormat(txt_fmt)

    # Mostra etichette solo a scale di dettaglio
    settings.scaleVisibility = True
    settings.minimumScale = 50000   # denominatore massimo (= zoom minimo)
    settings.maximumScale = 1       # zoom massimo

    # Posizionamento sopra il punto
    settings.placement = QgsPalLayerSettings.Placement.OverPoint
    settings.quadOffset = QgsPalLayerSettings.QuadrantPosition.QuadrantAbove

    labeling = QgsVectorLayerSimpleLabeling(settings)
    layer.setLabeling(labeling)
    layer.setLabelsEnabled(True)


# ── Coroplete regionale ────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Minuscolo + strip + rimuove segni diacritici per confronto robusto."""
    s = s.strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _apply_choropleth(layer, field_name: str) -> None:
    """Renderer graduated a 5 classi equal-interval sul campo numerico indicato."""
    values = [
        f[field_name] for f in layer.getFeatures()
        if f[field_name] is not None
    ]
    if not values:
        return

    max_val = max(values) or 1
    step = max_val / 5

    ranges = []
    for i in range(5):
        lower = i * step
        upper = (i + 1) * step
        label = f"{lower:.2f}–{upper:.2f} alberi/km²"

        symbol = QgsFillSymbol()
        while symbol.symbolLayerCount() > 0:
            symbol.deleteSymbolLayer(0)
        sl = QgsSimpleFillSymbolLayer()
        sl.setFillColor(QColor(CHOROPLETH_PALETTE[i]))
        sl.setStrokeColor(QColor("#ffffff"))
        sl.setStrokeWidth(0.4)
        symbol.appendSymbolLayer(sl)

        ranges.append(QgsRendererRange(lower, upper, symbol, label))

    renderer = QgsGraduatedSymbolRenderer(field_name, ranges)
    renderer.setMode(QgsGraduatedSymbolRenderer.Mode.Custom)
    layer.setRenderer(renderer)


def apply_choropleth_regions(trees_layer, plugin_dir: str):
    """
    Crea un memory layer poligonale delle regioni italiane tematizzato per
    numero di alberi monumentali.  Visibile solo in visione panoramica
    (denominatore mappa ≥ CHOROPLETH_MAX_SCALE).

    Args:
        trees_layer: QgsVectorLayer dei punti alberi
        plugin_dir:  directory del plugin (contiene regioni_istat_2025.gpkg)

    Returns:
        QgsVectorLayer (memory) oppure None se GPKG non trovato/non valido
    """
    gpkg_path = os.path.join(plugin_dir, "regioni_istat_2025.gpkg")
    if not os.path.isfile(gpkg_path):
        return None

    # 1. Conta alberi per regione (confronto normalizzato)
    regione_field = _find_field(trees_layer, ["REGIONE"])
    if not regione_field:
        return None

    counts: dict[str, int] = {}
    for feat in trees_layer.getFeatures():
        val = feat[regione_field]
        if val:
            key = _normalize(str(val))
            counts[key] = counts.get(key, 0) + 1

    # 2. Carica layer sorgente
    src = QgsVectorLayer(
        f"{gpkg_path}|layername=regioni",
        "regioni_src", "ogr"
    )
    if not src.isValid():
        return None

    # 3. Memory layer con geometrie + n_alberi
    mem = QgsVectorLayer(
        "MultiPolygon?crs=EPSG:4326",
        "Regioni — densità alberi monumentali",
        "memory"
    )
    pr = mem.dataProvider()
    pr.addAttributes(src.fields().toList() + [
        QgsField("n_alberi", QVariant.Int),
        QgsField("densita",  QVariant.Double),   # alberi per km²
    ])
    mem.updateFields()

    feats_out = []
    for feat in src.getFeatures():
        den_reg = feat["den_reg"]
        count = counts.get(_normalize(str(den_reg or "")), 0)
        area_km2 = (feat["shape_area"] or 0) / 1_000_000
        densita = round(count / area_km2, 4) if area_km2 > 0 else 0.0
        out = QgsFeature(mem.fields())
        out.setGeometry(feat.geometry())
        out.setAttributes(feat.attributes() + [count, densita])
        feats_out.append(out)

    pr.addFeatures(feats_out)
    mem.updateExtents()

    # 4. Tematizzazione coroplete
    apply_choropleth_symbology(mem)

    return mem


def apply_choropleth_symbology(layer) -> None:
    """
    Applica tematizzazione coroplete e visibilità scala a un layer regioni.
    Usata sia sul memory layer che sul layer ricaricato dal GPKG.
    """
    _apply_choropleth(layer, "densita")
    layer.setScaleBasedVisibility(True)
    layer.setMaximumScale(CHOROPLETH_MAX_SCALE)
    layer.triggerRepaint()
