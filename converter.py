# -*- coding: utf-8 -*-
"""
Modulo per la conversione delle coordinate DMS→DD e la creazione
del layer vettoriale (Shapefile o GeoPackage) con i dati degli alberi monumentali.

Strategia:
  1. Costruisce un layer in memoria (provider "memory")
  2. Aggiunge tutti i feature
  3. Salva su disco con QgsVectorFileWriter.writeAsVectorFormatV3
"""

import re
import os
import pandas as pd

from qgis.core import (
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
)

# ---------------------------------------------------------------------------
# Mappatura standard→nome campo output
# Chiavi = nomi "standard" usati internamente per trovare le colonne nel DF
# Valori = (nome_campo_output, tipo)  dove tipo è "int" | "double" | "str"
# Uso di stringhe Python invece di QVariant (rimosso in PyQt6 / QGIS 4)
# ---------------------------------------------------------------------------

# Shapefile: max 10 caratteri per nome campo
FIELD_MAP_SHP = {
    "PROGR":                 ("PROGR",      "int"),
    "REGIONE":               ("REGIONE",    "str"),
    "ID SCHEDA":             ("ID_SCHEDA",  "str"),
    "PROVINCIA":             ("PROVINCIA",  "str"),
    "COMUNE":                ("COMUNE",     "str"),
    "LOCALITA":              ("LOCALITA",   "str"),
    "LAT_DMS":               ("LAT_DMS",    "str"),
    "LON_DMS":               ("LON_DMS",    "str"),
    "ALTITUDINE":            ("ALTIT_M",    "double"),
    "CONTESTO URBANO":       ("CONT_URB",   "str"),
    "SPECIE SCIENTIFICO":    ("SP_SCI",     "str"),
    "SPECIE VOLGARE":        ("SP_VOLG",    "str"),
    "CIRCONFERENZA":         ("CIRCF_CM",   "double"),
    "ALTEZZA":               ("ALT_M",      "double"),
    "CRITERI":               ("CRITERI",    "str"),
    "PROPOSTA":              ("PROP_DICH",  "str"),
    "LAT_DD":                ("LAT_DD",     "double"),
    "LON_DD":                ("LON_DD",     "double"),
}

# GeoPackage: nomi completi senza limiti
FIELD_MAP_GPKG = {
    "PROGR":                 ("PROGR",                  "int"),
    "REGIONE":               ("REGIONE",                "str"),
    "ID SCHEDA":             ("ID_SCHEDA",              "str"),
    "PROVINCIA":             ("PROVINCIA",              "str"),
    "COMUNE":                ("COMUNE",                 "str"),
    "LOCALITA":              ("LOCALITA",               "str"),
    "LAT_DMS":               ("LAT_DMS",                "str"),
    "LON_DMS":               ("LON_DMS",                "str"),
    "ALTITUDINE":            ("ALTITUDINE_M",           "double"),
    "CONTESTO URBANO":       ("CONTESTO_URBANO",        "str"),
    "SPECIE SCIENTIFICO":    ("SPECIE_SCIENTIFICO",     "str"),
    "SPECIE VOLGARE":        ("SPECIE_VOLGARE",         "str"),
    "CIRCONFERENZA":         ("CIRCONFERENZA_FUSTO_CM", "double"),
    "ALTEZZA":               ("ALTEZZA_M",              "double"),
    "CRITERI":               ("CRITERI_MONUMENTALITA",  "str"),
    "PROPOSTA":              ("PROPOSTA_DICHIARAZIONE", "str"),
    "LAT_DD":                ("LATITUDINE_DD",          "double"),
    "LON_DD":                ("LONGITUDINE_DD",          "double"),
}

# Ricerca flessibile: standard_key → lista di pattern normalizzati nel DF
COLUMN_SEARCH = {
    "PROGR":              ["progr"],
    "REGIONE":            ["regione"],
    "ID SCHEDA":          ["idscheda"],
    "PROVINCIA":          ["provincia"],
    "COMUNE":             ["comune"],
    "LOCALITA":           ["localita", "localita"],
    # "LATITUDINE SU GIS" (IX agg.) / "LATITUDINE GIS" (versioni precedenti)
    "LAT_DMS":            ["latitudinesugis", "latitudinegis", "latitudine"],
    # "LONGITUDINE SU GIS" / "LONGITUDINE GIS"
    "LON_DMS":            ["longitudinesugis", "longitudinegis", "longitudine"],
    # "ALTITUDINE (m s.l.m.)"
    "ALTITUDINE":         ["altitudine"],
    "CONTESTO URBANO":    ["contestourbano", "contesto"],
    # "SPECIE NOME SCIENTIFICO"
    "SPECIE SCIENTIFICO": ["specienomescientifico", "nomescientifico", "specie"],
    # "SPECIE NOME VOLGARE"
    "SPECIE VOLGARE":     ["specienomevolgare", "nomevolgare"],
    # "CIRCONFERENZA FUSTO (cm)"
    "CIRCONFERENZA":      ["circonferenzafusto", "circonferenza"],
    # "ALTEZZA (m)"
    "ALTEZZA":            ["altezzam", "altezza"],
    # "CRITERI DI MONUMENTALITÀ"
    "CRITERI":            ["criterimonumentalita", "criteriDi", "criteri"],
    # "PROPOSTA DICHIARAZIONE NOTEVOLE INTERESSE PUBBLICO"
    "PROPOSTA":           ["propostadichiarazione", "proposta"],
}


