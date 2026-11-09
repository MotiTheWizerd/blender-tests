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

## Next (planned, not built)

3. Rig: a skeleton built from landmarks found on the mesh (spine, neck, head, jaw, tail chain, four legs, two wings
   with finger bones), automatic weights, then the wings and neck checked. **LOOK**: bend each chain, no tearing.
4. Animate: idle breathing, head look-around, wing fold/unfold, wing-flap loop, walk; roar once there is a jaw.
5. Export FBX into Forge's model contract; Unity: Animator, spring bones on tail, neck and wing tips.
6. LODs and colliders, as the other Forge models.

## What is kept in git

The scripts, this recipe, each step's json and pictures. Not the Tripo source (re-export it, step 0) nor what the
steps make from it (rerun them: steps 1-2 take about 2 minutes on the RTX 5060).

## Results, the dragon

| Step | Result | Time |
|---|---|---|
| 1 | 1 shell, 944,353 vertices welded, 1,888,702 triangles, 0 open edges; 3 maps at 4096 | 30 s |
| 2 | 40,000 triangles; normals baked at 4096; nearly identical at full view, horn tips and small spikes slightly faceted up close | 106 s (decimate 61 s, bake 18 s) |
