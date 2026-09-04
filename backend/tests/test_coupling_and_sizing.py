import math

import pytest

from backend.app.codes import (
    UNRESOLVED_JURISDICTION, JurisdictionProfile, gate_exterior_opening_area,
    gate_seismic_system,
)
from backend.app.coupling import (
    FACADE_DEMANDS, STRUCTURAL_SUPPLIES, demand_by_id, evaluate_program_structure,
    evaluate_structure_facade, program_by_id, run_code_screen, screen_project,
    supply_by_id,
)
from backend.app.loads import (
    OCCUPANCY_LIVE, LoadCase, composite_steel_deck, flat_roof_assembly,
    reduce_live_load,
)
from backend.app.optimizer import (
    FrameProblem, GaSettings, evaluate, optimise, steel_frame_space,
)
from backend.app.sections import MATERIALS, STEEL_BEAMS, STEEL_COLUMNS, i_section
from backend.app.sizing import (
    size_gravity_frame, steel_compression_capacity, steel_flexural_capacity,
)


LA = JurisdictionProfile(
    id='TEST-LA', status='resolved', adopted_building_code='IBC 2024 + CBC',
    sprinklered=True, risk_category=3, seismic_design_category='D',
    fire_separation_distance_m={'north': 2.0, 'south': 18.0, 'east': 9.0, 'west': 30.0},
)


# ---------------------------------------------------------------------------
# Section properties must match a hand calculation exactly
# ---------------------------------------------------------------------------

def test_i_section_properties_match_hand_calculation():
    section = i_section(500, 200, 10, 16, MATERIALS['steel_s355'])
    hw = 500 - 2 * 16
    assert section.area_mm2 == pytest.approx(2 * 200 * 16 + hw * 10)
    assert section.ix_mm4 == pytest.approx((200 * 500 ** 3 - 190 * hw ** 3) / 12, rel=1e-6)
    assert section.zx_mm3 == pytest.approx(200 * 16 * (500 - 16) + 10 * hw ** 2 / 4)
    assert section.sx_mm3 == pytest.approx(2 * section.ix_mm4 / 500)
    assert section.rx_mm == pytest.approx(
        math.sqrt(section.ix_mm4 / section.area_mm2), abs=1e-3)


def test_flexural_capacity_is_phi_fy_z():
    steel = MATERIALS['steel_s355']
    section = i_section(500, 200, 10, 16, steel)
    assert steel_flexural_capacity(section, steel) == pytest.approx(
        0.9 * steel.strength_mpa * section.zx_mm3 / 1e6, rel=1e-9)


def test_column_capacity_follows_the_aisc_e3_branches():
    steel = MATERIALS['steel_s355']
    stocky = i_section(300, 300, 12, 19, steel)
    short, short_detail = steel_compression_capacity(stocky, steel, 3.0)
    tall, tall_detail = steel_compression_capacity(stocky, steel, 12.0)
    assert short > tall
    assert short_detail['branch'].startswith('inelastic')
    assert tall_detail['branch'].startswith('elastic')
    # Euler stress must fall with the square of the slenderness
    assert tall_detail['fe_mpa'] == pytest.approx(
        short_detail['fe_mpa'] / 16.0, rel=1e-4)


# ---------------------------------------------------------------------------
# Loads
# ---------------------------------------------------------------------------

def test_dead_load_builds_up_from_the_modelled_layers():
    deck = composite_steel_deck(topping_m=0.075)
    concrete = 0.100 * MATERIALS['concrete_c30'].density_kn_m3
    assert deck.superimposed_dead_kpa() == pytest.approx(
        concrete + 0.15 + 0.30 + 0.35 + 0.72, abs=1e-6)


def test_lrfd_picks_the_governing_gravity_combination():
    heavy_live = LoadCase(dead_kpa=4.0, live_kpa=7.2)
    value, name = heavy_live.lrfd()
    assert name == '1.2D + 1.6L + 0.5Lr'
    assert value == pytest.approx(1.2 * 4.0 + 1.6 * 7.2)
    dead_only = LoadCase(dead_kpa=4.0, live_kpa=0.1)
    assert dead_only.lrfd()[1] == '1.4D'


