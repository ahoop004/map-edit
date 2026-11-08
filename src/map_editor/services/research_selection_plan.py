"""Frozen V2 publication plans verified against immutable preflight pool evidence."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import numpy as np
from map_editor.geometry import GeometryError
from .dataset_spec import DatasetSpec,DatasetSlot,DATASET_VERSION,candidate_seed
from .dataset_diversity import normalized_shape,pair_metrics,classify_pair
from .research_pool_selection import select_candidates
from .research_spec import spec_from_recipe
from .research_design import candidate_spec
from .specialist_templates import canonical_hash
from .extended_spec import load_vehicle_snapshot


def dataset_from_recipe(data):
    data=deepcopy(data)
    if data.pop('generator',None)!=DATASET_VERSION or data.pop('schema_version',None)!=1:raise GeometryError('Invalid frozen dataset recipe')
    data['slots']=tuple(DatasetSlot(**s) for s in data['slots'])
    return DatasetSpec(**data)


def plan_identity(plan):
    data=dict(plan);data.pop('plan_id',None)
    return canonical_hash(data)


def verify_plan(plan,pool,vehicle,*,source=None):
    """Read-only verification, no preparation, publication, reselection or tuning.

    Selector replay is a consistency check against the frozen result. It cannot
    change that result. Original review geometry is required when freezing only.
    """
    if plan.get('kind')!='frozen_v2_selection.v1' or plan.get('plan_id')!=plan_identity(plan):raise GeometryError('Frozen selection plan identity mismatch')
    dataset=dataset_from_recipe(plan['dataset_spec'])
    if dataset.design_version!='research_design.v2' or dataset.dataset_id!='phase5_v2':raise GeometryError('V2 plan requires explicit V2 dataset specification')
    if dataset.identity!=plan['dataset_spec_sha256'] or canonical_hash(pool['allocation'])!=canonical_hash(plan['dataset_spec']):raise GeometryError('Preflight/dataset specification mismatch')
    if pool['policy']!=dataset.policy or pool['filled']!=60 or not pool['allocation_complete']:raise GeometryError('Preflight is not a complete allocation under frozen policy')
    entries=plan['selected'];slots={s.slot_id:s for s in dataset.slots}
    if len(entries)!=60 or [e['slot_id'] for e in entries]!=[s.slot_id for s in dataset.slots]:raise GeometryError('Plan must contain all 60 slots in allocation order')
    if canonical_hash(entries)!=plan['selected_candidates_sha256']:raise GeometryError('Selected candidate list checksum mismatch')
    records=pool['evidence'];by_name={e['name']:e for e in records};valid={e['name']:e for e in records if e['status']=='geometry_valid'}
    if len(by_name)!=151 or len(valid)!=134 or len(records)-len(valid)!=17:raise GeometryError('Original preflight candidate counts differ')
    graph={name:set() for name in valid}
    for pair in pool['conflict_pairs']:
        graph[pair['first']].add(pair['second']);graph[pair['second']].add(pair['first'])
    pools={s.slot_id:[e['name'] for e in valid.values() if e['slot_id']==s.slot_id] for s in dataset.slots}
    attrs={name:dict(composite=e['generation_mode']=='composite',repetition=e['statistics']['repetition_fraction']) for name,e in valid.items()}
    replay=json.loads(json.dumps(select_candidates(pools,graph,attrs)))
    recorded={k:v for k,v in pool['selection_rounds'][-1].items() if k not in ('stage','attempted')}
    if replay!=recorded or plan['selection_evidence']!=recorded:raise GeometryError('Frozen selector evidence does not reproduce')
    selected_by_slot={e['slot_id']:e for e in pool['selected']}
    if len(selected_by_slot)!=60 or replay['selection']!={s:e['name'] for s,e in selected_by_slot.items()}:raise GeometryError('Selected records disagree with selector')
    shapes={};fingerprints=set();coordinates=set();source_checksums={}
    for entry in entries:
        slot=slots[entry['slot_id']];original=selected_by_slot[slot.slot_id]
        for key,value in dict(split=slot.split,scale=slot.scale,generation_mode=slot.generation_mode,family=slot.family,complexity=slot.complexity).items():
            if original[key]!=value:raise GeometryError('Preflight slot intent differs from allocation')
        if canonical_hash(original)!=entry['preflight_record_sha256'] or original!=by_name[entry['candidate_name']]:raise GeometryError('Frozen candidate differs from preflight record')
        native=spec_from_recipe(entry['native_recipe']);expected=candidate_spec(dataset,slot,entry['attempt'],vehicle)
        if native.configuration_id!=expected.configuration_id or native.configuration_id!=entry['native_recipe_sha256']:raise GeometryError('Selected native recipe differs from V2 specification')
        if native.track_id!=entry['track_id'] or native.seed!=candidate_seed(dataset,slot,entry['attempt']):raise GeometryError('Selected ID/seed mismatch')
        if (native.slot_id,native.split,native.parent_lineage,native.generation_mode,native.target_family)!=(slot.slot_id,slot.split,slot.parent_lineage,slot.generation_mode,slot.family):raise GeometryError('Selected lineage/split/family mismatch')
        if native.expected_primary_families!=(slot.complexity or 1):raise GeometryError('Selected complexity mismatch')
        from .research_dataset import scale_of
        stats=entry['statistics']
        if scale_of(stats['raw_lap_length_m'])!=slot.scale or stats['primary_family_count']!=(slot.complexity or 1):raise GeometryError('Preflight measured scale/family count mismatch')
        if stats['primary_coverage']<native.minimum_primary_coverage-1e-7 or stats['supporting_fraction']>native.maximum_supporting_fraction+1e-7:raise GeometryError('Preflight primary/support coverage mismatch')
        if canonical_hash(original['native_recipe'])!=native.configuration_id or original['identity']!=entry['identity'] or original['statistics']!=entry['statistics']:raise GeometryError('Selected native identity/statistics differ from preflight')
        identity=entry['identity']
        if identity['configuration_sha256']!=native.configuration_id or identity['centerline_fingerprint'] in fingerprints or identity['coordinate_fingerprint'] in coordinates:raise GeometryError('Selected configuration or exact uniqueness failure')
        fingerprints.add(identity['centerline_fingerprint']);coordinates.add(identity['coordinate_fingerprint'])
        if source is not None:
            folder=Path(source)/'candidates'/entry['candidate_name']
            metadata_path=folder/'metadata.json';review_path=folder/'review.npz'
            metadata=json.loads(metadata_path.read_text())
            if metadata['track_id']!=native.track_id or canonical_hash(metadata['requested']['research_specification'])!=native.configuration_id or metadata['provenance']['identity']!=identity or metadata['provenance']['research_statistics']!=entry['statistics']:raise GeometryError('Preflight review metadata mismatch')
            with np.load(review_path) as review:xy=review['xy'].copy()
            if canonical_hash(xy.tolist())!=entry['centerline_xy_sha256']:raise GeometryError('Preflight coordinate identity mismatch')
            shapes[slot.slot_id]=normalized_shape(xy)
            for path in (metadata_path,review_path):source_checksums[str(path.relative_to(source))]=hashlib.sha256(path.read_bytes()).hexdigest()
    low=sum(e['generation_mode']=='composite' and e['statistics']['repetition_fraction']<.65 for e in entries)
    if low<20:raise GeometryError('Selected low-repetition composite target not met')
    recorded_pairs=pool['retained_pairs']
    if len(recorded_pairs)!=1770:raise GeometryError('Preflight pair ledger is incomplete')
    expected_pairs={frozenset((a['candidate_name'],b['candidate_name'])) for i,a in enumerate(entries) for b in entries[i+1:]}
    if {frozenset((p['first'],p['second'])) for p in recorded_pairs}!=expected_pairs or any(classify_pair(p,dataset.policy)!='independent_under_policy' for p in recorded_pairs):raise GeometryError('Preflight pairwise independence ledger mismatch')
    if source is not None:
        for i,a in enumerate(entries):
            for b in entries[i+1:]:
                m=pair_metrics(a['statistics'],b['statistics'],shapes[a['slot_id']],shapes[b['slot_id']])
                if classify_pair(m,dataset.policy)!='independent_under_policy':raise GeometryError('Selected review geometry fails independence')
        if source_checksums!=plan['selected_source_sha256']:raise GeometryError('Frozen source review checksums mismatch')
    return dict(selected=60,pairs=1770,low_repetition_composites=low,selector_replay='identical',exact_unique_centerlines=60,
        split_counts=dict(Counter(e['split'] for e in entries)),scale_counts=dict(Counter(e['scale'] for e in entries)),native_specification_matches=60)


def freeze_selection(source,output,*,snapshot):
    from .research_dataset import _json
    source=Path(source);output=Path(output)
    if output.exists():raise FileExistsError('Frozen selection plan already exists')
    pool_path=source/'preflight.json';protocol_path=source/'protocol.json'
    pool=json.loads(pool_path.read_text());protocol=json.loads(protocol_path.read_text());dataset=dataset_from_recipe(pool['allocation'])
    if canonical_hash(protocol['allocation'])!=dataset.identity:raise GeometryError('Preflight protocol disagrees with allocation')
    by_slot={e['slot_id']:e for e in pool['selected']};selected=[];checksums={}
    for slot in dataset.slots:
        e=by_slot[slot.slot_id];native=spec_from_recipe(e['native_recipe']);folder=source/'candidates'/e['name']
        with np.load(folder/'review.npz') as review:xy=review['xy'].copy()
        for path in (folder/'metadata.json',folder/'review.npz'):checksums[str(path.relative_to(source))]=hashlib.sha256(path.read_bytes()).hexdigest()
        selected.append(dict(slot_id=slot.slot_id,candidate_name=e['name'],attempt=e['attempt'],seed=native.seed,
            track_id=native.track_id,native_recipe_sha256=native.configuration_id,native_recipe=native.recipe(),
            split=slot.split,scale=slot.scale,generation_mode=slot.generation_mode,target_family=slot.family,complexity=slot.complexity,
            parent_lineage=slot.parent_lineage,identity=e['identity'],statistics=e['statistics'],
            centerline_xy_sha256=canonical_hash(xy.tolist()),preflight_record_sha256=canonical_hash(e)))
    selection={k:v for k,v in pool['selection_rounds'][-1].items() if k not in ('stage','attempted')}
    plan=dict(kind='frozen_v2_selection.v1',dataset_spec=dataset.recipe(),dataset_spec_sha256=dataset.identity,
        preflight_sha256=hashlib.sha256(pool_path.read_bytes()).hexdigest(),protocol_sha256=hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
        vehicle_snapshot_sha256=hashlib.sha256(Path(snapshot).read_bytes()).hexdigest(),selected=selected,
        selected_candidates_sha256=canonical_hash(selected),selection_evidence=selection,selected_source_sha256=checksums)
    plan['plan_id']=plan_identity(plan)
    verify_plan(plan,pool,load_vehicle_snapshot(snapshot),source=source)
    output.parent.mkdir(parents=True,exist_ok=True);_json(output,plan)
    output.with_suffix('.sha256').write_text(hashlib.sha256(output.read_bytes()).hexdigest()+'  '+output.name+'\n')
    return plan


def verify_prepared_selection(native,prepared,selected):
    xy=[[p.x,p.y] for p in prepared.sampled.states[:-1]]
    if native.configuration_id!=selected['native_recipe_sha256'] or native.track_id!=selected['track_id']:raise GeometryError('Publication native identity differs from frozen selection')
    if canonical_hash(prepared.statistics)!=canonical_hash(selected['statistics']):raise GeometryError('Publication statistics differ from frozen preflight; refusing substitution')
    if canonical_hash(prepared.metadata['provenance']['identity'])!=canonical_hash(selected['identity']):raise GeometryError('Publication geometry identity differs from frozen preflight; refusing substitution')
    if canonical_hash(xy)!=selected['centerline_xy_sha256']:raise GeometryError('Publication centerline coordinates differ from frozen preflight')


def audit_selected_publication(root,manifest,spec):
    from .research_dataset import safe_path
    from .research_spec import load_research_spec
    from .technical_analysis import read_centerline
    root=Path(root);plan_path=root/'selection_plan.json';plan=json.loads(plan_path.read_text())
    if hashlib.sha256(plan_path.read_bytes()).hexdigest()!=manifest['selection_plan_file_sha256'] or plan['plan_id']!=manifest['selection_plan_id']:raise GeometryError('Published frozen plan checksum mismatch')
    pool_path=root/'development/preflight_pool.json';protocol=root/'development/preflight_protocol.json'
    if hashlib.sha256(pool_path.read_bytes()).hexdigest()!=plan['preflight_sha256'] or hashlib.sha256(protocol.read_bytes()).hexdigest()!=plan['protocol_sha256']:raise GeometryError('Published preflight evidence checksum mismatch')
    pool=json.loads(pool_path.read_text());verified=verify_plan(plan,pool,load_vehicle_snapshot(root/'development/vehicle_snapshot.json'))
    if spec.identity!=plan['dataset_spec_sha256']:raise GeometryError('Publication specification differs from frozen selection')
    selected={s['slot_id']:s for s in plan['selected']};published=manifest['accepted']
    if len({e['slot_id'] for e in published})!=len(published) or [e['slot_id'] for e in published]!=[s['slot_id'] for s in plan['selected'] if s['slot_id'] in {e['slot_id'] for e in published}]:raise GeometryError('Published candidate order/uniqueness differs from frozen plan')
    for e in published:
        expected=selected[e['slot_id']];native=load_research_spec(safe_path(root,e['recipe']))
        if native.configuration_id!=expected['native_recipe_sha256'] or e['track_id']!=expected['track_id'] or e['identity']!=expected['identity'] or e['statistics']!=expected['statistics']:raise GeometryError('Published candidate differs from frozen preflight')
        xy=read_centerline(safe_path(root,e['map']).parent/(e['track_id']+'_centerline.csv'))
        if canonical_hash(xy.tolist())!=expected['centerline_xy_sha256']:raise GeometryError('Serialized centerline differs from frozen preflight coordinates')
        ledger=json.loads((root/'evidence'/e['slot_id']/f"attempt_{e['attempt']:02d}.json").read_text())
        if ledger['status']!='accepted' or ledger['selection_plan_id']!=plan['plan_id'] or canonical_hash(ledger['native_recipe'])!=native.configuration_id:raise GeometryError('Published selected-candidate ledger mismatch')
    selected_names={e['candidate_name'] for e in plan['selected']};expected_files={};counts={'geometry_rejected':0,'valid_unselected':0}
    for record in pool['evidence']:
        if record['name'] in selected_names:continue
        bucket='geometry_rejected' if record['status']=='geometry_rejected' else 'valid_unselected';counts[bucket]+=1
        relative=f"candidate_evidence/{bucket}/{record['slot_id']}/attempt_{record['attempt']:02d}.json"
        path=safe_path(root,relative)
        if json.loads(path.read_text())!=record:raise GeometryError('Rejected/unselected candidate evidence changed')
        expected_files[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
    actual={str(p.relative_to(root)) for p in (root/'candidate_evidence').rglob('*.json')}
    if actual!=set(expected_files):raise GeometryError('Unexpected candidate evidence files')
    composite=[e for e in published if e['generation_mode']=='composite']
    low=[e['slot_id'] for e in composite if e['statistics']['repetition_fraction']<.65]
    if len(published)==60 and len(low)<20:raise GeometryError('Published composite repetition requirement failed')
    return dict(plan_id=plan['plan_id'],selected_candidates_sha256=plan['selected_candidates_sha256'],
        frozen_selection_verification=verified,published_matches=len(published),preflight_differences=[],
        candidate_evidence_counts=counts,candidate_evidence_sha256=expected_files,low_repetition_composites=len(low),
        high_repetition_composites=[e['slot_id'] for e in composite if e['statistics']['repetition_fraction']>.95],
        low_active_curvature_review_threshold=.25,
        low_active_curvature_composites=[dict(slot_id=e['slot_id'],active_curvature_fraction=e['statistics']['active_curvature_fraction']) for e in composite if e['statistics']['active_curvature_fraction']<.25])
