"""Frozen 60-layout allocation, seeds, quotas and development-calibrated policy."""
from dataclasses import asdict,dataclass,field
import json
from pathlib import Path
from .specialist_templates import FAMILIES,canonical_hash
from map_editor.geometry import GeometryError

DATASET_VERSION='map_editor.research_dataset.v1'
SCALES={'short':(70.,140.),'medium':(140.,260.),'long':(260.,450.)}
SPLIT_SCALES={'train':{'short':12,'medium':15,'long':13},'validation':{'short':2,'medium':3,'long':3},'test':{'short':4,'medium':4,'long':4}}

@dataclass(frozen=True)
class DatasetSlot:
    slot_id: str
    split: str
    generation_mode: str
    family: str | None
    complexity: int | None
    scale: str
    design_seed: int
    parent_lineage: str

@dataclass(frozen=True)
class DatasetSpec:
    slots: tuple[DatasetSlot,...]
    root_seed: int=20261108
    max_attempts: int=24
    dataset_id: str='phase5_research_v1'
    policy: dict=field(default_factory=lambda:dict(version='development_screen.v1',
        normalized_shape_threshold=.055,relative_length_threshold=.15,relative_radius_threshold=.2,
        family_exposure_l1_threshold=.25,ambiguous_shape_threshold=.085,
        ambiguous_relative_length_threshold=.08,ambiguous_relative_curvature_threshold=.12,
        ambiguous_family_exposure_l1_threshold=.15))
    native_generator: str='map_editor.research_tracks.v1'
    design_version: str='research_design.v1'
    specialist_exposure: dict=field(default_factory=lambda:dict(straight=.70,hairpin=.70,sweeper=.80,chicane=.60,s_curve=.65))
    objective_ranges: dict=field(default_factory=lambda:dict(minimum_primary_coverage=.60,maximum_supporting_fraction=.40,
        minimum_composite_family_exposure=.025,maximum_composite_family_exposure=.78,
        minimum_usable_width_m=.7,maximum_curvature_rate_inv_m2=2.,minimum_target_active_fraction=.5))

    def __post_init__(self):
        object.__setattr__(self,'slots',tuple(self.slots))
        if type(self.root_seed) is not int or self.root_seed<0 or type(self.max_attempts) is not int or not 1<=self.max_attempts<=30:raise GeometryError('Invalid dataset seed or bounded attempt count')
        verify_allocation(self.slots)
        if set(self.specialist_exposure)!=set(FAMILIES) or any(not .5<=v<=1 for v in self.specialist_exposure.values()):raise GeometryError('Invalid specialist exposure specification')
        if self.native_generator!='map_editor.research_tracks.v1' or self.design_version not in ('research_design.v1','research_design.v2'):raise GeometryError('Unsupported dataset/native design version')
        required={'version','normalized_shape_threshold','relative_length_threshold','relative_radius_threshold','family_exposure_l1_threshold',
            'ambiguous_shape_threshold','ambiguous_relative_length_threshold','ambiguous_relative_curvature_threshold','ambiguous_family_exposure_l1_threshold'}
        if set(self.policy)!=required or self.policy['version']!='development_screen.v1':raise GeometryError('Unsupported independence policy')
        import math
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<v<=2 for k,v in self.policy.items() if k!='version'):
            raise GeometryError('Invalid finite independence thresholds')
        required_objectives={'minimum_primary_coverage','maximum_supporting_fraction','minimum_composite_family_exposure',
            'maximum_composite_family_exposure','minimum_usable_width_m','maximum_curvature_rate_inv_m2','minimum_target_active_fraction'}
        if set(self.objective_ranges)!=required_objectives:raise GeometryError('Explicit complete dataset objective ranges required')
        for key,value in self.objective_ranges.items():
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
                raise GeometryError('Invalid finite dataset objective '+key)
            if key not in ('minimum_usable_width_m','maximum_curvature_rate_inv_m2') and value>1:
                raise GeometryError('Dataset fraction objective exceeds one: '+key)
        if self.objective_ranges['minimum_composite_family_exposure']>self.objective_ranges['maximum_composite_family_exposure']:
            raise GeometryError('Inverted composite family exposure bounds')

    def recipe(self):return dict(schema_version=1,generator=DATASET_VERSION,**asdict(self))
    @property
    def identity(self):return canonical_hash(self.recipe())


def candidate_seed(spec,slot,attempt):
    return int(canonical_hash(dict(root=spec.root_seed,slot=slot.slot_id,attempt=attempt))[:15],16)


