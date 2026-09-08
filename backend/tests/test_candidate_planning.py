from types import SimpleNamespace
import pytest

from backend.app.candidate_planning import composition_controls, plan_compact_candidate
from backend.app.legacy_program_layout import LegacyLayoutControls, LayoutRejected, hall_depth_for
from backend.tests.test_legacy_program_layout import _score


def test_dominant_hall_proportion_is_area_preserving_and_spatially_bounded():
    house = SimpleNamespace(area_m2=80, min_dimension_m=6)
    stage = SimpleNamespace(area_m2=30, min_dimension_m=4)
    depths = [hall_depth_for(house,stage,available_width=22.2,available_depth=12,
                            position=p) for p in (0,.5,1)]
    assert depths == pytest.approx([6,6.75,7.5])
    for depth in depths:
        assert house.area_m2/depth >= house.min_dimension_m
        assert stage.area_m2/depth >= stage.min_dimension_m
        assert (house.area_m2+stage.area_m2)/depth <= 22.2
    assert hall_depth_for(house,stage,available_width=22.2,available_depth=12) == 7.5
    with pytest.raises(LayoutRejected):
        hall_depth_for(house,stage,available_width=10,available_depth=5)


@pytest.mark.parametrize('confidence',[0,.15,.75,1])
def test_composition_keeps_confidence_clamp_and_does_not_change_other_controls(confidence):
    score = _score()
    dimension = next(d for d in score.dimensions if d.id=='variation')
    dimension.value=1
    dimension.confidence=confidence
    original = LegacyLayoutControls()
    changed,basis = composition_controls(score,original)
    assert changed.hall_depth_position == pytest.approx(round(.5-.5*min(1,confidence/.75),4))
    assert changed.model_dump(exclude={'hall_depth_position'}) == original.model_dump(exclude={'hall_depth_position'})
    assert original.hall_depth_position is None
    assert basis['confidence'] == confidence


def test_missing_variation_stays_fixture_and_neutral():
    score = _score()
    score.dimensions=[d for d in score.dimensions if d.id!='variation']
    controls,basis=composition_controls(score,LegacyLayoutControls())
    assert controls.hall_depth_position == .5
    assert basis['provenance'] == 'design_fixture'


def test_planning_budget_is_bounded():
    with pytest.raises(ValueError,match='one or two'):
        plan_compact_candidate(None,None,max_rounds=3)


