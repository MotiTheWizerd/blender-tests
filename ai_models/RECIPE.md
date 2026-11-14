# AI models: from a Tripo model to a game-ready one in Forge (creatures and buildings)

Moti + Claude, first run on the Tripo dragon, started 2026-11-10. Every step is a script that runs headless, so an
agent can run the whole recipe on the next creature; what needs an eye is marked **LOOK**, with what to look for.
Each creature has a folder here (`dragon/`), and every script takes its name: `blender -b --factory-startup -P
<step>.py -- dragon`. Blender 5.2.3; on this PC `C:/Program Files/Blender Foundation/Blender 5.2/blender.exe`.

## Coming back to it

```
python ai_models/run.py dragon                 # every step, source to clips (~4 min on the RTX 5060)
python ai_models/run.py dragon --from rig      # after editing dragon/landmarks.json
python ai_models/run.py dragon --only animate  # after editing a clip in animate.py
```

Two kinds, said by each model's `model.json` ("kind", "length" in metres front to back, "triangles"):
**creature** (every step) and **building** (inspect, reduce, export, check_export: no rig, no clips; its colliders
are slabs of its height cut at `"hulls"`, none for one hull). `python ai_models/run.py --steps` lists which runs for
which. Models so far: `dragon` (creature, 12 m), `grass_house` (building, a Viking longhouse, 16 m: sized by its door,
0.125 model units tall for a 2 m door).

Each model's folder holds three things (`place.py` says where, for every script):

| Where | What | In git |
|---|---|---|
| `<name>/source_tripo.glb` | the AI model (step 0) | **no**: private (this repo is public); kept in Tripo and backed up (below) |
| `<name>/model.json` | its kind, length, triangles (buildings: hulls) | yes |
| `<name>/landmarks.json` | a creature's joints (step 3's judgment) | yes |
| `<name>/checks/` | each step's pictures (JPEG) and numbers (json): the record of the last run | yes |
| `<name>/build/` | the .blend files, the maps, the Forge export, a log per step | no: `run.py` makes it again |

**Change scripts and inputs, never a .blend by hand**: every .blend is rebuilt, so a hand edit is lost on the next
run. A change found by eye in Blender goes back into the script or `landmarks.json`, then `run.py`.

**The private source's backup**: Moti's laptop (Tailscale `motithewizerdlab@100.74.136.46`, it asks him to approve
the first SSH of a session), `~/backups/ai_models/<name>/` with its `landmarks.json`; checked by sha256 when copied
(the dragon: `8f6223e0ebc95aee...`). The source also stays in Moti's Tripo account (Assets), downloadable on Pro.

## 0. The model (Tripo, by hand for now)

