# base_body: the body base for Forge

One mesh (MPFB's hm08 female, CC0, the MPFB2 Blender extension), each body type MPFB's own sliders fitted to one of
Moti's Tripo bodies, the Tripo relief baked on as a normal map, the types as shape keys of the one mesh with each
type's skeleton, exported for Forge as `Content/Characters/<Title>/`. The skeleton is MPFB's `mixamo_unity` rig
(breast, buttock, jaw, eye and eyelid bones; Mixamo names, so Forge's clips play on it).

## The recipe

`types.json` names the title, the base type (the mesh; the others are shapes of it) and each type's Tripo file,
`source_<type>.fbx|glb` in this folder (`"sources"`; private and git-ignored like every `ai_models/*/source_*`: the
Downloads copies went to the Recycle Bin once, and a type cannot be refitted without its file). Blender headless,
`blender -b -P <script> -- <args>`:

1. `fit_macros.py <tripo file> <type>`: MPFB's sliders (5 macros, 26 detail targets) fitted to the Tripo body by
   cross-sections (trunk, legs, arms, breasts) and the head's size (chin to crown, the skull's width and depth over
   the ears, read with `face.profile` over everything above 0.84 of the height: MPFB's head stands 7.8 heads to the
   height where the Tripo bodies stand 6.8 to 7.1, and read as too small; `head-scale-vert/horiz/depth` take it to
   the Tripo body's within 4 mm), damped Gauss-Newton. Writes `checks/fit_<type>.json` (the sliders, the profiles,
   the head's measures) and `checks/fit_<type>_front/side.png` (MPFB left, overlaid, Tripo right). Bar: a few mm RMS
   (6-10 so far). ~1 min. `probe_head_size.py` tables every body's head against its height (`checks/head_size.json`).
1b. `wrap.py <tripo file> <type>`: her skin the rest of the way onto the Tripo body, so its muscle and form are in her
   mesh and not only in a normal map over a smooth one. Her bones stand where the slider fit put them; the Tripo body
   is placed at her height and her bones turned until she lies on it (`pose.py`); then each vertex is pulled to the
   nearest Tripo surface facing its way, the pull smoothed over the mesh as a membrane, stiff first and looser each
   round; the head and neck (the bust's), fingers and toes (Tripo's are fused) and the breasts (one chest) take no
   pull and follow; unposed through the inverse skinning, kept as a delta on the slider fit. Every bone's head and
   tail move as the skin around them moved, so the joints keep their place in their limbs (s1026: the skin wrapped
   onto the Tripo knee while the bone stayed, 3 cm off). Pass bar, logged: the body's surface within 1 mm of the
   Tripo one at the median, no knee or elbow more than 5 mm further from its limb's centre than after the slider fit
   (woman2: 0.54 mm; knees 16.7 to 17.7 mm, MPFB's own rig stands 10-16 off). `her.apply_wrap` puts the delta and
   the bone moves on wherever a type is created. Writes `build/wrap_<type>.npy`, `checks/wrap_<type>.json` (the pose,
   the Tripo's placement, the gaps, the joints, the bones' moves, the verdict), `checks/wrap_<type>_{front,side,wire}.png`.
   2-3 min.
2. `bake_detail.py <tripo file> <type>`: her (wrapped, where 1b ran: the Tripo body placed and posed as the wrap had
   it) on the Tripo body, its normals baked onto a posed copy of her, tangent space, 4096 (the Tripo's own normal map
   in them when it has one). The Tripo hands cut off the source (they hang before the hips), her hands and wrists
   masked, and every pixel whose Tripo surface leans more than 35 degrees from hers flattened (a wrong surface hit:
   an upper arm from the armpit). A painted Tripo body (Base Color in its material) also gives its colour at 8192
   (the diffuse pass's colour alone, no light; the hands in, fused fingers still have skin colour; an unpainted pixel
   takes the median) and its roughness at 4096. Writes `build/<type>_normal.png` (`_color.png`, `_roughness.png`),
   `build/detail_<type>.blend` (look at her beside the Tripo body), `checks/detail_<type>_{torso,whole,side}.png`.
   1-5 min.
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

Adding a type: a line in `types.json`, steps 1, 1b, 2, 4, 5. `show_types.py` puts every fitted type beside its Tripo
body in one `.blend` to look at; `export_forge.py` exports one type alone (step 1 of the base, before the types).
`her.py` (her at a type's sliders and a face's, settled, wrapped) and `pose.py` (the Tripo body placed, her posed
onto it, her skinning as matrices) are what the steps share.

## Her face

`types.json` names the face (`"face"`, one of `"faces"`: a Tripo bust, `source_<name>.fbx` with its texture folder beside
it under the name the FBX carries inside, `woman_head_3d_model.fbm` (git-ignored as `*.fbm/`), bald, neutral, 8K
unlit paint;
`probe_head.py <bust> <tag>` looks one over first). Her head stays MPFB's own, so its face sliders, rig and expressions
are hers; the bust gives it its shape, paint and relief:

6. `fit_face.py <bust> <name>`: MPFB's face sliders (every target under head, forehead, eyebrows, eyes, nose, mouth,
   chin, cheek, ears, neck but the head's and neck's own height and place against the body: 124, a decr/incr pair one
   slider, left and right as one) fitted to the bust, Gauss-Newton: every head vertex to the bust's surface along its
   normal there, the bust scaled onto her head by chin to crown (her chin read with her neck in, as step 1 reads it:
   the head island ends under the chin and over it alone the profile takes the lip crease for the chin, 3 cm up; the
   scale then stays put: let float, it followed the head-shrinking sliders down and she lost a tenth of her head's
   height and a sixth of its width) and moved onto it with them, the landmarks in its paint pulled together (the
   pupils, the darkest points above the nose; the mouth's corners, the dark line between the lips; the nose tip, chin
   and crown from the profile, her nose and chin vertices kept from the start), the sliders held near 0. Her head
   0.8 mm off the bust at the median, 2.4 at p90, the crown, nose and chin within 2 mm. Writes `checks/face_<name>.json`
   (the sliders and their target files, the bust's scale and shift, the iris's colour), `checks/face_<name>_{front,side}.png`
   (her head in blue over the bust, landmarks as dots). 15 s.
7. `bake_face.py <bust> <name>`: her head's skin island (one UV island, the eye cups and the mouth pocket islands of
   their own) scaled to fill a square of its own (`her.head_uv_fit`), and Cycles bakes the bust's normals and colour
   onto a copy of her head alone, 4096, stray hits flattened as in step 2; the body's colour on her own UV, the bust
   wherever it reaches (its cut base taken off the source; a miss paints black, read as a miss), fading to its own skin
   tone. Writes `build/face_<name>_{color,normal}.png`, `build/body_<name>_color.png`, the UV fit and the tone into the
   face's json, `checks/bake_face_<name>_{face,quarter,whole}.png`. 2 min.
7b. `skin_body.py <skin> <face>`: the body's colour. The skin is a painted type's paint (`"skin"` in `types.json`
   names the type, the base; a type's Tripo body may come painted: `probe_body.py <file> <name>` looks a candidate
   over first, the mesh, the maps, the head to the height, and how even the paint is, a lit render baked into it
   showing as a darker back and underside; step 2 bakes its 8K paint and roughness onto her UV; every type lies on
   the one UV, so the skin type's roughness serves all, and another painted type's paint is toned to the skin's in
   the build), or else MPFB's own skin (a MakeHuman system asset, CC0: the pack
   `makehuman_system_assets_cc0.zip` from static.makehumancommunity.org, unzipped into MPFB's user data folder,
   `LocationService.get_user_data()`; 2K on her UV). The tone is matched median over median in linear light (a gain
   on the encoded values went green): a painted body sets the tone and the face follows it (`build/face_<face>_skin.png`,
   which the build takes for the face slot), MPFB's skin follows the face. Writes `build/body_<face>_color.png` after
   step 7. `skin_step1.py <skin>` puts her with an MPFB skin through MPFB's skin shader beside the built body, to look
   at in Blender (`build/skin_step1.blend`); `status_scene.py` puts the built body beside the painted Tripo body
   at her height (`build/status.blend`, `checks/status_{whole,torso,face}.png`): the comparison that decides.
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
8. `build_body.py` reads the face: every type worn with it, wrapped where 1b ran (the delta and the bones' moves),
   the skin's roughness as `<Title>_MetallicSmoothness.png` (smoothness in the alpha, as URP Lit reads it); the
   head's faces on a second slot `<Title>Face` with the square's UVs; Forge's face controls (`CONTROLS`: FaceEditorScreen's parts and controls, each an MPFB target pair,
   the shape named `PartControl`, the positive end at 100) as shape keys, the eyeballs carried with their sockets;
   eyeballs (`eyes.py`'s) on the LeftEye and RightEye bones, their radius the rims' least distance less 0.5 mm, a third
   slot `<Title>Eyes` with `eye_texture` in the paint's iris colour. Every shape key is pinned at 0 after the eyeballs
   (bmesh writes them back at 1.0) and asserted so: the FBX would carry them in the body otherwise.
9. Into Forge as step 5. Build Characters reads a humanoid model's skeleton off the model again when its bones moved
   (`HumanoidTPose`): Unity keeps the stored one through every reimport, and her eyes and jaw moved with the fit.

`her.py` is what the scripts share: `create` (her at a type's sliders and a face's), `settle`, `Head` (the skin island,
the rims of the eye cups and the mouth pocket). `built.py` is how a build is brought back to look at (`import_build`:
the FBX with its maps wired as URP reads them; `light_and_camera`), for `status_scene.py` and `compare_faces.py`.

### Replacing the face

A new Tripo bust (bald, neutral, unlit, 8K; colour alone is enough, the relief then comes from its geometry) replaces
the face without touching the body, the types or the wraps; done with woman2 (s1031, `human face 3d model.zip`, a
5k-quad bust with its two eyeballs as loose parts of the one mesh, 8K colour, no normal map):

1. Unzip into this folder: the FBX as `source_<name>.fbx`, its `.fbm` folder kept under the name it came with (the FBX
   finds its textures there). `probe_head.py source_<name>.fbx <name>`: bald, neutral, even paint, the eyes in it.
2. `types.json`: the bust under `faces`, `"face"` set to it.
3. `fit_face.py source_<name>.fbx <name>` (10 s; woman2: 0.9 mm median, 2.5 p90, the pupils 5 mm off, 96 sliders),
   `bake_face.py` (1 min), `skin_body.py skinny <name>` (the face toned to the body's paint), `build_body.py` (2 min).
4. To see the change: before the build, `cp -r build/forge/<Title> build/forge/<Title>_<old face>`; after it,
   `compare_faces.py <old face>` puts the snapshot on the left and the new build on the right (`build/faces.blend`,
   `checks/faces_{front,whole}.png`, `checks/faces_quarter_<face>.png`). Then `status_scene.py` as always.

The face's sliders, maps, tone and iris colour all come from the bust; what stays the same is MPFB's head mesh and
rig under them, so the face controls, the eyeballs and the expressions work on any face. Neither the bust's neck nor
its shoulders reach the build when the skin is a painted body's (step 7b): under the chin the face bake's body colour
can go dark where the bust is cut short (woman2's neck ends 2 cm under the chin), and `skin_body.py` paints over it.

## What is not done

- No subsurface in the game (URP Lit has none); the pore tile (7c) is superseded by the painted body's own normal map
  where there is one.
- The face is what MPFB's sliders can say: a residual pass onto the bust, as a shape key of her own (the wrap, 1b, on
  the head), is the next step.
- No blink, no eyes' colour choice, no brow thickness (MPFB has no target for it: the brows are paint on her).
- The shoulders are not in the fit's profile (the wrap carries them now).
- The Tripo fingers are fused, so her hands keep MPFB's own relief (masked in the bake).
