"""Versioned offline recipes: fixed primary geometry, bounded supporting motion."""
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import yaml
from map_editor.geometry import GeometryError
from map_editor.geometry.validation import VehicleProfile,GeometryLimits
from map_editor.geometry.width_profile import WidthProfile
from .technical_spec import TechnicalRequest,METRICS as TECHNICAL_METRICS
from .specialist_templates import canonical_hash

GENERATOR_VERSION='map_editor.extended_geometry.v1'
LAYOUT_VERSION='bounded_supporting_turns.v1'
LENGTH_PRESETS=dict(short=(70.,140.),medium=(140.,260.),long=(260.,450.))
METRICS=TECHNICAL_METRICS|{'corner_count','minimum_sustained_radius_m','left_turn_fraction',
    'minimum_width_m','maximum_width_m','mean_width_m','width_std_m','minimum_raster_width_m'}
WIDTH_METRICS={'minimum_width_m','maximum_width_m','mean_width_m','width_std_m','minimum_raster_width_m'}


def bounds(value,name,*,positive=False):
    if len(value)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in value) or value[0]>value[1] or (positive and value[0]<=0):
        raise GeometryError('Invalid finite ordered bounds for '+name)


@dataclass(frozen=True)
class SupportingTurn:
    after_index: int
    angle_bounds_deg: tuple[float,float] = (12.,55.)
    radius_m: float = 5.
    transition_m: float = .7

    def __post_init__(self):
        bounds(self.angle_bounds_deg,'supporting turn angle')
        if type(self.after_index) is not int or self.after_index<0:
            raise GeometryError('Supporting turn index must be nonnegative')
        if not all(math.isfinite(v) and v>0 for v in (self.radius_m,self.transition_m)):
            raise GeometryError('Supporting turn radius/ramp must be positive')
        lo,hi=self.angle_bounds_deg
        if lo<=0<=hi or max(abs(lo),abs(hi))>150 or min(abs(lo),abs(hi))*math.pi/180<=self.transition_m/self.radius_m+1e-5:
            raise GeometryError('Supporting angle bounds must have one sign and allow the fixed ramps')


@dataclass(frozen=True)
class LayoutTopology:
    name: str
    order: tuple[int,...]
    turns: tuple[SupportingTurn,...]

    def __post_init__(self):
        object.__setattr__(self,'order',tuple(self.order))
        object.__setattr__(self,'turns',tuple(self.turns))
        if not self.name or len({t.after_index for t in self.turns})!=len(self.turns):
            raise GeometryError('Topology needs a name and unique supporting slots')


