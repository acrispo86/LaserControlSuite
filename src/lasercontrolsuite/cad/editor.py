"""Operazioni di alto livello sul canvas (clipboard, nudge, align, ...)."""

from __future__ import annotations

from lasercontrolsuite.core.boolean_ops import BooleanMode, boolean_operation
from lasercontrolsuite.core.commands import (
    AddEntitiesCommand,
    BatchTransformCommand,
    RemoveEntitiesCommand,
    ReplaceEntityCommand,
)
from lasercontrolsuite.core.entities import Entity
from lasercontrolsuite.core.matrix import Matrix2D
from lasercontrolsuite.core.operations import (
    AlignMode,
    DistributeMode,
    clone_entity,
    compute_align,
    compute_distribute,
    compute_polar_array,
    nudge_transforms,
)
from lasercontrolsuite.core.path import PathEntity
from lasercontrolsuite.core.path_edit import entity_to_path


def _bbox_area(entity: Entity) -> float:
    """Area del bounding box in coordinate mondo (per ordinare le entità)."""
    x0, y0, x1, y1 = entity.world_bounding_box()
    return max(0.0, (x1 - x0) * (y1 - y0))


class CanvasEditor:
    """Servizio di editing collegato a una ``CadGraphicsView``."""

    def __init__(self, view) -> None:
        self._view = view
        self._clipboard: list[Entity] = []

    # --------------------------------------------------------------- helpers
    @property
    def scene(self):
        return self._view.cad_scene

    @property
    def document(self):
        return self.scene.document

    @property
    def undo_stack(self):
        return self.scene.undo_stack

    def selected_entities(self) -> list[Entity]:
        from lasercontrolsuite.cad.entity_item import EntityItem

        return [
            item.entity
            for item in self.scene.selectedItems()
            if isinstance(item, EntityItem)
        ]

    # --------------------------------------------------------------- clipboard
    def copy_selection(self) -> int:
        self._clipboard = [clone_entity(e) for e in self.selected_entities()]
        return len(self._clipboard)

    def paste(self, dx: float = 10.0, dy: float = 10.0) -> int:
        if not self._clipboard:
            return 0
        offset = Matrix2D.translation(dx, dy)
        copies: list[Entity] = []
        for e in self._clipboard:
            clone = clone_entity(e)
            clone.transform = offset @ clone.transform
            copies.append(clone)
        self.undo_stack.push(AddEntitiesCommand(self.document, copies, "Incolla"))
        self._select_entities(copies)
        return len(copies)

    def duplicate_selection(self, dx: float = 10.0, dy: float = 10.0) -> int:
        self.copy_selection()
        return self.paste(dx, dy)

    def delete_selection(self) -> int:
        entities = self.selected_entities()
        if not entities:
            return 0
        self.undo_stack.push(RemoveEntitiesCommand(self.document, entities))
        return len(entities)

    # --------------------------------------------------------------- nudge
    def nudge(self, dx: float, dy: float) -> int:
        entities = self.selected_entities()
        transforms = nudge_transforms(entities, dx, dy)
        if not transforms:
            return 0
        self.undo_stack.push(
            BatchTransformCommand(self.document, transforms, "Sposta")
        )
        return len(transforms)

    # --------------------------------------------------------------- align
    def align(self, mode: AlignMode) -> int:
        entities = self.selected_entities()
        transforms = compute_align(entities, mode)
        if not transforms:
            return 0
        self.undo_stack.push(
            BatchTransformCommand(self.document, transforms, f"Allinea {mode.value}")
        )
        return len(transforms)

    def distribute(self, mode: DistributeMode) -> int:
        entities = self.selected_entities()
        transforms = compute_distribute(entities, mode)
        if not transforms:
            return 0
        self.undo_stack.push(
            BatchTransformCommand(self.document, transforms, f"Distribuisci {mode.value}")
        )
        return len(transforms)

    # --------------------------------------------------------------- array
    def linear_array(
        self,
        rows: int,
        cols: int,
        dx: float,
        dy: float,
        include_original: bool = True,
    ) -> int:
        rows = max(1, int(rows))
        cols = max(1, int(cols))
        if rows == 1 and cols == 1:
            return 0

        sources = self.selected_entities()
        if not sources:
            return 0

        new_entities: list[Entity] = []
        for r in range(rows):
            for c in range(cols):
                if include_original and r == 0 and c == 0:
                    continue
                for src in sources:
                    clone = clone_entity(src)
                    offset = Matrix2D.translation(c * dx, r * dy)
                    clone.transform = offset @ clone.transform
                    new_entities.append(clone)
        if not new_entities:
            return 0
        self.undo_stack.push(
            AddEntitiesCommand(self.document, new_entities, "Array lineare")
        )
        self._select_entities(new_entities)
        return len(new_entities)

    def polar_array(
        self,
        center: tuple[float, float],
        count: int,
        total_angle_deg: float = 360.0,
        start_angle_deg: float = 0.0,
        include_original: bool = True,
        rotate_copies: bool = True,
    ) -> int:
        sources = self.selected_entities()
        if not sources:
            return 0
        new_entities = compute_polar_array(
            sources,
            center=center,
            count=count,
            total_angle_deg=total_angle_deg,
            start_angle_deg=start_angle_deg,
            include_original=include_original,
            rotate_copies=rotate_copies,
        )
        if not new_entities:
            return 0
        self.undo_stack.push(
            AddEntitiesCommand(self.document, new_entities, "Array circolare")
        )
        self._select_entities(new_entities)
        return len(new_entities)

    # --------------------------------------------------------------- booleane
    def _run_boolean(self, mode: BooleanMode, label: str) -> tuple[int, list[str]]:
        entities = self.selected_entities()
        if len(entities) < 2:
            return 0, ["Servono almeno due entità per l'operazione booleana."]

        # Per DIFFERENCE, il target è l'entità con area (bbox) maggiore;
        # le altre vengono sottratte. Questo rende il comportamento
        # deterministico e indipendente dall'ordine di stacking di Qt
        # (``scene.selectedItems()`` restituisce gli item in ordine inverso
        # di aggiunta, che non corrisponde a "cosa l'utente voleva sottrarre").
        if mode == BooleanMode.DIFFERENCE:
            entities = sorted(entities, key=_bbox_area, reverse=True)

        paths, warnings = boolean_operation(entities, mode)

        if not paths:
            return 0, warnings

        self.undo_stack.beginMacro(label)
        try:
            self.undo_stack.push(RemoveEntitiesCommand(self.document, entities))
            self.undo_stack.push(AddEntitiesCommand(self.document, paths, label))
        finally:
            self.undo_stack.endMacro()

        self._select_entities(paths)
        return len(paths), warnings

    def boolean_union(self) -> tuple[int, list[str]]:
        return self._run_boolean(BooleanMode.UNION, "Unione")

    def boolean_difference(self) -> tuple[int, list[str]]:
        return self._run_boolean(BooleanMode.DIFFERENCE, "Sottrai")

    def boolean_intersection(self) -> tuple[int, list[str]]:
        return self._run_boolean(BooleanMode.INTERSECTION, "Intersezione")

    # --------------------------------------------------------------- convert
    def convert_selection_to_path(self) -> int:
        entities = self.selected_entities()
        converted_ids: list[str] = []
        for e in entities:
            if isinstance(e, PathEntity):
                continue
            new_e = entity_to_path(e)
            if new_e is None or new_e is e:
                continue
            self.undo_stack.push(
                ReplaceEntityCommand(
                    self.document, e, new_e, label="Converti in path"
                )
            )
            converted_ids.append(e.id)
        if converted_ids:
            self.scene.clearSelection()
            for eid in converted_ids:
                item = self.scene.entity_item(eid)
                if item is not None:
                    item.setSelected(True)
        return len(converted_ids)

    # --------------------------------------------------------------- import
    def import_entities(
        self,
        entities: list[Entity],
        label: str = "Importa",
        select: bool = True,
    ) -> int:
        """Aggiunge un blocco di entità importate in un solo comando undo.

        Le entità vengono ricollegate al layer attivo del documento se il
        loro ``layer_id`` è vuoto. Non modifica le entità già valorizzate.
        """
        if not entities:
            return 0
        active = self.document.active_layer_id
        for e in entities:
            if not e.layer_id:
                e.layer_id = active
        self.undo_stack.push(AddEntitiesCommand(self.document, entities, label))
        if select:
            self._select_entities(entities)
        return len(entities)

    # --------------------------------------------------------------- misc
    def _select_entities(self, entities: list[Entity]) -> None:
        from lasercontrolsuite.cad.entity_item import EntityItem

        self.scene.clearSelection()
        ids = {e.id for e in entities}
        for item in self.scene.items():
            if isinstance(item, EntityItem) and item.entity.id in ids:
                item.setSelected(True)