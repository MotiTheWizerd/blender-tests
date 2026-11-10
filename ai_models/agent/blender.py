"""Blender for Smith: its arguments go to Blender as they are, so Python is the only program the agent starts.

    python ai_models/agent/blender.py -b ai_models/<name>/build/<name>_low.blend -P ai_models/<name>/build/probe.py
    python ai_models/agent/blender.py -b --factory-startup -P ai_models/inspect.py -- <name>

Blender is $BLENDER, else Blender 5.2's Windows install (as run.py).
"""
import os
import subprocess
import sys

BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")

if __name__ == "__main__":
    sys.exit(subprocess.run([BLENDER, *sys.argv[1:]]).returncode)
