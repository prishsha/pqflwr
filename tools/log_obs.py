"""Write an observation.  python tools/log_obs.py --stage 0 --cfg K1 --run <run_id> "what you saw"  """
import argparse, json, os, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ap = argparse.ArgumentParser(); ap.add_argument("--stage", required=True); ap.add_argument("--cfg", default="-")
ap.add_argument("--run", default="-"); ap.add_argument("--kind", default="measurement", help="setup|measurement|anomaly|decision|deviation|verification")
ap.add_argument("text"); a = ap.parse_args()
d = os.path.join(ROOT, "observations"); os.makedirs(d, exist_ok=True)
jl = os.path.join(d, "observations.jsonl")
n = sum(1 for _ in open(jl)) + 1 if os.path.exists(jl) else 1
rec = {"id": "OBS-%04d" % n, "utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "stage": a.stage, "cfg": a.cfg,
       "run": a.run, "kind": a.kind, "text": a.text}
open(jl, "a").write(json.dumps(rec) + "\n")
open(os.path.join(d, "OBSERVATIONS.md"), "a").write("### %s | stage %s | %s | %s | %s\nrun: `%s`\n\n%s\n\n" % (rec["id"], a.stage, a.cfg, a.kind, rec["utc"], a.run, a.text))
print("saved", rec["id"])
