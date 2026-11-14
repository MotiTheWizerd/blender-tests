"""A head's landmarks on its face's middle line, seen from the side (metres, front -Y, up Z): what head.py scales a
head by and neck.py seats it on a body by.

    from face import profile
    crown, chin, nose_tip, chin_front = profile(co)      # co: the head's vertices, an (n, 3) array
"""
import numpy as np


def profile(co):
    """The crown's height, the chin's underside's height, the nose tip and the chin's front (x, y, z) of a head (a bust,
    or a head on its neck: nothing below the collarbones). The middle line is the frontmost point (least y) in each 1%
    of the height (about 1 cm of a bust; finer slices of the 4% strip are often empty)."""
    width = co[:, 0].max() - co[:, 0].min()
    crown, floor = co[:, 2].max(), co[:, 2].min()
    # The strip down the face's middle, its front half only: a slice with no point in front would otherwise take
    # the back of the neck's for the face's, and that step back read as the chin (head_face_1: a head 13% too small).
    middle = co[(np.abs(co[:, 0] - (co[:, 0].max() + co[:, 0].min()) / 2) < width * 0.02)
                & (co[:, 1] < (co[:, 1].max() + co[:, 1].min()) / 2)]
    step = (crown - floor) / 100
    bins = {}
    for x, y, z in middle:
        k = int(z / step)
        bins[k] = min(bins.get(k, 1e9), y)
    levels = sorted(bins)
    nose = min(levels, key=lambda k: bins[k] if k * step > floor + 0.3 * (crown - floor) else 1e9)
    # Down from the nose tip: the chin's underside is where the profile falls back toward the neck the most over 3%
    # of the height (the lips recess too, but less).
    reach = int(0.4 * (crown - floor) / step)
    below = [k for k in levels if nose - reach < k < nose and bins.get(k - 3) is not None]
    chin_k = max(below, key=lambda k: bins[k - 3] - bins[k])
    nose_tip = np.array([0.0, bins[nose], nose * step])
    # Its front just above the underside: the first slice up that has a point (a lighter mesh's line has gaps).
    front_k = next(k for k in levels if k > chin_k)
    chin_front = np.array([0.0, bins[front_k], front_k * step])
    return crown, chin_k * step, nose_tip, chin_front