- tripo3d.ai Studio, image to model, **H3.1, 4K PBR** (the dragon: `picture-2.png`, 55 credits).
- Export needs a paid plan (the free plan's Export opens the upgrade page). Pro: 3,000 credits a month.
- Export **GLB, 4K textures**, saved as `<name>/source_tripo.glb` (the dragon: 67 MB).
- **The source picture is part of the recipe**: the pose decides what can be rigged. Legs apart, wings spread, tail
  free, and **the mouth slightly open**, teeth showing: Tripo then models the inside, and a jaw bone can close it. A
  closed mouth has nothing inside (the dragon), so it can't roar without a mouth built by hand.
- For a creature, keep **one skin** (not parts): it bends smoothly at the joints; parts crack at the seams.
- Not tried yet: **Generate in Parts**, which may give a separate jaw (see step 1: a closed mouth can't roar).
- Later, for agents: the Tripo API does the same without the browser.

## 1. Inspect: what did the AI make? (`inspect.py`, ~30 s)

Writes `checks/inspect.json` and four views, `inspect_front/side/top/three_quarter.jpg` (Workbench, texture colours).

- **A glTF splits its vertices along the UV seams**, so a model can look like hundreds of loose pieces when it is
  one skin (the dragon: 388 patches). Weld first (1e-5), then count: the dragon is **1 shell, 0 open edges, 0
  non-manifold**, which is the best case for every later step. Several shells or open edges: fix or ask before going on.
- Tripo's size is arbitrary (the dragon: 0.98 x 0.94 x 0.55 m). The game size is chosen, not read (the dragon: about
  12 m nose to tail, proposed), and applied when it goes to Unity.
- **LOOK** at the views: the pose (legs apart, wings out, tail free: good for a rig), anything fused that must move
  apart (the dragon's mouth is closed and part of the skin: no roar until a jaw is cut or made in parts).
- The maps: base colour (sRGB), normal, and `rm` (roughness in G, metal in B: glTF's packing), all 4096.

## 1b. A sliced model: join it (`join.py -- <name> [atlas]`, ~3 min; model.json `"sliced": true`)

Tripo can make a model in parts (woman_1: 19, head to feet), each its own mesh and colour map, cut where they meet.

- The parts are welded where they meet (their cut vertices are the same on both sides: woman_1 at distance 0) into
  one closed body; what still gapes (woman_1: 12 edges) is closed. Tripo's normals go (each part's were made alone,
  so every cut showed as a crease); the body is shaded from its own shape.
- The maps go into one atlas (default 8192) at their own size, each in its own square, and are padded 64 texels round
  every UV island (Tripo leaves black between them, which a reduced face over an edge, or a game's mipmaps, pick up).
- Writes `build/<name>_joined.glb` (reduce reads it in place of the source) and `<Title>_Atlas_basecolor.jpg`;
  `checks/join.json`: each part's square, the open edges before and after.
- Step 2 then **unwraps the reduced mesh afresh and bakes its colour** from the joined one as it bakes the normals,
  since the collapse can't keep UVs from smearing across islands that aren't one map (any model can ask: `"unwrap"`).
  `"bake_reach"` (default 0.004 of the size) where folds are narrow: woman_1 used 0.0015 (cleavage, groin).

## 2. Reduce and bake (`reduce.py -- <name> [triangles] [bake size]`)

The AI mesh is film-scale (the dragon: 1.89M triangles); a game creature wants 20-60k (default 40,000).

- Collapse-decimate a copy, **keeping its UVs**: the AI's colour and roughness/metal maps still fit, unchanged.
  Only the shape's detail is lost, so only the normal map is baked again.
- Bake the normals in Cycles on the GPU (OptiX), selected-to-active from the full mesh **with its own normal map**,
  so the bake carries the sculpted scales and the map's grain together. Extrusion 0.4% and ray 1.2% of the size.
- Triangulated and smooth-shaded, so Unity shades it exactly as it was baked.
- Writes `<Name>_BaseColor.jpg`, `<Name>_RM.jpg`, `<Name>_Normal.png`, `<name>_low.blend` (the input to step 3),
  `reduce_compare.jpg` (full left, reduced right), `reduce_head_high/low.jpg`, `reduce.json` (timings).
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
- **Grid views** (`grid_front/side/top.jpg`, 5 cm lines, 1500 px a metre) for what slices can't tell: the elbows and
  knees (the hind leg bends back at the hock, digitigrade), the wing's wrist (the hooked claw at the top, x 0.18
  z 0.48) and its three finger struts, each ending in a claw on the membrane's lower edge.
- Chains: spine 3, neck 4, head 1, tail 10, each front leg 3, each hind leg 4, each wing arm 3 and fingers 3+2+2:
  52 bones. No jaw yet (the mouth is fused).
- **Planted feet** (`"feet"` in landmarks.json): each foot gets an unparented twin `ik_<foot>` that its leg reaches by
  IK, so the body moves over feet that hold the ground (56 bones with the four). Without it the legs ride on the spine
  and the creature floats: Moti saw it at once (the dragon's front feet moved 32 mm per metre of height).
- **Rigid feet**: the skin below each planted foot's ankle goes to the foot bone alone; shared with the lower leg,
  the sole slides as the leg bends (4-10 mm/m left after IK, 0 after this).

Writes `<name>_rig.blend`, `rig.json` (52 bones, 0 vertices left unweighted), `rig_<view>.jpg` (bones drawn through
the see-through body) and `bend_<view>.jpg` (wings swung, neck and tail turned, a front leg lifted).
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
  `export_colliders.jpg`, `export_lods.jpg`.
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

Each clip is motion written as curves of time on the chains (`Idle` 4 s, `WingFlap` 1 s, `Walk` 1.6 s), keyed every frame,
each loop ending where it began. Writes `<name>_anim.blend`, `anim_<clip>.jpg` (frames across a loop), `anim.json`.
- **The rest pose is the legs' full reach**: the body only ever moves DOWN from it and back (the chest sinks with a
  breath and returns; it dips on the wings' downstroke). A chest rising past rest pulls planted feet off the ground.
- **Walk in place**: the feet's targets step (a lateral-sequence walk, hind-fore-hind-fore a quarter apart, 70% of
  the cycle on the ground), the game moves the creature at the speed the feet carry (`anim.json`, the dragon 0.135
  body lengths a second: 1.6 m/s at 12 m), or the feet skate. The body is **lowered for the whole walk** (5.5% of the
  height): near-straight legs at rest have no slack for a stride and would fall short of their feet.
- **The reach check** (`REACH` lines): how far each leg falls short of its foot's target, every clip. Must be ~0
  (the dragon: 0.0 in all three).
- **The feet check** (`anim.json`, `FEET` lines, clips that stand): how far the skin on the ground (the lowest 2% of the height) moves
  over each loop, per metre of height. It must be ~0; the dragon: 0.0 in both clips. Anything else floats or skates.
- **Loops need Cycles modifiers** on every curve: Blender's "Cyclic Animation" on an action is only a label, and a
  1 s clip in a 4 s timeline otherwise plays once and stands still (Moti caught it). Saved with the skeleton active,
  or the Action Editor shows nothing.
- **LOOK** in Blender (Space plays; select the skeleton, Dope Sheet > Action Editor picks the clip): weight, no
  floating, the wing roots, each clip repeating.

## 6b. A replaceable body (`pieces.py -- <name>`, ~1 min; a character, after Mixamo)

The player's base body, cut as Skyrim's into the pieces equipment replaces: **Body** (torso, arms, legs), **Head**
(the face editor's head takes its place), **Hands**, **Feet**, each a mesh on the one Mixamo skeleton. The route:
`reduce.py` (50k, as every character) → `mixamo.py` → Mixamo by hand (Upload Character, the markers, download FBX
with skin) saved as `<name>/source_mixamo.fbx` (private, git-ignored as the Tripo source) → `pieces.py`.
- **The seams come from the rig**: a plane square to a bone part way along it (the neck 0.4 up the Neck, the wrists
  0.8 down the forearm, the ankles 0.8 down the shin), so every body is cut at the same places and armour made for
  one fits its seams. The plane cuts only the limb it crosses; the piece is what the limb's end reaches without
  crossing the cut, and a cut with a gap is refused.
- **Small holes the AI left are closed first** (up to 24 edges); bits joined to nothing (an ear's fold, the mouth)
  go with the piece past whose seam they lie.
- **The check** (`checks/pieces.json`, on the pieces and again on the FBX read back): each seam's two sides have
  the same vertices, **0 mm apart and their normals within a fraction of a degree**. Anything else shows as a line.
  body_warrior_m: neck 156, wrists 84 and 91, ankles 111 and 112 vertices, 0.0 mm, at most 0.11°.
- **LOOK** at `pieces_front/back/side.jpg`: each piece its own colour, the seams low on the neck, above the wrists
  and the ankles. Then `forge/<Title>/` goes to Forge's `Content/Characters/<Title>/` (step 5's character route:
  *Build Characters*).
- **The head is a piece any head replaces**: `<Title>.fbx` holds Body, Hands and Feet; each head is its own FBX on the
  same skeleton, `Heads/<Head>.fbx` (its mesh named "Head"): the body's own head as cut (`Heads/<Title>.fbx`, drawing
  the body's maps), and each face editor head model.json lists (`"heads": ["head_warrior_m"]`; `neck.py`), so Forge
  puts any of them on the body by its bones' names and the face editor switches them.
- **A face editor head** (head.py's) is seated by its chin (face.py finds it, as head.py does) at the body's own head's
  size (its chin to its crown as the body's own head's: 25.7 cm on body_warrior_m, x1.107 of a real head's, which looked
  small on this thick neck; model.json `"head_size"` scales from there), cut 2.5 cm up the neck, its neck laid onto
  the body's over 2.5 cm more, and a collar of rings on the body's neck down to the seam, the last ring the body's own.
  The collar wears the body's material (its texture is the body's where it lies) and the head's own faces a material
  named as the head, with its own maps (`Heads/<Head>_Color.png`, `_Normal.png`); Forge tells them apart by that name
  (`faces_per_material_in_fbx`: the collar's few hundred faces on the body's). **Blender gotcha**: clearing a mesh's
  materials puts every face in slot 0, so the faces' slots are set after the slots are made. The head's texture is
  repainted on that strip of neck from the body's skin into its own, so neither the seam nor the cut shows; its
  colour is matched to the body's, whole skin to whole skin (`skin_gain_rgb`; a strip of neck matched only the neck,
  and in the game his face read pinker than his chest), after the body's own large blotches are evened (model.json
  `skin_even`, 0.7 here: the AI paints grime and shading into a body's skin; pores stay). Each collar face takes its
  UVs from one island of the texture (`collar_faces_across_uv_seams` must be 0: across two, it draws the black
  between them). The shape keys (the face's sliders) survive into the FBX (`shape_keys_in_fbx`). Per head, the seam
  is measured again (`neck_on_pieces`, `neck_in_fbx`: 156 vertices, 0.0005 mm, 0°) and pictured on the body
  (`whole_front_<Head>.jpg`, `neck_<view>_<Head>.jpg`). `pieces.py -- <name> --head-size S` tries another size beside
  the real one.
- **Eyes of their own** (`eyes.py`, run by `head.py` for every head): the painted eyes found from the paint (a front map
  ray-cast at 0.15 mm, what is not warm skin, flooded from the iris), cut open, the rim laid on the smoothed outline
  on the skin left after the cut (nearest, not along a ray: the upper lid overhangs), the lids' inside a band into
  the eyeball; the eyeball a sphere fitted to the painted eye (WarriorM: 11.9 and 11.3 mm radius, real 12), cornea
  bulge 6%, iris painted by code in the painted iris's colour, 3 mm pupil. Its material `<Title>Eyes` (the head's last
  slot, its own `_Color.png` and a wet `_MetallicSmoothness.png`); `neck.py` keeps the eyeballs (shells of their own)
  and puts them wholly on the Head bone (no eye bones in Mixamo's rig). **LOOK** at `head_<name>/checks/eyes_*.jpg`
  and `eyes_map_<side>.png` (the outline on the paint). `probe_eyes.py` measures a head's painted eyes before any cut.
- **A new head** for a body: Iris's sheet (bald, neutral, symmetric, facing front) → Tripo → `head_<name>/source_tripo.fbx`
  → `head.py -- head_<name> <Title>` → add it to the body's `"heads"` → `pieces.py` → copy `build/forge/<Title>/` to
  Forge's `Content/Characters/<Title>/` → *Build Characters*.

## Next (planned, not built)

7. More clips: head look-around, wing fold/unfold, turn on the spot, run; roar once there is a jaw.
8. Forge plays them (waits for Forge creatures): keep the skeleton on import, bake the IK into keys before the FBX,
   an Animator for a generic rig, spring bones on tail, neck and wing tips.

## Results, the dragon

| Step | Result | Time |
|---|---|---|
| 1 | 1 shell, 944,353 vertices welded, 1,888,702 triangles, 0 open edges; 3 maps at 4096 | 30 s |
| 2 | 40,000 triangles; normals baked at 4096; nearly identical at full view, horn tips and small spikes slightly faceted up close | 106 s (decimate 61 s, bake 18 s) |
| 3 | 52 bones, 0 vertices unweighted, no tearing in the bend test | 1 min |
| 4 | 12 x 12.5 x 7 m; LODs 40,000 / 16,000 / 4,800; 12 hulls of 118-246 faces; FBX 2.2 MB, maps 8.5 MB | 1 min |
| 5 | in Forge as `forge.core:dragon` (unity-game-test 53229a9); faces +Z; EditMode 1246/1246 | 5 min |
