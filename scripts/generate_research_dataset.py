#!/usr/bin/env python3
"""Generate, resume, audit or replay the formal offline Phase 5 research dataset."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from map_editor.services.dataset_spec import default_dataset_spec,load_dataset_spec
from map_editor.services.research_dataset import generate_dataset,audit_dataset,publish_selected_dataset
from map_editor.services.research_spec import load_research_spec
from map_editor.services.research_tracks import publish_research

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    generate=sub.add_parser('generate');generate.add_argument('--recipe',type=Path);generate.add_argument('--seed',type=int,default=20261108);generate.add_argument('--max-attempts',type=int,default=24)
    generate.add_argument('--resume',action='store_true');generate.add_argument('--max-requests',type=int);generate.add_argument('--profile',type=Path)
    generate.add_argument('--snapshot',type=Path,default=ROOT/'profiles/f110_resolved_phase3b.json')
    generate.add_argument('--calibration',type=Path,default=ROOT/'docs/phase5_calibration.json');generate.add_argument('--readiness',type=Path,default=ROOT/'docs/phase5_readiness.json')
    generate.add_argument('--output',type=Path,required=True)
    audit=sub.add_parser('audit');audit.add_argument('dataset',type=Path);audit.add_argument('--require-complete',action='store_true')
    replay=sub.add_parser('replay');replay.add_argument('recipe',type=Path);replay.add_argument('--output',type=Path,required=True)
    freeze=sub.add_parser('freeze-selection');freeze.add_argument('preflight',type=Path);freeze.add_argument('--output',type=Path,required=True)
    freeze.add_argument('--snapshot',type=Path,default=ROOT/'profiles/f110_resolved_phase3b.json')
    publish=sub.add_parser('publish-selection');publish.add_argument('plan',type=Path);publish.add_argument('--source',type=Path);publish.add_argument('--output',type=Path,required=True)
    publish.add_argument('--resume',action='store_true');publish.add_argument('--max-requests',type=int)
    publish.add_argument('--snapshot',type=Path,default=ROOT/'profiles/f110_resolved_phase3b.json');publish.add_argument('--calibration',type=Path,default=ROOT/'docs/phase5_calibration.json')
    a=p.parse_args()
    try:
        if a.command=='audit':
            r=audit_dataset(a.dataset,require_complete=a.require_complete,write=False);print(r['quotas']);return 0
        if a.command=='replay':print(publish_research(load_research_spec(a.recipe),a.output));return 0
        if a.command=='freeze-selection':
            from map_editor.services.research_selection_plan import freeze_selection
            print(freeze_selection(a.preflight,a.output,snapshot=a.snapshot)['plan_id']);return 0
        if a.command=='publish-selection':
            r=publish_selected_dataset(a.plan,a.source,a.output,snapshot=a.snapshot,calibration=a.calibration,resume=a.resume,max_requests=a.max_requests,progress=lambda s:print(s,flush=True))
            print(f"Frozen V2 publication {len(r['accepted'])}/60; complete={r['complete']}");return 0 if r['complete'] or a.max_requests is not None else 2
        recipe=a.recipe or (a.output/'dataset_recipe.json' if a.resume else None)
        spec=load_dataset_spec(recipe) if recipe else default_dataset_spec(a.seed,a.max_attempts)
        r=generate_dataset(spec,a.output,snapshot=a.snapshot,calibration=a.calibration,readiness=a.readiness,resume=a.resume,max_requests=a.max_requests,profile_path=a.profile,progress=lambda s:print(s,flush=True))
        print(f"Research dataset {len(r['accepted'])}/60; complete={r['complete']}; rejections={len(r['rejected'])}")
        return 0 if r['complete'] or a.max_requests is not None else 2
    except (ValueError,OSError) as exc:p.exit(1,str(exc)+'\n')
if __name__=='__main__':raise SystemExit(main())