def test_library_stacks_are_non_reducible_except_over_multiple_floors():
    stacks = OCCUPANCY_LIVE['library_stacks']
    single = reduce_live_load(stacks, 60.0, 'column', floors_supported=1)
    assert not single.permitted and single.factor == 1.0
    multi = reduce_live_load(stacks, 60.0, 'column', floors_supported=5)
    assert multi.permitted and multi.factor == pytest.approx(0.80)


def test_small_influence_area_gets_no_reduction():
    reading = OCCUPANCY_LIVE['library_reading']
    result = reduce_live_load(reading, 8.0, 'beam', floors_supported=1)
    assert not result.permitted
    assert result.influence_area_m2 == pytest.approx(16.0)


# ---------------------------------------------------------------------------
# Gate 1: program -> structure
# ---------------------------------------------------------------------------

def test_six_storey_library_cannot_be_a_tensile_membrane():
    """The decisive reason is not height: a membrane provides no occupied floors."""
    result = evaluate_program_structure(
        program_by_id('PRG-LIBRARY-MID-RISE'), supply_by_id('STR-SYS-TENSILE-MEMBRANE'))
    assert result.feasibility == 'infeasible'
    assert 'floor_plates' in result.failed_gates
    assert 'storey_count' in result.failed_gates
    assert result.burden == 'not_applicable'


def test_every_covering_system_fails_the_floor_plate_gate():
    program = program_by_id('PRG-LIBRARY-MID-RISE')
    for supply in STRUCTURAL_SUPPLIES:
        result = evaluate_program_structure(program, supply)
        if not supply.provides_occupied_floor_plates:
            assert 'floor_plates' in result.failed_gates, supply.system_id


def test_light_wood_frame_fails_on_storeys_span_and_load_together():
    result = evaluate_program_structure(
        program_by_id('PRG-LIBRARY-MID-RISE'), supply_by_id('STR-SYS-LIGHT-WOOD-FRAME'))
    assert set(result.failed_gates) >= {'storey_count', 'clear_span', 'floor_load'}


def test_mass_timber_survives_height_but_is_flagged_for_the_stack_load():
    result = evaluate_program_structure(
        program_by_id('PRG-LIBRARY-MID-RISE'),
        supply_by_id('STR-SYS-MASS-TIMBER-CLT-GLULAM'))
    assert result.feasibility == 'feasible'
    assert result.burden in ('minor_interfaces', 'significant_interfaces')
    load_axis = next(a for a in result.axes if a.axis == 'floor_load')
    assert load_axis.passed_gate and load_axis.score < 0.5
    assert 'open stacks' in (load_axis.mitigation or '')


def test_single_volume_pavilion_admits_covering_systems():
    result = evaluate_program_structure(
        program_by_id('PRG-PAVILION-SINGLE-VOLUME'),
        supply_by_id('STR-SYS-TENSILE-MEMBRANE'))
    assert 'floor_plates' not in result.failed_gates


# ---------------------------------------------------------------------------
# Gate 2: structure -> facade
# ---------------------------------------------------------------------------

def test_heavy_panel_facade_fails_three_independent_gates_on_a_membrane():
    result = evaluate_structure_facade(
        demand_by_id('FCD-03-BRUTALISM'), supply_by_id('STR-SYS-TENSILE-MEMBRANE'))
    assert result.feasibility == 'infeasible'
    assert set(result.failed_gates) == {'areal_mass', 'deflection', 'backup_type'}


def test_stiffness_is_checked_separately_from_strength():
    """A structure strong enough for the panel can still move too much for its joints."""
    demand = demand_by_id('FCD-08-MINIMALISM')          # 260 kg/m2, L/500
    supply = supply_by_id('STR-SYS-CABLE-NET-HYBRID')   # 60 kg/m2, L/150
    result = evaluate_structure_facade(demand, supply)
    deflection = next(a for a in result.axes if a.axis == 'deflection')
    assert not deflection.passed_gate
    assert 'L/150' in deflection.detail and 'L/500' in deflection.detail


def test_parametricism_sits_comfortably_on_a_double_curved_network():
    result = evaluate_structure_facade(
        demand_by_id('FCD-10-PARAMETRICISM'),
        supply_by_id('STR-SYS-STEEL-SPACE-FRAME-SHELL'))
    geometry = next(a for a in result.axes if a.axis == 'panel_geometry')
    assert geometry.score == 1.0
    assert result.feasibility == 'feasible'
    assert result.burden in ('clean', 'minor_interfaces')


