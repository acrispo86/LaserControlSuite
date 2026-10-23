"""Comandi undo/redo per il ``Document``."""

from __future__ import annotations

import copy

from PySide6.QtGui import QUndoCommand

from lasercontrolsuite.core.document import Document, DocumentEvent
from lasercontrolsuite.core.entities import Entity
from lasercontrolsuite.core.layer import Layer
from lasercontrolsuite.core.matrix import Matrix2D
from lasercontrolsuite.core.path import PathEntity, PathNode


class AddEntityCommand(QUndoCommand):
    def __init__(self, document: Document, entity: Entity) -> None:
        super().__init__(f"Aggiungi {type(entity).__name__}")
        self._document = document
        self._entity = entity

    def redo(self) -> None:
        self._document.add_entity(self._entity)

    def undo(self) -> None:
        self._document.remove_entity(self._entity.id)


class AddEntitiesCommand(QUndoCommand):
    def __init__(self, document: Document, entities: list[Entity], label: str = "Aggiungi entità") -> None:
        super().__init__(label)
        self._document = document
        self._entities = list(entities)

    def redo(self) -> None:
        for e in self._entities:
            self._document.add_entity(e)

    def undo(self) -> None:
        for e in self._entities:
            self._document.remove_entity(e.id)


class RemoveEntityCommand(QUndoCommand):
    def __init__(self, document: Document, entity: Entity) -> None:
        super().__init__(f"Rimuovi {type(entity).__name__}")
        self._document = document
        self._entity = entity

    def redo(self) -> None:
        self._document.remove_entity(self._entity.id)

    def undo(self) -> None:
        self._document.add_entity(self._entity)


class RemoveEntitiesCommand(QUndoCommand):
    def __init__(self, document: Document, entities: list[Entity], label: str = "Elimina") -> None:
        super().__init__(label)
        self._document = document
        self._entities = list(entities)

    def redo(self) -> None:
        for e in self._entities:
            self._document.remove_entity(e.id)

    def undo(self) -> None:
        for e in self._entities:
            self._document.add_entity(e)


class TransformEntityCommand(QUndoCommand):
    def __init__(self, document: Document, entity_id: str, new_transform: Matrix2D) -> None:
        super().__init__("Trasforma entità")
        self._document = document
        self._entity_id = entity_id
        entity = document.get_entity(entity_id)
        self._old_transform = entity.transform if entity else Matrix2D()
        self._new_transform = new_transform

    def redo(self) -> None:
        self._document.update_entity_transform(self._entity_id, self._new_transform)

    def undo(self) -> None:
        self._document.update_entity_transform(self._entity_id, self._old_transform)


class BatchTransformCommand(QUndoCommand):
    def __init__(
        self,
        document: Document,
        transforms: dict[str, Matrix2D],
        label: str = "Trasforma gruppo",
    ) -> None:
        super().__init__(label)
        self._document = document
        self._new: dict[str, Matrix2D] = dict(transforms)
        self._old: dict[str, Matrix2D] = {}
        for eid in transforms.keys():
            e = document.get_entity(eid)
            if e is not None:
                self._old[eid] = e.transform

    def redo(self) -> None:
        for eid, t in self._new.items():
            self._document.update_entity_transform(eid, t)

    def undo(self) -> None:
        for eid, t in self._old.items():
            self._document.update_entity_transform(eid, t)


class AddLayerCommand(QUndoCommand):
    def __init__(self, document: Document, layer: Layer) -> None:
        super().__init__(f"Aggiungi layer '{layer.name}'")
        self._document = document
        self._layer = layer

    def redo(self) -> None:
        self._document.add_layer(self._layer)

    def undo(self) -> None:
        self._document.remove_layer(self._layer.id)


class ChangeEntityLayerCommand(QUndoCommand):
    def __init__(self, document: Document, entity_id: str, new_layer_id: str) -> None:
        super().__init__("Cambia layer")
        self._document = document
        self._entity_id = entity_id
        self._new_layer_id = new_layer_id
        e = document.get_entity(entity_id)
        self._old_layer_id = e.layer_id if e else ""

    def redo(self) -> None:
        e = self._document.get_entity(self._entity_id)
        if e is not None:
            e.layer_id = self._new_layer_id
            self._document._emit(DocumentEvent("entity_changed", entity_id=e.id))

    def undo(self) -> None:
        e = self._document.get_entity(self._entity_id)
        if e is not None:
            e.layer_id = self._old_layer_id
            self._document._emit(DocumentEvent("entity_changed", entity_id=e.id))


class EditPathCommand(QUndoCommand):
    """Modifica dei nodi di un ``PathEntity``.

    Snapshot-based: memorizza le liste di nodi complete (deep-copiate) prima
    e dopo la modifica.
    """

    def __init__(
        self,
        document: Document,
        entity_id: str,
        old_nodes: list[PathNode],
        new_nodes: list[PathNode],
        old_closed: bool,
        new_closed: bool,
        label: str = "Modifica path",
    ) -> None:
        super().__init__(label)
        self._document = document
        self._entity_id = entity_id
        self._old_nodes = copy.deepcopy(old_nodes)
        self._new_nodes = copy.deepcopy(new_nodes)
        self._old_closed = old_closed
        self._new_closed = new_closed

    def _apply(self, nodes: list[PathNode], closed: bool) -> None:
        entity = self._document.get_entity(self._entity_id)
        if not isinstance(entity, PathEntity):
            return
        entity.nodes = copy.deepcopy(nodes)
        entity.closed = closed
        self._document._emit(DocumentEvent("entity_changed", entity_id=self._entity_id))

    def redo(self) -> None:
        self._apply(self._new_nodes, self._new_closed)

    def undo(self) -> None:
        self._apply(self._old_nodes, self._old_closed)


class ReplaceEntityCommand(QUndoCommand):
    """Sostituisce un'entità con un'altra che ha lo **stesso id**.

    Usato per conversioni trasparenti (es. ``PolylineEntity`` → ``PathEntity``
    quando si attiva il node editor): l'utente vede la stessa entità, ma il
    tipo cambia e l'operazione è annullabile.
    """

    def __init__(
        self,
        document: Document,
        old_entity: Entity,
        new_entity: Entity,
        label: str = "Converti entità",
    ) -> None:
        if old_entity.id != new_entity.id:
            raise ValueError(
                "ReplaceEntityCommand richiede che old e new abbiano lo stesso id"
            )
        super().__init__(label)
        self._document = document
        self._old = old_entity
        self._new = new_entity

    def _swap(self, entity: Entity) -> None:
        self._document.remove_entity(entity.id)
        self._document.add_entity(entity)

    def redo(self) -> None:
        self._swap(self._new)

    def undo(self) -> None:
        self._swap(self._old)