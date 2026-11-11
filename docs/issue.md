# Known Issues — LaserControlSuite

Registro delle problematiche note emerse durante la revisione del codice.
Ogni voce ha: severità, file coinvolto, descrizione, impatto e stato.

**Legenda severità**
- 🔴 **Grave** — produce G-code errato, corrompe dati, o rompe il flusso utente.
- 🟡 **Medio** — bug reale ma di impatto limitato, o comportamento discutibile.
- 🟢 **Minore / Miglioramento** — refactoring, performance, cosmetico.

**Stati**: `aperto`, `in-corso`, `risolto`, `wontfix`, `rimandato`.

---

## Indice rapido

| # | Severità | Area | Titolo | Stato |
|---|---|---|---|---|
| 1 | 🔴 | svg_importer | Archi: `seg.delta` in gradi trattato come radianti | risolto (9i-a) |
| 2 | 🔴 | svg_importer | Sotto-tracciati uniti da linea falsa | risolto (9i-a) |
| 3 | 🔴 | svg_importer | Path chiusi: handle del primo nodo perso | risolto (9i-a) |
| 4 | 🔴 | dxf_importer | INSERT trasformato due volte | risolto (9i-b) |
| 5 | 🔴 | dxf_importer | Spline grossolane su DXF non in mm | risolto (9i-b) |
| 6 | 🔴 | dxf_importer | Bulge mai emesso (archi → segmenti) | risolto (9i-b) |
| 7 | 🟡 | view | `fit_scene_in_view` ordine moltiplicazione | risolto (9i-c — falso positivo) |
| 8 | 🟡 | editor/view | Multi-selezione drag senza BatchTransformCommand | risolto (9i-c) |
| 9 | 🟡 | core/document | `remove_layer` permette eliminare l'ultimo layer | risolto (9c) |
| 10 | 🟡 | core/path_edit | `remove_node_at` su path chiuso a 3 nodi | risolto (9i-c) |
| 11 | 🟡 | core/path_edit | `set_node_smooth` tangente errata su nodi estremi | risolto (9i-c) |
| 12 | 🟢 | cad/io | Import/tracing bloccano il thread UI | aperto |
| 13 | 🟢 | core/entities | Layer color/visible/locked ignorati dall'UI | risolto (9c) |
| 14 | 🟢 | core/entities | `TextEntity.local_points` bbox approssimato | rimandato (post-9j) |
| 15 | 🟢 | cam/flatten | Cerchi a 64 segmenti: errore ~0.24 mm su r=200 | aperto |
| 16 | 🟢 | cad/snap | `snap()` scorre tutti gli item a ogni mousemove | aperto |
| 17 | 🟢 | cad/entity_item | `boundingRect`/`paint` ricostruiscono il path a ogni frame | aperto |
| 18 | 🟢 | core/entities | `_ARC_SEGMENTS`/`_SAMPLES` vanno `ClassVar` | risolto (9i-c) |
| 19 | 🟢 | core/commands | `core/commands.py` importa Qt | risolto (9j) |
| 20 | 🟢 | core/document | Uso di `document._emit` (privato) dall'esterno | risolto (9j) |
| 21 | 🟢 | core/entities | `StarEntity.points` (int) vs `PolylineEntity.points` (list) | rimandato (9j+) |
| 22 | 🟢 | ui | NodeEditTool converte a Path alla sola selezione | aperto |
| 23 | 🟢 | repository | `.gitignore` incompleto | risolto (9j) |
| 24 | 🟢 | tests | Test cache `.pytest_cache/lastfailed` obsoleto | risolto (9j) |
| 25 | 🟢 | tests | `qtbot.waitSignal`/`waitUntil` non affidabili su segnali cross-thread | aperto (pattern documentato) |
| 26 | 🟢 | comm/ui | `console_panel.py` spostato da `comm/` a `ui/panels/` | risolto (9b) |
| 27 | 🟢 | ui/panels | `cam_panel.py`: header tabella disallineati | risolto (9c) |
| 28 | 🟢 | resources | Cambio tema: QToolButton e testi non aggiornati | risolto (9d) |
| 29 | 🟡 | cad/node_overlay | Nodi/handle giganteschi a zoom > 100% | risolto (9i-d) |
| 30 | 🟡 | cad/view | Delete in modalità Nodi cancella l'entità intera | risolto (9i-d) |

