"""Modello dati puro (indipendente da Qt)."""

from __future__ import annotations

from lasercontrolsuite.core.document import Document, DocumentEvent
from lasercontrolsuite.core.entities import (
    BezierEntity,
    CircleEntity,
    EllipseEntity,
    Entity,
    PolygonEntity,
    PolylineEntity,
    StarEntity,
    TextEntity,
)
from lasercontrolsuite.core.ids import new_id
from lasercontrolsuite.core.layer import Layer
from lasercontrolsuite.core.matrix import Matrix2D
from lasercontrolsuite.core.operations import (
    AlignMode,
    DistributeMode,
    clone_entity,
    compute_align,
    compute_distribute,
    nudge_transforms,
    rotation_of,
)
from lasercontrolsuite.core.path import (
    SAMPLES_PER_CURVE,
    PathEntity,
    PathNode,
    polyline_to_path,
)
from lasercontrolsuite.core.path_edit import (
    HandleKind,
    HandleHit,
    NodeHit,
    SegmentHit,
    add_node_at_segment,
    curve_line_segment_through_point,
    entity_to_path,
    find_nearest_handle,
    find_nearest_node,
    find_nearest_segment,
    is_smooth_node,
    move_handle,
    move_node,
    remove_node_at,
    set_node_corner,
    set_node_smooth,
    translate_curve_segment,
)

__all__ = [
    "Document",
    "DocumentEvent",
    "Entity",
    "PolylineEntity",
    "CircleEntity",
    "EllipseEntity",
    "PolygonEntity",
    "StarEntity",
    "BezierEntity",
    "TextEntity",
    "PathEntity",
    "PathNode",
    "polyline_to_path",
    "SAMPLES_PER_CURVE",
    "Layer",
    "Matrix2D",
    "new_id",
    "AlignMode",
    "DistributeMode",
    "compute_align",
    "compute_distribute",
    "nudge_transforms",
    "clone_entity",
    "rotation_of",
    "HandleKind",
    "HandleHit",
    "NodeHit",
    "SegmentHit",
    "find_nearest_node",
    "find_nearest_handle",
    "find_nearest_segment",
    "add_node_at_segment",
    "remove_node_at",
    "set_node_corner",
    "set_node_smooth",
    "move_node",
    "move_handle",
    "is_smooth_node",
    "curve_line_segment_through_point",
    "translate_curve_segment",
    "entity_to_path",
]