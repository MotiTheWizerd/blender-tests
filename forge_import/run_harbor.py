"""Harbor batch (Forge, 2026-11-08): Poly Haven's ships, pier and props (CC0), each material a part with its own maps.
python run_harbor.py [Name ...]; out/<Name>/ is what goes into Content/Models/<Name>/. Sources: fetch_ph.py 2k <assets>."""
import json
import subprocess
import sys

D = r"C:\Users\User\AppData\Local\Temp\oga\harbor"
B = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
X = r"C:\Users\User\AppData\Local\Temp\oga\forge_export2.py"


def ph(asset):
    return D + rf"\ph\{asset}\{asset}_2k.gltf"


def sails(asset):
    """Poly Haven's sails keep their alpha in a map of its own, which their glTF leaves out (fetched beside it)."""
    return {"Sails": D + rf"\ph\{asset}\textures\{asset}_sails_alpha_2k.png"}


def parts(asset, *names):
    """Poly Haven names a model's materials <asset>_<part>: each becomes a part."""
    return {f"{asset}_{n.lower()}": n for n in names}


SHIP = dict(scale=1.0, grip=0, hulls=[], collide=["Hull"], lods=[0.4, 0.15], size=2048, arm=True)
PROP = dict(scale=1.0, grip=0, hulls=[], size=1024, arm=True)
PIER = {"modular_wooden_pier_planks": "Planks", "modular_wooden_pier_poles.001": "Poles"}

SPECS = [
    dict(SHIP, src=ph("dutch_ship_medium"), name="DutchShipMedium", alpha_maps=sails("dutch_ship_medium"), parts=parts("dutch_ship_medium", "Hull", "Rigging", "Sails"),
         part_size={"Rigging": 1024, "Sails": 1024}),
    dict(SHIP, src=ph("dutch_ship_large_01"), name="DutchShipLarge", alpha_maps=sails("dutch_ship_large_01"), parts=parts("dutch_ship_large_01", "Hull", "Rigging", "Sails"),
         part_size={"Rigging": 1024, "Sails": 1024}),
    dict(SHIP, src=ph("dutch_ship_large_02"), name="DutchShipLargeSailing", alpha_maps=sails("dutch_ship_large_02"), parts=parts("dutch_ship_large_02", "Hull", "Rigging", "Sails"),
         part_size={"Rigging": 1024, "Sails": 1024}),
    dict(SHIP, src=ph("ship_pinnace"), name="Pinnace",
         alpha_maps=sails("ship_pinnace"), parts=parts("ship_pinnace", "Hull", "Deck", "Aft", "Details", "Interior", "Rigging", "Sails"),
         part_size={"Aft": 1024, "Details": 1024, "Interior": 512, "Rigging": 1024, "Sails": 1024}),
    dict(PROP, src=ph("wooden_crate_01"), name="SmallCrate", parts={"wooden_crate_01": ""}, lods=[0.35]),
    dict(PROP, src=ph("wooden_crate_02"), name="LongCrate", parts={"wooden_crate_02": ""}, lods=[0.35]),
    dict(PROP, src=ph("wooden_barrels_01"), objects=["wooden_barrels_01_barrel01"], name="WoodenBarrel",
         parts={"wooden_barrels_01_barrel01": ""}, lods=[0.35]),
    dict(PROP, src=ph("wooden_barrels_01"), objects=["wooden_barrels_01_barrel02"], name="WornBarrel",
         parts={"wooden_barrels_01_barrel02": ""}, lods=[0.35]),
    dict(PROP, src=ph("wine_barrel_01"), name="WineBarrel", parts={"wine_barrel_01": ""}, lods=[0.35]),
    dict(PROP, src=ph("wooden_bucket_01"), name="WoodenBucket", parts={"wooden_bucket_01": ""}, lods=[0.35]),
    dict(PROP, src=ph("wooden_bucket_02"), name="WashTub", parts={"wooden_bucket_02": ""}, lods=[0.35]),
    dict(PROP, src=ph("wooden_lantern_01"), name="WoodenLantern", parts={"wooden_lantern_01": "", "wooden_lantern_01_glass": "Glass"},
         alpha_maps={"Glass": D + r"\ph\wooden_lantern_01\textures\wooden_lantern_01_glass_opacity_2k.png"}, lods=[0.35], collide=[""]),
    dict(PROP, src=ph("treasure_chest"), name="TreasureChest", parts={"treasure_chest": ""}, decimate=0.1, lods=[0.35]),
    dict(PROP, src=ph("cannon_01"), name="Cannon", parts={"cannon_01": ""}, decimate=0.3, lods=[0.4, 0.15]),
    dict(PROP, src=ph("wicker_basket_01"), name="WickerTray", parts={"wicker_basket_01": ""}, decimate=0.25, lods=[0.35]),
    dict(PROP, src=ph("wicker_basket_02"), name="LiddedBasket", parts={"wicker_basket_02": ""}, decimate=0.3, lods=[0.35]),
]
for n in range(1, 6):
    SPECS.append(dict(PROP, src=ph("modular_wooden_pier"), objects=[f"modular_wooden_pier_section_0{n}"], name=f"PierSection{n}",
                      parts=PIER, hulls=[0.8], lods=[0.4]))

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
        print(spec["name"], lines[-3:] if lines else (r.stdout + r.stderr)[-1500:], flush=True)
