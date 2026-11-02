#!/usr/bin/env python3
"""Talk to the BlenderMCP addon's socket directly. Usage: bl.py info | bl.py code FILE|-"""
import json, socket, sys
def send(cmd):
    s = socket.create_connection(("127.0.0.1", 9876), timeout=1200)
    s.sendall(json.dumps(cmd).encode())
    buf = b""
    while True:
        chunk = s.recv(65536)
        if not chunk: break
        buf += chunk
        try: return json.loads(buf)
        except json.JSONDecodeError: continue
    return json.loads(buf)
if sys.argv[1] == "info":
    r = send({"type": "get_scene_info", "params": {}})
else:
    src = sys.stdin.read() if sys.argv[2] == "-" else open(sys.argv[2]).read()
    r = send({"type": "execute_code", "params": {"code": src}})
print(json.dumps(r, indent=1)[:3000])
