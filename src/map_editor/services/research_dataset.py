"""Deterministic resumable formal dataset coordinator; accepted bundles immutable."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path,PurePosixPath
from time import perf_counter
from map_editor.geometry import GeometryError
from .dataset_spec import DATASET_VERSION,SCALES,SPLIT_SCALES,DatasetSpec,load_dataset_spec,candidate_seed
from .research_spec import load_research_spec
from .research_design import candidate_spec
from .research_tracks import prepare_research,publish_research,ResearchGenerationError,validate_research_metadata
from .dataset_diversity import normalized_shape,screen,pair_metrics,classify_pair
from .technical_analysis import read_centerline
from .extended_spec import load_vehicle_snapshot
from .specialist_templates import canonical_hash,FAMILIES


def _json(path,value):
    raw=json.dumps(value,indent=2,allow_nan=False)+'\n';temporary=path.with_name('.'+path.name+'.tmp')
    temporary.write_text(raw);temporary.replace(path)


def safe_path(root,relative):
    p=PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or '\\' in relative:raise GeometryError('Dataset paths must be safe relative POSIX paths')
    target=root/p
    if not target.resolve().is_relative_to(root.resolve()):raise GeometryError('Dataset path escapes root')
    return target


def scale_of(length):
    for name,(lo,hi) in SCALES.items():
        if lo<=length and (length<=hi if name=='long' else length<hi):return name
    raise GeometryError('Measured lap outside dataset scale design ranges')


def verify_entry(root,entry,slot=None):
    root=Path(root)
    for name,checksum in entry['artifact_sha256'].items():
        path=safe_path(root,name)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=checksum:raise GeometryError('Dataset artifact checksum mismatch: '+name)
    metadata=json.loads(safe_path(root,entry['metadata']).read_text());validate_research_metadata(metadata)
    if metadata['provenance']['identity']!=entry['identity'] or metadata['provenance']['research_statistics']!=entry['statistics']:
        raise GeometryError('Manifest identity/statistics disagree with immutable metadata')
    native=load_research_spec(safe_path(root,entry['recipe']))
    if native.slot_id!=entry['slot_id'] or native.split!=entry['split'] or native.track_id!=entry['track_id']:raise GeometryError('Dataset entry/native identity mismatch')
    if (native.parent_lineage!=entry['parent_lineage'] or native.generation_mode!=entry['generation_mode'] or
        native.seed!=entry['seed'] or native.attempt!=entry['attempt']):raise GeometryError('Manifest lineage/mode/candidate identity differs from native recipe')
    if slot and (native.parent_lineage!=slot.parent_lineage or entry['scale']!=slot.scale or native.generation_mode!=slot.generation_mode or entry['split']!=slot.split or entry['target_family']!=slot.family or entry['complexity']!=slot.complexity):raise GeometryError('Dataset entry differs from preassigned slot')
    if slot and (native.target_family!=slot.family or (slot.complexity is not None and native.expected_primary_families!=slot.complexity)):
        raise GeometryError('Native family/complexity differs from dataset allocation')
    if scale_of(metadata['measured']['length_m'])!=entry['scale']:raise GeometryError('Dataset measured scale differs from assigned scale')
    validation=json.loads(safe_path(root,entry['validation']).read_text())
    expected={str((safe_path(root,entry['map']).parent/name).relative_to(root)) for name in validation['artifact_sha256']}
    expected.add(entry['validation'])
    if set(entry['artifact_sha256'])!=expected or validation['statistics']!=entry['statistics']:
        raise GeometryError('Manifest artifact coverage or validation statistics mismatch')
    if validation['recipe_replay']!=dict(status='passed',byte_identical=True,artifacts_compared=10):raise GeometryError('Dataset entry lacks native byte replay')
    return native


def _entry(root,slot,spec,bundle,screening):
    folder=bundle.parent;metadata_path=folder/(spec.track_id+'_metadata.json');report_path=folder/(spec.track_id+'_validation.json')
    metadata=json.loads(metadata_path.read_text());report=json.loads(report_path.read_text())
    checksums={str((folder/name).relative_to(root)):checksum for name,checksum in report['artifact_sha256'].items()}
    checksums[str(report_path.relative_to(root))]=hashlib.sha256(report_path.read_bytes()).hexdigest()
    return dict(slot_id=slot.slot_id,split=slot.split,generation_mode=slot.generation_mode,target_family=slot.family,
        complexity=slot.complexity,scale=slot.scale,parent_lineage=slot.parent_lineage,track_id=spec.track_id,
        map=str(bundle.relative_to(root)),metadata=str(metadata_path.relative_to(root)),recipe=str((folder/(spec.track_id+'_generation.yaml')).relative_to(root)),
        validation=str(report_path.relative_to(root)),seed=spec.seed,attempt=spec.attempt,
        identity=metadata['provenance']['identity'],statistics=report['statistics'],independence_screen=screening,
        artifact_sha256=checksums)


def quota_report(entries):
    return dict(count=len(entries),split_counts=dict(Counter(e['split'] for e in entries)),scale_counts=dict(Counter(e['scale'] for e in entries)),
        split_scale={s:dict(Counter(e['scale'] for e in entries if e['split']==s)) for s in SPLIT_SCALES},
        specialists={s:dict(Counter(e['target_family'] for e in entries if e['split']==s and e['generation_mode']=='specialist')) for s in SPLIT_SCALES},
        composites={s:dict(Counter(str(e['complexity']) for e in entries if e['split']==s and e['generation_mode']=='composite')) for s in SPLIT_SCALES})


def audit_dataset(root,*,require_complete=False,write=False):
    from .dataset_bundle_audit import audit_bundle
    root=Path(root);spec=load_dataset_spec(root/'dataset_recipe.json');manifest=json.loads((root/'manifest.json').read_text())
    if manifest['dataset_spec_sha256']!=spec.identity:raise GeometryError('Master manifest/root specification checksum mismatch')
    for key,name in [('calibration','calibration.json'),('readiness','readiness.json'),('snapshot','vehicle_snapshot.json')]:
        if hashlib.sha256((root/'development'/name).read_bytes()).hexdigest()!=manifest['evidence_sha256'][key]:raise GeometryError('Frozen development evidence checksum mismatch')
    entries=manifest['accepted'];slots={s.slot_id:s for s in spec.slots};shape_cache={};fingerprints=set();polygons=set();lineage_splits={};groups={};bundle_checks={}
    for entry in entries:
        if entry['slot_id'] not in slots:raise GeometryError('Unallocated dataset slot')
        native=verify_entry(root,entry,slots[entry['slot_id']]);identity=entry['identity']
        if native.seed!=candidate_seed(spec,slots[entry['slot_id']],native.attempt) or native.attempt>spec.max_attempts:
            raise GeometryError('Native candidate seed/budget differs from dataset protocol')
        bundle_checks[entry['slot_id']]=audit_bundle(root,entry)
        if identity['centerline_fingerprint'] in fingerprints or identity['coordinate_fingerprint'] in polygons:raise GeometryError('Exact duplicate dataset layout')
        fingerprints.add(identity['centerline_fingerprint']);polygons.add(identity['coordinate_fingerprint'])
        lineage_splits.setdefault(entry['parent_lineage'],set()).add(entry['split'])
        groups.setdefault(identity['near_duplicate_group'],set()).add(entry['split'])
        folder=safe_path(root,entry['map']).parent;shape_cache[entry['slot_id']]=normalized_shape(read_centerline(folder/(entry['track_id']+'_centerline.csv')))
    pairs=[]
    for i,a in enumerate(entries):
        for b in entries[i+1:]:
            metrics=pair_metrics(a['statistics'],b['statistics'],shape_cache[a['slot_id']],shape_cache[b['slot_id']]);status=classify_pair(metrics,spec.policy)
            pairs.append(dict(first=a['slot_id'],second=b['slot_id'],cross_split=a['split']!=b['split'],status=status,**metrics))
    leaked=[k for k,v in lineage_splits.items() if len(v)>1];group_leaks=[k for k,v in groups.items() if len(v)>1]
    not_independent=[p for p in pairs if p['status']!='independent_under_policy']
    complete=len(entries)==60 and len({e['slot_id'] for e in entries})==60
    evidence_checksums={}
    for path in sorted((root/'evidence').glob('*/*.json')):
        record=json.loads(path.read_text());slot=slots.get(record['slot_id'])
        if slot is None or record['candidate_seed']!=candidate_seed(spec,slot,record['attempt']) or not 1<=record['attempt']<=spec.max_attempts:
            raise GeometryError('Candidate evidence identity/seed mismatch')
        evidence_checksums[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
    previous_report=root/'integrity_report.json'
    if previous_report.exists():
        previous=json.loads(previous_report.read_text())
        for name,checksum in previous.get('candidate_evidence_sha256',{}).items():
            if evidence_checksums.get(name)!=checksum:raise GeometryError('Immutable candidate evidence checksum mismatch')
    if complete:
        for e in entries:
            record=json.loads((root/'evidence'/e['slot_id']/f"attempt_{e['attempt']:02d}.json").read_text())
            if record['status']!='accepted' or record['candidate_seed']!=e['seed']:raise GeometryError('Accepted candidate evidence mismatch')
    quotas=quota_report(entries)
    if complete:
        if set(e['slot_id'] for e in entries)!=set(slots):raise GeometryError('Complete manifest has wrong slots')
        for split in SPLIT_SCALES:
            if quotas['split_scale'][split]!=SPLIT_SCALES[split]:raise GeometryError('Measured split/scale quota failed')
            if quotas['specialists'][split]!={f:(4 if split=='train' else 1) for f in FAMILIES}:raise GeometryError('Measured specialist quota failed')
        comp=Counter(2 if e['complexity']==2 else 3 if e['complexity']==3 else 4 for e in entries if e['split']=='train' and e['generation_mode']=='composite')
        if comp!={2:6,3:8,4:6}:raise GeometryError('Training composite quota failed')
    if leaked or group_leaks or not_independent:raise GeometryError('Dataset independence or split leakage audit failed')
    for split in SPLIT_SCALES:
        expected=[e for e in entries if e['split']==split]
        if json.loads((root/(split+'_manifest.json')).read_text())['accepted']!=expected:raise GeometryError('Split manifest disagrees with master')
        if (root/(split+'_maps.txt')).read_text().splitlines()!=[e['map'] for e in expected]:raise GeometryError('Split path list disagrees with master')
    if (root/'all_maps.txt').read_text().splitlines()!=[e['map'] for e in entries]:raise GeometryError('Master path list mismatch')
    if require_complete and not complete:raise GeometryError('Dataset is explicitly partial; fewer than 60 accepted layouts')
    report=dict(generator=DATASET_VERSION,dataset_spec_sha256=spec.identity,complete=complete,quotas=quotas,
        unique_centerline_fingerprints=len(fingerprints),unique_polygon_fingerprints=len(polygons),
        cross_split_lineage_leaks=leaked,cross_split_near_group_leaks=group_leaks,near_duplicate_pairs=not_independent,
        pairwise_comparisons=pairs,policy=spec.policy,bundle_file_checks=bundle_checks,candidate_evidence_sha256=evidence_checksums,artifact_checksums='passed',physical_drivability='unassessed',driving_difficulty='unrated',
        held_out_topology_families=[],generalization_condition='shared broad topology families; independent geometric scaffolds and screened layouts')
    if 'selection_plan_id' in manifest:
        from .research_selection_plan import audit_selected_publication
        report['selection_plan_verification']=audit_selected_publication(root,manifest,spec)
    if write:_json(root/'integrity_report.json',report)
    return report


def _save_manifests(root,manifest):
    _json(root/'manifest.json',manifest)
    for split in SPLIT_SCALES:
        entries=[e for e in manifest['accepted'] if e['split']==split]
        _json(root/(split+'_manifest.json'),dict(generator=DATASET_VERSION,split=split,complete=manifest['complete'],accepted=entries))
        (root/(split+'_maps.txt')).write_text(''.join(e['map']+'\n' for e in entries))
    (root/'all_maps.txt').write_text(''.join(e['map']+'\n' for e in manifest['accepted']))


def generate_dataset(spec,output,*,snapshot,calibration,readiness,resume=False,max_requests=None,progress=None,profile_path=None):
    root=Path(output);calibration=Path(calibration);readiness=Path(readiness)
    if profile_path and Path(profile_path).exists():raise FileExistsError('Dataset runtime evidence is immutable')
    calibrated=json.loads(calibration.read_text());ready=json.loads(readiness.read_text())
    if calibrated['policy']!=spec.policy or not calibrated['frozen_before_formal_generation'] or not ready['complete']:raise GeometryError('Frozen development calibration and complete specialist readiness are required')
    evidence_hashes=dict(calibration=hashlib.sha256(calibration.read_bytes()).hexdigest(),readiness=hashlib.sha256(readiness.read_bytes()).hexdigest(),snapshot=hashlib.sha256(Path(snapshot).read_bytes()).hexdigest())
    if root.exists():
        if not resume:raise FileExistsError('Dataset exists; use explicit resume after integrity verification')
        saved=load_dataset_spec(root/'dataset_recipe.json')
        if saved.identity!=spec.identity:raise GeometryError('Resume cannot change the dataset recipe')
        manifest=json.loads((root/'manifest.json').read_text())
        if manifest['evidence_sha256']!=evidence_hashes:raise GeometryError('Resume cannot change calibration/readiness/vehicle evidence')
        audit_dataset(root)
        if manifest['complete']:return manifest
    else:
        root.mkdir(parents=True,exist_ok=False);_json(root/'dataset_recipe.json',spec.recipe())
        manifest=dict(generator=DATASET_VERSION,dataset_id=spec.dataset_id,dataset_spec_sha256=spec.identity,evidence_sha256=evidence_hashes,
            requested_tracks=60,complete=False,accepted=[],rejected=[],incomplete_requests=[s.slot_id for s in spec.slots],
            integration=dict(status='not_run',reason='strict_offline_dataset'))
        # Evidence is portable and self-contained, and never changes after root creation.
        (root/'development').mkdir();(root/'development/calibration.json').write_bytes(calibration.read_bytes());(root/'development/readiness.json').write_bytes(readiness.read_bytes());(root/'development/vehicle_snapshot.json').write_bytes(Path(snapshot).read_bytes())
        _save_manifests(root,manifest)
    vehicle=load_vehicle_snapshot(root/'development/vehicle_snapshot.json');shape_cache={};accepted_slots={e['slot_id'] for e in manifest['accepted']}
    for entry in manifest['accepted']:
        shape_cache[entry['slot_id']]=normalized_shape(read_centerline(safe_path(root,entry['map']).parent/(entry['track_id']+'_centerline.csv')))
    started=perf_counter();timings=[];processed=0
    for slot in spec.slots:
        if slot.slot_id in accepted_slots:continue
        if max_requests is not None and processed>=max_requests:break
        processed+=1;slot_dir=root/'tracks'/slot.slot_id;accepted=False
        # Recover a fully published bundle if interruption happened after its
        # atomic directory publication but before the manifest checkpoint.
        if slot_dir.exists():
            recipes=list(slot_dir.glob('*_generation.yaml'))
            if len(recipes)!=1:raise GeometryError('Unrecognized orphan directory; refusing overwrite')
            native=load_research_spec(recipes[0])
            expected=candidate_spec(spec,slot,native.attempt,vehicle)
            if native.configuration_id!=expected.configuration_id:raise GeometryError('Orphan bundle does not match deterministic slot candidate')
            prepared=prepare_research(native);ok,screening,shape=screen(prepared,manifest['accepted'],shape_cache,spec.policy)
            if not ok:raise GeometryError('Orphan bundle fails independence policy; refusing adoption')
            entry=_entry(root,slot,native,slot_dir/(native.track_id+'.yaml'),screening);verify_entry(root,entry,slot)
            evidence=root/'evidence'/slot.slot_id/f'attempt_{native.attempt:02d}.json'
            if not evidence.exists():
                evidence.parent.mkdir(parents=True,exist_ok=True)
                _json(evidence,dict(status='accepted',candidate_seed=native.seed,attempt=native.attempt,slot_id=slot.slot_id,native_recipe=native.recipe(),independence_screen=screening))
            manifest['accepted'].append(entry);accepted_slots.add(slot.slot_id);shape_cache[slot.slot_id]=shape;accepted=True
            if progress:progress('Recovered '+slot.slot_id)
        for attempt in range(1,spec.max_attempts+1):
            if accepted:break
            evidence=root/'evidence'/slot.slot_id/f'attempt_{attempt:02d}.json'
            if evidence.exists():
                saved=json.loads(evidence.read_text())
                if saved['candidate_seed']!=candidate_seed(spec,slot,attempt):raise GeometryError('Candidate evidence seed mismatch')
                if saved['status']=='rejected':continue
                raise GeometryError('Accepted evidence without recoverable bundle')
            begin=perf_counter();profile=dict(slot_id=slot.slot_id,attempt=attempt);native=None
            try:
                native=candidate_spec(spec,slot,attempt,vehicle);prepared=prepare_research(native,profile=profile)
                if scale_of(prepared.statistics['raw_lap_length_m'])!=slot.scale:raise GeometryError('Candidate crossed its half-open measured scale quota')
                ok,screening,shape=screen(prepared,manifest['accepted'],shape_cache,spec.policy)
                if not ok:
                    error=GeometryError('Geometric independence screen: '+screening['status']);error.screening=screening;raise error
                bundle=publish_research(native,slot_dir,prepared=prepared,profile=profile)
                entry=_entry(root,slot,native,bundle,screening);verify_entry(root,entry,slot)
                manifest['accepted'].append(entry);accepted_slots.add(slot.slot_id);shape_cache[slot.slot_id]=shape;accepted=True
                result=dict(status='accepted',candidate_seed=native.seed,attempt=attempt,slot_id=slot.slot_id,native_recipe=native.recipe(),independence_screen=screening)
                if progress:progress(f"Accepted {len(manifest['accepted'])}/60 {slot.slot_id} ({slot.scale}, attempt {attempt})")
            except (GeometryError,ValueError) as exc:
                result=dict(status='rejected',candidate_seed=candidate_seed(spec,slot,attempt),attempt=attempt,slot_id=slot.slot_id,
                    failure_stage='independence' if hasattr(exc,'screening') else 'geometry',reason=str(exc),
                    native_recipe=native.recipe() if native else None,layout_attempts=getattr(exc,'attempts',[]),screening=getattr(exc,'screening',None))
                manifest['rejected'].append({k:v for k,v in result.items() if k not in ('native_recipe','layout_attempts')})
                if progress:progress(f'Rejected {slot.slot_id} attempt {attempt}: {str(exc)[:140]}')
            evidence.parent.mkdir(parents=True,exist_ok=True)
            if evidence.exists():raise FileExistsError('Candidate evidence is immutable')
            _json(evidence,result);profile['candidate_total_seconds']=perf_counter()-begin;timings.append(profile)
            manifest['incomplete_requests']=[s.slot_id for s in spec.slots if s.slot_id not in accepted_slots];manifest['quotas']=quota_report(manifest['accepted']);_save_manifests(root,manifest)
        manifest['incomplete_requests']=[s.slot_id for s in spec.slots if s.slot_id not in accepted_slots];_save_manifests(root,manifest)
    audit=audit_dataset(root,write=True);manifest['complete']=audit['complete'];manifest['quotas']=audit['quotas'];_save_manifests(root,manifest)
    if profile_path:
        path=Path(profile_path)
        if path.exists():raise FileExistsError('Refusing to overwrite dataset runtime record')
        path.parent.mkdir(parents=True,exist_ok=True)
        _json(path,dict(total_seconds=perf_counter()-started,candidates=timings,accepted_this_invocation=sum(t.get('replay_seconds',0)>0 for t in timings)))
    return manifest


def publish_selected_dataset(plan_path,source,output,*,snapshot,calibration,resume=False,max_requests=None,slot_ids=None,progress=None):
    """Publish only the frozen Phase 5.2E selection; never search or substitute.

    Uses the existing bundle staging/replay, entry checks, checkpoints and orphan
    adoption. slot_ids/max_requests support a development-only partial test.
    """
    from .research_selection_plan import verify_plan,verify_prepared_selection,dataset_from_recipe
    from .research_spec import spec_from_recipe
    root=Path(output);source=Path(source) if source is not None else None;plan_path=Path(plan_path);snapshot=Path(snapshot);calibration=Path(calibration)
    if source is None and not resume:raise GeometryError('Fresh selected publication requires preflight source evidence')
    plan=json.loads(plan_path.read_text())
    pool_path=source/'preflight.json' if source is not None else root/'development/preflight_pool.json'
    protocol_path=source/'protocol.json' if source is not None else root/'development/preflight_protocol.json'
    pool=json.loads(pool_path.read_text());dataset=dataset_from_recipe(plan['dataset_spec']);vehicle=load_vehicle_snapshot(snapshot)
    if hashlib.sha256(pool_path.read_bytes()).hexdigest()!=plan['preflight_sha256'] or hashlib.sha256(protocol_path.read_bytes()).hexdigest()!=plan['protocol_sha256']:raise GeometryError('Source preflight evidence differs from frozen plan')
    if hashlib.sha256(snapshot.read_bytes()).hexdigest()!=plan['vehicle_snapshot_sha256']:raise GeometryError('Vehicle snapshot differs from frozen preflight')
    calibrated=json.loads(calibration.read_text())
    if calibrated['policy']!=dataset.policy or not calibrated['frozen_before_formal_generation']:raise GeometryError('Original frozen independence calibration required')
    verify_plan(plan,pool,vehicle)
    selected={e['slot_id']:e for e in plan['selected']};slots={s.slot_id:s for s in dataset.slots}
    if slot_ids is not None and (len(set(slot_ids))!=len(slot_ids) or set(slot_ids)-selected.keys()):raise GeometryError('Unallocated publication-test slots')
    requested=[s.slot_id for s in dataset.slots if slot_ids is None or s.slot_id in slot_ids]
    plan_file_sha=hashlib.sha256(plan_path.read_bytes()).hexdigest()
    ready=dict(complete=True,kind='frozen_v2_preflight_readiness',selection_plan_id=plan['plan_id'],slots=60,
        low_repetition_composites=pool['low_repetition_composites'],source_preflight_sha256=plan['preflight_sha256'])
    ready_bytes=(json.dumps(ready,indent=2,allow_nan=False)+'\n').encode()
    hashes=dict(calibration=hashlib.sha256(calibration.read_bytes()).hexdigest(),snapshot=hashlib.sha256(snapshot.read_bytes()).hexdigest(),readiness=hashlib.sha256(ready_bytes).hexdigest())
    if root.exists():
        if not resume:raise FileExistsError('Selected publication exists; explicit resume required')
        manifest=json.loads((root/'manifest.json').read_text())
        if manifest.get('selection_plan_id')!=plan['plan_id'] or manifest.get('selection_plan_file_sha256')!=plan_file_sha or manifest['evidence_sha256']!=hashes:raise GeometryError('Resume cannot change frozen publication inputs')
        audit_dataset(root)
        if manifest['complete']:return manifest
    else:
        root.mkdir(parents=True,exist_ok=False);(root/'development').mkdir()
        _json(root/'dataset_recipe.json',dataset.recipe());(root/'selection_plan.json').write_bytes(plan_path.read_bytes())
        (root/'selection_plan.sha256').write_text(plan_file_sha+'  selection_plan.json\n')
        (root/'selected_candidates.sha256').write_text(plan['selected_candidates_sha256']+'\n')
        (root/'development/vehicle_snapshot.json').write_bytes(snapshot.read_bytes());(root/'development/calibration.json').write_bytes(calibration.read_bytes())
        (root/'development/readiness.json').write_bytes(ready_bytes)
        (root/'development/preflight_pool.json').write_bytes(pool_path.read_bytes());(root/'development/preflight_protocol.json').write_bytes(protocol_path.read_bytes())
        rejected=[];unselected=[];chosen={e['candidate_name'] for e in plan['selected']}
        for record in pool['evidence']:
            if record['name'] in chosen:continue
            bucket='geometry_rejected' if record['status']=='geometry_rejected' else 'valid_unselected'
            path=root/'candidate_evidence'/bucket/record['slot_id']/f"attempt_{record['attempt']:02d}.json";path.parent.mkdir(parents=True,exist_ok=True);_json(path,record)
            (rejected if bucket=='geometry_rejected' else unselected).append(str(path.relative_to(root)))
        manifest=dict(generator=DATASET_VERSION,dataset_id=dataset.dataset_id,dataset_spec_sha256=dataset.identity,
            selection_plan_id=plan['plan_id'],selection_plan_file_sha256=plan_file_sha,selected_candidates_sha256=plan['selected_candidates_sha256'],
            evidence_sha256=hashes,requested_tracks=60,complete=False,accepted=[],rejected=rejected,valid_unselected=unselected,
            incomplete_requests=[s.slot_id for s in dataset.slots],integration=dict(status='not_run',reason='strict_offline_selected_publication'))
        _save_manifests(root,manifest)
    shape_cache={e['slot_id']:normalized_shape(read_centerline(safe_path(root,e['map']).parent/(e['track_id']+'_centerline.csv'))) for e in manifest['accepted']}
    done=set(shape_cache);processed=0
    for name in requested:
        if name in done:continue
        if max_requests is not None and processed>=max_requests:break
        processed+=1;expected=selected[name];slot=slots[name];native=spec_from_recipe(expected['native_recipe']);folder=root/'tracks'/name
        # Even recovery prepares only this frozen native recipe. No call to the
        # candidate generator occurs here and no fallback candidate is allowed.
        prepared=prepare_research(native);verify_prepared_selection(native,prepared,expected)
        ok,screening,shape=screen(prepared,manifest['accepted'],shape_cache,dataset.policy)
        if not ok:raise GeometryError('Frozen publication independence mismatch: '+str(screening))
        if folder.exists():
            recipes=list(folder.glob('*_generation.yaml'))
            if len(recipes)!=1 or load_research_spec(recipes[0]).configuration_id!=native.configuration_id:raise GeometryError('Orphan bundle differs from frozen selected recipe')
            bundle=folder/(native.track_id+'.yaml')
        else:bundle=publish_research(native,folder,prepared=prepared)
        entry=_entry(root,slot,native,bundle,screening);verify_entry(root,entry,slot)
        if entry['identity']!=expected['identity'] or entry['statistics']!=expected['statistics']:raise GeometryError('Published bundle changed selected identity/statistics')
        evidence=root/'evidence'/name/f'attempt_{native.attempt:02d}.json'
        record=dict(status='accepted',candidate_seed=native.seed,attempt=native.attempt,slot_id=name,
            selection_plan_id=plan['plan_id'],source_candidate_name=expected['candidate_name'],native_recipe=native.recipe(),independence_screen=screening)
        if evidence.exists():
            if canonical_hash(json.loads(evidence.read_text()))!=canonical_hash(record):raise GeometryError('Selected evidence is immutable')
        else:evidence.parent.mkdir(parents=True,exist_ok=True);_json(evidence,record)
        manifest['accepted'].append(entry);done.add(name);shape_cache[name]=shape
        manifest['incomplete_requests']=[s.slot_id for s in dataset.slots if s.slot_id not in done];manifest['quotas']=quota_report(manifest['accepted']);_save_manifests(root,manifest)
        if progress:progress(f'Published frozen candidate {len(done)}/60 {name} attempt {native.attempt}')
    audit=audit_dataset(root);manifest['complete']=audit['complete'];manifest['quotas']=audit['quotas'];_save_manifests(root,manifest)
    _json(root/'integrity_report.json',audit)
    return manifest
