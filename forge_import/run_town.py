"""Town batch (Forge, 2026-11-08), the map agent's street dressing: system-g6's Medieval Props and Buildings packs,
iconoclast's covered well and hreikin's houses 1, 2 and 4 (all OpenGameArt, CC0).
python run_town.py [Name ...]; out/<Name>/ is what goes into Content/Models/<Name>/."""
import json
import subprocess
import sys

D = r"C:\Users\User\AppData\Local\Temp\oga\town"
B = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
X = r"C:\Users\User\AppData\Local\Temp\oga\forge_export2.py"
PROPS = D + r"\x_medieval_props_pack\medieval_props_pack"
BUILDINGS = D + r"\x_medieval_buildings_pack\medieval_buildings_pack"
HOUSE_WIRE = {"DoorType1_1": "DoorType1_1.jpg", "DoorType1_2": "DoorType1_2.jpg", "GreyBrick2": "GreyBricks2.jpg",
              "GreyStone2": "GreyStone2.jpg", "LogEdgeWeathered": "TreeLogEdgeWeathered.jpg", "Plaster": "PlasterLarge.jpg",
              "RoofTiles": "RoofTiles.jpg", "RustedMetal": "Rusted Metal.jpg", "Stone": "Stone.jpg",
              "WindowBlue1": "WindowsBlue2.jpg", "WindowBlue2": "WindowsBlue2.jpg", "Wood": "Wood.jpg"}


def g6(pack, name, objects, **extra):
    """A system-g6 piece: modelled about 2.5 times life size (scale 0.4), each material mat_<x> with its tex_<x>.png
    beside the blend; the first material is the model's own, any other a part named in 'parts'."""
    mats = extra.pop("mats", [f"mat_{objects[0]}"])
    names = extra.pop("part_names", [""] + [m.replace("mat_", "").title().replace("_", "") for m in mats[1:]])
    return dict(src=f"{pack}\\{pack.split(chr(92))[-1]}.blend", objects=objects, name=name, scale=0.4, grip=0, hulls=[],
                size=512, parts=dict(zip(mats, names)),
                wire={m: {"base": f"{pack}\\textures\\tex_{m[4:]}.png", "roughness": 0.85} for m in mats}, **extra)


def house(src, name):
    return dict(src=src, objects=None, name=name, scale=1.0, grip=0, hulls=[], bake=True, size=2048,
                wire={k: {"base": v} for k, v in HOUSE_WIRE.items()},
                surface={"RustedMetal": [0.8, 0.35], "WindowBlue1": [0.0, 0.8], "WindowBlue2": [0.0, 0.8], "*": [0.0, 0.2]})


SPECS = [
    # Street dressing (props pack).
    g6(PROPS, "Cart", ["cart"]),
    g6(PROPS, "HayBundle", ["hay_bundle"]),
    g6(PROPS, "WaterTrough", ["trough_wood"]),
    g6(PROPS, "HitchingPost", ["hitching_post"]),
    g6(PROPS, "Sawbuck", ["sawbuck"]),
    g6(PROPS, "Log", ["wooden_log"]),
    g6(PROPS, "Firewood", ["wooden_log_2"]),
    g6(PROPS, "Campfire", ["campfire"]),
    g6(PROPS, "Bench", ["bench_wood"]),
    g6(PROPS, "WoodenChest", ["chest_1"]),
    g6(PROPS, "StoneBrazier", ["brazier_stone"]),
    # The town (buildings pack): stalls, walls and gates, small buildings.
    # The pack's canvas stall and wooden-roofed stall are two whole stalls, each with its own posts.
    g6(BUILDINGS, "MarketStall", ["canopy_cloth"], double_sided=True),
    g6(BUILDINGS, "WoodenAwning", ["canopy_wood"], double_sided=True),
    g6(BUILDINGS, "TownGate", ["gate_wood"]),
    g6(BUILDINGS, "Palisade", ["wall_wood"]),
    g6(BUILDINGS, "Fence", ["fence_wood"]),
    g6(BUILDINGS, "FenceGate", ["fence_wood_door"], mats=["mat_fence_wood"]),
    g6(BUILDINGS, "StoneArchway", ["door_stone_frame"]),
    g6(BUILDINGS, "IronGate", ["gate_metal"]),
    g6(BUILDINGS, "Outhouse", ["outhouse"]),
    g6(BUILDINGS, "Watchtower", ["watchtower_wood"]),
    g6(BUILDINGS, "WoodenHut", ["house_wood", "house_wood_window_stick_left", "house_wood_window_stick_right", "house_wood_door"],
       mats=["mat_house_wood"]),
    g6(BUILDINGS, "Longhouse", ["house_wood_2", "house_wood_2_door"] + [f"house_wood_2_window_stick_{s}_{n}" for s in ("left", "right") for n in (1, 2, 3, 4)],
       mats=["mat_house_wood_2"]),
    # A covered well (iconoclast) with its own colour and normal maps.
    dict(src=D + r"\well.coveredopen.blend", objects=None, name="CoveredWell", scale=1.0, grip=0, hulls=[], size=1024,
         parts={"well.covered.O.ma": ""}, wire={"well.covered.O.ma": {"base": "well.O.jpg", "normal": "well.O.nor.jpg", "roughness": 0.8}}),
    # hreikin's houses, siblings of the Timber House (House 3), baked the same way.
    house(D + r"\x_75519_House1Upload_blend\House1Upload.blend", "StoneCottage"),
    house(D + r"\x_75861_House2_1Upload_blend\House2_1Upload.blend", "PlasterHouse"),
    house(D + r"\x_75864_House4Upload_blend\House4Upload.blend", "BrickHouse"),
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
        lines = [l for l in (r.stdout + r.stderr).splitlines() if "EXPORTED" in l or "Error" in l or "Traceback" in l or "WIRE" in l]
        print(spec["name"], [l[:300] for l in lines[-4:]] if lines else (r.stdout + r.stderr)[-1200:], flush=True)
