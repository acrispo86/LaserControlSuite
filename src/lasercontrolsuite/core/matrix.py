"""Matrice affine 2D in puro Python.

Rappresentazione:
    | a  c  e |
    | b  d  f |
    | 0  0  1 |

Un punto ``(x, y)`` è trasformato in ``(a*x + c*y + e, b*x + d*y + f)``.

La composizione ``A @ B`` significa "prima B, poi A":
    ``(A @ B).transform_point(p) == A.transform_point(B.transform_point(p))``

Questo è coerente con la convenzione Qt (row-vector, ``A * B`` = prima A poi B
nel senso del *flusso* del punto), quindi le conversioni verso/da ``QTransform``
sono banali.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EPS = 1e-12


@dataclass(frozen=True, slots=True)
class Matrix2D:
    """Matrice affine 2D immutabile."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    # ------------------------------------------------------------------ builders
    @classmethod
    def identity(cls) -> "Matrix2D":
        return cls()

    @classmethod
    def translation(cls, tx: float, ty: float) -> "Matrix2D":
        return cls(1.0, 0.0, 0.0, 1.0, float(tx), float(ty))

    @classmethod
    def scaling(cls, sx: float, sy: float | None = None) -> "Matrix2D":
        if sy is None:
            sy = sx
        return cls(float(sx), 0.0, 0.0, float(sy), 0.0, 0.0)

    @classmethod
    def rotation(cls, radians: float) -> "Matrix2D":
        c = math.cos(radians)
        s = math.sin(radians)
        return cls(c, s, -s, c, 0.0, 0.0)

    @classmethod
    def rotation_deg(cls, degrees: float) -> "Matrix2D":
        return cls.rotation(math.radians(degrees))

    # ------------------------------------------------------------------ algebra
    def __matmul__(self, other: "Matrix2D") -> "Matrix2D":
        if not isinstance(other, Matrix2D):
            return NotImplemented
        return Matrix2D(
            a=self.a * other.a + self.c * other.b,
            b=self.b * other.a + self.d * other.b,
            c=self.a * other.c + self.c * other.d,
            d=self.b * other.c + self.d * other.d,
            e=self.a * other.e + self.c * other.f + self.e,
            f=self.b * other.e + self.d * other.f + self.f,
        )

    def transform_point(self, x: float, y: float) -> tuple[float, float]:
        return (
            self.a * x + self.c * y + self.e,
            self.b * x + self.d * y + self.f,
        )

    def transform_points(
        self, points: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        a, b, c, d, e, f = self.a, self.b, self.c, self.d, self.e, self.f
        return [(a * x + c * y + e, b * x + d * y + f) for (x, y) in points]

    def determinant(self) -> float:
        return self.a * self.d - self.b * self.c

    def inverted(self) -> "Matrix2D":
        det = self.determinant()
        if abs(det) < EPS:
            raise ValueError("Matrix2D non invertibile (determinante ~ 0)")
        inv_a = self.d / det
        inv_b = -self.b / det
        inv_c = -self.c / det
        inv_d = self.a / det
        inv_e = (self.c * self.f - self.d * self.e) / det
        inv_f = (self.b * self.e - self.a * self.f) / det
        return Matrix2D(inv_a, inv_b, inv_c, inv_d, inv_e, inv_f)

    # ------------------------------------------------------------------ utility
    def is_identity(self, tol: float = 1e-12) -> bool:
        return (
            abs(self.a - 1.0) < tol
            and abs(self.b) < tol
            and abs(self.c) < tol
            and abs(self.d - 1.0) < tol
            and abs(self.e) < tol
            and abs(self.f) < tol
        )

    def almost_equals(self, other: "Matrix2D", tol: float = 1e-9) -> bool:
        return (
            abs(self.a - other.a) < tol
            and abs(self.b - other.b) < tol
            and abs(self.c - other.c) < tol
            and abs(self.d - other.d) < tol
            and abs(self.e - other.e) < tol
            and abs(self.f - other.f) < tol
        )