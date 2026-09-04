# Legacy Grasshopper Reference — ProgramDiagram2 1.gh

## Source

```text
../architecture_automation_pipeline/ProgramDiagram2 1.gh
```

- Inspection date: 2026-08-26
- Inspection method: read-only load through installed Rhino 8 / Grasshopper APIs
- Rhino version reported during inspection: 8.29.26063.11001
- Grasshopper object count: 13
- Legacy file was not modified or copied

## Observed component flow

```text
Panel with absolute path to outAgent.txt
        ↓
File Path
        ↓
Read File
        ↓ list of text lines
Python 3 Script
  inputs:
    inLines
    floorHeight
    floorCount
    minFloor
  outputs:
    pointList
    diameterList
    ColorList
        ↓
native Grasshopper operations
  Deconstruct Vector
  Scale NU
  Move
  Colour RGB
        ↓
Human Custom Preview Materials
```

Other observed inputs include two number sliders, a `minFloor` panel with value `-1`,
and a Brep parameter used as the base geometry to scale and move.

## Legacy data source

The definition reads:

```text
../architecture_automation_pipeline/program_generator/fileTransfer/outAgent.txt
```

The file uses positional comma-separated rows. A representative row is:

```text
20.2007,26.8475,0,168.0,7.0,6.0,fabrication,private
```

Observed records consistently contain eight fields that appear to represent position,
floor, area/size values, program name, and category. The exact Python parsing source
was not extracted during this structural inspection, so field semantics beyond the
visible downstream names remain an inference and should be confirmed before migrating
any parsing logic.

## Patterns worth retaining

### External file as an application boundary

The Grasshopper definition does not need to own the upstream program generator. It
reads a published artifact, which supports the new provider/compiler architecture.

### Native file reader before custom parsing

Grasshopper's `Read File` component owns basic file access, while Python receives the
lines as data. This keeps the visible input path and file boundary inspectable.

### Script output split by responsibility

The Python component exposes separate point, size, and color outputs. Native components
perform deconstruction, scaling, movement, color construction, and preview. This is a
useful precedent for keeping geometry and display operations visible on the canvas.

### Real-time controls remain on the canvas

Floor height, floor count, and minimum floor are exposed as Grasshopper inputs rather
than buried inside the upstream program file.

## Limitations to address in the new definition

- the source path is absolute and machine-specific;
- the input uses positional text/CSV without a schema version;
- a malformed or partially written line has no visible contract-level recovery path;
- run ID, content hash, dependency identity, and provenance are absent;
- the inspected definition exposes one Python parser/mapper for all input fields;
- contract validation and architectural validation are not separate;
- no last-accepted-state or mixed-run protection is visible;
- program, size, color, and point mapping remain coupled to the legacy row format;
- selective regeneration across program, circulation, structure, and envelope is not
  represented in this small definition.

## New-project adaptation

Retain the readable pattern:

```text
visible path/workspace
→ native or bounded file reader
→ contract-specific parser
→ separate structured outputs
→ native/reusable geometry components
→ explicit preview
```

Upgrade the data and state model:

```text
versioned JSON contracts
→ atomic publication
→ schema gate
→ one reader per contract
→ stable IDs + provenance
→ system-specific generators
→ independent validators
→ accepted-state gate
→ Rhino bake/export
```

The new definition should preserve user-facing sliders and visible native operations.
Python/C# components should remain bounded readers, translators, or generators with
clear inputs and outputs. The entire pipeline should not disappear inside a single
script component.

## Verification still available later

If exact legacy parsing behavior becomes necessary, inspect the embedded Python 3
component source in Grasshopper or rebuild the eight-field parser from the upstream
writer with explicit tests. Do this only when a concrete compatibility fixture or
migration task requires it.