@dataclass(frozen=True)
class ExtendedSpec:
    inventory: tuple[TechnicalRequest,...]
    vehicle: VehicleProfile
    topologies: tuple[LayoutTopology,...]
    target_lap_length_m: float = 350.
    lap_length_range_m: tuple[float,float] = (300.,450.)
    connector_length_bounds_m: tuple[float,float] = (.4,32.)
    width: WidthProfile = WidthProfile()
    candidate_budget: int = 6
    optimization_iterations: int = 70
    spacing_m: float = .08
    resolution_m_per_pixel: float = .05
    padding_m: float = 1.
    seam_offset_m: float = 1.7
    maximum_supporting_fraction: float = .4
    minimum_primary_coverage: float = .6
    minimum_useful_corner_m: float = .6
    maximum_offset_curvature: float = .95
    objectives: dict = field(default_factory=dict)
    limits: GeometryLimits = GeometryLimits()
    seed: int = 42
    variant: str = 'extended'
    category: str = 'long_technical'
    dataset_id: str = 'phase4b_pilot'
    matched_group: str | None = None
    generation_mode: str = 'composite'
    layout_version: str = LAYOUT_VERSION

    def __post_init__(self):
        inventory=tuple(self.inventory);topologies=tuple(self.topologies)
        if not 4<=len(inventory)<=32 or len({r.name for r in inventory})!=len(inventory):
            raise GeometryError('Extended inventory requires 4..32 uniquely named requests')
        if not isinstance(self.vehicle,VehicleProfile) or not isinstance(self.width,WidthProfile):
            raise GeometryError('Resolved local vehicle snapshot and width profile required')
        if self.generation_mode!='composite' or self.layout_version!=LAYOUT_VERSION:
            raise GeometryError('Extended layout version and explicit intent required')
        if not topologies or len({t.name for t in topologies})!=len(topologies):
            raise GeometryError('Unique explicit layout topologies required')
        for t in topologies:
            if sorted(t.order)!=list(range(len(inventory))) or any(s.after_index>=len(inventory) for s in t.turns):
                raise GeometryError('Topology order/turn slot is outside inventory')
        for name in ('target_lap_length_m','spacing_m','resolution_m_per_pixel','padding_m','minimum_useful_corner_m'):
            value=getattr(self,name)
            if isinstance(value,bool) or not math.isfinite(value) or value<=0:raise GeometryError('Invalid positive '+name)
        if not math.isfinite(self.seam_offset_m) or self.seam_offset_m<0:raise GeometryError('Invalid seam offset')
        bounds(self.lap_length_range_m,'lap length',positive=True)
        bounds(self.connector_length_bounds_m,'connector length',positive=True)
        if not self.lap_length_range_m[0]<=self.target_lap_length_m<=self.lap_length_range_m[1]:raise GeometryError('Target lap lies outside accepted range')
        for name in ('maximum_supporting_fraction','minimum_primary_coverage','maximum_offset_curvature'):
            value=getattr(self,name)
            if isinstance(value,bool) or not math.isfinite(value) or not 0<value<=1:raise GeometryError('Invalid fraction '+name)
        if type(self.seed) is not int or self.seed<0:raise GeometryError('Seed must be nonnegative')
        for name,lo,hi in [('candidate_budget',1,64),('optimization_iterations',1,200)]:
            if type(getattr(self,name)) is not int or not lo<=getattr(self,name)<=hi:raise GeometryError('Invalid bounded '+name)
        if set(self.objectives)-METRICS:raise GeometryError('Unknown extended objective')
        for key,value in self.objectives.items():bounds(value,key)
        if not isinstance(self.variant,str) or not self.variant or self.variant in {'.','..'} or any(c in self.variant for c in '/\\\x00') or not self.dataset_id:
            raise GeometryError('Safe variant and dataset identity required')
        object.__setattr__(self,'inventory',inventory);object.__setattr__(self,'topologies',topologies)

    def recipe(self):return dict(schema_version=1,generator=GENERATOR_VERSION,**asdict(self))

    @property
    def configuration_id(self):return canonical_hash(self.recipe())

    @property
    def track_id(self):return 'extended_'+self.configuration_id[:24]

    @property
    def centerline_configuration_id(self):
        data=self.recipe()
        for key in ('width','variant','category','dataset_id','matched_group','maximum_offset_curvature'):
            data.pop(key,None)
        data['objectives']={k:v for k,v in self.objectives.items() if k not in WIDTH_METRICS}
        return canonical_hash(data)


def load_vehicle_snapshot(path):
    data=json.loads(Path(path).read_text())
    if data.get('schema_version')!=1 or data.get('kind')!='resolved_vehicle_snapshot':raise GeometryError('Unsupported local resolved snapshot')
    return VehicleProfile(**data['vehicle'])


def spec_from_recipe(data):
    if not isinstance(data,dict) or data.get('schema_version')!=1 or data.get('generator')!=GENERATOR_VERSION:raise GeometryError('Unsupported extended recipe')
    data=dict(data)
    for key in ('schema_version','generator','achieved','files'):data.pop(key,None)
    try:
        data['inventory']=tuple(TechnicalRequest(**r) for r in data['inventory'])
        data['vehicle']=VehicleProfile(**data['vehicle']);data['width']=WidthProfile(**data['width'])
        data['limits']=GeometryLimits(**data.get('limits',{}))
        data['topologies']=tuple(LayoutTopology(t['name'],tuple(t['order']),tuple(SupportingTurn(**s) for s in t['turns'])) for t in data['topologies'])
        return ExtendedSpec(**data)
    except (TypeError,KeyError) as exc:raise GeometryError('Malformed extended recipe: '+str(exc)) from exc


def load_extended_spec(path):return spec_from_recipe(yaml.safe_load(Path(path).read_text()))
