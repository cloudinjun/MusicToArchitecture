"""Data-owned configuration for the integrated library demonstration.

Legacy references (read-only):
``architecture_automation_pipeline/program_generator/OpenAI_ProgramDetails.py``,
``EllipseAgent.py``, and ``Blender/structural_generator.py``.  This module retains
only the neutral ideas of explicit support rooms, relationship graphs, non-overlap,
column exclusions, load-path continuity, and semantic reasons.  Legacy coordinates,
program names, dimensions, materials, and form language are intentionally excluded.
"""

from __future__ import annotations


DESIGN_VERSION = "library-steel-international-v1"

LIBRARY_SPACE_SPECS = (
    # id, name, type, category, access, x0, x1, y0, y1, height, exterior faces
    ("SP-L01-COMMUNITY-001", "Community room", "community_room", "public", "public", -15.0, -9.0, -8.0, -3.4, 4.6, ("south", "west")),
    ("SP-L01-VESTIBULE-001", "Entry vestibule", "entry_vestibule", "circulation", "public", -9.0, -7.0, -8.0, -3.4, 4.8, ("south",)),
    ("SP-L01-LOBBY-001", "Lobby and welcome", "lobby_welcome_checkout", "circulation", "public", -7.0, -3.0, -8.0, -3.4, 5.2, ("south",)),
    ("SP-L01-CHILDREN-001", "Children reading", "children_reading", "public", "public", -3.0, 4.0, -8.0, -3.4, 4.8, ("south",)),
    ("SP-L01-GROUP-001", "Group study", "group_study", "public", "public", 4.0, 9.0, -8.0, -3.4, 4.4, ("south",)),
    ("SP-L01-DIGITAL-001", "Digital learning", "digital_learning", "public", "public", 9.0, 15.0, -8.0, -3.4, 4.8, ("south", "east")),
    ("SP-L01-SPINE-001", "Primary circulation spine", "primary_circulation", "circulation", "public", -15.0, 15.0, -3.4, -0.6, 3.6, ("west", "east")),
    ("SP-L01-ADULT-001", "Adult reading room", "adult_reading", "public", "public", -15.0, -7.0, -0.6, 6.0, 6.6, ("west",)),
    ("SP-L01-STACKS-001", "Open stacks", "open_stacks", "public", "public", -7.0, 2.0, -0.6, 6.0, 5.6, ()),
    ("SP-L01-PERIODICALS-001", "Periodicals and media", "periodicals_media", "public", "public", 2.0, 8.0, -0.6, 6.0, 5.2, ()),
    ("SP-L01-QUIET-001", "Quiet reading room", "quiet_reading", "public", "public", 8.0, 15.0, -0.6, 6.0, 6.2, ("east",)),
    ("SP-L01-STAFF-001", "Staff workroom", "staff_workroom", "private", "staff", -15.0, -10.0, 6.0, 9.0, 3.8, ("north", "west")),
    ("SP-L01-ADMIN-001", "Administration", "administration", "private", "staff", -10.0, -7.0, 6.0, 9.0, 3.8, ("north",)),
    ("SP-L01-PROCESSING-001", "Collection processing", "collection_processing", "service", "service", -7.0, -2.0, 6.0, 9.0, 3.8, ("north",)),
    ("SP-L01-STORAGE-001", "Secure storage", "secure_storage", "service", "restricted", -2.0, 1.0, 6.0, 9.0, 3.8, ("north",)),
    ("SP-L01-RESTROOM-PUBLIC-001", "Public restrooms", "public_restroom", "service", "public", 1.0, 5.0, 6.0, 9.0, 3.8, ("north",)),
    ("SP-L01-RESTROOM-STAFF-001", "Staff restroom", "staff_restroom", "service", "staff", 5.0, 7.0, 6.0, 9.0, 3.8, ("north",)),
    ("SP-L01-JANITOR-001", "Janitor closet", "janitor", "service", "service", 7.0, 9.0, 6.0, 9.0, 3.8, ("north",)),
    ("SP-L01-ELECTRICAL-001", "Electrical and IT", "electrical_it", "service", "restricted", 9.0, 11.0, 6.0, 9.0, 3.8, ("north",)),
    ("SP-L01-MECHANICAL-001", "Mechanical room", "mechanical_room", "service", "service", 11.0, 13.0, 6.0, 9.0, 3.8, ("north",)),
    ("SP-L01-RECEIVING-001", "Loading and receiving", "loading_receiving", "service", "service", 13.0, 15.0, 6.0, 9.0, 3.8, ("north", "east")),
)

