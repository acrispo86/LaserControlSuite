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
| 1 | 🔴 | svg_importer | Archi: `seg.delta` in gradi trattato come radianti | aperto |
| 2 | 🔴 | svg_importer | Sotto-tracciati uniti da linea falsa | aperto |
| 3 | 🔴 | svg_importer | Path chiusi: handle del primo nodo perso | aperto |
| 4 | 🔴 | dxf_importer | INSERT trasformato due volte | aperto |
| 5 | 🔴 | dxf_importer | Spline grossolane su DXF non in mm | aperto |
| 6 | 🔴 | dxf_importer | Bulge mai emesso (archi → segmenti) | aperto |
| 7 | 🟡 | view | `fit_scene_in_view` ordine moltiplicazione | da verificare |
| 8 | 🟡 | editor/view | Multi-selezione drag senza BatchTransformCommand | aperto |
| 9 | 🟡 | core/document | `remove_layer` permette eliminare l'ultimo layer | risolto (9c) |
| 10 | 🟡 | core/path_edit | `remove_node_at` su path chiuso a 3 nodi | aperto |
| 11 | 🟡 | core/path_edit | `set_node_smooth` tangente errata su nodi estremi | aperto |
| 12 | 🟢 | cad/io | Import/tracing bloccano il thread UI | aperto |
| 13 | 🟢 | core/entities | Layer color/visible/locked ignorati dall'UI | risolto (9c) |
| 14 | 🟢 | core/entities | `TextEntity.local_points` bbox approssimato | aperto |
| 15 | 🟢 | cam/flatten | Cerchi a 64 segmenti: errore ~0.24 mm su r=200 | aperto |
| 16 | 🟢 | cad/snap | `snap()` scorre tutti gli item a ogni mousemove | aperto |
| 17 | 🟢 | cad/entity_item | `boundingRect`/`paint` ricostruiscono il path a ogni frame | aperto |
| 18 | 🟢 | core/entities | `_ARC_SEGMENTS`/`_SAMPLES` vanno `ClassVar` | aperto |
| 19 | 🟢 | core/commands | `core/commands.py` importa Qt | aperto |
| 20 | 🟢 | core/document | Uso di `document._emit` (privato) dall'esterno | aperto |
| 21 | 🟢 | core/entities | `StarEntity.points` (int) vs `PolylineEntity.points` (list) | aperto |
| 22 | 🟢 | ui | NodeEditTool converte a Path alla sola selezione | aperto |
| 23 | 🟢 | repository | `.gitignore` incompleto | aperto |
| 24 | 🟢 | tests | Test cache `.pytest_cache/lastfailed` obsoleto | aperto |
| 25 | 🟢 | tests | `qtbot.waitSignal`/`waitUntil` non affidabili su segnali cross-thread | aperto |
| 26 | 🟢 | comm/ui | `console_panel.py` spostato da `comm/` a `ui/panels/` | risolto (9b) |
| 27 | 🟢 | ui/panels | `cam_panel.py`: header tabella disallineati | risolto (9c) |
| 28 | 🟢 | resources | Cambio tema: QToolButton e testi non aggiornati | risolto (9d) |

---

## 🔴 Bug gravi

### 1. SVG — Archi con delta trattato come radianti
**File**: `src/lasercontrolsuite/cad/io/svg_importer.py`
**Problema**: `svgpathtools` restituisce `seg.delta` in **gradi**, ma il codice lo usa come radianti nel calcolo del numero di segmenti. Risultato: un quarto di cerchio produce ~1300 nodi invece di ~23.
**Impatto**: G-code enormemente gonfiato; possibile saturazione del buffer del controller, rallentamento, e in alcuni casi allarmi di overflow.
**Fix proposto**: convertire `delta` in radianti con `math.radians()` prima di calcolare il numero di campioni. Aggiungere test con cerchio SVG e confrontare il conteggio nodi atteso (≈ 16-24 per quarto di cerchio).
**Stato**: aperto — Step 9i

### 2. SVG — Sotto-tracciati uniti da linea falsa
**File**: `src/lasercontrolsuite/cad/io/svg_importer.py`
**Problema**: un `d` con più comandi `M` (tipico di lettere con fori: O, A, B, P, R, 0-9) viene trattato come un unico tracciato continuo. Viene disegnata una linea fantasma che collega la fine di un sotto-tracciato all'inizio del successivo.
**Impatto**: fori tagliati come linee → pezzo sbagliato, potenzialmente inutilizzabile.
**Fix proposto**: usare `svgpathtools.path.continuous_subpaths()` e generare una entità separata per ogni sotto-tracciato.
**Stato**: aperto — Step 9i