def verify_allocation(slots):
    from collections import Counter
    if len(slots)!=60 or len({s.slot_id for s in slots})!=60:raise GeometryError('Dataset allocation must contain exactly 60 distinct slots')
    if any(not isinstance(s.slot_id,str) or not s.slot_id or s.slot_id in ('.','..') or any(c in s.slot_id for c in '/\\\x00') or
           type(s.design_seed) is not int or s.design_seed<0 or not s.parent_lineage for s in slots):raise GeometryError('Invalid safe slot identity or design seed')
    if len({s.parent_lineage for s in slots})!=60:raise GeometryError('Parent scaffolds must be independently allocated')
    for split,count in [('train',40),('validation',8),('test',12)]:
        selected=[s for s in slots if s.split==split]
        if len(selected)!=count or Counter(s.scale for s in selected)!=SPLIT_SCALES[split]:raise GeometryError('Joint split/scale quota conflict: '+split)
        specialists=[s for s in selected if s.generation_mode=='specialist']
        expected=4 if split=='train' else 1
        if Counter(s.family for s in specialists)!={f:expected for f in FAMILIES}:raise GeometryError('Specialist family quota conflict: '+split)
        composites=[s for s in selected if s.generation_mode=='composite']
        if len(composites)!={'train':20,'validation':3,'test':7}[split]:raise GeometryError('Composite quota conflict: '+split)
        if split=='train' and Counter(2 if s.complexity==2 else 3 if s.complexity==3 else 4 for s in composites)!={2:6,3:8,4:6}:
            raise GeometryError('Training composite complexity quota conflict')
    if Counter(s.scale for s in slots)!={'short':18,'medium':22,'long':20}:raise GeometryError('Global scale quota conflict')
    if any(s.generation_mode not in ('specialist','composite') or s.scale not in SCALES or (s.generation_mode=='composite' and s.complexity not in (2,3,4,5)) for s in slots):raise GeometryError('Unsupported allocation slot')
    if any((s.generation_mode=='specialist' and (s.family not in FAMILIES or s.complexity is not None)) or
           (s.generation_mode=='composite' and s.family is not None) for s in slots):raise GeometryError('Allocation mode/family intent mismatch')


def default_dataset_spec(root_seed=20261108,max_attempts=24,*,design_version='research_design.v1'):
    slots=[]
    # Joint allocation is frozen before any final candidate is constructed.
    specialist_scales={
      'train':['short','medium','long','short','medium','long','medium','long','short','medium','long','short','medium','long','short','medium','long','short','medium','long'],
      'validation':['short','medium','long','medium','long'],
      'test':['short','long','medium','short','long']}
    composite_scales={'train':['short']*6+['medium']*8+['long']*6,
        'validation':['short','medium','long'],'test':['short']*2+['medium']*3+['long']*2}
    for split in ('train','validation','test'):
        for i,scale in enumerate(specialist_scales[split]):
            family=FAMILIES[i%5];slot=f'{split}_specialist_{family}_{i//5+1:02d}'
            seed=int(canonical_hash(dict(root=root_seed,slot=slot))[:15],16)
            slots.append(DatasetSlot(slot,split,'specialist',family,None,scale,seed,'lineage_'+canonical_hash(dict(scaffold_seed=seed,slot=slot))[:24]))
        for i,scale in enumerate(composite_scales[split]):
            complexity=[2,3,4,3,2,5,3,2,4,3,5,2,3,4,3,2,5,3,2,3][i] if split=='train' else ([2,3,5][i] if split=='validation' else [2,3,4,5,2,3,5][i])
            slot=f'{split}_composite_{i+1:02d}';seed=int(canonical_hash(dict(root=root_seed,slot=slot))[:15],16)
            slots.append(DatasetSlot(slot,split,'composite',None,complexity,scale,seed,'lineage_'+canonical_hash(dict(scaffold_seed=seed,slot=slot))[:24]))
    spec=DatasetSpec(tuple(slots),root_seed,max_attempts,design_version=design_version)
    if design_version=='research_design.v2':
        from dataclasses import replace
        spec=replace(spec,dataset_id='phase5_v2',specialist_exposure={f:.5 for f in FAMILIES},
            slots=tuple(replace(s,parent_lineage='research_design.v2:'+s.parent_lineage) for s in spec.slots))
    return spec


def load_dataset_spec(path):
    data=json.loads(Path(path).read_text())
    if data.get('generator')!=DATASET_VERSION or data.get('schema_version')!=1:raise GeometryError('Unsupported dataset recipe')
    data=dict(data);data.pop('schema_version');data.pop('generator');data['slots']=tuple(DatasetSlot(**s) for s in data['slots'])
    return DatasetSpec(**data)