def _norm(s):
    """Normalizza stringa: minuscolo, solo alfanumerici."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def find_columns(df):
    """
    Mappa standard_key → nome colonna reale nel DataFrame.

    Strategia a due passaggi:
    1. Corrispondenza esatta sul nome normalizzato
    2. Fallback: il nome normalizzato inizia con il pattern (es. "latitudinegis84" → pattern "latitudinegis")
    """
    df_lookup = {_norm(c): c for c in df.columns}
    col_map = {}
    for std_key, patterns in COLUMN_SEARCH.items():
        # 1. match esatto
        for p in patterns:
            if p in df_lookup:
                col_map[std_key] = df_lookup[p]
                break
        if std_key in col_map:
            continue
        # 2. match per prefisso
        for p in patterns:
            for norm_col, orig_col in df_lookup.items():
                if norm_col.startswith(p):
                    col_map[std_key] = orig_col
                    break
            if std_key in col_map:
                break
    return col_map


def dms_to_dd(dms_str):
    """
    Converte stringa DMS → gradi decimali.
    Gestisce separatore decimale italiano (virgola) e vari caratteri di gradi/minuti/secondi.

    Esempi input validi:
        37° 17' 22,25''
        13° 35' 35.7''
        37°17'22''
    """
    if not dms_str:
        return None
    s = str(dms_str).strip()
    if s in ("", "nan", "None", "-"):
        return None

    # Pattern robusto: tolera spazi variabili e diversi simboli
    m = re.match(
        r"(\d+)\s*[°º˚]\s*(\d+)\s*[''`\u2019]\s*([\d,\.]+)\s*[''\"″\u2019\u201d]{0,2}",
        s
    )
    if not m:
        # Fallback: solo gradi e minuti senza secondi (es. "37°17'")
        m2 = re.match(r"(\d+)\s*[°º˚]\s*(\d+)\s*[''`\u2019]?", s)
        if m2:
            return float(m2.group(1)) + float(m2.group(2)) / 60.0
        return None

    deg = float(m.group(1))
    minutes = float(m.group(2))
    seconds = float(m.group(3).replace(",", "."))
    return round(deg + minutes / 60.0 + seconds / 3600.0, 8)


def safe_float(val):
    if val is None:
        return None
    s = str(val).strip()
    if s in ("", "nan", "None", "-"):
        return None
    try:
        return float(s.replace(",", "."))
    except (ValueError, TypeError):
        return None


def safe_int(val):
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return None


def safe_str(val):
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s in ("nan", "None") else s


def read_xls(filepath):
    """Legge un file .xls del MASAF e restituisce un DataFrame."""
    try:
        import xlrd  # noqa: F401
    except ImportError:
        raise ValueError(
            "Pacchetto 'xlrd' non trovato.\n"
            "Installalo con:  pip install xlrd\n"
            "dalla OSGeo4W Shell, poi riavvia QGIS."
        )
    try:
        return pd.read_excel(filepath, engine="xlrd", header=0)
    except Exception as e:
        raise ValueError(f"Impossibile leggere il file XLS: {e}")


def _build_memory_layer(df_list, fmt, layer_name):
    """
    Costruisce un QgsVectorLayer in memoria con tutti i dati.

    Returns:
        (layer, n_written, n_skipped)
    """
    fmap = FIELD_MAP_SHP if fmt == "SHP" else FIELD_MAP_GPKG

    # Costruisce URI del layer in memoria con i campi
    # Formato: "Point?crs=EPSG:4326&field=nome:tipo&..."
    fields_parts = ["crs=EPSG:4326", "index=yes"]
    for std_key, (fname, ftype) in fmap.items():
        if ftype == "int":
            fields_parts.append(f"field={fname}:integer")
        elif ftype == "double":
            fields_parts.append(f"field={fname}:double")
        else:
            fields_parts.append(f"field={fname}:string(254)")

    uri = "Point?" + "&".join(fields_parts)
    layer = QgsVectorLayer(uri, layer_name, "memory")

    if not layer.isValid():
        raise RuntimeError("Impossibile creare il layer in memoria.")

    provider = layer.dataProvider()
    layer.startEditing()

    n_written = 0
    n_skipped = 0

    for region_name, df in df_list:
        col_map = find_columns(df)

        # Colonne coordinate nel DF
        lat_col = col_map.get("LAT_DMS")
        lon_col = col_map.get("LON_DMS")

        if lat_col is None or lon_col is None:
            cols = ", ".join(str(c) for c in df.columns.tolist())
            mancanti = []
            if lat_col is None:
                mancanti.append("latitudine")
            if lon_col is None:
                mancanti.append("longitudine")
            raise ValueError(
                f"Colonne {' e '.join(mancanti)} non trovate nel file di {region_name}.\n"
                f"Colonne presenti nel file:\n{cols}"
            )

        for _, row in df.iterrows():
            # Coordinate
            lat_raw = str(row[lat_col]).strip() if lat_col and lat_col in row.index else ""
            lon_raw = str(row[lon_col]).strip() if lon_col and lon_col in row.index else ""

            lat_dd = dms_to_dd(lat_raw)
            lon_dd = dms_to_dd(lon_raw)

            if lat_dd is None or lon_dd is None:
                n_skipped += 1
                continue

            # Bbox Italia (incluse isole remote)
            if not (35.0 <= lat_dd <= 48.0 and 6.0 <= lon_dd <= 19.0):
                n_skipped += 1
                continue

            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon_dd, lat_dd)))

            attrs = []
            for std_key, (fname, ftype) in fmap.items():
                # Campi calcolati
                if std_key == "LAT_DD":
                    attrs.append(lat_dd)
                    continue
                if std_key == "LON_DD":
                    attrs.append(lon_dd)
                    continue
                # Campi coordinate DMS originali
                if std_key == "LAT_DMS":
                    attrs.append(lat_raw)
                    continue
                if std_key == "LON_DMS":
                    attrs.append(lon_raw)
                    continue

                col = col_map.get(std_key)
                val = row[col] if col and col in row.index else None

                if ftype == "int":
                    attrs.append(safe_int(val))
                elif ftype == "double":
                    attrs.append(safe_float(val))
                else:
                    attrs.append(safe_str(val))

            feat.setAttributes(attrs)
            layer.addFeature(feat)
            n_written += 1

    layer.commitChanges()
    layer.updateExtents()
    return layer, n_written, n_skipped


def dataframes_to_layer(df_list, output_path, fmt, layer_name="Alberi Monumentali"):
    """
    Converte i DataFrame in un layer vettoriale su disco (SHP o GPKG).

    Args:
        df_list:     lista di (regione, DataFrame)
        output_path: cartella (SHP) o percorso file .gpkg (GPKG)
        fmt:         'SHP' o 'GPKG'
        layer_name:  nome del layer

    Returns:
        (QgsVectorLayer caricato da disco, n_written, n_skipped)
    """
    # 1. Costruisce layer in memoria
    mem_layer, n_written, n_skipped = _build_memory_layer(df_list, fmt, layer_name)

    if n_written == 0:
        raise ValueError(
            "Nessun albero con coordinate valide trovato.\n"
            "Controlla che il file XLS contenga colonne di latitudine/longitudine."
        )

    # 2. Opzioni di salvataggio
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile

    if fmt == "SHP":
        out_file = os.path.join(output_path, f"{layer_name.replace(' ', '_')}.shp")
        options.driverName = "ESRI Shapefile"
    else:
        out_file = output_path
        options.driverName = "GPKG"
        options.layerName = layer_name

    # 3. Salva su disco
    transform_ctx = QgsProject.instance().transformContext()

    error, err_msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        mem_layer,
        out_file,
        transform_ctx,
        options,
    )

    if error != QgsVectorFileWriter.WriterError.NoError:
        raise IOError(f"Errore scrittura file ({error}): {err_msg}")

    # 4. Carica il layer da disco
    if fmt == "SHP":
        out_layer = QgsVectorLayer(out_file, layer_name, "ogr")
    else:
        out_layer = QgsVectorLayer(f"{out_file}|layername={layer_name}", layer_name, "ogr")

    return out_layer, n_written, n_skipped
