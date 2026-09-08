from types import SimpleNamespace as NS
from backend.app.geometry import v2
from backend.app.lateral_clearance import lateral_bay_clear


def test_registered_house_keeps_brace_and_its_body_outside():
    lattice=NS(levels=[NS(voids=[])],carved={0:[(2,2,10,8)]})
    assert not lateral_bay_clear(lattice,0,0,12,5,.08)
    assert not lateral_bay_clear(lattice,0,0,12,2,.08)
    assert lateral_bay_clear(lattice,0,0,12,1,.08)


def test_void_above_carved_base_also_keeps_its_storey_clear():
    lattice=NS(levels=[NS(voids=[]),NS(voids=[
        [v2(2,2),v2(10,2),v2(10,8),v2(2,8)]])],carved={})
    assert lateral_bay_clear(lattice,0,0,12,5,.08)
    assert not lateral_bay_clear(lattice,1,0,12,5,.08)
