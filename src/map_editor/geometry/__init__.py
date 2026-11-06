"""Arc-length geometry backend, independent of the legacy spline sampler."""
from .curves import CurvatureSegment, Frame, GeometryError, State
from .maneuvers import Maneuver, chicane, hairpin, s_curve, sample_parameters, straight, sweeper, transition
from .sequence import GeometrySequence, ContinuityTolerances

GENERATOR_VERSION = "map_editor.parametric_curvature.v1"
