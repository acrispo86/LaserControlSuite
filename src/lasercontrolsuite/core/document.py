"""Documento: contenitore di layer ed entità con sistema di notifica."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from lasercontrolsuite.core.entities import Entity
from lasercontrolsuite.core.layer import Layer
from lasercontrolsuite.core.matrix import Matrix2D


@dataclass(frozen=True)
class DocumentEvent:
    """Evento emesso quando il documento cambia."""

    type: str
    entity_id: str | None = None
    layer_id: str | None = None


Subscriber = Callable[[DocumentEvent], None]


class Document:
    """Contenitore dati principale. Nessuna dipendenza da Qt."""

    def __init__(self) -> None:
        self.layers: dict[str, Layer] = {}
        self.entities: dict[str, Entity] = {}
        self.active_layer_id: str = ""
        self._subscribers: list[Subscriber] = []

        default_layer = Layer.new("Layer 1", color="#00D4FF")
        self.layers[default_layer.id] = default_layer
        self.active_layer_id = default_layer.id

    # ---------------------------------------------------------------- observer
    def subscribe(self, callback: Subscriber) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Subscriber) -> None:
        try:
            self._subscribers.remove(callback)
        except ValueError:
            pass

    def _emit(self, event: DocumentEvent) -> None:
        for cb in list(self._subscribers):
            cb(event)

    # ---------------------------------------------------------------- entità
    def add_entity(self, entity: Entity) -> None:
        if entity.id in self.entities:
            raise ValueError(f"Entità con id {entity.id} già presente nel documento")
        if not entity.layer_id:
            entity.layer_id = self.active_layer_id
        self.entities[entity.id] = entity
        self._emit(DocumentEvent("entity_added", entity_id=entity.id))

    def remove_entity(self, entity_id: str) -> Entity | None:
        entity = self.entities.pop(entity_id, None)
        if entity is not None:
            self._emit(DocumentEvent("entity_removed", entity_id=entity_id))
        return entity

    def get_entity(self, entity_id: str) -> Entity | None:
        return self.entities.get(entity_id)

    def update_entity_transform(
        self, entity_id: str, new_transform: Matrix2D
    ) -> None:
        entity = self.entities.get(entity_id)
        if entity is None:
            return
        entity.transform = new_transform
        self._emit(DocumentEvent("entity_changed", entity_id=entity_id))

    def entities_of_layer(self, layer_id: str) -> list[Entity]:
        return [e for e in self.entities.values() if e.layer_id == layer_id]

    # ---------------------------------------------------------------- layer
    def add_layer(self, layer: Layer) -> None:
        if layer.id in self.layers:
            raise ValueError(f"Layer con id {layer.id} già presente")
        self.layers[layer.id] = layer
        self._emit(DocumentEvent("layer_added", layer_id=layer.id))

    def remove_layer(self, layer_id: str) -> None:
        if layer_id not in self.layers:
            return
        for entity in list(self.entities.values()):
            if entity.layer_id == layer_id:
                self.remove_entity(entity.id)
        del self.layers[layer_id]
        self._emit(DocumentEvent("layer_removed", layer_id=layer_id))
        if self.active_layer_id == layer_id and self.layers:
            self.active_layer_id = next(iter(self.layers))

    def get_layer(self, layer_id: str) -> Layer | None:
        return self.layers.get(layer_id)

    def set_active_layer(self, layer_id: str) -> None:
        if layer_id in self.layers:
            self.active_layer_id = layer_id
            self._emit(DocumentEvent("active_layer_changed", layer_id=layer_id))