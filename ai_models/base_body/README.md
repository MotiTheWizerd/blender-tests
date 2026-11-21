# base_body: the body base for Forge

One mesh (MPFB's hm08 female, CC0, the MPFB2 Blender extension), each body type MPFB's own sliders fitted to one of
Moti's Tripo bodies, the Tripo relief baked on as a normal map, the types as shape keys of the one mesh with each
type's skeleton, exported for Forge as `Content/Characters/<Title>/`. The skeleton is MPFB's `mixamo_unity` rig
(breast, buttock, jaw, eye and eyelid bones; Mixamo names, so Forge's clips play on it).

## The recipe

`types.json` names the title, the base type (the mesh; the others are shapes of it) and each type's Tripo file in
`~/Downloads`. Blender headless, `blender -b -P <script> -- <args>`:

1. `fit_macros.py <tripo file> <type>`: MPFB's sliders (5 macros, 25 detail targets) fitted to the Tripo body by
   cross-sections (trunk, legs, arms, breasts), damped Gauss-Newton. Writes `checks/fit_<type>.json` (the sliders,
   the profiles) and `checks/fit_<type>_front/side.png` (MPFB left, overlaid, Tripo right). Bar: a few mm RMS (6-10
   so far). ~1 min.
2. `bake_detail.py <tripo file> <type>`: her pose fitted onto the Tripo body (bones turned), the Tripo normals baked
   onto a posed copy of her, tangent space, 4096. The Tripo hands cut off the source (they hang before the hips), her
   hands and wrists masked, and every pixel whose Tripo surface leans more than 35 degrees from hers flattened (a
   wrong surface hit: an upper arm from the armpit). Writes `build/<type>_normal.png`, `build/detail_<type>.blend`
   (look at her beside the Tripo body), `checks/detail_<type>_{torso,whole,side}.png`. 1-4 min.
3. `probe_types.py`: all types share the vertex order, where each type's joints stand, and how far each knee and
   elbow is from its limb's centre (`checks/probe_types.json`). MPFB's rig: knees 10-16 mm, elbows 5-7 mm.
4. `build_body.py`: `build/forge/<Title>/`: the FBX (the base as "Body" on the rig, the other types as shape keys,
   weights trimmed to 4 bones a vertex as Unity reads them), the maps, `Bodies/types.json` for Forge with each type's
   `joints` (every bone's rest position, Unity's frame) and `landmarks` (48 points of its skin). A shape key holds the
   type less what moving the bones to its joints does to the skin, so in Unity the shape at 100 and the bones moved
   are the type.
5. Into Forge: copy `build/forge/<Title>/` over `Assets/_Project/Content/Characters/<Title>/` (the json
   `{ "textureSize": 4096, "voice": "female" }` is Forge's), refresh, `Forge/Characters/Build Characters`,
   `git checkout` Humanoid.controller if it only re-serialized, EditMode (`BodyTypesContentTests`: every bone within
   1 mm of its joint, the skin within 3 mm of where built, knees and elbows centred, each type's avatar its own).

Adding a type: a line in `types.json`, steps 1, 2, 4, 5. `show_types.py` puts every fitted type beside its Tripo body
in one `.blend` to look at; `export_forge.py` exports one type alone (step 1 of the base, before the types).

## What is not done

- Her skin is flat (`SKIN` in `build_body.py`); MPFB's own skin material is not wired in.
- Her head is MPFB's own, no eyes: the Tripo heads come as Forge's replaceable heads.
- Built and fit read soft where their muscle is only in the normal map; the shoulders are not in the fit's profile.
- The Tripo fingers are fused, so her hands keep MPFB's own relief (masked in the bake).
