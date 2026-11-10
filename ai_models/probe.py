"""Step 3a for a creature: measurements to place its landmarks by (the joints rig.py builds bones from).

    blender -b <name>/build/<name>_low.blend -P probe.py

Prints the centre line (slices every 4 cm along Y: the core's middle x and its height), the four feet (vertices
on the ground, by side and front/back) with each leg traced up by the centroid of 3 cm slabs, and the +X wing by
x bins with its lower edge (claws are its local lows). Written for the dragon (facing -Y, 1 m long); a creature of
another size or shape needs its thresholds scaled.
"""
import bpy, numpy as np
o = next(o for o in bpy.data.objects if o.type == "MESH")
n = len(o.data.vertices); co = np.empty(n*3); o.data.vertices.foreach_get("co", co); P = co.reshape(-1,3)
x,y,z = P.T
print("CENTRE LINE (core: z>0.10, |x - median|<0.09):")
for y0 in np.linspace(-0.46, 0.46, 24):
    s = (np.abs(y - y0) < 0.02) & (z > 0.08)
    if not s.any(): continue
    mx = np.median(x[s & (np.abs(x) < 0.2 + max(0, y0) )])
    c = s & (np.abs(x - mx) < 0.09)
    print(f" y{y0:+.3f} x{mx:+.3f} z {z[c].min():.3f}-{z[c].max():.3f} mid {(z[c].min()+z[c].max())/2:.3f}")
f = z < 0.03
for sx in (-1, 1):
    for name, ym in (("front", y < -0.2), ("hind", y >= -0.2)):
        m = f & (np.sign(x) == sx) & ym
        c = P[m].mean(0)
        print(f"LEG {name} side{sx:+d} foot {c.round(3)} y {y[m].min():.3f}..{y[m].max():.3f}")
        cur = c[:2].copy()
        for z0 in np.arange(0.03, 0.34, 0.03):
            k = (np.abs(z - z0) < 0.015) & (np.hypot(x - cur[0], y - cur[1]) < 0.06)
            if k.sum() < 5: print(f"   z{z0:.2f} -"); continue
            cur = 0.5 * cur + 0.5 * np.array([x[k].mean(), y[k].mean()])
            print(f"   z{z0:.2f} x{cur[0]:+.3f} y{cur[1]:+.3f} n{k.sum()}")
print("WING +x, by x bin (verts x>bin, y<0.1, z>0.15):")
for x0 in np.arange(0.10, 0.50, 0.03):
    k = (np.abs(x - x0) < 0.015) & (y < 0.1) & (z > 0.12)
    if k.any(): print(f" x{x0:.2f} z {z[k].min():.3f}-{z[k].max():.3f} y {y[k].min():.3f}..{y[k].max():.3f} n{k.sum()}")
# Claws on the wing's lower edge: local minima of z along the edge, x>0.2
k = (x > 0.18) & (y < 0.1) & (z > 0.1)
W = P[k]; order = np.argsort(W[:,0])
bins = np.arange(0.18, 0.5, 0.01); lows = []
for b in bins:
    m = (W[:,0] >= b) & (W[:,0] < b + 0.01)
    if m.any(): lows.append((b, W[m][np.argmin(W[m][:,2])]))
print("WING LOWER EDGE:", " ".join(f"{p[0]:.2f}:{p[1][2]:.3f}" for p in lows))
