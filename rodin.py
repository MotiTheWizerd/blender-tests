#!/usr/bin/env python3
"""Image-to-3D through the BlenderMCP addon's Hyper3D Rodin handlers.
  rodin.py submit NAME IMAGE "prompt"   -> prints the job (uuid + subscription key) into source/rodin_jobs.json
  rodin.py poll NAME                    -> job status list
  rodin.py import NAME                  -> imports the finished model into the open scene as NAME
"""
import base64, json, os, sys
sys.argv, args = sys.argv[:1], sys.argv[1:]
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bl.py")).read().split("if sys.argv[1]")[0])
JOBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "source", "rodin_jobs.json")
jobs = json.load(open(JOBS)) if os.path.exists(JOBS) else {}
cmd, name = args[0], args[1]
if cmd == "submit":
    img = base64.b64encode(open(args[2], "rb").read()).decode()
    r = send({"type": "create_rodin_job", "params": {"text_prompt": args[3], "images": [[".png", img]]}})
    print(json.dumps(r)[:800])
    res = r.get("result", {})
    if res.get("uuid"):
        jobs[name] = {"uuid": res["uuid"], "subscription_key": res["jobs"]["subscription_key"]}
        json.dump(jobs, open(JOBS, "w"), indent=1)
elif cmd == "poll":
    print(send({"type": "poll_rodin_job_status", "params": {"subscription_key": jobs[name]["subscription_key"]}}))
elif cmd == "import":
    print(json.dumps(send({"type": "import_generated_asset", "params": {"task_uuid": jobs[name]["uuid"], "name": name}}))[:800])
