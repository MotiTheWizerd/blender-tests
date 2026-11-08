"""Ground clutter batch (Forge, 2026-11-08): Poly Haven's small nature models (CC0), the small things that make ground look
lived in: a stone, mossy rocks, fallen branches, roots, a stump and low plants.
Left out: Poly Haven's grass, nettles, sorrel and stone sets are sprigs and pebbles a few centimetres across laid out
in a showcase row, made to be scattered by the thousand; grass at street edges comes from the terrain's own grass instead. Each model one object (a
Poly Haven set holds several), its single material a part with its own maps; plants cut out by Poly Haven's own alpha
map. python run_clutter.py [Name ...]; out/<Name>/ goes into Content/Models/<Name>/. Sources: fetch_ph.py 2k <assets>,
plus each plant's Alpha map (2k png) beside its textures as <asset>_alpha_2k.png."""
import json
import subprocess
import sys

D = r"C:\Users\User\AppData\Local\Temp\oga\clutter"
B = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
X = r"C:\Users\User\AppData\Local\Temp\oga\forge_export2.py"


def ph(asset):
    return D + rf"\ph\{asset}\{asset}_2k.gltf"


def alpha(asset):
    return {"": D + rf"\ph\{asset}\textures\{asset}_alpha_2k.png"}


PROP = dict(scale=1.0, grip=0, hulls=[], size=1024, arm=True, lods=[0.4, 0.15])
PLANT = dict(PROP, size=512)

SPECS = [
    dict(PROP, src=ph("stone_01"), name="Stone", parts={"stone_01": ""}, decimate=0.3),
    dict(PROP, src=ph("rock_moss_set_01"), objects=["rock_moss_set_01_rock01"], name="MossyRock", parts={"rock_moss_set_01": ""}),
    dict(PROP, src=ph("rock_moss_set_01"), objects=["rock_moss_set_01_rock03"], name="MossyRockLow", parts={"rock_moss_set_01": ""}),
    dict(PROP, src=ph("rock_moss_set_02"), objects=["rock_moss_set_02_rock08"], name="MossyBoulder", parts={"rock_moss_set_02": ""}),
    dict(PROP, src=ph("dry_branches_medium_01"), name="DryBranches", parts={"dry_branches_medium_01": ""}),
    dict(PROP, src=ph("pine_roots"), objects=["pine_roots_a"], name="Roots", parts={"pine_roots_a": ""}, decimate=0.25),
    dict(PROP, src=ph("tree_stump_01"), name="TreeStump", parts={"tree_stump_01": ""}, decimate=0.5),
    dict(PLANT, src=ph("fern_02"), objects=["fern_02_a"], name="Fern", parts={"fern_02": ""}, alpha_maps=alpha("fern_02")),
    dict(PLANT, src=ph("weed_plant_02"), objects=["weed_plant_02_a_LOD0"], name="Weed", parts={"weed_plant_02": ""}, alpha_maps=alpha("weed_plant_02")),
    dict(PLANT, src=ph("dandelion_01"), objects=["dandelion_01_a_LOD0"], name="Dandelion", parts={"dandelion_01": ""}, alpha_maps=alpha("dandelion_01")),
]

if __name__ == "__main__":
    only = sys.argv[1:]
    for spec in SPECS:
        if only and spec["name"] not in only:
            continue
        spec["out_dir"] = D + rf"\out\{spec['name']}"
        path = D + rf"\spec_{spec['name']}.json"
        json.dump(spec, open(path, "w"))
        r = subprocess.run([B, "-b", "--python", X, "--", path], capture_output=True, text=True)
        lines = [l for l in (r.stdout + r.stderr).splitlines() if "EXPORTED" in l or "Error" in l or "Traceback" in l]
        print(spec["name"], lines[-3:] if lines else (r.stdout + r.stderr)[-600:], flush=True)
