"""Bounded allocation repair and diversity templates; no full geometry suite."""
from dataclasses import replace
from pathlib import Path
import math
import pytest
from map_editor.services.research_pool_selection import select_candidates
from map_editor.services.research_reliable_design import diverse_composite_spec
from map_editor.services.research_spec import spec_from_recipe
from map_editor.services.extended_spec import load_vehicle_snapshot
from map_editor.geometry import GeometryError


def attrs(nodes,repetitions=None):
    repetitions=repetitions or {}
    return {n:dict(composite=True,repetition=repetitions.get(n,.2)) for n in nodes}


def test_two_blockers_can_be_rehomed_without_losing_slots():
    pools={'a':['a0','a1'],'b':['b0','b1'],'c':['c0']}
    graph={'a0':{'c0'},'a1':set(),'b0':{'c0'},'b1':set(),'c0':{'a0','b0'}}
    result=select_candidates(pools,graph,attrs(graph),initial={'a':'a0','b':'b0'})
    assert result['selection']=={'a':'a1','b':'b1','c':'c0'}
    assert result['candidate_replacements']==2
    assert any(e['kind']=='coverage_repair' and e['coverage_after']==3 for e in result['events'])


def test_quality_swap_rehomes_a_blocker_at_equal_coverage():
    pools={'a':['a0','a1'],'b':['b0','b1']}
    graph={'a0':set(),'a1':{'b0'},'b0':{'a1'},'b1':set()}
    result=select_candidates(pools,graph,attrs(graph,{'a0':.99,'a1':.1,'b0':.1,'b1':.15}),initial={'a':'a0','b':'b0'})
    assert result['selection']=={'a':'a1','b':'b1'}
    assert result['score'][0:2]==(2,2)
    assert all(e['coverage_before']==e['coverage_after']==2 for e in result['events'])


def test_duplicate_alternatives_do_not_inflate_independent_capacity():
    pools={'a':['a0','a1'],'b':['b0','b1']}
    graph={'a0':{'a1'},'a1':{'a0'},'b0':set(),'b1':set()}
    result=select_candidates(pools,graph,attrs(graph))
    assert result['slot_independent_option_counts']=={'a':1,'b':2}
    assert result['events'][0]['changes'][0]['slot']=='a'
    assert len(result['selection'])==2


def test_selector_is_deterministic_and_budget_bounded():
    pools={'b':['b1','b0'],'a':['a1','a0']}
    graph={n:set() for n in ('a0','a1','b0','b1')}
    first=select_candidates(pools,graph,attrs(graph),max_visits=1)
    second=select_candidates({s:list(reversed(v)) for s,v in reversed(list(pools.items()))},graph,attrs(graph),max_visits=1)
    assert first==second and first['budget_exhausted'] and first['node_visits']==1
    assert len(first['selection'])==1


def test_unavoidable_conflicts_and_invalid_initial_selection():
    graph={'a0':{'b0'},'b0':{'a0'}};pools={'a':['a0'],'b':['b0']}
    assert len(select_candidates(pools,graph,attrs(graph))['selection'])==1
    with pytest.raises(ValueError,match='conflicts'):select_candidates(pools,graph,attrs(graph),initial={'a':'a0','b':'b0'})


@pytest.mark.parametrize('complexity',[2,3])
@pytest.mark.parametrize('scale',['short','medium','long'])
def test_technical_diversity_profiles_have_honest_families_and_heading_budgets(complexity,scale):
    vehicle=load_vehicle_snapshot(Path(__file__).resolve().parents[1]/'profiles/f110_resolved_phase3b.json')
    structural=[]
    for profile in range(6):
        try:spec=diverse_composite_spec(scale,complexity,profile,87000,vehicle)
        except GeometryError:continue
        families={r.family for r in spec.inventory}|({'straight'} if any(r.straight_after_m for r in spec.inventory) else set())
        assert len(families)==spec.expected_primary_families==complexity
        assert spec.assembly_method=='bounded_supporting_turns.v1'
        assert spec.minimum_primary_coverage==.6 and spec.maximum_supporting_fraction==.4
        source=sum(r.build().length_m+r.straight_after_m for r in spec.inventory)
        assert source/spec.target_lap_length_m>=.6
        heading=sum(r.build().at(r.build().length_m).heading for r in spec.inventory)
        turns=spec.topologies[0].turns
        assert sum(math.radians(t.angle_bounds_deg[0]) for t in turns)-1e-7<=math.tau-heading<=sum(math.radians(t.angle_bounds_deg[1]) for t in turns)+1e-7
        assert spec_from_recipe(spec.recipe()).configuration_id==spec.configuration_id
        assert spec.recipe()==diverse_composite_spec(scale,complexity,profile,87000,vehicle).recipe()
        assert spec.limits.minimum_usable_width_m==.7 and spec.limits.maximum_curvature_rate_inv_m2==2.
        structural.append([(r.family,r.parameters,r.straight_after_m) for r in spec.inventory])
    assert len(structural)>=3
    assert len({repr(v) for v in structural})==len(structural)