### 3. SVG — Handle del primo nodo perso sui path chiusi
**File**: `src/lasercontrolsuite/cad/io/svg_importer.py`
**Problema**: quando un tracciato torna al punto di partenza, l'ultimo nodo duplicato viene rimosso con `nodes.pop()`, ma il suo `handle_in` **non viene copiato** in `nodes[0].handle_in`. Il primo nodo perde la curva in ingresso.
**Impatto**: tracciati chiusi con curve distorte all'attacco.
**Fix proposto**: prima di `nodes.pop()`, copiare `nodes[-1].handle_in` in `nodes[0].handle_in`.
**Stato**: aperto — Step 9i

### 4. DXF — INSERT trasformato due volte
**File**: `src/lasercontrolsuite/cad/io/dxf_importer.py`
**Problema**: `virtual_entities()` di `ezdxf` restituisce già le entità trasformate secondo la matrice dell'INSERT. Il codice applica poi di nuovo posizione, rotazione e scala del blocco.
**Impatto**: blocchi inseriti in punti diversi dall'origine appaiono spostati/ruotati/scalati in modo errato.
**Test di verifica**: DXF con un blocco (es. quadrato 10×10 con un cerchio dentro) inserito in (100, 0) con rotazione 45° e scala 2. Il risultato atteso è il blocco in (100,0) ruotato; quello attuale è un blocco in posizione diversa.
**Fix proposto**: usare direttamente le entità di `virtual_entities()` senza riapplicare la trasformazione dell'INSERT.
**Stato**: aperto — Step 9i

### 5. DXF — Spline grossolane su DXF non in mm
**File**: `src/lasercontrolsuite/cad/io/dxf_importer.py`
**Problema**: `flattening(distance=0.05 * scale)` usa la moltiplicazione invece della divisione. Se `scale` è il fattore di conversione a mm, un DXF in pollici ha `scale ≈ 25.4`, quindi la tolleranza diventa 1.27 pollici (~32 mm) invece di ~2 mm.
**Impatto**: spline approssimate a segmenti lunghissimi, geometria irriconoscibile su file in pollici.
**Fix proposto**: `flattening(distance=0.05 / scale)`.
**Stato**: aperto — Step 9i

### 6. DXF — Bulge mai emesso
**File**: `src/lasercontrolsuite/cad/io/dxf_importer.py`
**Problema**: il flag `has_bulge` è sempre falso perché `get_points("xyb")` restituisce tuple a 3 elementi `(x, y, bulge)` e il codice controlla `len(p) > 4`.
**Impatto**: archi in LWPOLYLINE (rettangoli arrotondati, asole, ecc.) importati come segmenti retti, senza alcun avviso all'utente.
**Fix proposto**: correggere la condizione a `len(p) > 2` (o controllare la presenza del campo `bulge`). Convertire i bulge in archi di cerchio. Emettere warning quando un bulge non è supportato.
**Stato**: aperto — Step 9i

---

## 🟡 Bug medi

### 7. `fit_scene_in_view` — Ordine di moltiplicazione da verificare
**File**: `src/lasercontrolsuite/cad/view.py`
**Problema**: il docstring dice "prima trasla, poi scala", ma il codice fa `QTransform().translate(...) * t`. In Qt row-vector, `A * B` = applica B poi A. Va verificato con un test che `mapFromScene(centro_bounding)` coincida col centro del viewport dopo il fit.
**Impatto**: se sbagliato, il contenuto dopo "Adatta" non è centrato (ma la scala può essere corretta).
**Fix proposto**: verificare con test; se confermato, invertire l'ordine delle moltiplicazioni.
**Stato**: da verificare — Step 9i

