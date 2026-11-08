import json
import subprocess
import sys

D = r"C:\Users\User\AppData\Local\Temp\oga\c2"
B = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
ARCH = D + r"\d_archery-set\archerySetOGA.blend"
QUIVER = ["quiver"] + [f"Circle.{n:03d}" for n in (4, 5, 6, 7, 8, 9, 10, 11, 12, 14)]
SPECS = [
    dict(src=D + r"\d_short-sword-0\Short Sword.fbx", name="ShortSword", length=0.78, grip=0.11, hulls=[0.17, 0.27]),
    dict(src=D + r"\d_historical-swords-set\historical_swords_set.blend", objects=["ArmingSword"], name="ArmingSword",
         rotate=[90, 0, 0], length=0.96, grip=0.11, hulls=[0.17, 0.25], bake=True, size=1024,
         wire={"Steel": {"base": "steel_diffuse.png", "normal": "steel_normal.png"}, "LeatherDark": {"base": "leather_darker.png", "normal": "leather_normal.png"}},
         surface={"Steel": [1.0, 0.75], "LeatherDark": [0.0, 0.25]}),
    dict(src=ARCH, objects=["bow"], name="HuntingBow", length=1.3, grip=0.5, hulls=[0.33, 0.67]),
    dict(src=D + r"\d_low-poly-composite-bow\composite bow.blend", objects=["bow", "bowstring"], name="RecurveBow",
         stretch=[1, 3.5, 1], length=1.15, grip=0.5, hulls=[0.33, 0.67], bake=True, size=512, surface={"*": [0.0, 0.35]}),
    dict(src=ARCH, objects=QUIVER, name="Quiver", length=0.8, grip=0.5, hulls=[0.8]),
    dict(src=ARCH, objects=["arrow"], name="Arrow", rotate=[0, 90, 0], length=0.8, grip=0.5, hulls=[]),
    dict(src=D + r"\d_medieval-arrow\arrow.blend", objects=["Arrow"], name="BroadheadArrow", rotate=[90, 0, 0],
         length=0.8, grip=0.5, hulls=[], bake=True, size=512, surface={"Metal": [1.0, 0.6], "*": [0.0, 0.3]}),
]
only = sys.argv[1:]
for spec in SPECS:
    if only and spec["name"] not in only:
        continue
    spec["out_dir"] = D + r"\out2"
    path = D + rf"\spec_{spec['name']}.json"
    json.dump(spec, open(path, "w"))
    r = subprocess.run([B, "-b", "--python", r"C:\Users\User\AppData\Local\Temp\oga\forge_export2.py", "--", path],
                       capture_output=True, text=True)
    lines = [l for l in (r.stdout + r.stderr).splitlines() if "EXPORTED" in l or "Error" in l or "Traceback" in l]
    print(spec["name"], lines[-3:] if lines else (r.stdout + r.stderr)[-800:])
