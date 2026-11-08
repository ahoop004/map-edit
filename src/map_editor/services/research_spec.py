"""Phase 5 native track recipes; prior recipe interpreters are unchanged."""
from dataclasses import asdict,dataclass,field
import math
from pathlib import Path
import yaml
from map_editor.geometry import GeometryError,straight,hairpin,sweeper,chicane,s_curve
from map_editor.geometry.technical import technical_corner
from map_editor.geometry.validation import GeometryLimits,VehicleProfile
from map_editor.geometry.width_profile import WidthProfile
from .extended_spec import LayoutTopology,SupportingTurn,METRICS,bounds
from .specialist_templates import FAMILIES,canonical_hash

GENERATOR_VERSION='map_editor.research_tracks.v1'
TEMPLATE_VERSION='scaled_maneuver_inventory.v1'
BUILDERS=dict(straight=straight,hairpin=hairpin,sweeper=sweeper,chicane=chicane,s_curve=s_curve,
    corner=technical_corner,kink=lambda **p:technical_corner(kind='kink',**p),
    compound_corner=lambda **p:technical_corner(kind='compound_corner',**p))

@dataclass(frozen=True)
class ResearchFeature:
    name: str
    family: str
    parameters: dict
    straight_after_m: float=0.

    def __post_init__(self):
        if not self.name or self.family not in BUILDERS or not isinstance(self.parameters,dict):raise GeometryError('Unsupported named research feature')
        if not math.isfinite(self.straight_after_m) or self.straight_after_m<0:raise GeometryError('Invalid fixed primary straight')
        self.build()

    def build(self):
        try:return BUILDERS[self.family](**self.parameters)
        except TypeError as exc:raise GeometryError('Invalid feature parameters: '+str(exc)) from exc

