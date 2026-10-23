# LaserControlSuite

Suite CAD/CAM desktop multi-piattaforma per progettazione 2D, generazione G-Code
e controllo in tempo reale di laser basati su firmware GRBL (Atomstack, FluidNC, ecc.).

Target di funzionalità: competere con LightBurn.

## Requisiti
- Python 3.10+
- Windows / macOS / Linux

## Installazione (sviluppo)

```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
source .venv/bin/activate  # macOS / Linux
pip install -e ".[dev]"
```

> ⚠️ Verifica sempre che l'installazione sia in modalità **editable**:
> `pip show lasercontrolsuite` deve riportare `Editable project location: <path>`.
> Se è installato in modalità stabile, le modifiche a `src/` non hanno effetto.

## Extra: tracciamento immagini (opzionale)

```bash
pip install -e ".[trace]"
```

## Avvio

```bash
python -m lasercontrolsuite
```

## Test

```bash
pytest -v
```

## Architettura (sintesi)

- `src/lasercontrolsuite/core/` — modello dati puro Python (mm), nessuna dipendenza Qt.
  Include `boolean_ops.py` (unione/sottrazione/intersezione via `shapely`).
- `src/lasercontrolsuite/cad/` — adapter Qt per il canvas e gli strumenti di disegno.
- `src/lasercontrolsuite/cam/` — motore CAM puro Python (flatten, ordinamento, G-code).
- `src/lasercontrolsuite/comm/` — protocollo GRBL, controller `QThread`, porta seriale finta per i test.
- `src/lasercontrolsuite/ui/` — finestra principale, pannelli (`ui/panels/`), dialoghi, widget.
- `src/lasercontrolsuite/config/` — `Settings` (macchine) e `ConsoleSettings` (console).
- `src/lasercontrolsuite/resources/` — tema (`theme.py`), gestore tema (`theme_manager.py`), icone.

Regola: **il core parla solo mm**. Ogni conversione da altre unità (px Qt, unità DXF, unità SVG)
avviene nell'adapter al confine del sistema.

### Dipendenze principali

- **PySide6** — UI
- **pyserial** — comunicazione GRBL
- **ezdxf**, **svgpathtools** — import DXF/SVG
- **Pillow**, **numpy** — immagini
- **shapely** — operazioni booleane sui path

## Tema chiaro / scuro

`Vista → Tema → Scuro / Chiaro`. La preferenza è persistita in `QSettings` (chiave `ui/theme`).

Al cambio tema:
1. `ThemeManager.apply_to_app()` applica **QSS + QPalette + repolish** di tutti i widget.
2. I widget che cachano colori si aggiornano via `themeChanged`.
3. La tela LightBurn (area di lavoro bianca) è **diversa tra i temi**:
   tema scuro → sfondo tela `#585858`; tema chiaro → sfondo tela `#C8C8C8`.

## Modello multi-layer

Ogni layer è un'unità di lavorazione indipendente, come in LightBurn:

- **Attributi visivi**: `color` (`#RRGGBB`), `visible`, `locked`.
- **Parametri di taglio**: `speed_mm_min`, `power_percent`, `passes`, `air_assist`.
- **Priority**: numero crescente che determina l'ordine di lavorazione tra i layer.

I parametri globali (S max, modalità laser M3/M4, feed di rapido, ritorno a home,
commento di testa) sono proprietà della **macchina**.

## Pannello CAM multi-layer

- **Tabella layer** editabile in-place.
- **Azioni**: `+ Layer`, `− Rimuovi`, `↑` / `↓`, `→ Assegna selezione`.
- **Click su una riga**: imposta layer attivo e assegna le entità selezionate.
- **Doppio click sul colore** → `QColorDialog`.
- **Tasto destro** → menu contestuale.
- **Statistiche per layer**: percorso, lunghezza, tempo stimato, S e F.

## Operazioni di modifica

### Array lineare e circolare

`Azioni → Array…` apre un dialog con due schede:

- **Lineare**: righe, colonne, spaziatura X/Y.
- **Circolare**: centro, numero elementi, angolo totale/iniziale,
  opzione "Ruota le copie". Se angolo = 360°, l'ultima copia non si sovrappone.

### Operazioni booleane

`Azioni → Unione / Sottrai / Intersezione` (oppure dal menu). Servono **almeno 2 entità**.

- **Unione** — fonde i poligoni selezionati.
- **Sottrai** — l'entità con **area (bbox) maggiore** è il target; le altre vengono sottratte.
  (La regola è deterministica e non dipende dall'ordine di selezione Qt,
  che restituisce gli item in ordine inverso di aggiunta.)
- **Intersezione** — mantiene solo le aree comuni.