@pytest.mark.parametrize('second_refuses',[False,True])
@pytest.mark.parametrize('joint_layout',[False,True])
def test_feedback_reauthors_reserve_without_changing_site_or_room_requirements(monkeypatch,second_refuses,joint_layout):
    from backend.app import candidate_planning as planner
    from backend.tests.test_legacy_program_layout import _brief
    from shapely.geometry import box

    brief = _brief()
    original = brief.model_dump(mode='json')
    seen=[]
    root_briefs=[]
    if joint_layout:
        from backend.app import joint_layout as roots
        from backend.app.joint_layout import JointRoot
        def propose(b,d,c,r):
            assert c.root_proposal is None
            root_briefs.append(b)
            if second_refuses and len(root_briefs)==2:
                raise LayoutRejected(['New root cannot fit revised field'])
            x0,y0,x1,y1=b.massing_limit_shape.bounds
            yield JointRoot(relation=r,hall_bounds=(x0,y0,x1,y1),
                primary_left=x0,primary_top=y1,secondary_right=x1,
                secondary_bottom=y0,arrival_top=y1,basis='Test root')
        monkeypatch.setattr(roots,'root_proposals',propose)
    class Volumes:
        grammar_reason=['test proposal']
        def __init__(self,b,c):
            self.brief=b
            self.circulation_intent=SimpleNamespace(arrival_assembly=SimpleNamespace(
                facade_allowance_m=c.arrival_facade_allowance_m))
        def digest(self): return str(len(seen))
        def model_dump(self,**kw): return {'proposal':len(seen)}
        def to_program_massing(self): return self
    def organize(score,typology,*,project_brief,legacy_controls):
        seen.append((project_brief,legacy_controls))
        if second_refuses and len(seen)==2:
            raise LayoutRejected(['Whole composition cannot fit the narrowed reserve'])
        return Volumes(project_brief,legacy_controls)
    allocation=SimpleNamespace(fits=True,required_area_m2=309,delivered_area_m2=309,
        unplaced=[],short=[],public_circulation=SimpleNamespace(unresolved={}))
    monkeypatch.setattr(planner,'organize_program_volumes',organize)
    monkeypatch.setattr(planner,'prepare_massing',lambda m,**kw:SimpleNamespace(
        lattice=m,datums=None,allocation=allocation,carve=None,family=None))
    monkeypatch.setattr(planner,'plan_building_systems',lambda **kw:dict(
        selection=SimpleNamespace(model_dump=lambda **kw:{}),envelope=None,spec=None))
    def facade(lattice,*args):
        shape=lattice.brief.massing_limit_shape.buffer(1.2,join_style=2)
        return SimpleNamespace(resolved_offset_m=1.2,
            levels=[SimpleNamespace(level_id='L01',weather_boundary=list(shape.exterior.coords),weather_voids=[])],
            model_dump=lambda **kw:{'offset':1.2})
    monkeypatch.setattr(planner,'facade_control_for',facade)
    result=plan_compact_candidate(_score(),brief,controls=LegacyLayoutControls(),
                                  joint_layout=joint_layout)
    root_refused=joint_layout and second_refuses
    assert len(seen)==(1 if root_refused else 2)
    revised=root_briefs[1] if root_refused else seen[1][0]
    controls=result.controls
    assert revised.site==brief.site
    assert revised.site_setbacks.setback_m==brief.site_setbacks.setback_m
    assert revised.site_setbacks.facade_projection_m==1.2
    assert revised.resolved_spaces()==brief.resolved_spaces()
    assert revised.massing_limit_shape.area < brief.massing_limit_shape.area
    assert controls.arrival_facade_allowance_m==1.2
    assert brief.model_dump(mode='json')==original
    assert result.attempts[0]['status']=='facade_spatial_reproposal'
    assert result.status==('form_unresolved' if second_refuses else 'spatially_coordinated')
    assert (result.volumes is None)==second_refuses
    if root_refused:
        assert result.attempts[1]['phase']=='root_proposal'
        assert result.attempts[1]['controls']['root_proposal'] is None
        assert result.controls.root_proposal is None
    assert result.attempts[1]['massing_limit_m2']==revised.massing_limit_shape.area


def test_weather_plane_check_uses_setback_polygon_not_its_bounding_box():
    from backend.app.facade_control import weather_plane_site_overflow
    from shapely.geometry import Polygon
    boundary=[(0,0),(8,0),(8,8),(4,8),(4,3),(0,3)]
    facade=SimpleNamespace(levels=[SimpleNamespace(level_id='L01',
        weather_boundary=[(1,4),(3,4),(3,6),(1,6)],weather_voids=[])])
    assert weather_plane_site_overflow(facade,Polygon(boundary))=={'L01':4.0}


def test_final_compiler_refuses_the_same_site_conflict_before_emission(monkeypatch):
    from backend.app import compiler_v3
    from backend.app.grammar_specs import spec_for
    from backend.app.tectonics import ENVELOPE_TECTONICS
    from backend.tests.test_facade_control import _lattice, _Datums
    from shapely.geometry import box
    systems=dict(selection=None,domain=None,frame=None,sizing=None,governing_occupancy=None,
        seismic_weight_kn=0,envelope=ENVELOPE_TECTONICS['ENV-PANEL-FIELD'],
        spec=spec_for('FCD-10-PARAMETRICISM'))
    monkeypatch.setattr(compiler_v3,'plan_building_systems',lambda **kw:systems)
    def forbidden(*args,**kwargs):
        pytest.fail('Member emission was reached after a weather-plane site conflict')
    monkeypatch.setattr(compiler_v3,'_assemble',forbidden)
    brief=SimpleNamespace(resolved_spaces=lambda:[],buildable_shape=box(0,0,10,8))
    with pytest.raises(ValueError,match='PV-FACADE-SITE'):
        compiler_v3._compile_from_lattice(score=None,datums=_Datums(envelope_offset_m=.5),
            lattice=_lattice(),allocation=None,carve=None,typology='theater',massing=None,
            massing_why=[],site=None,cutaway=False,pinned_massing=None,pinned_typology=None,
            grammar_id=None,project_brief=brief)
