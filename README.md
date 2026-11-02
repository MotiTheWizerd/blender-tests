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

## The Viking sword's AI parts (scene `viking`)

| Part | Script | Source |
|---|---|---|
| Pommel | `fit_pommel.py` | `source/ai3d/hy3d-model.glb` — Moti's Hunyuan3D web run on `crops/pommel.png` |
| Guard | `fit_guard.py` | `source/ai3d/dragon_head_hunyuan.glb` — Hunyuan3D v2.5 via Siray (Claude's `brokkr`) on `crops/dragon_head_noblade.png` |

The guard is one AI head, its band cut away, mirrored into the pair and scaled by the reference
(beak tip 88 mm from the centre on the 52 mm band). The code-built parts it replaced are kept
in the excluded collections `ravens_from_code` and `guard_from_code`. Render: `source/guard_ai_front.png`.

## The Viking sword, game-ready (`game_viking.py` → `export/viking/`, `viking_game.blend`)

`blender -b langford.blend -P game_viking.py` (headless, ~12 min on 8 CPU cores) bakes the whole
`viking` scene, 135k faces of procedural materials and AI meshes, onto one low mesh:

| | |
|---|---|
| LOD0 / LOD1 / LOD2 | 8,781 / 4,389 / 1,755 tris, one material, one UV set |
| Low mesh | decimated blade, AI guard and AI pommel; a plain grip cylinder; the two bands as they are |
| Textures (4096²) | `Viking_BaseColor` (sRGB), `Viking_MetallicSmoothness` (R metal, A smoothness), `Viking_Normal` (OpenGL) |
| Colliders | `Viking_Blade_COL`, `Viking_Guard_COL`, `Viking_Grip_COL` (convex, 12–20 tris) |
| Pivot | the grip's centre; the point is Unity +Y |

Runes, knotwork and the wire braid exist only in the textures. Base colour, metal and roughness are
baked as emission from each high material's own sockets, because a diffuse-colour bake reads black
on metal. Previews: `export/viking/viking_game_*.png` show the low mesh alone, rendered in EEVEE.

The AI guard's material came from Hunyuan as metallic 0, roughness 1 (chalk). `fit_guard_iron.py`
darkens its painted texture and makes it iron before the bake.

## Beauty shots (`beauty.py`, `render_beauty.py` → `export/beauty/`)

Scene `viking_beauty`: the high-poly sword instanced, a dark studio built for metal (a key softbox,
two narrow rim strips, a weak fill, a glow on the backdrop, and a strip placed in the blade's mirror
direction so a highlight runs down the steel), AgX Punchy at -1 exposure, Cycles. Cameras `cam_hero`
(full sword) and `cam_hilt` (100 mm, f/4, focused on the near dragon). Previews: `-- preview`
(960x540, 24 samples, ~25 s); finals 1920x1080 at 96 samples + denoise, 3-4 min each on this CPU.

## Into Unity

1. Copy `export/Sword.fbx` and the three `Sword_*.png` into `Assets/`.
2. Copy `export/Editor/SwordImportSetup.cs` into `Assets/Editor/` — it turns the `_COL` meshes into invisible convex colliders.
3. Unity builds the LOD Group from the `_LOD0/1/2` names by itself.
4. Material (URP/Lit): Base Map = `Sword_BaseColor`, Metallic Map = `Sword_MetallicSmoothness` (smoothness from its alpha), Normal Map = `Sword_Normal` (set its Texture Type to Normal map).

The Viking sword goes the same way: `export/viking/Viking.fbx` + the three `Viking_*.png`, the same Editor script.

Not yet tested inside Unity. Known: small specks on one cutting edge (bake), LOD1/2 blades shade darker (they share LOD0's normal map).
