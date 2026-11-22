"""A tileable height tile of skin's micro relief: cells with grooves between them and a pore at a cell's corners.

    python skin_pores.py [size] [cells]

Skin at close range is a net of small plateaus (0.3 to 1 mm) parted by fine grooves, with pores where grooves meet.
A periodic jittered grid of points gives the cells (Worley: the nearest point F1, the second F2); the groove is where
F2 - F1 is small, the pore where F1 is small, and three scales of noise break the regularity. Periodic in both axes,
so the tile repeats across the body without a seam (the shader tiles it; at 4K over her whole UV a millimetre is two
pixels, so the pores cannot live in the baked map). Writes build/skin_pores_height.png (grey, 0.5 flat).
"""
import os, sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = int(sys.argv[1]) if len(sys.argv) > 1 else 1024
CELLS = int(sys.argv[2]) if len(sys.argv) > 2 else 48  # cells across the tile
GROOVE = 0.08  # the groove's width, a share of a cell
PORE = 0.10  # the pore's radius, a share of a cell
rng = np.random.default_rng(3)

# periodic jittered points, one a cell
jitter = rng.uniform(-0.4, 0.4, (CELLS, CELLS, 2))
pts = (np.stack(np.meshgrid(np.arange(CELLS), np.arange(CELLS), indexing="ij"), -1) + 0.5 + jitter) / CELLS
y, x = np.mgrid[0:SIZE, 0:SIZE]
P = np.stack([(x + 0.5) / SIZE, (y + 0.5) / SIZE], -1)
F1 = np.full((SIZE, SIZE), 9.0)
F2 = np.full((SIZE, SIZE), 9.0)
cell_x, cell_y = (P[..., 0] * CELLS).astype(int), (P[..., 1] * CELLS).astype(int)
for dx in (-1, 0, 1):
    for dy in (-1, 0, 1):
        cx, cy = (cell_x + dx) % CELLS, (cell_y + dy) % CELLS
        q = pts[cx, cy]
        d = P - q
        d -= np.round(d)  # periodic
        dist = np.hypot(d[..., 0], d[..., 1]) * CELLS
        closer = dist < F1
        F2 = np.where(closer, F1, np.minimum(F2, dist))
        F1 = np.where(closer, dist, F1)

smooth = lambda e0, e1, t: np.clip((t - e0) / (e1 - e0), 0, 1) ** 2 * (3 - 2 * np.clip((t - e0) / (e1 - e0), 0, 1))
groove = 1 - smooth(0.0, GROOVE * 2, F2 - F1)  # 1 in the groove
pore = 1 - smooth(0.0, PORE * 2, F1)  # 1 at a cell's point


def noise(freq, seed):
    """Periodic value noise at freq across the tile."""
    r = np.random.default_rng(seed)
    g = r.uniform(-1, 1, (freq, freq))
    gx, gy = P[..., 0] * freq, P[..., 1] * freq
    i, j = gx.astype(int) % freq, gy.astype(int) % freq
    fx, fy = gx - np.floor(gx), gy - np.floor(gy)
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = g[i, j], g[(i + 1) % freq, j]
    c, d = g[i, (j + 1) % freq], g[(i + 1) % freq, (j + 1) % freq]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


height = 0.5 - 0.22 * groove - 0.30 * pore + 0.05 * noise(8, 1) + 0.03 * noise(32, 2) + 0.02 * noise(128, 4)
height = np.clip(height, 0, 1)
out = os.path.join(HERE, "build", "skin_pores_height.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
Image.fromarray((height * 65535).astype(np.uint16)).save(out)
print("wrote", out, "%d px, %d cells, height %.2f to %.2f" % (SIZE, CELLS, height.min(), height.max()))
