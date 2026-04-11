# Alberi Monumentali Italia — Plugin QGIS

Plugin QGIS per scaricare e visualizzare gli **alberi monumentali d'Italia**
dal sito del Ministero dell'agricoltura, della sovranità alimentare e delle foreste (MASAF).

## Funzionalità

- Scarica i dati per **singola regione** o **tutta Italia** direttamente dal sito MASAF
- Aggiornamento automatico degli URL dalla pagina ufficiale
- Converte le coordinate **DMS → gradi decimali WGS84**
- Salva il risultato in **GeoPackage (.gpkg)** o **Shapefile (.shp)**
- Applica una **tematizzazione** graduata basata sulla circonferenza del fusto (5 classi di verde)
- Etichette con il nome volgare della specie (visibili a scale di dettaglio)

## Dipendenze

Il plugin usa esclusivamente pacchetti già inclusi in QGIS — non è necessario installare nulla di aggiuntivo.

| Pacchetto | Versione minima | Note |
|-----------|----------------|------|
| **QGIS** | 3.20 | compatibile con QGIS 4.x / PyQt6 |
| **pandas** | qualsiasi | incluso in QGIS |
| **xlrd** | 1.x | incluso in QGIS; necessario per leggere i file `.xls` MASAF |

> Se in un'installazione personalizzata di QGIS `xlrd` risultasse mancante,
> installarlo con il gestore pacchetti integrato o con:
> ```
> pip install xlrd
> ```

## Installazione

1. Scarica il file [`ami_masaf.zip`](https://github.com/pigreco/ami_masaf/releases/latest)
2. In QGIS: **Plugin → Gestisci e installa plugin → Installa da ZIP**
3. Seleziona il file ZIP e clicca **Installa plugin**

## Utilizzo

1. Apri il plugin dal menu **Web → Alberi Monumentali** o dalla toolbar
2. Seleziona le regioni desiderate (Ctrl+click per selezione multipla) o clicca **Tutta Italia**
3. Scegli il formato di output (GeoPackage consigliato)
4. Seleziona la destinazione
5. Clicca **Scarica e converti**

## Struttura dei campi

| Campo (SHP)   | Campo (GPKG)            | Descrizione                          |
|---------------|-------------------------|--------------------------------------|
| PROGR         | PROGR                   | Numero progressivo                   |
| REGIONE       | REGIONE                 | Regione                              |
| ID_SCHEDA     | ID_SCHEDA               | Codice scheda MASAF                  |
| PROVINCIA     | PROVINCIA               | Provincia                            |
| COMUNE        | COMUNE                  | Comune                               |
| LOCALITA      | LOCALITA                | Località                             |
| LAT_DMS       | LAT_DMS                 | Latitudine in formato DMS originale  |
| LON_DMS       | LON_DMS                 | Longitudine in formato DMS originale |
| ALTIT_M       | ALTITUDINE_M            | Altitudine (m s.l.m.)               |
| CONT_URB      | CONTESTO_URBANO         | Contesto urbano                      |
| SP_SCI        | SPECIE_SCIENTIFICO      | Specie nome scientifico              |
| SP_VOLG       | SPECIE_VOLGARE          | Specie nome volgare                  |
| CIRCF_CM      | CIRCONFERENZA_FUSTO_CM  | Circonferenza fusto (cm)             |
| ALT_M         | ALTEZZA_M               | Altezza (m)                          |
| CRITERI       | CRITERI_MONUMENTALITA   | Criteri di monumentalità             |
| PROP_DICH     | PROPOSTA_DICHIARAZIONE  | Proposta dichiarazione interesse     |
| LAT_DD        | LATITUDINE_DD           | Latitudine gradi decimali (calcolata)|
| LON_DD        | LONGITUDINE_DD          | Longitudine gradi decimali (calcolata)|

## Dati

I dati provengono dall'elenco ufficiale degli alberi monumentali d'Italia
pubblicato dal MASAF ai sensi della Legge n. 10/2013.

**Licenza dati**: Creative Commons Attribution CC BY 4.0

**Fonte**: https://www.masaf.gov.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/11260

## Note tecniche

- Sistema di riferimento: **WGS84 (EPSG:4326)**
- Le coordinate vengono validate (bbox Italia: lat 36–48, lon 6–19)
- Gli alberi senza coordinate valide vengono saltati e conteggiati nel report finale
