"""Independent, fully resolved technical layout recipes."""
from dataclasses import asdict, dataclass, field
import math
from pathlib import Path
import yaml
from map_editor.geometry import GeometryError, hairpin, straight, chicane, s_curve
from map_editor.geometry.technical import technical_corner
from map_editor.geometry.validation import GeometryLimits, VehicleProfile
from map_editor.services.specialist_templates import canonical_hash

GENERATOR_VERSION='map_editor.technical_layout.v1'
LAYOUT_VERSION='distributed_connector_projection.v1'
BUILDERS=dict(corner=technical_corner,kink=lambda **p:technical_corner(kind='kink',**p),
              compound_corner=lambda **p:technical_corner(kind='compound_corner',**p),
              hairpin=hairpin,chicane=chicane,s_curve=s_curve,straight=straight)
METRICS={'corner_density_per_100m','maximum_curvature_inv_m','p95_curvature_inv_m',
    'curvature_reversals','near_straight_fraction','longest_straight_m','shortest_significant_corner_m',
    'primary_coverage','supporting_fraction','raw_lap_length_m','symmetry_error_m',
    'repetition_fraction','minimum_corner_angle_deg','maximum_corner_angle_deg','long_straight_to_tight_corner_count',
    'median_corner_angle_deg','p90_corner_angle_deg','corner_angle_std_deg'}


@dataclass(frozen=True)
class TechnicalRequest:
    name: str
    family: str
    parameters: dict
    straight_after_m: float = 0.

    def build(self):
        if self.family not in BUILDERS:
            raise GeometryError('Unknown technical request family')
        return BUILDERS[self.family](**self.parameters)

    def __post_init__(self):
        if not isinstance(self.name,str) or not self.name or not math.isfinite(self.straight_after_m) or self.straight_after_m<0:
            raise GeometryError('Invalid request name or primary straight length')
        self.build()


@dataclass(frozen=True)
class TechnicalSpec:
    inventory: tuple[TechnicalRequest,...]
    vehicle: VehicleProfile
    variant: str = 'technical'
    category: str = 'compact'
    topology_orders: tuple[tuple[int,...],...] = ()
    candidate_budget: int = 6
    optimization_iterations: int = 2000
    connector_bounds_m: tuple[float,float] = (.4,18.)
    target_lap_length_m: float = 120.
    lap_length_range_m: tuple[float,float] = (110.,130.)
    objectives: dict = field(default_factory=dict)
    maximum_supporting_fraction: float = .45
    minimum_primary_coverage: float = .55
    minimum_useful_corner_m: float = .6
    track_width_m: float = 1.5
    spacing_m: float = .1
    resolution_m_per_pixel: float = .04
    padding_m: float = 1.
    seam_offset_m: float = 1.7
    seed: int = 42
    dataset_id: str = 'phase3b_technical_pilot'
    generation_mode: str = 'composite'
    layout_version: str = LAYOUT_VERSION
    limits: GeometryLimits = GeometryLimits()

    def __post_init__(self):
        inventory=tuple(self.inventory)
        if not 4<=len(inventory)<=24 or len({r.name for r in inventory})!=len(inventory):
            raise GeometryError('Technical inventory needs 4..24 uniquely named requests')
        if not isinstance(self.vehicle,VehicleProfile) or self.generation_mode!='composite' or self.layout_version!=LAYOUT_VERSION:
            raise GeometryError('Technical layout version/intent/vehicle required')
        if type(self.seed) is not int or self.seed<0 or type(self.candidate_budget) is not int or not 1<=self.candidate_budget<=64:
            raise GeometryError('Invalid seed or bounded topology budget')
        if type(self.optimization_iterations) is not int or not 1<=self.optimization_iterations<=10000:
            raise GeometryError('Invalid optimization iteration budget')
        for key in ['target_lap_length_m','track_width_m','spacing_m','resolution_m_per_pixel','padding_m','minimum_useful_corner_m']:
            v=getattr(self,key)
            if isinstance(v,bool) or not math.isfinite(v) or v<=0:
                raise GeometryError('Invalid positive geometry setting: '+key)
        if not math.isfinite(self.seam_offset_m) or self.seam_offset_m<0:
            raise GeometryError('Invalid seam offset')
        for bounds in [self.connector_bounds_m,self.lap_length_range_m,*self.objectives.values()]:
            if len(bounds)!=2 or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in bounds) or bounds[0]>bounds[1]:
                raise GeometryError('Target bounds must be finite and ordered')
        if self.connector_bounds_m[0]<=0 or not self.lap_length_range_m[0]<=self.target_lap_length_m<=self.lap_length_range_m[1]:
            raise GeometryError('Positive connector bounds and in-range target lap required')
        if any(isinstance(v,bool) or not math.isfinite(v) or not 0<=v<=1
               for v in (self.maximum_supporting_fraction,self.minimum_primary_coverage)):
            raise GeometryError('Coverage limits must be fractions')
        if set(self.objectives)-METRICS:
            raise GeometryError('Unknown technical complexity objective')
        orders=tuple(tuple(o) for o in self.topology_orders) or (tuple(range(len(inventory))),)
        if any(sorted(o)!=list(range(len(inventory))) for o in orders) or len(set(orders))!=len(orders):
            raise GeometryError('Topologies must be unique complete inventory permutations')
        if not self.variant or any(c in self.variant for c in '/\\\x00') or self.variant in {'.','..'} or not self.dataset_id:
            raise GeometryError('Safe variant and dataset identity required')
        object.__setattr__(self,'inventory',inventory)
        object.__setattr__(self,'topology_orders',orders)

    def recipe(self):
        return dict(schema_version=1,generator=GENERATOR_VERSION,**asdict(self))

    @property
    def configuration_id(self):
        return canonical_hash(self.recipe())

    @property
    def track_id(self):
        return 'technical_'+self.configuration_id[:24]


def spec_from_recipe(data):
    if not isinstance(data,dict) or data.get('schema_version')!=1 or data.get('generator')!=GENERATOR_VERSION:
        raise GeometryError('Unsupported technical recipe')
    data=dict(data)
    for key in ('schema_version','generator','achieved','files'):
        data.pop(key,None)
    try:
        data['inventory']=tuple(TechnicalRequest(**r) for r in data['inventory'])
        data['vehicle']=VehicleProfile(**data['vehicle'])
        data['limits']=GeometryLimits(**data.get('limits',{}))
        return TechnicalSpec(**data)
    except (TypeError,KeyError) as exc:
        raise GeometryError('Malformed technical recipe: '+str(exc)) from exc


def load_technical_spec(path):
    return spec_from_recipe(yaml.safe_load(Path(path).read_text()))