def test_planar_glass_on_a_double_curved_host_is_penalised_not_blocked():
    result = evaluate_structure_facade(
        demand_by_id('FCD-01-INTERNATIONAL-STYLE'), supply_by_id('STR-SYS-RC-SHELL'))
    geometry = next(a for a in result.axes if a.axis == 'panel_geometry')
    assert geometry.score < 0.5 and geometry.passed_gate
    assert 'planarise' in (geometry.mitigation or '')


# ---------------------------------------------------------------------------
# Code layer: screens, never scores
# ---------------------------------------------------------------------------

def test_code_layer_does_not_change_any_physical_result():
    """A code exclusion must leave the physical numbers exactly as they were."""
    program = program_by_id('PRG-LIBRARY-MID-RISE')
    domain = screen_project(program, jurisdiction=LA)
    for option in domain.feasible + domain.excluded + domain.physically_infeasible:
        gate1 = evaluate_program_structure(program, supply_by_id(option.system_id))
        gate2 = evaluate_structure_facade(demand_by_id(option.grammar_id),
                                          supply_by_id(option.system_id))
        assert option.program_structure.resolution_burden == gate1.resolution_burden
        assert option.structure_facade.resolution_burden == gate2.resolution_burden
        assert option.failed_gates == gate1.failed_gates + gate2.failed_gates


def test_soft_axes_have_no_elimination_power():
    """A pile of small penalties must never remove a possible, lawful option."""
    domain = screen_project(program_by_id('PRG-LIBRARY-MID-RISE'), jurisdiction=LA)
    for option in domain.feasible:
        assert option.feasibility == 'feasible' and not option.failed_gates
    # every removal names a hard gate or a code rule, never a burden value
    for reasons in domain.eliminated_because().values():
        assert reasons


def test_feasible_set_is_not_ordered_by_burden():
    """Presentation must not imply a preference; selection is a later stage."""
    domain = screen_project(program_by_id('PRG-LIBRARY-MID-RISE'), jurisdiction=LA)
    burdens = [o.resolution_burden for o in domain.feasible]
    assert burdens != sorted(burdens)
    keys = [(o.system_id, o.grammar_id) for o in domain.feasible]
    assert keys == sorted(keys)


def test_an_unresolved_jurisdiction_can_never_return_pass():
    screen = run_code_screen(
        program_by_id('PRG-LIBRARY-MID-RISE'), supply_by_id('STR-SYS-STEEL-FRAME'),
        demand_by_id('FCD-03-BRUTALISM'), UNRESOLVED_JURISDICTION)
    assert all(r.status != 'pass' for r in screen.results)
    assert screen.incomplete


def test_placeholder_blocking_is_provisional_not_final():
    domain = screen_project(program_by_id('PRG-LIBRARY-MID-RISE'))
    assert not domain.jurisdiction_resolved
    assert domain.excluded == []
    for option in domain.feasible:
        assert option.admissibility == 'admissible_pending_code_inputs'


def test_tight_lot_line_removes_fully_glazed_grammars_only():
    domain = screen_project(program_by_id('PRG-LIBRARY-MID-RISE'), jurisdiction=LA)
    assert 'FCD-01-INTERNATIONAL-STYLE' not in domain.feasible_grammars
    assert 'FCD-03-BRUTALISM' in domain.feasible_grammars
    blocked = [o for o in domain.excluded
               if o.grammar_id == 'FCD-01-INTERNATIONAL-STYLE']
    assert blocked and all('IBC-705.8-OPENING-AREA-NORTH' in o.blocking_rules
                           for o in blocked)


def test_opening_gate_clamps_rather_than_blocks_when_the_grammar_can_go_solid():
    clamped = gate_exterior_opening_area((0.10, 0.45), 'north', LA)
    assert not clamped.blocking and clamped.status == 'warning'
    blocked = gate_exterior_opening_area((0.55, 0.90), 'north', LA)
    assert blocked.blocking and blocked.status == 'fail'


def test_seismic_gate_falls_back_to_a_permitted_lateral_system():
    """A CLT shear wall runs out of height in SDC D, so the mass timber building has to
    adopt a concrete core -- which the gate must say out loud."""
    result = gate_seismic_system('STR-SYS-MASS-TIMBER-CLT-GLULAM', 26.0, LA)
    assert not result.blocking
    assert 'rc_special_shear_wall' in result.message
    assert 'clt_shear_wall' in (result.mitigation or '')