---

## 🔴 Bug gravi

### 1. SVG — Archi con delta trattato come radianti
**File**: `src/lasercontrolsuite/cad/io/svg_importer.py`
**Problema**: `svgpathtools` restituisce `seg.delta` in **gradi**, ma il codice lo usa come radianti nel calcolo del numero di segmenti. Risultato: un quarto di cerchio produce ~1300 nodi invece di ~23.
**Impatto**: G-code enormemente gonfiato; possibile saturazione del buffer del controller.
**Fix applicato (Step 9i-a)**: campionamento basato su `seg.length()` (target 1 mm/segmento, min 8) — indipendente da `seg.delta`/`seg.theta` (semantica variabile tra versioni di `svgpathtools`). Vedi anche P28 nei pattern.
**Stato**: risolto — Step 9i-a

### 2. SVG — Sotto-tracciati uniti da linea falsa
**File**: `src/lasercontrolsuite/cad/io/svg_importer.py`
**Problema**: un `d` con più comandi `M` veniva trattato come un unico tracciato continuo, con una linea fantasma che collega la fine di un sotto-tracciato all'inizio del successivo.
**Impatto**: fori tagliati come linee → pezzo sbagliato.
**Fix applicato (Step 9i-a)**: split in N `PathEntity` su discontinuità `seg.start != prev_end`. Lettera "O" → 2 entità chiuse.
**Stato**: risolto — Step 9i-a

### 3. SVG — Handle del primo nodo perso sui path chiusi
**File**: `src/lasercontrolsuite/cad/io/svg_importer.py`
**Problema**: quando un tracciato torna al punto di partenza, l'ultimo nodo duplicato veniva rimosso con `nodes.pop()`, ma il suo `handle_in` **non veniva copiato** in `nodes[0].handle_in`.
**Fix applicato (Step 9i-a)**: prima di `nodes.pop()`, `nodes[0].handle_in = nodes[-1].handle_in`.
**Stato**: risolto — Step 9i-a

### 4. DXF — INSERT trasformato due volte
**File**: `src/lasercontrolsuite/cad/io/dxf_importer.py`
**Problema**: `virtual_entities()` di `ezdxf` restituisce già le entità trasformate secondo la matrice dell'INSERT. Il codice applicava poi di nuovo posizione, rotazione e scala del blocco.
**Fix applicato (Step 9i-b)**: rimosso `se.transform = mm_m @ se.transform` — `virtual_entities()` è già world-transformed.
**Stato**: risolto — Step 9i-b

### 5. DXF — Spline grossolane su DXF non in mm
**File**: `src/lasercontrolsuite/cad/io/dxf_importer.py`
**Problema**: `flattening(distance=0.05 * scale)` usava la moltiplicazione invece della divisione.
**Fix applicato (Step 9i-b)**: `flattening(distance=0.05 / scale)`.
**Stato**: risolto — Step 9i-b

### 6. DXF — Bulge mai emesso
**File**: `src/lasercontrolsuite/cad/io/dxf_importer.py`
**Problema**: `has_bulge` era sempre falso perché `get_points("xyb")` restituisce tuple `(x, y, bulge)` a 3 elementi e il codice controllava `len(p) > 4`.
**Fix applicato (Step 9i-b)**: check corretto `len(p) > 2`; bulge convertiti in archi Bézier.
**Nota test**: `add_lwpolyline` di `ezdxf` richiede `format="xyb"` (vedi P26).
**Stato**: risolto — Step 9i-b

---

## 🟡 Bug medi