@dataclass(frozen=True)
class ResearchSpec:
    inventory: tuple[ResearchFeature,...]
    vehicle: VehicleProfile
    topologies: tuple[LayoutTopology,...]
    target_lap_length_m: float
    lap_length_range_m: tuple[float,float]
    split: str
    slot_id: str
    parent_lineage: str
    topology_family: str
    generation_mode: str='composite'
    target_family: str | None=None
    minimum_target_exposure: float=.7
    expected_primary_families: int=2
    minimum_family_exposure: float=.025
    maximum_family_exposure: float=.78
    connector_length_bounds_m: tuple[float,float]=(.3,80.)
    width: WidthProfile=WidthProfile()
    candidate_budget: int=3
    optimization_iterations: int=80
    spacing_m: float=.12
    resolution_m_per_pixel: float=.06
    padding_m: float=1.
    seam_offset_m: float=1.7
    maximum_supporting_fraction: float=.4
    minimum_primary_coverage: float=.6
    minimum_useful_corner_m: float=.6
    maximum_offset_curvature: float=.95
    objectives: dict=field(default_factory=dict)
    limits: GeometryLimits=GeometryLimits()
    seed: int=42
    attempt: int=1
    dataset_id: str='phase5_research_v1'
    template_version: str=TEMPLATE_VERSION
    layout_version: str='bounded_supporting_turns.v1'
    assembly_method: str='bounded_supporting_turns.v1'
    support_gap_m: float=.3
    minimum_target_active_fraction: float=.5
    design_version: str='research_design.v1'

    def __post_init__(self):
        object.__setattr__(self,'inventory',tuple(self.inventory));object.__setattr__(self,'topologies',tuple(self.topologies))
        if self.design_version not in ('research_design.v1','research_design.v2'):raise GeometryError('Unsupported research design version')
        if not 2<=len(self.inventory)<=40 or len({r.name for r in self.inventory})!=len(self.inventory):raise GeometryError('Research inventory requires 2..40 named features')
        if self.generation_mode not in ('specialist','composite') or self.split not in ('train','validation','test'):raise GeometryError('Explicit research intent and split required')
        if self.template_version!=TEMPLATE_VERSION or self.layout_version!='bounded_supporting_turns.v1':raise GeometryError('Unsupported research template/layout version')
        if self.assembly_method not in ('bounded_supporting_turns.v1','controlled_halfturn.v1') or not math.isfinite(self.support_gap_m) or self.support_gap_m<=0:raise GeometryError('Unsupported assembly method/gap')
        if self.generation_mode=='specialist' and (self.target_family not in FAMILIES or not .5<=self.minimum_target_exposure<=1):raise GeometryError('Specialist family and dominance threshold required')
        if self.generation_mode=='composite' and (self.target_family is not None or not 2<=self.expected_primary_families<=5):raise GeometryError('Composite family-count intent required')
        if not self.topologies or len({t.name for t in self.topologies})!=len(self.topologies):raise GeometryError('Unique topologies required')
        for t in self.topologies:
            if sorted(t.order)!=list(range(len(self.inventory))) or any(s.after_index>=len(self.inventory) for s in t.turns):raise GeometryError('Invalid research topology')
        bounds(self.lap_length_range_m,'lap',positive=True);bounds(self.connector_length_bounds_m,'support length',positive=True)
        if not self.lap_length_range_m[0]<=self.target_lap_length_m<=self.lap_length_range_m[1]:raise GeometryError('Source target outside scale bounds')
        for name in ('spacing_m','resolution_m_per_pixel','padding_m','minimum_useful_corner_m'):
            if not math.isfinite(getattr(self,name)) or getattr(self,name)<=0:raise GeometryError('Invalid positive '+name)
        for name in ('minimum_primary_coverage','maximum_supporting_fraction','minimum_family_exposure','maximum_family_exposure','maximum_offset_curvature','minimum_target_active_fraction'):
            if not math.isfinite(getattr(self,name)) or not 0<getattr(self,name)<=1:raise GeometryError('Invalid fraction '+name)
        if type(self.seed) is not int or self.seed<0 or type(self.attempt) is not int or self.attempt<1:raise GeometryError('Invalid candidate identity')
        if type(self.candidate_budget) is not int or not 1<=self.candidate_budget<=16 or type(self.optimization_iterations) is not int or not 1<=self.optimization_iterations<=200:raise GeometryError('Invalid bounded search budget')
        if not self.parent_lineage or not self.slot_id or any(c in self.slot_id for c in '/\\\x00') or self.slot_id in ('.','..'):raise GeometryError('Stable safe slot and parent lineage required')
        if set(self.objectives)-METRICS:raise GeometryError('Unknown geometric objective')
        for key,value in self.objectives.items():bounds(value,key)

    def recipe(self):
        data=asdict(self)
        # The absent V1 key is part of the frozen native identity/byte contract.
        if self.design_version=='research_design.v1':data.pop('design_version')
        return dict(schema_version=1,generator=GENERATOR_VERSION,**data)
    @property
    def configuration_id(self):return canonical_hash(self.recipe())
    @property
    def track_id(self):return 'research_'+self.configuration_id[:24]


def spec_from_recipe(data):
    if not isinstance(data,dict) or data.get('generator')!=GENERATOR_VERSION or data.get('schema_version')!=1:raise GeometryError('Unsupported research native recipe')
    data=dict(data)
    for key in ('schema_version','generator','achieved','files'):data.pop(key,None)
    try:
        data['inventory']=tuple(ResearchFeature(**r) for r in data['inventory'])
        data['vehicle']=VehicleProfile(**data['vehicle']);data['width']=WidthProfile(**data['width']);data['limits']=GeometryLimits(**data['limits'])
        data['topologies']=tuple(LayoutTopology(t['name'],tuple(t['order']),tuple(SupportingTurn(**s) for s in t['turns'])) for t in data['topologies'])
        return ResearchSpec(**data)
    except (KeyError,TypeError) as exc:raise GeometryError('Malformed research native recipe: '+str(exc)) from exc

def load_research_spec(path):return spec_from_recipe(yaml.safe_load(Path(path).read_text()))
