'use client';

import { useMemo } from 'react';
import { Edges } from '@react-three/drei';
import type {
  AuthoredProgramVolume,
  Lattice,
  ProgramAllocation,
  ProgramCategory,
  ProgramVolumeModel,
  Vector3Value,
} from '../lib/types';

/**
 * A program zone expressed in the GLB coordinate system.
 *
 * This record is a derived display primitive only. In the authored path its
 * plan coordinates come from ProgramVolumeModel grid indices and its vertical
 * extent comes from the matching authored level. The allocation path remains
 * available as an explicitly labelled presentation fallback for old runs.
 */
export interface ProgramVolume {
  zoneId: string;
  /** Stable id of the authored volume or the allocation zone used as fallback. */
  sourceId: string;
  sourceKind: 'program_volume_model' | 'allocation_fallback';
  role: AuthoredProgramVolume['role'];
  spaceIds: string[];
  label: string;
  category: ProgramCategory | string;
  spaceType: string;
  level: { id: string; index: number };
  center: Vector3Value;
  size: Vector3Value;
  /** Source lattice elevations, retained to make the full-height derivation inspectable. */
  bottomZ: number;
  topZ: number;
  required: number;
  delivered: number;
  planBounds: { x0: number; y0: number; x1: number; y1: number };
}

function isFinitePositiveBox(values: number[]): boolean {
  return values.every((value) => Number.isFinite(value))
    && values[0] > 0 && values[1] > 0 && values[2] > 0;
}

/**
 * Derive display boxes from the score-authored Program Volume protocol.
 *
 * `grid_rect` contains indices, never coordinates. Resolving those indices
 * here keeps the overlay faithful to the same registration grid consumed by
 * massing, structure, circulation, and facade generation.
 */
export function deriveAuthoredProgramVolumes(
  programVolumeModel: ProgramVolumeModel | null | undefined,
): ProgramVolume[] {
  if (!programVolumeModel) return [];

  const levelsById = new Map(
    programVolumeModel.levels.map((level) => [level.id, level]),
  );

  return programVolumeModel.volumes.flatMap((volume) => {
    const level = levelsById.get(volume.level_id)
      ?? programVolumeModel.levels.find((candidate) => candidate.index === volume.level_index);
    if (!level) return [];

    const [i0, j0, i1, j1] = volume.grid_rect;
    const x0 = programVolumeModel.grid.x_lines[i0];
    const y0 = programVolumeModel.grid.y_lines[j0];
    const x1 = programVolumeModel.grid.x_lines[i1];
    const y1 = programVolumeModel.grid.y_lines[j1];
    const width = x1 - x0;
    const depth = y1 - y0;
    const height = level.z_top - level.z_base;
    if (!isFinitePositiveBox([width, depth, height, x0, y0, x1, y1, level.z_base, level.z_top])) {
      return [];
    }

    return [{
      zoneId: volume.id,
      sourceId: volume.id,
      sourceKind: 'program_volume_model',
      role: volume.role,
      spaceIds: [...volume.space_ids],
      label: volume.id,
      category: volume.category,
      // Authored volumes do not carry a room type. Keep the role visible in
      // the established field while exposing the exact role separately.
      spaceType: volume.role,
      level: { id: level.id, index: level.index },
      center: {
        // GLB/R3F uses [x, z, -y]: plan y becomes the negative scene z axis.
        x: (x0 + x1) / 2,
        y: (level.z_base + level.z_top) / 2,
        z: -((y0 + y1) / 2),
      },
      size: { x: width, y: height, z: depth },
      bottomZ: level.z_base,
      topZ: level.z_top,
      required: volume.target_area_m2,
      delivered: volume.gross_area_m2,
      planBounds: { x0, y0, x1, y1 },
    }];
  });
}

/**
 * Derive one full-height display volume per allocated zone.
 *
 * No plan or building coordinates are authored here. This is retained for
 * legacy runs whose payload predates ProgramVolumeModel. A malformed zone is
 * omitted because there is no honest way to fabricate a missing adjacent level
 * or a non-positive box.
 */