# ---------------------------------------------------------------------------
# Sizing
# ---------------------------------------------------------------------------

def _library_frame(**overrides):
    deck, roof = composite_steel_deck(), flat_roof_assembly()
    kwargs = dict(
        bay_x_m=6.52, bay_y_m=7.12, joist_spacing_m=1.96, floor_to_floor_m=4.72,
        storeys=6, plan_x_m=36.0, plan_y_m=22.0,
        occupancy=OCCUPANCY_LIVE['library_stacks'],
        roof_occupancy=OCCUPANCY_LIVE['roof_ordinary'],
        superimposed_dead_kpa=deck.superimposed_dead_kpa(),
        roof_dead_kpa=roof.superimposed_dead_kpa(),
        beam_catalogue=STEEL_BEAMS, column_catalogue=STEEL_COLUMNS)
    kwargs.update(overrides)
    return size_gravity_frame(**kwargs)


def test_gravity_takedown_is_feasible_and_in_a_plausible_range():
    result = _library_frame()
    assert result.feasible
    assert 30.0 < result.steel_kg_per_m2 < 90.0
    assert all(check.max_ratio <= 1.0 for check in result.checks)


def test_every_selected_member_reports_its_governing_check():
    for check in _library_frame().checks:
        assert check.governing in {u.label for u in check.utilisations}
        assert check.validation_status == 'professional_review_required'
        assert check.assumptions


def test_heavier_occupancy_costs_more_steel():
    light = _library_frame(occupancy=OCCUPANCY_LIVE['office'])
    heavy = _library_frame(occupancy=OCCUPANCY_LIVE['library_stacks'])
    assert heavy.steel_kg_per_m2 > light.steel_kg_per_m2


def test_a_shallow_depth_limit_can_make_the_frame_infeasible():
    result = _library_frame(max_beam_depth_mm=200.0)
    assert not result.feasible
    assert result.failures


# ---------------------------------------------------------------------------
# Optimiser
# ---------------------------------------------------------------------------

SCORE_DATUMS = {'bay_x_m': 6.52, 'bay_y_m': 7.12,
                'joist_spacing_m': 1.96, 'floor_to_floor_m': 4.72}
PROBLEM = FrameProblem(storeys=6, plan_x_m=36.0, plan_y_m=22.0,
                       occupancy_id='library_stacks')
FAST = GaSettings(population=20, generations=8)


def test_optimiser_is_deterministic():
    space = steel_frame_space(SCORE_DATUMS)
    a = optimise(space, PROBLEM, settings=FAST)
    b = optimise(space, PROBLEM, settings=FAST)
    assert a.best.datums == b.best.datums
    assert a.best.fitness == b.best.fitness


def test_optimiser_never_returns_worse_than_the_score_proposal():
    result = optimise(steel_frame_space(SCORE_DATUMS), PROBLEM, settings=FAST)
    assert result.best.fitness >= result.baseline.fitness


def test_optimiser_stays_inside_the_declared_legal_ranges():
    space = steel_frame_space(SCORE_DATUMS)
    result = optimise(space, PROBLEM, settings=FAST)
    for gene in space.genes:
        assert gene.low <= result.best.datums[gene.name] <= gene.high


def test_score_fidelity_keeps_the_music_in_the_result():
    """Without a fidelity objective the search collapses to the cheapest frame and the
    score stops mattering. With it, the adopted datums stay near the proposal."""
    space = steel_frame_space(SCORE_DATUMS)
    result = optimise(space, PROBLEM, settings=FAST)
    assert result.best.objectives['score_fidelity'] > 0.85


def test_a_different_score_proposal_produces_a_different_building():
    tight = steel_frame_space({'bay_x_m': 5.7, 'bay_y_m': 5.7,
                               'joist_spacing_m': 1.55, 'floor_to_floor_m': 4.0})
    wide = steel_frame_space({'bay_x_m': 8.6, 'bay_y_m': 8.6,
                              'joist_spacing_m': 2.8, 'floor_to_floor_m': 5.2})
    a = optimise(tight, PROBLEM, settings=FAST).best
    b = optimise(wide, PROBLEM, settings=FAST).best
    assert a.datums['bay_x_m'] < b.datums['bay_x_m'] - 1.0
    assert a.sections != b.sections


