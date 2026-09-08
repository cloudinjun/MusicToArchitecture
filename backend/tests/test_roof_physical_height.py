"""Physical cap checks must not use rounded, minimum-size display bounds."""
import pytest

from backend.app.geometry import ExtrusionGeometry, QuadGeometry, Vector3, v2, bounds
from backend.app.roof import roof_control_for, roof_geometry_max_z, validate_roof_emission


def test_fractional_coping_cap_reads_the_emitted_top_and_still_refuses_overflow():
    control=roof_control_for([(0,0),(12,0),(12,10),(0,10)],[],
        datum_z=17.5256,truss_depth_m=1.2178167966666666)
    geometry=ExtrusionGeometry(boundary=[v2(1,1),v2(2,1),v2(2,2),v2(1,2)],
        z_base=round(control.physical_top_z-.04,6),z_top=round(control.physical_top_z,6))
    centre,size=bounds(geometry)
    assert centre.z+size.z/2 > control.physical_top_z+1e-6
    assert roof_geometry_max_z(geometry)==geometry.z_top
    validate_roof_emission(control,[('coping',geometry)])
    overflowing=geometry.model_copy(update={'z_top':control.physical_top_z+2e-6})
    with pytest.raises(ValueError,match='excess'):
        validate_roof_emission(control,[('coping',overflowing)])


@pytest.mark.parametrize('thickness',[None,.002])
def test_quad_height_uses_vertices_plus_only_its_declared_thickness(thickness):
    top=12.3456789
    geometry=QuadGeometry(corners=[Vector3(x=x,y=y,z=top)
        for x,y in ((0,0),(1,0),(1,1),(0,1))])
    assert roof_geometry_max_z(geometry,thickness_m=thickness)==pytest.approx(
        top+(thickness or 0)/2,abs=1e-12)
