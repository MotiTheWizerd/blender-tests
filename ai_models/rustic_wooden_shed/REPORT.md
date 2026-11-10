# RusticWoodenShed: a small turf-roofed plank shed on a stone base, a door and a shuttered window at the front

Status: done

## What it is
- kind: building. Plank walls on a dry-stone base, a turf roof with mossy stones and grass tufts between carved
  gable boards, a plank door with iron strap hinges and a ring handle, and a shuttered window. The front is at -Y
  (the door's side), so no turn was needed.
- Size: **4 m front to back, 5.73 m wide, 4.45 m tall**, eaves at 2.45 m. I sized it by the door. A front-face depth
  probe (`build/door_probe.py`) puts the door opening at 0.34 model units tall and 0.18 wide. Taking the door as 2 m
  gives 5.85 m a unit, so the door comes out 1.06 m wide and the window shutters about 1.1 m tall. Both fit.
- Triangles: 1,851,777 -> 29,999 (`uv_seams: 1`). LODs 29,999 / 11,999 / 3,599.
- Hulls: 2, cut at 0.55 of the height (the eaves). Walls 0-2.45 m (196 faces), roof 2.45-4.45 m (194 faces).
- Maps: base colour, normal, rm at 4096 in the source. The normal map is baked at **2048** (`bake_size`, see below);
  Forge gets every map at 2048.
- Source: 1 shell, 13 open edges and 8 non-manifold edges (small, nothing visible).

## What I saw
- inspect_front: the door and window face the camera. The front is at -Y.
- inspect_side / top / three_quarter: a gabled roof whose eaves overhang a little, and turf over the whole roof.
  Nothing floats loose.
- reduce_compare: almost identical to the source at full view. The door hinges, the window shutters, the carved
  gable boards, the stone base and the turf mounds all keep their shape.
- reduce_head_high/low (the roof turf up close): the turf mounds keep their shape. The grass blades become thin
  spikes, and some turf patches smear where faces merged. That only shows up close.
- export_lods: LOD2 (3.6k) still reads as the shed: the roof, door and window outlines are all there.
- export_colliders: one box on the walls and one prism on the roof. Their bounds, read back from the FBX, sit on
  them.

## Doubts
- The turf smears in places up close (reduce_head_low.jpg). From any normal game distance it reads fine. If it
  bothers you, try `"triangles": 45000`. More triangles didn't cure this kind of smear on the longhouse.
- The normal map is baked at 2048, not 4096. The reduce bake crashed twice for lack of memory: a `pythonw` running
  `raam-manage/vision/server.py` was holding about 27 GB committed, which left about 6 GB. Forge uses 2048 maps
  anyway, so nothing is lost in the game. With memory free, you can remove `bake_size` and rerun
  `--from reduce` to get the old 4096 path.

## Into Forge
`forge.core:rustic_wooden_shed`, category `Architecture/Buildings`, upright, placed as aimed, at its own size
(4 m deep).

## Script changes
- `run.py`: an optional model.json key `"bake_size"` is passed to `reduce.py` as its bake size. Without the key
  nothing changes (reduce.py's 4096), so the dragon's, grass_house's and viking_longhouse's steps are the same as
  before. I added it because the 4096 bake ran out of memory on this PC.
- `reduce.py` still carries the uncommitted `uv_seams` change from the viking longhouse job. This model uses it.
