# LogCabin: a small round-log cabin with a shingle roof, a door, a shuttered window and a woodpile

Status: done

## What it is
- kind: building. Front at -Y (door, window, woodpile), no turn needed.
- Size: 6.28 m wide, 3.2 m deep, 5.0 m tall; eaves at about 2.85 m. Sized by the door: a front-face depth probe
  (`build/door_probe.txt`) shows the recessed door panel 0.315 model units tall and 0.15 wide. For a 2 m door that
  is 6.35 m a unit; the export's scale is 6.41, which makes the door about 2.0 m by 0.96 m. Cross-check: the wall logs
  come out about 0.38 m thick (heavy but believable), and the window about 0.8 m tall.
- Source: 1 shell, 962,640 welded vertices, 1,925,305 triangles, 2 open edges, 1 non-manifold edge (too few to see).
- Triangles: 1,925,305 -> 29,999 (LOD0) / 11,999 (LOD1) / 3,599 (LOD2). Reduced with `"uv_seams": 1` and a
  2048 normal bake (`"bake_size": 2048`), as on the earlier buildings.
- Colliders: 2 convex hulls cut at 0.57 of the height (the eaves). The walls (240 faces) span z 0-2.85 m and the roof
  prism (128 faces) spans z 2.85-5.0 m.
- Maps: base colour, normal and rm from Tripo at 4096; delivered at 2048 (BaseColor, Normal, MetallicSmoothness).

## What I saw
- inspect_front: a log cabin facing -Y: notched log corners, a plank door with strap hinges and a ring handle, a
  four-pane window with a Z-braced shutter, a woodpile in a frame, a ridge log with carved knotwork posts at each end.
- inspect_side / top / three_quarter: a simple gable with a small gable window at each end and shingles all over.
  Nothing loose or floating.
- reduce_compare: at full view the reduced model is nearly identical: crisp shingles (no streaks, thanks to
  uv_seams), the logs, door, window and woodpile all keep their shape.
- reduce_head_high/low: the close-up of a ridge-end post. Its knotwork carving turns into a faceted smear when
  reduced. I tried 40,000 triangles too, and it looked the same, so I kept 30,000. The ridge log shows a little
  texture streaking up close.
- export_lods: LOD1 is nearly LOD0. LOD2 keeps the silhouette, the door and the window, but the shingle rows flatten.
  That is fine at LOD2 distance.
- export_colliders: a wall box and a roof prism that follow the walls and the gable. Bounds read back from the FBX
  match.

## Doubts
- The carved knotwork posts at the ridge ends (about 0.5 m) lose their carving up close. It is a texture smear and
  more triangles did not help. Seen from the ground at game distance it reads as carving.
- The size depends on the door being 2 m. The cabin comes out shallow (3.2 m deep and 6.3 m wide), which is what the
  model's shape is. A smaller door (1.8 m) would make it 2.9 m deep.
- The wall hull reaches up to the eaves, so it includes the roof's small overhang above about 2.6 m. That is a few
  cm of air at most.

## Into Forge
`forge.core:log_cabin`, category `Architecture/Buildings`, upright, placed as aimed, at its own size.

## Script changes
None. It uses the existing `uv_seams` and `bake_size` keys (still uncommitted from earlier jobs).
