"""Tiny MCP-over-HTTP client for the Unity server: python mcp.py <tool> '<json args>'"""
import json
import sys
import urllib.request

URL = "http://127.0.0.1:8765/mcp"
H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def post(body, sid=None):
    h = dict(H)
    if sid:
        h["mcp-session-id"] = sid
    req = urllib.request.Request(URL, json.dumps(body).encode(), h)
    with urllib.request.urlopen(req, timeout=600) as r:
        sid = r.headers.get("mcp-session-id") or sid
        text = r.read().decode("utf-8", "replace")
    msgs = [json.loads(l[5:]) for l in text.splitlines() if l.startswith("data:")]
    return sid, (msgs[-1] if msgs else None)


sid, _ = post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "raven", "version": "1"}}})
post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
tool = sys.argv[1]
if tool == "list":
    _, m = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, sid)
    for t in m["result"]["tools"]:
        print(t["name"])
    sys.exit()
if tool == "schema":
    _, m = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, sid)
    for t in m["result"]["tools"]:
        if t["name"] == sys.argv[2]:
            print(json.dumps(t["inputSchema"], indent=1)[:4000])
    sys.exit()
args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
_, m = post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args}}, sid)
res = m.get("result", m)
for c in res.get("content", []):
    if c.get("type") == "text":
        print(c["text"][:20000])
    else:
        print("[", c.get("type"), "]")
if res.get("structuredContent") and not res.get("content"):
    print(json.dumps(res["structuredContent"])[:20000])