PROGRAM_RELATION_SPECS = (
    ("REL-ARRIVAL-001", "SP-L01-VESTIBULE-001", "SP-L01-LOBBY-001", "must_connect", "PRG-LIB-ARRIVAL-001", "Arrival reaches the staffed welcome point."),
    ("REL-PUBLIC-SPINE-001", "SP-L01-LOBBY-001", "SP-L01-SPINE-001", "public_connect", "PRG-LIB-PUBLIC-GRAPH-001", "Lobby joins the primary public circulation spine."),
    ("REL-CHILDREN-RESTROOM-001", "SP-L01-CHILDREN-001", "SP-L01-RESTROOM-PUBLIC-001", "accessible_connect", "PRG-LIB-RESTROOM-001", "Children reading has a traceable accessible route to public restrooms."),
    ("REL-AFTER-HOURS-001", "SP-L01-COMMUNITY-001", "SP-L01-VESTIBULE-001", "must_connect", "PRG-LIB-AFTER-HOURS-001", "Community room can operate from the entry zone without opening all collection areas."),
    ("REL-BOOK-RETURN-001", "SP-L01-LOBBY-001", "SP-L01-PROCESSING-001", "service_connect", "PRG-LIB-BOOK-RETURN-001", "Book return reaches processing through a service-controlled handoff."),
    ("REL-RECEIVING-001", "SP-L01-RECEIVING-001", "SP-L01-PROCESSING-001", "service_connect", "PRG-LIB-SERVICE-GRAPH-001", "Receiving connects to processing without crossing the arrival sequence."),
    ("REL-STORAGE-001", "SP-L01-PROCESSING-001", "SP-L01-STORAGE-001", "service_connect", "PRG-LIB-SERVICE-GRAPH-001", "Processing reaches secure storage."),
    ("REL-QUIET-SEPARATION-001", "SP-L01-QUIET-001", "SP-L01-DIGITAL-001", "must_separate", "PRG-LIB-ACOUSTIC-001", "Quiet reading is separated from active digital learning."),
    ("REL-READING-DAYLIGHT-001", "SP-L01-ADULT-001", "SP-L01-ADULT-001", "daylight_edge", "PRG-LIB-DAYLIGHT-001", "Adult reading owns west facade daylight control."),
    ("REL-STACKS-COLUMN-001", "SP-L01-STACKS-001", "SP-L01-STACKS-001", "column_exclusion", "PRG-STR-COLUMN-COORD-001", "Primary columns remain on room boundaries and circulation edges."),
)

REQUIRED_LIBRARY_SPACE_TYPES = {
    "entry_vestibule", "lobby_welcome_checkout", "primary_circulation",
    "adult_reading", "children_reading", "open_stacks", "community_room",
    "public_restroom", "staff_restroom", "janitor", "secure_storage",
    "collection_processing", "staff_workroom", "electrical_it",
    "mechanical_room", "loading_receiving",
}

STRUCTURAL_PROFILE = {
    "id": "STR-PROFILE-STEEL-LIBRARY-DEMO-001",
    "gravity_system": "steel columns + primary/secondary beams + composite-deck candidate",
    "lateral_system": "perimeter concentrically braced bays candidate",
    "foundation_system": "isolated pad foundations candidate pending soils",
    "limitations": [
        "Member dimensions are schematic coordination envelopes, not analyzed sections.",
        "Jurisdiction, loads, seismic, wind, fire protection, connections, and soils remain unresolved.",
        "A structural engineer must verify every member, connection, diaphragm, brace, and foundation.",
    ],
}

FACADE_PROFILE = {
    "id": "FCD-PROFILE-IS-LIBRARY-DEMO-001",
    "qualified_name": "International Style-informed modular library facade candidate",
    "assembly_system": "unitized vision glazing + insulated opaque panels + aluminum mullions + steel secondary supports candidate",
    "limitations": [
        "MTA-F2 coordination model only; barrier continuity, anchors, waterproofing, thermal performance, fire, acoustics, and fabrication remain unresolved.",
        "This demonstration grammar is selected for one integrated test and does not replace the user's final two-grammar decision.",
    ],
}
