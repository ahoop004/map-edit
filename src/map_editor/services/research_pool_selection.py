"""Small deterministic allocation repair over already validated candidates.

No geometry generation or policy changes. A shared node-visit budget bounds
scarcity-first placement, depth-two rehoming, and equal-coverage quality swaps.
"""
from itertools import combinations


def select_candidates(pools,conflicts,attributes,*,initial=None,max_visits=5000,max_passes=3):
    pools={slot:tuple(sorted(nodes)) for slot,nodes in sorted(pools.items())}
    conflicts={node:set(conflicts.get(node,())) for nodes in pools.values() for node in nodes}
    for node,neighbors in conflicts.items():
        if any(node not in conflicts.get(other,set()) for other in neighbors):raise ValueError('Conflict graph must be symmetric')
    capacities={}
    for slot,nodes in pools.items():
        capacities[slot]=max((len(group) for n in range(len(nodes)+1) for group in combinations(nodes,n)
            if all(b not in conflicts[a] for a,b in combinations(group,2))),default=0)
    visits=0;events=[];selection=dict(initial or {})
    def score(chosen):
        composite=[attributes[n] for n in chosen.values() if attributes[n]['composite']]
        return len(chosen),sum(a['repetition']<.65 for a in composite),-round(sum(a['repetition'] for a in composite),10)
    def options(slot,chosen):
        return sorted(pools[slot],key=lambda n:(
            sum(n in conflicts[v] for s,v in chosen.items() if s!=slot),
            attributes[n]['repetition'] if attributes[n]['composite'] else 0.,len(conflicts[n]),n))
    def scarcity(slot,chosen):
        available=[n for n in pools[slot] if all(n not in conflicts[v] for s,v in chosen.items() if s!=slot)]
        return len(available),capacities[slot],-sum(len(conflicts[n]) for n in pools[slot]),slot
    def place(slot,chosen,locked,depth,forced=None):
        nonlocal visits
        for node in ([forced] if forced is not None else options(slot,chosen)):
            if visits>=max_visits:return None
            visits+=1
            blockers=[s for s,v in chosen.items() if s!=slot and node in conflicts[v]]
            if any(s in locked for s in blockers) or len(blockers)>2 or blockers and depth==0:continue
            trial={s:v for s,v in chosen.items() if s!=slot and s not in blockers};trial[slot]=node
            for blocker in sorted(blockers,key=lambda s:scarcity(s,trial)):
                trial=place(blocker,trial,locked|{slot},depth-1)
                if trial is None:break
            if trial is not None:return trial
        return None
    def commit(new,kind):
        nonlocal selection
        changes=[dict(slot=s,old=selection.get(s),new=n) for s,n in sorted(new.items()) if selection.get(s)!=n]
        events.append(dict(kind=kind,coverage_before=len(selection),coverage_after=len(new),changes=changes))
        selection=new
    for s,n in selection.items():
        if s not in pools or n not in pools[s]:raise ValueError('Initial candidate is not in its slot pool')
    if any(b in conflicts[a] for a,b in combinations(selection.values(),2)):raise ValueError('Initial selection has conflicts')
    # Preserve capacity for scarce slots; score ties prefer low repetition.
    remaining=set(pools)-selection.keys()
    while remaining and visits<max_visits:
        slot=min(remaining,key=lambda s:scarcity(s,selection));remaining.remove(slot)
        proposed=place(slot,selection,set(),0)
        if proposed is not None:commit(proposed,'initial')
    for _ in range(max_passes):
        changed=False
        for slot in sorted(set(pools)-selection.keys(),key=lambda s:scarcity(s,selection)):
            proposed=place(slot,selection,set(),2)
            if proposed is not None and score(proposed)>score(selection):commit(proposed,'coverage_repair');changed=True
        # Equal-coverage replacement can rehome up to two blockers. It cannot
        # drop an allocated slot or lower the low-repetition composite count.
        for slot in sorted(selection,key=lambda s:(-attributes[selection[s]]['repetition'],s)):
            for node in options(slot,selection):
                if node==selection[slot]:continue
                proposed=place(slot,selection,set(),2,forced=node)
                if proposed is not None and score(proposed)>score(selection):commit(proposed,'quality_repair');changed=True
                if visits>=max_visits:break
            if visits>=max_visits:break
        if not changed or visits>=max_visits:break
    assert all(b not in conflicts[a] for a,b in combinations(selection.values(),2))
    replacements=sum(c['old'] is not None for e in events for c in e['changes'])
    return dict(selection=selection,events=events,node_visits=visits,max_node_visits=max_visits,
        budget_exhausted=visits>=max_visits,slot_independent_option_counts=capacities,
        candidate_replacements=replacements,score=score(selection))
