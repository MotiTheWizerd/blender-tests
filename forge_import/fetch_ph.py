import json, os, sys, urllib.request
res = sys.argv[1]
for a in sys.argv[2:]:
    req = urllib.request.Request(f"https://api.polyhaven.com/files/{a}", headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req))
    g = d["gltf"][res]["gltf"]
    root = os.path.join("ph", a)
    os.makedirs(os.path.join(root, "textures"), exist_ok=True)
    items = [(g["url"], os.path.basename(g["url"]))] + [(v["url"], k) for k, v in g["include"].items()]
    for url, rel in items:
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            urllib.request.urlretrieve(url, p)
    print(a, "ok", flush=True)
