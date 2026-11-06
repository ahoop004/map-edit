"""Analytic heading and deterministic quadrature of physical curvature k(s)."""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np


class GeometryError(ValueError):
    """Requested geometry or its achieved realization is invalid."""


def finite(*values):
    if not all(math.isfinite(v) for v in values):
        raise GeometryError("Geometry parameters must be finite")


@dataclass(frozen=True)
class Frame:
    x: float = 0.
    y: float = 0.
    heading: float = 0.

    def __post_init__(self):
        finite(self.x, self.y, self.heading)


@dataclass(frozen=True)
class State:
    s: float
    x: float
    y: float
    heading: float
    curvature: float
    curvature_rate: float

    @property
    def frame(self):
        return Frame(self.x, self.y, self.heading)


_NODES, _WEIGHTS = np.polynomial.legendre.leggauss(12)


@dataclass(frozen=True)
class CurvatureSegment:
    length_m: float
    k_start: float = 0.
    k_end: float = 0.
    ramp: str = "smoothstep"

    def __post_init__(self):
        finite(self.length_m, self.k_start, self.k_end)
        if self.length_m <= 1e-8:
            raise GeometryError("Segment length must exceed 1e-8 m")
        if self.ramp not in {"smoothstep", "linear"}:
            raise GeometryError("Ramp must be smoothstep or linear (clothoid)")

    def _fields(self, s):
        u = s / self.length_m
        delta = self.k_end - self.k_start
        if self.ramp == "linear":
            k = self.k_start + delta * u
            heading = self.k_start * s + delta * self.length_m * u**2 / 2
            rate = delta / self.length_m + np.zeros_like(u)
        else:
            k = self.k_start + delta * (3*u**2 - 2*u**3)
            heading = self.k_start * s + delta * self.length_m * (u**3 - u**4/2)
            rate = delta * (6*u - 6*u**2) / self.length_m
        return heading, k, rate

    def at(self, s: float, frame: Frame = Frame(), *, mirrored: bool = False) -> State:
        finite(s)
        if not 0 <= s <= self.length_m:
            raise GeometryError("Arc position lies outside the segment")
        heading, k, rate = self._fields(s)
        if self.k_start == self.k_end:
            if abs(self.k_start) < 1e-14:
                x, y = s, 0.
            else:
                x = math.sin(heading) / self.k_start
                y = 2 * math.sin(heading/2)**2 / self.k_start
        elif s == 0:
            x, y = 0., 0.
        else:
            # Integration panels depend on physical length/curvature, never on
            # output spacing. At most 0.25 m and 0.1 rad of heading per panel.
            step = min(.25, .1/max(abs(self.k_start), abs(self.k_end), 1e-12))
            panels = max(1, math.ceil(s/step))
            if panels > 100000:
                raise GeometryError("Quadrature panel budget exceeded")
            edges = np.linspace(0., s, panels + 1)
            mid = (edges[:-1] + edges[1:])/2
            half = np.diff(edges)/2
            locations = mid[:, None] + half[:, None] * _NODES
            angles = self._fields(locations)[0]
            x = float(np.sum(half * (np.cos(angles) @ _WEIGHTS)))
            y = float(np.sum(half * (np.sin(angles) @ _WEIGHTS)))
        sign = -1 if mirrored else 1
        y, heading, k, rate = y*sign, heading*sign, k*sign, rate*sign
        co, si = math.cos(frame.heading), math.sin(frame.heading)
        return State(s, frame.x + co*x - si*y, frame.y + si*x + co*y,
                     frame.heading + float(heading), float(k), float(rate))

    def sample(self, spacing: float, frame: Frame = Frame(), *, mirrored=False):
        finite(spacing)
        if spacing <= 0:
            raise GeometryError("Sampling spacing must be positive")
        count = max(1, math.ceil(self.length_m/spacing))
        if count > 1000000:
            raise GeometryError("Sampling budget exceeded")
        positions = {self.length_m*i/count for i in range(count)} | {self.length_m}
        if self.k_start != self.k_end and count % 2:
            positions.add(self.length_m/2)  # include peak smoothstep dk/ds
        return tuple(self.at(s, frame, mirrored=mirrored) for s in sorted(positions))