def test_infeasible_genomes_are_rejected_not_silently_repaired():
    space = steel_frame_space(SCORE_DATUMS)
    shallow = FrameProblem(storeys=6, plan_x_m=36.0, plan_y_m=22.0,
                           occupancy_id='library_stacks', max_beam_depth_mm=200.0)
    from backend.app.optimizer import ObjectiveWeights
    result = evaluate(space.proposed(), space, shallow, ObjectiveWeights())
    assert not result.feasible and result.fitness < 0.0


# ---------------------------------------------------------------------------
# Elimination stage: cost is not a criterion yet
# ---------------------------------------------------------------------------

def test_cost_is_not_an_objective_at_the_elimination_stage():
    from backend.app.optimizer import ObjectiveWeights
    weights = ObjectiveWeights.elimination_stage()
    assert weights.material_efficiency == 0.0
    assert 'material_efficiency' not in weights.active()
    assert sum(weights.active().values()) == pytest.approx(1.0)


def test_selection_stage_scales_the_other_objectives_proportionally():
    from backend.app.optimizer import ObjectiveWeights
    base = ObjectiveWeights.elimination_stage()
    later = ObjectiveWeights.selection_stage(material_efficiency=0.26)
    assert later.material_efficiency == 0.26
    ratio = later.score_fidelity / later.constructability
    assert ratio == pytest.approx(base.score_fidelity / base.constructability, rel=1e-3)


def test_disabled_objective_cannot_leak_into_fitness():
    from backend.app.optimizer import ObjectiveWeights
    space = steel_frame_space(SCORE_DATUMS)
    light = FrameProblem(storeys=6, plan_x_m=36.0, plan_y_m=22.0, occupancy_id='office')
    heavy = FrameProblem(storeys=6, plan_x_m=36.0, plan_y_m=22.0,
                         occupancy_id='library_stacks')
    weights = ObjectiveWeights.elimination_stage()
    a = evaluate(space.proposed(), space, light, weights)
    b = evaluate(space.proposed(), space, heavy, weights)
    # the two use very different amounts of steel
    assert b.steel_kg_per_m2 > a.steel_kg_per_m2
    # but with cost switched off, only utilisation may separate their fitness
    assert a.objectives['score_fidelity'] == b.objectives['score_fidelity']
    assert a.objectives['constructability'] == b.objectives['constructability']


# ---------------------------------------------------------------------------
# Feasibility mapping is elimination work, not optimisation
# ---------------------------------------------------------------------------

def test_feasibility_map_covers_the_whole_legal_box_when_nothing_binds():
    from backend.app.optimizer import map_feasible_region
    result = map_feasible_region(steel_frame_space(SCORE_DATUMS), PROBLEM, resolution=4)
    assert result.verdict == 'broad'
    assert result.feasible_fraction == 1.0
    assert result.proposal_feasible
    assert all(r.fully_usable for r in result.gene_ranges)


def test_feasibility_map_narrows_the_legal_range_under_a_depth_limit():
    """The elimination-grade result a single-point check cannot give: physics has
    shrunk the usable part of a legal datum range."""
    from backend.app.optimizer import map_feasible_region
    shallow = FrameProblem(storeys=6, plan_x_m=36.0, plan_y_m=22.0,
                           occupancy_id='library_stacks', max_beam_depth_mm=350.0)
    result = map_feasible_region(steel_frame_space(SCORE_DATUMS), shallow, resolution=6)
    assert result.verdict == 'narrow'
    assert 0.0 < result.feasible_fraction < 0.35
    assert not result.proposal_feasible
    bay_x = next(r for r in result.gene_ranges if r.name == 'bay_x_m')
    assert bay_x.feasible_high < bay_x.legal_high
    assert result.binding_constraints


def test_feasibility_map_reports_a_system_that_cannot_serve_the_program():
    from backend.app.optimizer import map_feasible_region
    impossible = FrameProblem(storeys=6, plan_x_m=36.0, plan_y_m=22.0,
                              occupancy_id='library_stacks', max_beam_depth_mm=150.0)
    result = map_feasible_region(steel_frame_space(SCORE_DATUMS), impossible, resolution=4)
    assert result.verdict == 'no_feasible_design'
    assert result.feasible_count == 0
    assert all(r.feasible_low is None for r in result.gene_ranges)