### 7. `fit_scene_in_view` — Ordine di moltiplicazione **falso positivo**
**File**: `src/lasercontrolsuite/cad/view.py`
**Esito (Step 9i-c)**: verificato con `test_fit_to_work_area_angles_visible`. L'ordine di moltiplicazione in `_fit_rect` è corretto.
**Stato**: risolto — Step 9i-c (falso positivo dell'analisi statica, `view.py` invariato)

### 8. Multi-selezione drag senza comando di undo
**File**: `src/lasercontrolsuite/cad/entity_item.py` + `cad/commands.py`
**Problema**: trascinando un gruppo di entità, solo l'elemento sotto il mouse riceveva il rilascio.
**Fix applicato (Step 9i-c)**: `EntityItem.mousePressEvent` salva `_drag_pre_transforms` per tutti gli item selezionati. `mouseReleaseEvent` chiama `_finalize_drag()`, che emette un singolo `BatchTransformCommand`.
**Test**: `test_multi_selection_drag_is_single_undo`.
**Stato**: risolto — Step 9i-c

### 9. `Document.remove_layer` può lasciare documento senza layer attivo
**File**: `src/lasercontrolsuite/core/document.py`
**Stato**: risolto a livello UI — Step 9c.

### 10. `remove_node_at` su path chiuso con pochi nodi
**File**: `src/lasercontrolsuite/core/path_edit.py`
**Problema**: rimuovere un nodo da un tracciato chiuso da 3 nodi lasciava `closed=True` con 2 nodi, causando un taglio doppio nel G-code.
**Fix applicato (Step 9i-c)**: se dopo la rimozione `len(nodes) < 3`, forzare `closed = False`.
**Test**: `test_remove_node_closed_3_to_2_opens_path`, `test_remove_node_closed_4_to_3_stays_closed`.
**Stato**: risolto — Step 9i-c

### 11. `set_node_smooth` — tangente errata sui nodi estremi aperti
**File**: `src/lasercontrolsuite/core/path_edit.py`
**Problema**: per un nodo al bordo di un path aperto, il calcolo della tangente usava `(index - 1) % n`, che avvolgeva all'ultimo nodo.
**Fix applicato (Step 9i-c)**: tangente **one-sided** verso il vicino interno per `index == 0` e `index == n-1` su path aperti.
**Test**: `test_set_node_smooth_open_first_endpoint`, `test_set_node_smooth_open_last_endpoint`, `test_set_node_smooth_closed_endpoint_still_wraps`.
**Stato**: risolto — Step 9i-c

---

## 🟢 Miglioramenti

### 12. Import/tracing bloccano la UI
**File**: `ui/main_window.py`, `cad/io/*`
**Fix proposto**: `QThread` di lavoro con `progressChanged` e pulsante Annulla.
**Stato**: rimandato — post Step 9j

### 13. Layer — colore, visibilità, locked non usati dall'UI
**Stato**: risolto — Step 9c.

### 14. `TextEntity.local_points` bbox approssimato
**File**: `src/lasercontrolsuite/core/entities.py`
**Fix proposto**: usare `QPainterPath.addText` per estrarre i contorni reali dei glifi.
**Stato**: rimandato — post Step 9j (relativo al text-to-path; la bbox "vera" è un miglioramento estetico non bloccante)

### 15. Cerchi con 64 segmenti fissi
**File**: `src/lasercontrolsuite/core/entities.py` (`CircleEntity`)
**Fix proposto**: tolleranza adattiva basata sul raggio, o emissione di G2/G3 nativi in fase CAM.
**Stato**: aperto — miglioria futura

### 16. `snap()` scorre tutti gli item a ogni mousemove
**File**: `src/lasercontrolsuite/cad/snap.py`
**Fix proposto**: `scene.items(rect)` con intorno cursore, e/o indice spaziale degli endpoint.
**Stato**: rimandato — ottimizzazione dopo 9j

### 17. `boundingRect`/`paint` ricostruiscono il path a ogni frame
**File**: `src/lasercontrolsuite/cad/entity_item.py`
**Fix proposto**: cache del `QPainterPath` invalidata solo su `sync_from_entity()`.
**Stato**: rimandato — ottimizzazione dopo 9j

### 18. Costanti di classe vanno annotate `ClassVar`
**File**: `src/lasercontrolsuite/core/entities.py`
**Fix applicato (Step 9i-c)**: `from typing import ClassVar`, annotati `_ARC_SEGMENTS` (Circle, Ellipse) e `_SAMPLES` (Bezier).
**Test**: `test_circle_arc_segments_is_classvar`, `test_ellipse_arc_segments_is_classvar`, `test_bezier_samples_is_classvar`.
**Stato**: risolto — Step 9i-c

### 19. `core/commands.py` importa Qt
**File**: `src/lasercontrolsuite/cad/commands.py` (nuovo)
**Problema**: il core dichiarava di essere puro Python, ma `commands.py` importava `QUndoCommand` da PySide6.
**Fix applicato (Step 9j)**: spostato il file da `core/` a `cad/commands.py`. Aggiornati tutti gli import (`cad/entity_item.py`, `cad/editor.py`, `cad/tools.py`, `ui/panels/cam_panel.py`, `ui/panels/property_panel.py`, `tests/*`). Rinominato `tests/test_core_commands.py` in `tests/test_cad_commands.py`.
**Stato**: risolto — Step 9j

### 20. Uso di `document._emit` (privato) dall'esterno
**File**: `src/lasercontrolsuite/core/document.py` + chiamanti
**Problema**: diversi punti chiamavano `document._emit(...)` (metodo privato).
**Fix applicato (Step 9i-c e 9j)**: esposto `Document.notify(event)` pubblico come alias di `_emit`. Aggiornati `cad/commands.py`, `cad/tools.py`, `ui/panels/cam_panel.py` e `core/operations.py` (dove possibile).
**Stato**: risolto — Step 9j

### 21. `StarEntity.points` è un int, `PolylineEntity.points` è una lista
**File**: `src/lasercontrolsuite/core/entities.py`
**Decisione (Step 9i-c)**: **rimandato a Step 9j+** (opzione A confermata dall'utente).
**Motivo**: il rename `points → spikes` è breaking (tocca `__init__`, `__eq__`, `__repr__`, `ToolOptionsBar`, `StarTool`, `PropertyPanel`, `entity_to_path`, test). Da fare in un blocco dedicato.
**Nota in codice**: aggiunta docstring in `StarEntity` con rimando a questa issue.
**Stato**: rimandato — Step 9j+

### 22. NodeEditTool converte a Path alla sola selezione
**File**: `src/lasercontrolsuite/cad/tools.py`
**Problema**: appena si attiva lo strumento Nodi su un rettangolo, l'entità viene convertita in `PathEntity` con un `ReplaceEntityCommand`.
**Fix proposto**: convertire solo alla prima modifica effettiva; raggruppare le conversioni in un `beginMacro`.
**Stato**: aperto — UX post Step 9j

### 23. `.gitignore` incompleto
**File**: `.gitignore`
**Fix applicato (Step 9j)**: aggiunti `.venv/`, `.pytest_cache/`, `*.egg-info/`, `__pycache__/`, `.vscode/`, `.idea/`.
**Stato**: risolto — Step 9j

### 24. Test cache obsoleto
**File**: `.pytest_cache/v/cache/lastfailed`
**Fix applicato (Step 9j)**: cartella `.pytest_cache/` ripulita e aggiunta al `.gitignore`.
**Stato**: risolto — Step 9j

### 25. `qtbot.waitSignal`/`waitUntil` non affidabili su segnali cross-thread
**File**: `tests/test_ui_console_panel.py`
**Pattern documentato** (vedi P16): `_pump()` + loop esplicito con `processEvents(AllEvents)`.
**Stato**: aperto — pattern documentato, workaround in uso

### 26. `console_panel.py` spostato da `comm/` a `ui/panels/`
**Stato**: risolto — Step 9b

### 27. `cam_panel.py` — header tabella disallineati
**Stato**: risolto — Step 9c

### 28. Cambio tema: QToolButton e testi non aggiornati
**Stato**: risolto — Step 9d

### 29. Nodi/handle giganteschi a zoom > 100%
**File**: `src/lasercontrolsuite/cad/node_overlay.py`
**Problema (Step 9i-d)**: i marker dei nodi e degli handle apparivano come cerchi enormi a zoom 194%. Causa: `painter.transform().m11()` per un `QGraphicsItem` figlio non include in modo affidabile la trasformazione della view in tutte le versioni di Qt.
**Fix applicato (Step 9i-d)**: `paint()` legge la scala da `option.levelOfDetailFromTransform(painter.worldTransform())`, con fallback su `painter.transform().m11()`. Aggiunto helper `_paint_scale(painter, option)`.
**Impatto**: cosmetico ma grave per usabilità.
**Stato**: risolto — Step 9i-d

### 30. Delete in modalità Nodi cancella l'entità intera invece del solo nodo
**File**: `src/lasercontrolsuite/cad/view.py` + `src/lasercontrolsuite/cad/tools.py`
**Problema (Step 9i-d)**: in modalità Nodi (`N`), premendo `Canc` si cancellava l'**intera entità**. Causa: l'azione globale "Elimina" ha `StandardKey.Delete` con contesto `WindowShortcut`, che scatta prima del `keyPressEvent` della view.
**Fix applicato (Step 9i-d)**:
  - `NodeEditTool.has_selected_nodes()`: True se almeno un nodo è selezionato.
  - `CadGraphicsView.event()` override di `ShortcutOverride`: se tool = `"nodes"` e `has_selected_nodes()` e tasto = `Delete`/`Backspace`, l'evento viene accettato (la shortcut globale non scatta, il tasto arriva al tool).
**Impatto**: regressione funzionale in modalità Nodi.
**Stato**: risolto — Step 9i-d

---

## Note

- I punti 🔴 1-6 sono chiusi in Step 9i-a/b.
- I punti 🟡 7-11 sono chiusi in Step 9i-c (7 è falso positivo verificato).
- I punti 🟡 29-30 sono chiusi in Step 9i-d (segnalazione utente).
- I punti 🟢 19, 20, 23, 24 sono chiusi in Step 9j.
- **Bug 21 e 14**: rimandati (9j+). Il rename di `StarEntity.points` e la bbox reale di `TextEntity` sono miglioramenti non bloccanti per i moduli futuri.

## Pattern imparati (riferimento rapido)

Le seguenti lezioni non sono "issue" da chiudere ma **regole da rispettare** quando si scrive codice o test.

| # | Pattern | Regola |
|---|---|---|
| P1 | Qt row-vector | `A @ B` significa "prima B, poi A". Pan vuole traslazione **post-viewport**. |
| P2 | AABB trasformato | Trasformare i 4 angoli di un AABB non produce l'AABB della geometria ruotata. |
| P3 | Y-up vs Y-down | Scena Y-up (CNC), Qt rendering Y-down. Il flip + scala mm/px va in un'unica `QTransform`. |
| P4 | Testo in mm | Chiedere il DPI a Qt (`logicalDotsPerInch`), non assumere 96. |
| P5 | Campionamento | **Un solo** `local_points()` per entità, sempre. |
| P6 | Doppio click | Qt emette `MouseButtonDblClick` **al posto di** `MouseButtonPress`. |
| P7 | Pannelli Qt | `detach()` idempotente + `shiboken6.isValid()` + disconnessione in `closeEvent`. |
| P8 | Colori Qt | `#AARRGGBB` con 8 cifre: `#000000A0` è alpha 0x00, non RGB 0x0000A0. Usare colori opachi. |
| P9 | Fit iniziale | Il viewport è 0×0 al `showEvent`. Ritentare con `QTimer.singleShot` finché valido. |
| P10 | Ordine fit | `translate viewport → scale → translate scena`. Non invertire. |
| P11 | Editable mode | Verificare `pip show lasercontrolsuite` → `Editable project location`. |
| P12 | QSS completo | Il tema deve coprire `QDialog`, `QPushButton`, `QComboBox`, `QCheckBox`, `QGroupBox`, `QPlainTextEdit`, `QToolButton`, `QTableWidget`, `QMenu`, `QColorDialog`, `QToolBar > QToolButton`. |
| P13 | `shape()` sottile | Con penna cosmetica `QGraphicsPathItem.shape()` è troppo sottile. Override con `QPainterPathStroker`. |
| P14 | Esc sul dialog | `QDialog` chiude su Esc per default. Override di `keyPressEvent` per deselezionare **prima**. |
| P15 | Legenda/overlay | Disegnarli in `drawForeground` con `resetTransform` è fragile. Meglio come widget figlio del viewport. |
| P16 | Cross-thread in pytest-qt | Vedi issue #25. `qtbot.waitSignal`/`waitUntil` non bastano. Usare `_pump()` + loop esplicito con `processEvents(AllEvents)`. |
| P17 | Signal → tabelle | Non emettere `DocumentEvent` da un handler di `QTableWidget.itemChanged`. Usare `blockSignals(True)` + update mirati. |
| P18 | Layer priority | L'ordine di lavorazione è un attributo del layer (`priority`), non dell'ordine di inserimento. |
| P19 | Header di QTableWidget | `setHorizontalHeaderLabels` richiede **esattamente** N etichette. Un elemento vuoto "in più" sfalsa gli header. |
| P20 | Click-to-assign su tabelle | Click su riga = imposta layer attivo + assegna selezione in un unico `beginMacro`. |
| P21 | Cambio tema a runtime | `setStyleSheet()` da solo NON ricostruisce lo stile di tutti i widget. Serve `setPalette()` + repolish esplicito. |
| P22 | Proxy di tema | `THEME` è un proxy che legge il singleton. Chi cacha colori in `__init__` deve collegarsi a `themeChanged`. |
| P23 | Array polari | Esporre l'opzione "ruota le copie" vs "trasla lungo l'arco". |
| P24 | Ordine di selezione in QGraphicsScene | `selectedItems()` restituisce per stacking, non per ordine selezione. Per operazioni semantiche (es. difference), usare regola deterministica esplicita. |
| P25 | Booleane con `shapely` | Estrarre tutti i `Polygon` (esterno + fori come `PathEntity` separate). Warning per path aperti e entità non convertibili. |
| P26 | `add_lwpolyline` `ezdxf` | Serve `format="xyb"` per i bulge. Check `len(p) > 2`. |
| P27 | `closed` di POLYLINE DXF | È un flag esplicito, non derivabile dalla geometria. Fonte di verità per l'importatore. |
| P28 | Hermite→Bézier numerico | Per archi da `svgpathtools`: usare solo `seg.point(t)` + derivate per differenza finita. Mai `seg.theta`/`seg.delta`. |
| P29 | Fit circolare 3 punti | Formula chiusa deterministica più robusta del metodo di Kasa per archi esplosi. |
| P30 | Fit Bézier Schneider | Serve `is_smooth_for_bezier_fit` (max turn angle + ratio) per non fittare zig-zag. |
| P31 | Test "pochi nodi" | Quando un importatore produce N entità, verificare `len(nodes) <= K` (es. `<= 6`). |
| P32 | Dialog non modale `Qt.Tool` | Per tool interattivi (measure): no taskbar, `hide()` invece di `close()`, position-once. |
| P33 | Text-to-path nel core è impossibile | `QPainterPath.addText` è Qt → adapter in `cad/`. `entity_to_path` resta `None` per testi. |
| P34 | Shortcut di `QAction` vs `keyPressEvent` | Le shortcut `WindowShortcut` scattano **prima** del `keyPressEvent`. Intercettare `QEvent.Type.ShortcutOverride` per dare precedenza ai tool. |
| P35 | Marker a dimensione costante in pixel | Nei `QGraphicsItem` figli, `painter.transform().m11()` non è affidabile. Usare `option.levelOfDetailFromTransform(painter.worldTransform())`. Fallback su `painter.transform().m11()` solo se `option is None`. |

## Come usare questo file

- Quando si chiude un punto: cambiare `Stato` in `risolto` e aggiungere il riferimento allo Step.
- Quando si scopre un nuovo problema: aggiungere una riga in tabella e una sezione.
- Quando si scopre un **pattern** (lezione metodologica, non bug): aggiungerlo alla sezione "Pattern imparati".
- Ad ogni Step: scorrere l'indice e aggiornare gli stati dei punti toccati.