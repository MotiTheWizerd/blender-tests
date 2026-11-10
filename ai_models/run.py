"""The whole recipe for one creature, every step in order: plain Python, each step a headless Blender.

    python run.py dragon                    every step, from the source to the clips
    python run.py dragon --from rig         from a step on (after editing landmarks.json, say)
    python run.py dragon --only animate     one step
    python run.py --steps                   the steps, in order

Needs <name>/source_tripo.glb (step 0, by hand), <name>/model.json (its kind, length, triangles) and, for a
creature, <name>/landmarks.json (step 3's judgment: probe.py and grid.py help find it). A building skips the rig and
the clips. Blender is $BLENDER, else Blender 5.2's Windows install. Each step's output
goes to <name>/build/<step>.log; its last lines are shown, and the run stops at the first step that fails.
What each step makes and what to look at: RECIPE.md.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
# (step, script, the kinds it is for, its extra arguments from model.json after the name)
STEPS = [
    # "still": a creature standing as it was made, no rig (the ravens); exported as a building is
    ("inspect", "inspect.py", ("creature", "building", "still"), lambda spec: []),
    # model.json "bake_size" (optional; absent: reduce.py's 4096): a smaller normal bake when memory is short
    ("reduce", "reduce.py", ("creature", "building", "still"),
     lambda spec: [str(spec.get("triangles", 40000))] + ([str(spec["bake_size"])] if "bake_size" in spec else [])),
    ("rig", "rig.py", ("creature",), lambda spec: []),
    ("export", "export.py", ("creature", "building", "still"), lambda spec: [str(spec.get("length", 12))]),
    ("check_export", "check_export.py", ("creature", "building", "still"), lambda spec: []),
    ("animate", "animate.py", ("creature",), lambda spec: []),
]
# The lines each step prints that say how it went.
SAYS = ("INSPECT", "REDUCE", "RIG", "EXPORT", "CLIP", "FEET", "REACH", "WALK", "Error", "Traceback")


def main(argv):
    if "--steps" in argv:
        print("\n".join(f"{step:13} {', '.join(kinds)}" for step, _, kinds, _ in STEPS))
        return 0
    name = argv[0]
    names = [step for step, _, _, _ in STEPS]
    sys.path.insert(0, HERE)
    from place import Creature
    spec = Creature(name).spec
    first, only = 0, None
    if "--from" in argv:
        first = names.index(argv[argv.index("--from") + 1])
    if "--only" in argv:
        only = argv[argv.index("--only") + 1]
    build = os.path.join(HERE, name, "build")
    os.makedirs(build, exist_ok=True)
    for step, script, kinds, extra in STEPS[first:]:
        if (only and step != only) or spec["kind"] not in kinds:
            continue
        started = time.time()
        log = os.path.join(build, f"{step}.log")
        with open(log, "w", encoding="utf-8", errors="replace") as out:
            done = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(HERE, script), "--", name, *extra(spec)],
                                  stdout=out, stderr=subprocess.STDOUT)
        said = [line.rstrip() for line in open(log, encoding="utf-8", errors="replace") if line.startswith(SAYS)]
        failed = done.returncode != 0 or any(line.startswith(("Error", "Traceback")) for line in said)
        print(f"{step:13} {'FAILED' if failed else 'ok':6} {time.time() - started:5.0f} s")
        for line in said[-8:]:
            print("   ", line[:160])
        if failed:
            print(f"    see {log}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
