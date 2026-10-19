"""Resumable full-matrix runner.  Needs root:   sudo venv/bin/python controller/matrix.py --stage 7 ...
It looks at results/runs.csv, works out which (cell, repeat) runs are still missing, shuffles them
(random order spreads infrastructure noise evenly) and runs them one by one.  Stop it any time with Ctrl+C;
start it again with the same command and it continues where it stopped.
  --dry-run   only print the plan and a time estimate"""
import argparse, os, random, subprocess, sys, time
import pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from profiles import PROFILES

ap = argparse.ArgumentParser()
ap.add_argument("--stage", required=True)
ap.add_argument("--cfgs", nargs="+", default=["PLAIN", "K1", "H1", "H2", "P1"])
ap.add_argument("--modes", nargs="+", default=["native", "reconnect"])
ap.add_argument("--resumes", nargs="+", default=["off", "on"])
ap.add_argument("--profiles", nargs="+", default=list(PROFILES))
ap.add_argument("--clients", type=int, nargs="+", default=[10]); ap.add_argument("--rounds", type=int, nargs="+", default=[10])
ap.add_argument("--repeats", type=int, default=10)
ap.add_argument("--initcwnd", type=int, default=0); ap.add_argument("--rto-min-ms", type=int, default=0)
ap.add_argument("--seed", type=int, default=1); ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--local-test", action="store_true")
a = ap.parse_args()

cells = []
for prof in a.profiles:
    for mode in a.modes:
        for cfg in a.cfgs:
            for res in (["off"] if cfg == "PLAIN" else a.resumes):       # no TLS -> nothing to resume
                for c in a.clients:
                    for r in a.rounds:
                        cells.append((cfg, mode, res, c, r, prof))
key = ["cfg", "mode", "resume", "clients", "rounds", "profile", "initcwnd", "rto_min_ms"]
out = os.path.join(ROOT, "results", "runs.csv")
done = {}
if os.path.exists(out):
    d = pd.read_csv(out)
    if "profile" in d:
        d = d[(d.stage.astype(str) == a.stage) & (d.local_test == a.local_test)]
        if "tcpdump_dropped" in d: d = d[(d.tcpdump_dropped.fillna(0) == 0)]
        for k, g in d.groupby(key): done[k] = len(g)
tasks = []
for cell in cells:
    k = cell[:5] + (cell[5], a.initcwnd, a.rto_min_ms)
    for rep in range(done.get(k, 0) + 1, a.repeats + 1): tasks.append((cell, rep))
random.Random(a.seed).shuffle(tasks)
print("cells: %d   runs still missing: %d (target %d repeats per cell)" % (len(cells), len(tasks), a.repeats))
def est(cell):   # rough seconds per run, only for the plan
    cfg, mode, res, c, r, prof = cell
    base = 12 + r * 0.6
    return base + (r * (8 + 6 * PROFILES[prof]["delay_ms"] / 25) if mode == "reconnect" else 0)
print("rough time estimate: %.1f hours (very approximate; your first real runs will tell)" % (sum(est(t[0]) for t in tasks) / 3600))
if a.dry_run or not tasks: sys.exit(0)
fails = open(os.path.join(ROOT, "results", "failed.log"), "a")
for n, (cell, rep) in enumerate(tasks, 1):
    cfg, mode, res, c, r, prof = cell; p = PROFILES[prof]
    cmd = [sys.executable, os.path.join(ROOT, "controller", "run_experiment.py"), "--cfg", cfg, "--clients", str(c), "--rounds", str(r),
           "--mode", mode, "--resume", res, "--repeat", str(rep), "--stage", a.stage, "--profile", prof,
           "--delay-ms", str(p["delay_ms"]), "--loss", str(p["loss"]), "--rate-mbit", str(p["rate_mbit"]),
           "--initcwnd", str(a.initcwnd), "--rto-min-ms", str(a.rto_min_ms)] + (["--local-test"] if a.local_test else [])
    t0 = time.time(); print("[%d/%d] %s rep %d ..." % (n, len(tasks), cell, rep), end=" ", flush=True)
    rc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if rc.returncode != 0:
        print("FAILED"); fails.write("%s rep %d\n%s\n----\n" % (cell, rep, rc.stderr[-1500:])); fails.flush()
        subprocess.run("pkill nginx; pkill -f fl/server.py; pkill -f fl/client.py", shell=True)
    else:
        print("ok %.0fs" % (time.time() - t0))
print("finished")
