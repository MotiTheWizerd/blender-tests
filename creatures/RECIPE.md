# Creatures: from an AI model to an animated creature in Forge

Moti + Claude, first run on the Tripo dragon, started 2026-11-10. Every step is a script that runs headless, so an
agent can run the whole recipe on the next creature; what needs an eye is marked **LOOK**, with what to look for.
Each creature has a folder here (`dragon/`), and every script takes its name: `blender -b --factory-startup -P
<step>.py -- dragon`. Blender 5.2.3; on this PC `C:/Program Files/Blender Foundation/Blender 5.2/blender.exe`.

## 0. The model (Tripo, by hand for now)

- tripo3d.ai Studio, image to model, **H3.1, 4K PBR** (the dragon: `picture-2.png`, 55 credits).
- Export needs a paid plan (the free plan's Export opens the upgrade page). Pro: 3,000 credits a month.
- Export **GLB, 4K textures**, saved as `<name>/source_tripo.glb` (the dragon: 67 MB).
- Not tried yet: **Generate in Parts**, which may give a separate jaw (see step 1: a closed mouth can't roar).
- Later, for agents: the Tripo API does the same without the browser.

## 1. Inspect: what did the AI make? (`inspect.py`, ~30 s)

Writes `inspect.json` and four views, `inspect_front/side/top/three_quarter.png` (Workbench, texture colours).

- **A glTF splits its vertices along the UV seams**, so a model can look like hundreds of loose pieces when it is
  one skin (the dragon: 388 patches). Weld first (1e-5), then count: the dragon is **1 shell, 0 open edges, 0
  non-manifold**, which is the best case for every later step. Several shells or open edges: fix or ask before going on.
- Tripo's size is arbitrary (the dragon: 0.98 x 0.94 x 0.55 m). The game size is chosen, not read (the dragon: about
  12 m nose to tail, proposed), and applied when it goes to Unity.
- **LOOK** at the views: the pose (legs apart, wings out, tail free: good for a rig), anything fused that must move
  apart (the dragon's mouth is closed and part of the skin: no roar until a jaw is cut or made in parts).
- The maps: base colour (sRGB), normal, and `rm` (roughness in G, metal in B: glTF's packing), all 4096.

## 2. Reduce and bake (`reduce.py -- <name> [triangles] [bake size]`)

The AI mesh is film-scale (the dragon: 1.89M triangles); a game creature wants 20-60k (default 40,000).

- Collapse-decimate a copy, **keeping its UVs**: the AI's colour and roughness/metal maps still fit, unchanged.
  Only the shape's detail is lost, so only the normal map is baked again.
- Bake the normals in Cycles on the GPU (OptiX), selected-to-active from the full mesh **with its own normal map**,
  so the bake carries the sculpted scales and the map's grain together. Extrusion 0.4% and ray 1.2% of the size.
- Triangulated and smooth-shaded, so Unity shades it exactly as it was baked.
- Writes `<Name>_BaseColor.jpg`, `<Name>_RM.jpg`, `<Name>_Normal.png`, `<name>_low.blend` (the input to step 3),
  `reduce_compare.png` (full left, reduced right), `reduce_head_high/low.png`, `reduce.json` (timings).
- **LOOK** at the comparison: silhouette (claws, spikes, horn tips, wing edges keep their shape?), the wing membrane
  (no holes where its two sides met), the scales still read in the head close-up.

## 3. Rig (`rig.py`, ~1 min), from `<name>/landmarks.json`

The judgment of this step is the landmarks: each chain's joints in the source frame. `rig.py` turns them into bones,
mirrors the left (+X) side, skins with automatic (heat) weights and renders the checks; the rest is mechanical.

How the dragon's were found (an agent repeats this with `probe.py` and `grid.py`, both run on `<name>_low.blend`):
- **Slices along the body** (every 4 cm in Y, core vertices only) give the centre line: the spine is level at
  z 0.25-0.29, and the tail curves off to +X (its tip 0.38 m to the side), so its bones follow the slices, not a line.
- **Feet** are the vertices on the ground (z < 3 cm), split in four by side and by front/back; each leg is traced up
  from its foot by the centroid of 3 cm slabs. Left and right agreed to 2 mm, so mirroring is safe.
- **Grid views** (`grid_front/side/top.png`, 5 cm lines, 1500 px a metre) for what slices can't tell: the elbows and
  knees (the hind leg bends back at the hock, digitigrade), the wing's wrist (the hooked claw at the top, x 0.18
  z 0.48) and its three finger struts, each ending in a claw on the membrane's lower edge.
- Chains: spine 3, neck 4, head 1, tail 10, each front leg 3, each hind leg 4, each wing arm 3 and fingers 3+2+2:
  52 bones. No jaw yet (the mouth is fused).
- **Planted feet** (`"feet"` in landmarks.json): each foot gets an unparented twin `ik_<foot>` that its leg reaches by
  IK, so the body moves over feet that hold the ground (56 bones with the four). Without it the legs ride on the spine
  and the creature floats: Moti saw it at once (the dragon's front feet moved 32 mm per metre of height).
- **Rigid feet**: the skin below each planted foot's ankle goes to the foot bone alone; shared with the lower leg,
  the sole slides as the leg bends (4-10 mm/m left after IK, 0 after this).

Writes `<name>_rig.blend`, `rig.json` (52 bones, 0 vertices left unweighted), `rig_<view>.png` (bones drawn through
the see-through body) and `bend_<view>.png` (wings swung, neck and tail turned, a front leg lifted).
- **LOOK** at `rig_*`: every bone inside its limb, the finger bones along the struts. At `bend_*`: no tearing
  (the dragon: none), smooth curves (the tail curls evenly), stretching where a limb meets the body (the dragon: the
  back skin stretches at the wing roots when a whole wing swings 40 deg; watch it in the fold animation).

## 4. Export for Forge (`export.py -- <name> [length]`, ~1 min; `check_export.py` to look)

Forge's model contract (unity-game-test ARCHITECTURE.md, "Models"): `<Name>.fbx` in metres with `<Name>_LOD0/1/2` and
`…_COL` convex colliders, `<Name>_BaseColor`, `_Normal` (OpenGL), `_MetallicSmoothness` (metal R, smoothness A).
**Forge imports models still** (no animation; characters are a humanoid-only path), so a creature goes in as a
statue until Forge has creatures.

- The game size is chosen: `length` front to back (the dragon: 12 m, so 12.5 m across the wings and 7 m tall).
  Pivot at the lowest point, the footprint centred on it.
- LODs: the reduced mesh, 40% and 12% of it (the dragon: 40,000 / 16,000 / 4,800 triangles).
- **Colliders from the skeleton**: each vertex goes to the region of its strongest bone (body, neck, head, tail in
  three, each leg, each wing); one convex hull per region, at most 250 faces (PhysX: 255). One hull for the whole
  creature would fill the air between its wings and legs.
- Maps at 2048 (what Forge builds at). glTF's `rm` (roughness G, metal B) becomes URP's MetallicSmoothness.
- `CREDITS.md`: made by Tripo on Moti's Pro plan (private models, commercial use).
- Writes `<name>/forge/<Name>/` (git-ignored, rerun it) and `export.json`. `check_export.py` reads the FBX back:
  `export_colliders.png`, `export_lods.png`.
- **LOOK** at the LODs (LOD2 keeps the silhouette) and the hulls (each on its own region; the overlaps are fine).
  Bounds of each hull: read the FBX back and print them, a picture of overlapping hulls is hard to judge.

## 5. Into Forge (unity-game-test, ~5 min with the tests)

1. Copy `forge/<Name>/` to `Assets/_Project/Content/Models/<Name>/` (new files: a plain copy, then a refresh).
2. A record in `CoreModels.cs` (the dragon: `forge.core:dragon`, category `Creatures/Dragons`, upright, placed as
   aimed, at its own size). Compile, no console errors.
3. *Forge → Models → Build Models* makes `<Name>.mat` and `<Name>.prefab` and lists it in `PrefabCatalog.asset`.
   **It rebuilds every model folder**, so other prefabs and materials may change with it: commit only your own paths.
4. *Forge → Generate Core Plugin*: `forge.core.json` should gain only the new record.
5. EditMode tests (`ModelContentTests` checks the contract: on its pivot, centred, colliders undrawn).
6. **LOOK** in play mode: instantiate the prefab 30 m in front of the camera turned to face it
   (`Quaternion.LookRotation(-forward)`), screenshot. Its face toward the camera means it faces +Z, as Forge wants
   (the dragon did: Blender's -Y front exported with forward -Z, up Y comes out right). Its tab shows in the browser.

## 6. Animate (`animate.py`, ~1 min)

Each clip is motion written as curves of time on the chains (`Idle` 4 s, `WingFlap` 1 s so far), keyed every frame,
each loop ending where it began. Writes `<name>_anim.blend`, `anim_<clip>.png` (frames across a loop), `anim.json`.
- **The rest pose is the legs' full reach**: the body only ever moves DOWN from it and back (the chest sinks with a
  breath and returns; it dips on the wings' downstroke). A chest rising past rest pulls planted feet off the ground.
- **The feet check** (`anim.json`, `FEET` lines): how far the skin on the ground (the lowest 2% of the height) moves
  over each loop, per metre of height. It must be ~0; the dragon: 0.0 in both clips. Anything else floats or skates.
- **LOOK** in Blender (Space plays; Dope Sheet > Action Editor picks the clip): weight, no floating, the wing roots.

## Next (planned, not built)

7. More clips: head look-around, wing fold/unfold, walk (the feet's IK targets step), roar once there is a jaw.
8. Forge plays them (waits for Forge creatures): keep the skeleton on import, bake the IK into keys before the FBX,
   an Animator for a generic rig, spring bones on tail, neck and wing tips.

## What is kept in git

The scripts, this recipe, each step's json and pictures. Not the Tripo source (re-export it, step 0) nor what the
steps make from it (rerun them: steps 1-2 take about 2 minutes on the RTX 5060).

## Results, the dragon

| Step | Result | Time |
|---|---|---|
| 1 | 1 shell, 944,353 vertices welded, 1,888,702 triangles, 0 open edges; 3 maps at 4096 | 30 s |
| 2 | 40,000 triangles; normals baked at 4096; nearly identical at full view, horn tips and small spikes slightly faceted up close | 106 s (decimate 61 s, bake 18 s) |
| 3 | 52 bones, 0 vertices unweighted, no tearing in the bend test | 1 min |
| 4 | 12 x 12.5 x 7 m; LODs 40,000 / 16,000 / 4,800; 12 hulls of 118-246 faces; FBX 2.2 MB, maps 8.5 MB | 1 min |
| 5 | in Forge as `forge.core:dragon` (unity-game-test 53229a9); faces +Z; EditMode 1246/1246 | 5 min |