Il risultato con fori viene restituito come `PathEntity` separate: un anello esterno +
uno per ciascun foro. I path aperti vengono chiusi automaticamente (con warning).
Le entità non convertibili (es. testo) vengono ignorate (con warning).

## Scorciatoie

### Strumenti
- `V` — Seleziona
- `N` — Nodi
- `P` — Penna
- `L` / `Shift+L` — Linea / Polilinea
- `B` — Bézier
- `R` / `E` — Rettangolo / Ellisse
- `G` / `S` — Poligono / Stella
- `T` — Testo

### Import
- `Ctrl+I` — Importa DXF
- `Ctrl+Shift+I` — Importa SVG
- `File → Traccia immagine…` — Tracing raster

### CAM
- `Ctrl+G` — Genera G-code
- `CAM → Salva G-code come…`

### Controller
- `Ctrl+Shift+K` — Console GRBL
- `Controller → Impostazioni macchina…`
- `Controller → Home ($H)`, `Unlock ($X)`, `Status (?)`
- `Controller → Pausa (!)`, `Riprendi (~)`, `Soft Reset (Ctrl+X)`

### Vista e modifica
- Rotellina: zoom — tasto centrale: pan
- `Ctrl+Z` / `Ctrl+Shift+Z` — Annulla / Ripeti
- `Ctrl+Shift+P` — Converti in path
- Frecce / `Shift+frecce` — Nudge 1 mm / 0.1 mm
- `Ctrl+0` — Zoom 100%
- `F` / `Ctrl+Shift+F` — Adatta / Adatta all'area di lavoro

## Console GRBL

La console (`Controller → Console…` o `Ctrl+Shift+K`) è tabificata con il pannello CAM.

- Filtri di categoria (`ok` / `err` / `alarm` / `status` / `msg` / `tx`)
- Colorazione sintattica stile LightBurn
- Timestamp opzionale
- Auto-scroll con pausa automatica
- Cronologia comandi (`↑` / `↓`)
- Contatore buffer `Bf` live
- Salva log su file
- Contatori per categoria
- Macro personalizzate
- Ricerca con evidenziazione

## Stato del progetto

- [x] Step 1 — Struttura, packaging, smoke test
- [x] Step 2 — Canvas QGraphicsView con zoom/pan/griglia/snapping
- [x] Step 3 — Modello dati, trasformazioni, undo/redo, tool base
- [x] Step 4 — Toolbar verticale a icone + forme complete
- [x] Step 5 — Pannello proprietà, input numerico, edit operations
- [x] Step 5.5 — Pen tool + Node editor (curvatura segmenti)
- [x] Step 6 — Import DXF/SVG + Trace immagine
- [x] Step 7 — Motore CAM (generazione G-code, pannello CAM)
- [x] Step 8 — Comunicazione seriale GRBL (console, jog, streaming)
- [x] Step 9a — Anteprima grafica CAM + tela stile LightBurn + area di lavoro macchina
- [x] Step 9b — Console GRBL avanzata (filtri, colorazione, macro, buffer live)
- [x] Step 9c — Multi-layer CAM (parametri per layer, tabella editabile, layer visuali)
- [x] Step 9d — Tema chiaro alternativo (switch a runtime, QSS + QPalette + repolish)
- [x] Step 9e — Array circolare/polare
- [x] Step 9f — Operazioni booleane (unione/sottrazione/intersezione via shapely)
- [ ] Step 9g — Offset/contorno (inset/outset)
- [ ] Step 9h — Misura distanza/angolo + Text-to-path
- [ ] Step 9i — Fix importatori DXF/SVG (bug gravi + medi)
- [ ] Step 9j — Fix minori e pulizie architetturali

### Progetti futuri (post Step 9)

Pianificati, non ancora iniziati. La struttura `modules/` e il concetto di
"gruppo parametrico" nel core sono ancora da progettare.

- Generatore di scatole a incastro (kerf compensato, giunzioni a pettine/a T)
- Nesting 2D su fogli (MaxRects, rotazioni, spaziatura, quantità per pezzo)
- Living hinge (linee parallele / a mattone / onde)
- Editor immagini con dithering (Floyd–Steinberg, Jarvis, Atkinson) e regolazioni
- Wizard "foto → progetto" che orchestra i moduli esistenti
- Nesting avanzato (No-Fit Polygon con Shapely + pyclipper)
- Libreria materiali unica nel core (JSON) letta da tutti i moduli

## Documentazione aggiuntiva

- `docs/KNOWN_ISSUES.md` — registro bug, migliorie e pattern imparati.

## Bug noti

I principali bug funzionali ancora aperti (importatori DXF/SVG) sono tracciati in
`docs/KNOWN_ISSUES.md` §🔴. La loro correzione è pianificata nello Step 9i.

## Licenza

Proprietary.