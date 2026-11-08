import json, subprocess, sys
D = r"C:\Users\User\AppData\Local\Temp\oga\ph\o"
B = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
ARB = D + r"\d_dims-arboretum-for-blender-431\dim_arboretum_converted_oga.blend"
HP = D + r"\d_medieval-house-pack\House3Upload.blend"
HOUSE_WIRE = {"DoorType1_2": "DoorType1_2.jpg", "GreyBrick2": "GreyBricks2.jpg", "GreyStone2": "GreyStone2.jpg",
              "LogEdgeWeathered": "TreeLogEdgeWeathered.jpg", "Plaster": "PlasterLarge.jpg", "RoofTiles": "RoofTiles.jpg",
              "RustedMetal": "Rusted Metal.jpg", "Stone": "Stone.jpg", "WindowBlue1": "WindowsBlue2.jpg",
              "WindowBlue2": "WindowsBlue2.jpg", "Wood": "Wood.jpg"}
SPECS = [
    dict(src=D + r"\d_medieval-cottage\Cottage\cottage.blend", objects=["cottage"], name="MedievalCottage", fix_normals=True, scale=1.0, grip=0, hulls=[]),
    dict(src=D + r"\d_medieval-shack\medievalshackwood.blend", objects=["Hut01"], name="WoodenShack", double_sided=True, length=3.4, grip=0, hulls=[],
         bake=True, size=2048, surface={"*": [0.0, 0.2]}),
    dict(src=D + r"\d_old-medieval-house\small_shack.FBX", name="OldShack", length=4.9, grip=0, hulls=[], bake=True, size=2048,
         alpha=True, surface={"*": [0.0, 0.2]}),
    dict(src=HP, objects=None, name="TimberHouse", scale=1.0, grip=0, hulls=[], bake=True, size=2048,
         wire={k: {"base": v} for k, v in HOUSE_WIRE.items()}, surface={"RustedMetal": [0.8, 0.35], "WindowBlue1": [0.0, 0.8], "WindowBlue2": [0.0, 0.8], "*": [0.0, 0.2]}),
    dict(src=ARB, objects=["AbiesBalsamica"], name="BalsamFir", scale=1.0, grip=0, trunk=[0.25, 2.0], bake=True, size=1024, alpha=True, surface={"*": [0.0, 0.15]}),
    dict(src=ARB, objects=["FagusAmericana"], name="BeechTree", scale=1.0, grip=0, trunk=[0.3, 2.0], bake=True, size=1024, alpha=True, surface={"*": [0.0, 0.15]}),
    dict(src=ARB, objects=["AthyriumFelix-Femina"], name="LadyFern", scale=0.55, grip=0, trunk=[0.05, 0.3], bake=True, size=512, alpha=True, surface={"*": [0.0, 0.2]}),
    dict(src=ARB, objects=["ClethraAlnifolia"], name="FloweringBush", scale=0.55, grip=0, trunk=[0.1, 0.5], bake=True, size=512, alpha=True, surface={"*": [0.0, 0.2]}),
    dict(src=ARB, objects=["ChrysanthemumLeucanth"], name="OxeyeDaisy", scale=0.22, grip=0, trunk=[0.03, 0.2], bake=True, size=512, alpha=True, surface={"*": [0.0, 0.2]}),
    dict(src=ARB, objects=["DaucusCarota"], name="WildCarrot", scale=0.35, grip=0, trunk=[0.03, 0.2], bake=True, size=512, alpha=True, surface={"*": [0.0, 0.2]}),
    dict(src=ARB, objects=["TyphaLatifolia"], name="Cattail", scale=0.6, grip=0, trunk=[0.05, 0.3], bake=True, size=512, alpha=True, surface={"*": [0.0, 0.2]}),
    dict(src=ARB, objects=["ArctinumMinus"], name="Burdock", scale=0.6, grip=0, trunk=[0.05, 0.2], bake=True, size=512, alpha=True, surface={"*": [0.0, 0.2]}),
]
for n in (1, 2, 3, 4, 5):
    SPECS.append(dict(src=D + rf"\d_bushes\0{n}\bush_0{n}.FBX", name=f"Bush{n}", length=1.4 if n != 3 else 1.8, grip=0, trunk=[0.08, 0.4]))
only = sys.argv[1:]
for spec in SPECS:
    if only and spec["name"] not in only:
        continue
    spec["out_dir"] = D + r"\out"
    path = D + rf"\spec_{spec['name']}.json"
    json.dump(spec, open(path, "w"))
    r = subprocess.run([B, "-b", "--python", r"C:\Users\User\AppData\Local\Temp\oga\forge_export2.py", "--", path], capture_output=True, text=True)
    lines = [l for l in (r.stdout + r.stderr).splitlines() if "EXPORTED" in l or "Error" in l or "Traceback" in l]
    print(spec["name"], lines[-3:] if lines else (r.stdout + r.stderr)[-600:], flush=True)
