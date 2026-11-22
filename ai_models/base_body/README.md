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

## Her face

`types.json` names the face (`"face"`, one of `"faces"`: a Tripo bust in `~/Downloads`, bald, neutral, 8K unlit paint;
`probe_head.py <bust> <tag>` looks one over first). Her head stays MPFB's own, so its face sliders, rig and expressions
are hers; the bust gives it its shape, paint and relief:

6. `fit_face.py <bust> <name>`: MPFB's face sliders (every target under head, forehead, eyebrows, eyes, nose, mouth,
   chin, cheek, ears, neck but the head's and neck's own size and place against the body: 124, a decr/incr pair one
   slider, left and right as one) fitted to the bust, Gauss-Newton: every head vertex to the bust's surface along its
   normal there, the bust scaled and moved onto her head with them, the landmarks in its paint pulled together (the
   pupils, the darkest points above the nose; the mouth's corners, the dark line between the lips; the nose tip, chin
   and crown from the profile), the sliders held near 0. Her head 1 mm off the bust at the median, 2.6 at p90. Writes
   `checks/face_<name>.json` (the sliders and their target files, the bust's scale and shift, the iris's colour),
   `checks/face_<name>_{front,side}.png` (her head in blue over the bust, landmarks as dots). 15 s.
7. `bake_face.py <bust> <name>`: her head's skin island (one UV island, the eye cups and the mouth pocket islands of
   their own) scaled to fill a square of its own (`her.head_uv_fit`), and Cycles bakes the bust's normals and colour
   onto a copy of her head alone, 4096, stray hits flattened as in step 2; the body's colour on her own UV, the bust
   wherever it reaches (its cut base taken off the source; a miss paints black, read as a miss), fading to its own skin
   tone. Writes `build/face_<name>_{color,normal}.png`, `build/body_<name>_color.png`, the UV fit and the tone into the
   face's json, `checks/bake_face_<name>_{face,quarter,whole}.png`. 2 min.
7b. `skin_body.py <skin> <face>`: the body's colour is MPFB's own skin (a MakeHuman system asset, CC0: the pack
   `makehuman_system_assets_cc0.zip` from static.makehumancommunity.org, unzipped into MPFB's user data folder,
   `LocationService.get_user_data()`; 2K on her UV) shifted to the face paint's tone, median over median in linear
   light (a gain on the encoded values went green), so the face slot and the body meet at the neck in one skin.
   Overwrites `build/body_<face>_color.png`, so it runs after step 7. `skin_step1.py <skin>` puts her with the skin
   through MPFB's skin shader beside the built body, to look at in Blender (`build/skin_step1.blend`).
7c. `skin_pores.py [size] [cells]`: a tileable height tile of skin's micro relief (periodic Worley cells: grooves
   where the second point is as near as the first, a pore at each point, three scales of periodic noise), 1024 px,
   48 cells. At 4K over her whole UV a millimetre is two pixels, so pores cannot live in the baked map: the tile
   repeats in the shader, PORE_TILES (36) across her UV, a bump over the baked normals (skin_step1.py wires it; the
   face's square takes fewer tiles, its island 1.465 times larger, so the pores keep one size). Unity's URP Lit
   carries it later as the detail normal.
7d. Roughness by region (`skin_step1.py`, `ROUGH`): a vertex attribute, the nose 0.4, the forehead 0.44, the lips
   0.38, the rest of the face 0.52, the body 0.6, smoothed six passes over the mesh so no region has an edge, and the
   pore tile's grooves 0.2 rougher than its plateaus; the shader adds the two. Forge takes it later as the
   `_MetallicSmoothness` map's alpha (1 - roughness).
8. `build_body.py` reads the face: every type worn with it; the head's faces on a second slot `<Title>Face` with the
   square's UVs; Forge's face controls (`CONTROLS`: FaceEditorScreen's parts and controls, each an MPFB target pair,
   the shape named `PartControl`, the positive end at 100) as shape keys, the eyeballs carried with their sockets;
   eyeballs (`eyes.py`'s) on the LeftEye and RightEye bones, their radius the rims' least distance less 0.5 mm, a third
   slot `<Title>Eyes` with `eye_texture` in the paint's iris colour. Every shape key is pinned at 0 after the eyeballs
   (bmesh writes them back at 1.0) and asserted so: the FBX would carry them in the body otherwise.
9. Into Forge as step 5. Build Characters reads a humanoid model's skeleton off the model again when its bones moved
   (`HumanoidTPose`): Unity keeps the stored one through every reimport, and her eyes and jaw moved with the fit.

`her.py` is what the scripts share: `create` (her at a type's sliders and a face's), `settle`, `Head` (the skin island,
the rims of the eye cups and the mouth pocket).

## What is not done

- Her skin is MPFB's 2K paint in the face's tone with the pore tile over it: one roughness still, no subsurface in
  the game (URP Lit has none), and the pore tile is not in the Forge build yet.
- Her head's size against the body is MPFB's, not the Tripo body's (the head is not in fit_macros' profile), and the
  face is what MPFB's sliders can say: a residual pass onto the bust, as a shape key of her own, is the next step.
- No blink, no eyes' colour choice, no brow thickness (MPFB has no target for it: the brows are paint on her).
- Built and fit read soft where their muscle is only in the normal map; the shoulders are not in the fit's profile.
- The Tripo fingers are fused, so her hands keep MPFB's own relief (masked in the bake).
