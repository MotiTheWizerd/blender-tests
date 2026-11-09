"""Where a creature's files live, the same for every step and every creature.

    creatures/<name>/              what a person decides: source_tripo.glb (the AI model; private, not in git),
                                   landmarks.json (its joints, step 3's judgment)
    creatures/<name>/checks/       what each step shows: its pictures and numbers (in git: the record of the run)
    creatures/<name>/build/        what the steps make and can make again: the .blend files, the maps, the Forge
                                   export, the logs (not in git; `run.py <name>` rebuilds it all in a few minutes)

A step script imports it from beside itself: `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))`.
"""
import os

HOME = os.path.dirname(os.path.abspath(__file__))


class Creature:
    def __init__(self, name):
        self.name = name
        self.title = name.capitalize()
        self.root = os.path.join(HOME, name)
        for folder in ("checks", "build"):
            os.makedirs(os.path.join(self.root, folder), exist_ok=True)

    @property
    def source(self):
        return os.path.join(self.root, "source_tripo.glb")

    @property
    def landmarks(self):
        return os.path.join(self.root, "landmarks.json")

    def checks(self, file):
        return os.path.join(self.root, "checks", file)

    def build(self, *parts):
        return os.path.join(self.root, "build", *parts)

    def picture(self, name):
        """A check's picture: checks/<name>.jpg (JPEG: a sixth of a PNG's size, and each rerun commits them again)."""
        return self.checks(name + ".jpg")

    def blend(self, stage):
        """A stage's .blend in build/ ("low", "rig", "anim")."""
        return self.build(f"{self.name}_{stage}.blend")


def pictures_as_jpeg(scene):
    """Renders from here on are written as JPEG, for check pictures (not maps: those keep their own formats)."""
    settings = scene.render.image_settings
    settings.file_format, settings.color_mode, settings.quality = "JPEG", "RGB", 88


def save_blend(bpy, path):
    """Save without Blender's numbered backups (.blend1): every .blend here is rebuilt by a script, not hand-kept."""
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=path)
