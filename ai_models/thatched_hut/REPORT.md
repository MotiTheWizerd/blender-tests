# ThatchedHut: a small A-frame thatched hut with a log gable and a plank door

Status: done (a second run of the same file: it came back into waiting-tasks-models at 04:15)

## This run
The GLB in waiting-tasks-models had the same sha256 (`5a0e0757...`) as `ai_models/thatched_hut/source_tripo.glb`
and as the hut already delivered to `game-ready-models/ThatchedHut/` at 03:21. SMITH.md says the same file means a
model tried before, so I took it again with the earlier run's model.json, reran inspect, reduce, export and
check_export, and looked at every picture again. Nothing changed: the same numbers, the same pictures. It is
delivered as `ThatchedHut-2/`, because `ThatchedHut/` is already there. **If you put it back to get something
changed, tell me what**, because this run found no reason to change anything.

## What it is
- kind: building. A steep thatched roof down to the ground, horizontal-log gable walls, crossed timbers at both
  peaks, a plank door with iron strap hinges and a ring handle at the front (-Y, no turn needed).
- Size: 7.3 m front to back, 7.66 m wide, 4.59 m tall (scale 7.8). Sized by the door: the opening is 0.255 units
  tall (front-face depth probe `build/door_probe.py`, from the first run) for a 2 m door. I checked again on the
  front view this run: the door is about 190 x 265 px, so 1.43 m wide at 2 m tall. The ring handle sits about halfway
  up, near 1 m, which is a normal handle height and supports the 2 m reading. The wall logs come out about 0.38 m.
- Source: 1 shell, 6 open edges and 14 non-manifold edges (none visible), 1,884,504 triangles, 3 maps at 4096
  (base colour, normal, rm).
- Triangles: 1,884,504 -> 39,999 (`"uv_seams": 1`, normals baked at 2048 with `"bake_size": 2048`; reduce 63 s).
- LODs: 39,999 / 15,999 / 4,799. Maps at 2048 (BaseColor, MetallicSmoothness, Normal).
- Hulls: 1 (`"hulls": []`), 238 faces. It's a solid A-frame, so a single hull fits.

## What I saw
- inspect_front: the gable, door and crossed peak timbers face the camera, so the front is at -Y.
- inspect_side / top / three_quarter: one thatched roof down to the ground, crossed timbers at both gables, no
  loose parts.
- reduce_compare: nearly identical at full view. The thatch fringe is a little softer.
- reduce_head_high/low: up close the thatch texture smears and some straws are flat spikes, and the hollow end of
  the peak timber is closed. Not visible at game distance.
- export_lods: LOD1 is like LOD0. LOD2 rounds the thatch but keeps the A-frame, the door and the peak timbers.
- export_colliders: the single hull hugs the roof and gable, with a little air at the peak timbers and the eaves.
- check_export: the FBX reads back at 7.66 x 4.59 x 7.3 m (x, up, depth), pivot at 0.

## Doubts
- The size depends on reading the door as 2 m, and the door is wide (1.4 m). If you want it smaller, a 1.8 m door
  would make the hut 6.6 m long.
- Up close the thatch smears. More triangles won't fix it (it's the texture, as on the log cabin).
- The hull closes the doorway. The model has no interior anyway.
- Two packages of the same hut are now in game-ready-models (`ThatchedHut/` and `ThatchedHut-2/`). Their FBX and maps
  should be the same, so keep either one.

## Into Forge
`forge.core:thatched_hut`, category `Architecture/Buildings`, upright, placed as aimed, at its own size.

## Script changes
None. It uses the existing `uv_seams` (reduce.py) and `bake_size` (run.py) keys, which are still uncommitted.
