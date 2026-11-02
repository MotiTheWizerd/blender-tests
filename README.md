# blender-tests

Moti + Claude learning Blender → Unity, one asset at a time. Started 2026-11-02.

Claude drives a live Blender through the BlenderMCP addon's socket (`bl.py`),
so every step here is a script you can read and re-run.

## langford.blend — three scenes

| Scene | What |
|---|---|
| `Scene` | A Langford pairing (n=7) as glowing arcs (`langford.py`) |
| `longship` | A night longship, Huginn and Muninn on the yard, rowing oars, the arcs as an aurora (`longship.py`, `upgrade1.py`) |
| `sword` | A game-ready one-handed sword for a Skyrim-like Unity game |

## The sword pipeline

| Step | Script | What it does |
|---|---|---|
| 1–2 | `sword.py` | Low-poly mesh (1,462 tris), real scale, pivot at the grip, Unity axes |
| 3 | `sword.py`, `uv_tall.py` | Seams + Blender unwrap, packed for a tall 1:4 texture (66% coverage) |
| 4 | `texture.py` | Procedural steel / iron / leather, baked to colour, metallic-smoothness, normal |
| 5 | `step5.py` | High poly (bevels + subdivision, 45k faces) with runes in the fullers, baked to 1024×4096 |
| 6 | `step6.py` | LOD0/1/2 (1,462 / 730 / 292 tris) and convex colliders |

Runes: ᚺᚢᚷᛁᚾᚾ · ᛗᚢᚾᛁᚾᚾ on one side, the makers' mark ᛗᛟᛏᛁ · ᚲᛚᚨᚢᛞᛖ on the other.

## Into Unity

1. Copy `export/Sword.fbx` and the three `Sword_*.png` into `Assets/`.
2. Copy `export/Editor/SwordImportSetup.cs` into `Assets/Editor/` — it turns the `_COL` meshes into invisible convex colliders.
3. Unity builds the LOD Group from the `_LOD0/1/2` names by itself.
4. Material (URP/Lit): Base Map = `Sword_BaseColor`, Metallic Map = `Sword_MetallicSmoothness` (smoothness from its alpha), Normal Map = `Sword_Normal` (set its Texture Type to Normal map).

Not yet tested inside Unity. Known: small specks on one cutting edge (bake), LOD1/2 blades shade darker (they share LOD0's normal map).
