# VikingLonghouse: a Viking hall with a shingled roof, a carved double door and a lower side wing

Status: done

## What it is
- **kind** building. One shell, 4 open edges (a tiny hole, harmless for a still building).
- **size** 10 m front to back, 12.4 m wide, 10 m tall to the top of the dragon-head carving. Read off the door: the
  double door is 0.155 model units tall, taken as 2 m, so 1 unit = 12.9 m (export's exact scale: 12.6). Cross-check:
  the round shields on the walls come out ~0.9 m across, the size of a real Viking shield.
- **triangles** 1,800,076 -> 60,000 (LOD0); LODs 60,000 / 24,000 / 7,200.
- **hulls** 3 slabs, cut at 45% and 67% of the height: walls 0-4.5 m (whole footprint, 228 faces), both roofs
  4.5-6.7 m (164), the hall's gable and carving 6.7-10 m (100, only x -3.0..0.3 m).
- **maps** BaseColor, Normal (baked at 4096, shipped at 2048), MetallicSmoothness. FBX 3.5 MB.
- Front at -Y (the door), as Forge needs: no turn.

## What I saw
- inspect_front/side/top/three_quarter: a gabled hall with its door at the front, a hip-roofed wing on its right,
  dragon heads on both gable peaks, shields along the walls, stone base. Front view shows the door: good.
- reduce_compare (first at 30k, then 60k, plain collapse): silhouette fine, but **the shingle roof's colour smeared
  into streaks**. Not a triangle count problem (60k looked the same): the collapse merged faces across the UV seams,
  so roof faces spanned several of Tripo's small texture islands. Fixed with `uv_seams` (below).
- reduce_compare (60k, `uv_seams`): the shingles read again (a few soft streaks left); the shields' rims are a little
  notched/polygonal, the budget spent on seams comes from elsewhere.
- reduce_head_high/low: the gable's dragon carving keeps its horns and spikes but is faceted close up.
- export_lods: LOD2 keeps the silhouette (roofs, gable, carving, wing); the shields become bumps, fine at that range.
- export_colliders + hull bounds read back from the FBX: each slab on its walls/roofs, the top one only on the hall's
  gable; nothing fills the air beside the gable.

## Doubts
1. **The shield rims** are slightly notched at LOD0 (look at them from 5-10 m in game). A higher `triangles` or a
   tuned seam weight could help; I stopped tuning.
2. **The dragon-head carving** is faceted seen close; it sits 9 m up, so probably fine from the ground.
3. **Size**: a 2 m door makes a 10 m-long, 10 m-tall hall. If the door is meant to be a grand 2.5 m double door, the
   hall is 12.5 m (change `length`, rerun export).
4. 60,000 triangles is more than the grass_house (30,000): this one's shingles and shields need it.

## Into Forge
`forge.core:viking_longhouse`, category `Architecture/Buildings`, upright, placed at its own size.

## Script changes
- `reduce.py`: a new model.json key **`uv_seams`** (a cost factor for Blender's collapse; absent = 0 = the old
  behaviour, so the dragon and grass_house are unchanged). With it, the welded vertices on UV seams (124,637 here) go
  in an inverted vertex group at weight 0.5, so the collapse prefers not to merge faces across texture islands.
  Weight 1.0 froze the seams entirely (288k triangles instead of 40k); the factor itself (1 vs 5) made no visible
  difference. Reported in reduce.json as `uv_seams` and `seam_vertices`.