### 8. Multi-selezione drag senza comando di undo
**File**: `src/lasercontrolsuite/cad/tools.py` (SelectTool) + `cad/editor.py`
**Problema**: trascinando un gruppo di entità selezionate, solo l'elemento sotto il mouse riceve il rilascio. Gli altri restano con `pos()` spostato ma senza `TransformEntityCommand` corrispondente.
**Impatto**: `Ctrl+Z` dopo un drag multiplo non ripristina la posizione di tutte le entità; stato documento incoerente con l'undo stack.
**Fix proposto**: nel `mouseReleaseEvent` del tool, estendere la modifica a tutti gli item selezionati con un `BatchTransformCommand` (o un macro di `TransformEntityCommand`).
**Stato**: aperto — Step 9i

### 9. `Document.remove_layer` può lasciare documento senza layer attivo
**File**: `src/lasercontrolsuite/core/document.py`
**Problema**: non c'era un controllo che impedisse di eliminare l'ultimo layer. Dopo la rimozione, `active_layer_id` continuava a puntare a un layer inesistente.
**Fix applicato (Step 9c)**: il pannello CAM (`ui/panels/cam_panel.py`) blocca la rimozione quando `len(doc.layers) <= 1` con un messaggio in status bar. Il core resta invariato (nessuna eccezione sollevata: il chiamante ha la responsabilità di non invocare `remove_layer` sull'ultimo). Test: `test_remove_last_layer_is_prevented`.
**Impatto residuo**: codice esterno al pannello CAM (es. script) potrebbe ancora eliminare l'ultimo layer. In futuro esporremo un `Document.try_remove_layer() -> bool`.
**Stato**: risolto (a livello UI) — Step 9c

### 10. `remove_node_at` su path chiuso con pochi nodi
**File**: `src/lasercontrolsuite/core/path_edit.py`
**Problema**: rimuovere un nodo da un tracciato chiuso da 3 nodi lascia `closed=True` con 2 nodi. La chiusura forza un'ultima linea che duplica il segmento tra i due nodi rimanenti.
**Impatto**: la linea di chiusura coincide col segmento → taglio doppio nel G-code.
**Fix proposto**: se dopo la rimozione il path ha `< 3` nodi, impostare `closed=False`.
**Stato**: aperto — Step 9i

### 11. `set_node_smooth` — tangente errata sui nodi estremi aperti
**File**: `src/lasercontrolsuite/core/path_edit.py`
**Problema**: per un nodo al bordo di un path aperto, il calcolo della tangente usa `(index - 1) % n`, che avvolge all'ultimo nodo anziché gestire il bordo.
**Impatto**: la tangente del primo nodo di un path aperto è calcolata come se fosse collegato all'ultimo, producendo un handle in direzione sbagliata.
**Fix proposto**: gestire esplicitamente i casi `index == 0` e `index == n-1` per i path aperti; usare la formula one-sided.
**Stato**: aperto — Step 9i

---

## 🟢 Miglioramenti

### 12. Import/tracing bloccano la UI
**File**: `ui/main_window.py`, `cad/io/*`
**Problema**: `import_dxf`, `import_svg`, `trace_image_file` girano sul thread principale. Immagini grandi (migliaia di pixel) o DXF complessi congelano la finestra per decine di secondi.
**Fix proposto**: `QThread` di lavoro con `progressChanged` e pulsante Annulla. Riusare il pattern del `GrblController`.
**Stato**: rimandato — Step 9 avanzato o successivo

### 13. Layer — colore, visibilità, locked non usati dall'UI
**File**: `cad/entity_item.py`, `cad/scene.py`, `core/layer.py`, `ui/panels/cam_panel.py`
**Problema**: il core definiva `Layer.visible`, `Layer.locked` e `Layer.color`, ma l'UI non li leggeva né li applicava.
**Fix applicato (Step 9c)**:
  - `EntityItem.paint()` legge `layer.color` e lo applica alla penna.
  - `EntityItem.sync_from_layer(layer)` imposta `setVisible()` e disabilita `ItemIsSelectable`/`ItemIsMovable` in base a `layer.visible`/`layer.locked`.
  - `CadScene._apply_layer_to_item()` e `_refresh_layers()` rispondono agli eventi `layer_added`/`layer_removed`/`layer_changed`.
  - Il pannello CAM ora espone i layer in una **tabella editabile** con:
    - **click su riga** → imposta layer attivo e assegna le entità selezionate al layer
    - **bottone "→ Assegna selezione"** → assegna la selezione al layer selezionato
    - **menu contestuale** (tasto destro): "Assegna selezione a '<layer>'", "Cambia colore…", "Rinomina…"
    - **doppio click sul colore** → apre `QColorDialog`
    - **doppio click sulle altre celle** → edit in-place (velocità, potenza, passate, air)
  - L'assegnazione multipla usa un unico `beginMacro`/`endMacro` di `ChangeEntityLayerCommand`, quindi `Ctrl+Z` la annulla in un colpo solo.
  - `CamPanel._assign_entities_to_layer()` forza `item.sync_from_layer()` come rete di sicurezza.
**Test**: `tests/test_cad_layer_visual.py`, `tests/test_ui_cam_panel.py`.
**Stato**: risolto — Step 9c (fix successivo)

### 14. `TextEntity.local_points` bbox approssimato
**File**: `src/lasercontrolsuite/core/entities.py`
**Problema**: la bbox di `TextEntity` è un rettangolo calcolato sulla base del font_size, non sui glifi reali. Allineamenti e snap risultano imprecisi.
**Fix proposto**: usare `QPainterPath.addText` (già disponibile in `entity_item.py`) per estrarre i contorni reali dei glifi e calcolare la bbox vera. Aprire la strada a Text-to-path (Step 9h).
**Stato**: aperto — Step 9h (text-to-path)

### 15. Cerchi con 64 segmenti fissi
**File**: `src/lasercontrolsuite/core/entities.py` (`CircleEntity`)
**Problema**: `local_points()` campiona il cerchio a 64 segmenti fissi. Con raggio 200 mm l'errore di corda è di circa 0.24 mm.
**Fix proposto**: tolleranza adattiva basata sul raggio (`n = ceil(π / acos(1 - tol / r))`), o emissione di G2/G3 nativi in fase CAM.
**Stato**: aperto — miglioria futura

### 16. `snap()` scorre tutti gli item a ogni mousemove
**File**: `src/lasercontrolsuite/cad/snap.py`
**Problema**: `SnapEngine.snap` itera su tutti gli item della scena a ogni movimento del mouse. Con migliaia di entità (tipico dopo un trace) la UI diventa lenta.
**Fix proposto**: usare `scene.items(rect)` con un intorno del cursore, e/o indicizzare gli endpoint in una struttura spaziale.
**Stato**: rimandato — ottimizzazione dopo Step 9

### 17. `boundingRect`/`paint` ricostruiscono il path a ogni frame
**File**: `src/lasercontrolsuite/cad/entity_item.py`
**Problema**: ogni chiamata ricostruisce il `QPainterPath` da zero. Con molte entità visibili il repaint è lento.
**Fix proposto**: cache del `QPainterPath` invalidata solo su `sync_from_entity()`.
**Stato**: rimandato — ottimizzazione dopo Step 9

### 18. Costanti di classe vanno annotate `ClassVar`
**File**: `src/lasercontrolsuite/core/entities.py`, `core/path.py`
**Problema**: `_ARC_SEGMENTS`, `_SAMPLES` sono dichiarati come attributi di dataclass, quindi diventano campi di istanza. Andrebbero `ClassVar[int]`.
**Fix proposto**: aggiungere `from typing import ClassVar` e annotare.
**Stato**: aperto — pulizia Step 9i

### 19. `core/commands.py` importa Qt
**File**: `src/lasercontrolsuite/core/commands.py`
**Problema**: il core dichiara di essere puro Python, ma `commands.py` importa `QUndoCommand` da PySide6.
**Fix proposto**: spostare i comandi in `cad/commands.py` (adapter Qt) e lasciare nel core solo le operazioni pure, oppure definire un'interfaccia `Command` astratta nel core con implementazione Qt nell'adapter.
**Stato**: aperto — refactoring architetturale, Step 9 o successivo

### 20. Uso di `document._emit` dall'esterno
**File**: vari (`core/operations.py`, `core/path_edit.py`, `ui/panels/cam_panel.py`)
**Problema**: diversi punti chiamano `document._emit(...)` (metodo privato) invece di un metodo pubblico. Step 9c ha **ulteriormente aggravato**: `cam_panel.py` emette `layer_changed` da `_edit_layer_color` e `_move_layer`, e `cad/scene.py` risponde a questi eventi.
**Fix proposto**: esporre `document.notify_entity_changed(entity_id)`, `document.notify_layer_changed(layer_id)`, `document.notify_layer_added/removed(layer_id)` come API pubblica e sostituire le chiamate.
**Stato**: aperto — pulizia Step 9i (priorità aumentata)

### 21. `StarEntity.points` è un int, `PolylineEntity.points` è una lista
**File**: `src/lasercontrolsuite/core/entities.py`
**Problema**: stesso nome, significati diversi. Confonde chi legge e favorisce bug.
**Fix proposto**: rinominare `StarEntity.points` in `StarEntity.num_points` (o simile). Attenzione alla compatibilità con `entity_to_path` e con i test.
**Stato**: aperto — pulizia Step 9i

### 22. NodeEditTool converte a Path alla sola selezione
**File**: `src/lasercontrolsuite/cad/tools.py` (NodeEditTool)
**Problema**: appena si attiva lo strumento Nodi su un rettangolo, l'entità viene convertita in `PathEntity` con un `ReplaceEntityCommand`. L'utente non ha ancora toccato nulla.
**Impatto**: la conversione non è voluta e riempie l'undo stack di azioni non desiderate.
**Fix proposto**: convertire solo alla prima modifica effettiva di un nodo, e raggruppare più conversioni in un unico `beginMacro`.
**Stato**: aperto — Step 9 UX

### 23. `.gitignore` incompleto
**File**: `.gitignore`
**Problema**: `.venv/`, `.pytest_cache/`, `*.egg-info/`, `__pycache__/` non sono esclusi.
**Fix proposto**: aggiungere le voci.
**Stato**: aperto — pulizia immediata

### 24. Test cache obsoleto
**File**: `.pytest_cache/v/cache/lastfailed`
**Problema**: cita test falliti che non esistono più nel codebase attuale.
**Fix proposto**: cancellare `.pytest_cache/` (rientra in #23).
**Stato**: aperto — pulizia immediata

### 25. `qtbot.waitSignal`/`waitUntil` non affidabili su segnali cross-thread
**File**: `tests/test_ui_console_panel.py` (e qualunque test che aspetti segnali emessi da `QThread`)
**Problema**: con `pytest-qt 4.5` + `Qt 6.12` + `Windows`, i context manager `qtbot.waitSignal(...)` e `qtbot.waitUntil(...)` **non consegnano in modo affidabile** i segnali emessi da un `QThread` quando il controller ha già uno o più slot collegati (es. `ConsolePanel`). Il segnale è effettivamente emesso (dimostrato con uno spy manuale + loop esplicito) ma il context manager scade senza mai osservarlo. Alzare il timeout **non risolve** — il `waitUntil` ritorna quasi istantaneamente con `None` invece di rispettare il timeout.
**Impatto**: test che sembrano "flaky" ma sono in realtà deterministicamente rotti; tempo speso a caccia di bug inesistenti nel controller/UI.
**Pattern robusto** (documentato e usato in `tests/test_ui_console_panel.py`):
```python
def _pump(qtbot, ms=20):
    QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    qtbot.wait(ms)

def _wait_until(qtbot, predicate, timeout_ms=2000):
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        if predicate():
            return True
        _pump(qtbot)
    return predicate()
```
Il pattern `processEvents(AllEvents) + qtbot.wait(POLL_MS)` in loop esplicito **consegna** correttamente gli eventi `QueuedConnection` provenienti dal worker thread **e** cede il GIL al worker perché possa avanzare. Il pattern `qtbot.waitSignal`/`waitUntil`/`qtbot.wait(N)` singolo no.
**Regola**: nei test che aspettano segnali da `QThread` con slot UI collegati, **usare sempre l'helper `_wait_until`**, mai un'attesa singola.
**Stato**: aperto — pattern documentato, workaround in uso

### 26. `console_panel.py` spostato da `comm/` a `ui/panels/`
**File**: `src/lasercontrolsuite/comm/console_panel.py` → `src/lasercontrolsuite/ui/panels/console_panel.py`
**Problema**: incoerenza architetturale. `comm/` conteneva `protocol.py`, `controller.py`, `port_scanner.py`, `fake_serial.py` (tutti puro Python tranne `controller.py`) e anche un `ConsolePanel` (QWidget). Gli altri pannelli (`PropertyPanel`, `CamPanel`) vivevano già in `ui/panels/`.
**Fix applicato (Step 9b)**: spostato il pannello in `ui/panels/console_panel.py`, aggiornato `main_window.py`, `comm/__init__.py`. Il pacchetto `comm/` ora contiene solo: `protocol`, `controller`, `port_scanner`, `fake_serial`.
**Impatto**: nessuno funzionale, ma coerenza architetturale e un solo punto di verità per "dove vivono i pannelli UI".
**Stato**: risolto — Step 9b

### 27. `cam_panel.py` — header tabella disallineati
**File**: `src/lasercontrolsuite/ui/panels/cam_panel.py`
**Problema**: la lista degli header era `["", "Colore", "Nome", "Velocità", "Potenza", "Air"]`, con un elemento vuoto in più (probabilmente pensato per un row header che non esisteva). Risultato: ogni header tranne l'ultimo era spostato di una posizione a destra rispetto alla colonna dati sottostante. La colonna "Passate" era inoltre priva di header perché il `QTableWidget` era stato creato con 6 colonne ma solo 5 etichette utili.
**Fix applicato (Step 9c)**: header corretti a `["Colore", "Nome", "Velocità", "Potenza", "Passate", "Air"]`. Aggiunto `setVisible(False)` sul vertical header per nascondere i row number.
**Impatto**: cosmetico ma fuorviante.
**Stato**: risolto — Step 9c (fix successivo)

### 28. Cambio tema: QToolButton e testi non aggiornati
**File**: `src/lasercontrolsuite/resources/theme.py`, `src/lasercontrolsuite/resources/theme_manager.py`, `src/lasercontrolsuite/app.py`, `src/lasercontrolsuite/ui/main_window.py`
**Problema**: con il cambio tema a runtime, alcuni widget — in particolare `QToolButton` dentro `QToolBar` — continuavano a usare la palette precedente. Anche alcuni testi (placeholder di `QLineEdit`, `specialValueText` di `QDoubleSpinBox`, testo di `QComboBox`) non si aggiornavano perché `setStyleSheet` da solo non ricostruisce lo stile calcolato di **tutti** i widget già creati.
**Inoltre**: l'area attorno al piano di lavoro nel tema chiaro restava grigio scuro `#585858` (colore del tema dark).
**Fix applicato (Step 9d)**:
  - `ThemeManager.apply_to_app(app)` ora fa tre cose: `setStyleSheet` + `setPalette` (con `PlaceholderText`, `ButtonText`, `WindowText`, `Text`, `Highlight`, `HighlightedText`, ...) + **repolish esplicito** di tutti i widget (`app.allWidgets()` con `unpolish`/`polish`/`update`).
  - `LIGHT.canvas_outside_bg` portato a `#C8C8C8` (grigio chiaro), `LIGHT.canvas_workarea_border` a `#808080`.
  - `LIGHT.fg_primary` portato a `#1A1A1A`, `fg_secondary` a `#505050` per migliorare il contrasto.
  - Aggiunte regole QSS specifiche `QToolBar > QToolButton` per forzare il colore del testo dentro le toolbar.
**Stato**: risolto — Step 9d

---

## Note

- I punti 🔴 1-6 sono **bug funzionali confermati** nell'analisi. Vanno corretti tutti insieme nello **Step 9i** (dedicato a DXF/SVG), con un test di regressione per ciascuno.
- I punti 🟡 7-11 sono piccoli fix, sempre Step 9i.
- I punti 🟢 12-22 e 25 sono refactoring/ottimizzazioni/pattern, distribuiti sugli step successivi.
- I punti 23-24 sono pulizia immediata, da fare quando si tocca il `.gitignore`.
- I punti 9, 13, 26, 27, 28 sono già chiusi e restano come traccia storica.
- Step 9c ha **ulteriormente aggravato** il punto 20 (`document._emit`): il pannello CAM ora emette `layer_changed` anche da `_edit_layer_color` e `_move_layer`. Da sanare appena possibile con `notify_layer_changed()`.

## Pattern imparati (riferimento rapido)

Le seguenti lezioni non sono "issue" da chiudere ma **regole da rispettare** quando si scrive codice o test. Sono qui per memoria, perché ognuna è costata almeno un'iterazione di debug.

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
| P11 | Editable mode | Verificare `pip show lasercontrolsuite` → `Editable project location`. Altrimenti le modifiche a `src/` non hanno effetto. |
| P12 | QSS completo | Il tema deve coprire `QDialog`, `QPushButton`, `QComboBox`, `QCheckBox`, `QGroupBox`, `QPlainTextEdit`, `QToolButton`, `QTableWidget`, `QMenu`, `QColorDialog`, `QToolBar > QToolButton`. |
| P13 | `shape()` sottile | Con penna cosmetica `QGraphicsPathItem.shape()` è troppo sottile per l'hover. Override con `QPainterPathStroker` a tolleranza fissa. |
| P14 | Esc sul dialog | `QDialog` chiude su Esc per default. Override di `keyPressEvent` per deselezionare **prima**. |
| P15 | Legenda/overlay | Disegnarli in `drawForeground` con `resetTransform` è fragile. Meglio come widget figlio del viewport. |
| P16 | Cross-thread in pytest-qt | Vedi issue #25. `qtbot.waitSignal`/`waitUntil` e `qtbot.wait(N)` singolo non bastano. Usare `_pump()` + loop esplicito con `processEvents(AllEvents)`. |
| P17 | Signal → tabelle | Non emettere `DocumentEvent` da un handler di `QTableWidget.itemChanged`: la `setText()` triggera `itemChanged` di nuovo e distrugge gli item C++ a metà callback (`RuntimeError: Internal C++ object already deleted`). Usare `blockSignals(True)` durante gli update programmatici, e preferire update mirati (riga) a rebuild completi. |
| P18 | Layer priority | Nei sistemi multi-layer, l'ordine di lavorazione è un attributo del layer (`priority`), non dell'ordine di inserimento. A parità di priority, vale l'ordine di inserimento nel documento. |
| P19 | Header di QTableWidget | `setHorizontalHeaderLabels` richiede **esattamente** N etichette, una per colonna, nell'ordine corretto. Un elemento vuoto "in più" sfalsa tutti gli header a partire dal primo. |
| P20 | Click-to-assign su tabelle | Nelle UI stile LightBurn, il click su una cut/layer deve (1) impostare quel layer come attivo e (2) assegnare la selezione del canvas a quel layer. Farlo in un unico `beginMacro` così `Ctrl+Z` annulla l'intera operazione. |
| P21 | Cambio tema a runtime | `QApplication.setStyleSheet()` **non** ricostruisce lo stile calcolato di tutti i widget già creati. Serve anche: `setPalette(QPalette coerente)` + **repolish esplicito** (`unpolish`/`polish`/`update` per ogni widget in `app.allWidgets()`). Senza repolish, `QToolButton` dentro `QToolBar` e vari testi (placeholder, `specialValueText`) restano con la palette vecchia. |
| P22 | Proxy di tema | Per cambiare tema a runtime senza toccare N file che fanno `from ...theme import THEME`, si usa un **proxy** (`__getattr__` che inoltra a un singleton `ThemeManager`). Ogni `THEME.accent` legge il valore *corrente*. Chi cachа colori in `__init__` deve collegarsi a `themeChanged` e ricostruirli. |
| P23 | Array polari | Un array polare può **ruotare** le copie o solo **traslarle** lungo l'arco. Entrambe le modalità sono utili (es. per disporre icone vs disporre pezzi). Esporre l'opzione, non hardcodare. |
| P24 | Ordine di selezione in QGraphicsScene | `scene.selectedItems()` restituisce gli item in **ordine di stacking**, non in ordine di selezione. Per operazioni dove l'ordine è semanticamente significativo (es. `difference` booleana), **non fidarsi** di `selectedItems()`: usare una regola deterministica esplicita (es. area del bbox maggiore come target). |
| P25 | Booleane con `shapely` | Il risultato di `difference`/`intersection` può essere `MultiPolygon`. Vanno estratti **tutti** i `Polygon` (esterno + eventuali fori come `PathEntity` separate) e non solo `geoms[0]`. Le entità non convertibili e i path aperti vanno gestiti con warning espliciti, mai silenziosamente. |

## Come usare questo file

- Quando si chiude un punto: cambiare `Stato` in `risolto` e aggiungere una riga con l'hash del commit o il riferimento allo Step.
- Quando si scopre un nuovo problema: aggiungere una riga in tabella e una sezione. Non rimuovere mai nulla: i `wontfix` restano per memoria.
- Quando si scopre un **pattern** (lezione metodologica, non bug): aggiungerlo alla sezione "Pattern imparati", non alle issue.
- Ad ogni Step: scorrere l'indice e aggiornare gli stati dei punti toccati.