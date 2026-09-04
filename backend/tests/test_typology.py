"""The typology kit registry: a half-added typology fails loudly, a whole one agrees
with the modules that own its parts.

Before the registry, the parts of a typology lived in four files and failed four
different ways when one was missed -- two of them silently. These tests hold the deal
the registry makes: every typology the Literal names has a kit with every part, the
kit's references really are the owning modules' objects rather than copies that can
drift, and asking for a typology nobody registered is an error that names what it
knows instead of a KeyError three modules downstream.
"""

from typing import get_args

import pytest

from backend.app import typology
from backend.app.briefs import BRIEFS, TypologyId, brief_for
from backend.app.massing import MASSING_FAMILIES
from backend.app.typology import KITS, kit_for


def test_every_declared_typology_has_a_whole_kit():
    declared = set(get_args(TypologyId))
    assert set(KITS) == declared
    for name in declared:
        kit = kit_for(name)
        assert kit.brief, name
        assert kit.demand.program_id == kit.program_id, name
        assert kit.massing_bias in MASSING_FAMILIES, name
        assert kit.occupancy_group, name


def test_kit_brief_is_the_installed_brief_not_a_copy():
    # Editing THEATER_BRIEF must edit the kit: the registry is a lookup, not a home,
    # and a copy would let the two drift apart without either noticing.
    assert kit_for('theater').brief == tuple(BRIEFS['theater'])
    assert kit_for('theater').brief[0] is BRIEFS['theater'][0]


def test_unknown_typology_names_what_it_knows():
    with pytest.raises(KeyError, match='transit_hub'):
        kit_for('transit_hub')
    with pytest.raises(KeyError, match='library'):
        kit_for('transit_hub')


def test_build_refuses_a_spec_without_a_demand_row(monkeypatch):
    monkeypatch.setitem(typology._SPECS, 'library',
                        ('PRG-DOES-NOT-EXIST', 'MAS-SLAB', False, None))
    with pytest.raises(LookupError, match='PRG-DOES-NOT-EXIST'):
        typology._build()


def test_build_refuses_a_bias_that_is_not_a_family(monkeypatch):
    monkeypatch.setitem(typology._SPECS, 'library',
                        ('PRG-LIBRARY-MID-RISE', 'MAS-DIRIGIBLE', False, None))
    with pytest.raises(LookupError, match='MAS-DIRIGIBLE'):
        typology._build()


def test_loading_dock_follows_the_kit():
    # The rule moved out of a membership test in `support_spaces`; the observable
    # behaviour must not have moved with it.
    for name in get_args(TypologyId):
        types = {space.space_type for space in brief_for(name, storeys=4)}
        assert ('loading' in types) == kit_for(name).requires_loading_dock, name