export function deriveProgramVolumes(
  lattice: Lattice | null | undefined,
  allocation: ProgramAllocation | null | undefined,
): ProgramVolume[] {
  if (!lattice || !allocation) return [];

  return allocation.zones.flatMap((zone) => {
    const levelPosition = lattice.levels.findIndex((level) => level.id === zone.level_id);
    const position = levelPosition >= 0 ? levelPosition : zone.level_index;
    const level = lattice.levels[position];
    const nextLevel = lattice.levels[position + 1];
    if (!level || !nextLevel) return [];

    const width = zone.x1 - zone.x0;
    const depth = zone.y1 - zone.y0;
    const height = nextLevel.z - level.z;
    const values = [zone.x0, zone.y0, zone.x1, zone.y1, level.z, nextLevel.z,
      width, depth, height, zone.area_required_m2, zone.area_delivered_m2];
    if (values.some((value) => !Number.isFinite(value))
      || width <= 0 || depth <= 0 || height <= 0) return [];

    return [{
      zoneId: zone.space_id,
      sourceId: zone.space_id,
      sourceKind: 'allocation_fallback',
      role: 'program',
      spaceIds: [zone.space_id],
      label: zone.label,
      category: zone.category,
      spaceType: zone.space_type,
      level: { id: level.id, index: level.index },
      center: {
        // GLB/R3F uses [x, z, -y]: plan y becomes the negative scene z axis.
        x: (zone.x0 + zone.x1) / 2,
        y: (level.z + nextLevel.z) / 2,
        z: -((zone.y0 + zone.y1) / 2),
      },
      size: { x: width, y: height, z: depth },
      bottomZ: level.z,
      topZ: nextLevel.z,
      required: zone.area_required_m2,
      delivered: zone.area_delivered_m2,
      planBounds: { x0: zone.x0, y0: zone.y0, x1: zone.x1, y1: zone.y1 },
    }];
  });
}

/** Legacy program colors retained for parity with the old Volume_Massing view. */
export const PROGRAM_VOLUME_COLORS: Record<string, string> = {
  private: '#ff0000',
  public: '#0000ff',
  circulation: '#00ff00',
  service: '#ff9900',
};

function colorForCategory(category: string): string {
  return PROGRAM_VOLUME_COLORS[category.toLowerCase()] ?? '#b36bff';
}

export interface ProgramVolumeMassingProps {
  lattice: Lattice | null | undefined;
  allocation: ProgramAllocation | null | undefined;
  /** Score-authored Program Volumes; preferred over allocation-derived boxes. */
  programVolumeModel?: ProgramVolumeModel | null;
  /** Hide the overlay without changing or filtering the allocation. */
  visible?: boolean;
  /** Face opacity; edge opacity remains fully legible. */
  opacity?: number;
  onVolumeClick?: (volume: ProgramVolume) => void;
}

/**
 * Presentation-only R3F overlay for the program-volume intermediate stage.
 *
 * It deliberately does not write to the model, GLB, or allocation. Consumers can
 * mount it beside the accepted model and remove it when the massing stage is done.
 */
export function ProgramVolumeMassing({
  lattice,
  allocation,
  programVolumeModel,
  visible = true,
  opacity = 0.38,
  onVolumeClick,
}: ProgramVolumeMassingProps) {
  const volumes = useMemo(
    () => programVolumeModel
      ? deriveAuthoredProgramVolumes(programVolumeModel)
      // Presentation fallback for legacy payloads only: the authored model is
      // intentionally never reconstructed from detailed room allocation.
      : deriveProgramVolumes(lattice, allocation),
    [allocation, lattice, programVolumeModel],
  );

  if (!visible || volumes.length === 0) return null;

  return (
    <group
      name="program-volume-massing"
      userData={{
        presentationOnly: true,
        'mta:layer': 'program',
        'mta:subsystem': 'volume_massing',
        'mta:authority': 'presentation_only',
      }}
    >
      {volumes.map((volume) => {
        const color = colorForCategory(volume.category);
        return (
          <group
            key={volume.zoneId}
            name={`program-volume-${volume.zoneId}`}
            position={[volume.center.x, volume.center.y, volume.center.z]}
            userData={{
              presentationOnly: true,
              'mta:layer': 'program',
              'mta:subsystem': 'volume_massing',
              'mta:category': volume.category,
              'mta:authority': 'presentation_only',
              zoneId: volume.zoneId,
              sourceId: volume.sourceId,
              sourceKind: volume.sourceKind,
              role: volume.role,
              spaceIds: volume.spaceIds,
              category: volume.category,
              levelId: volume.level.id,
            }}
            onClick={onVolumeClick ? (event) => {
              event.stopPropagation();
              onVolumeClick(volume);
            } : undefined}
          >
            <mesh>
              <boxGeometry args={[volume.size.x, volume.size.y, volume.size.z]} />
              <meshBasicMaterial
                color={color}
                transparent
                opacity={opacity}
                depthWrite={false}
              />
              <Edges color={color} threshold={15} />
            </mesh>
          </group>
        );
      })}
    </group>
  );
}
