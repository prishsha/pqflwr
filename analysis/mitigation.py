"""Compare mitigations against the baseline of the SAME condition.
   Baseline = Stage 7 rows with default TCP settings.  Mitigation rows = Stage 10 runs (initcwnd / rto_min changed),
   plus the structural mitigations that are already inside Stage 7 (persistent connection, session resumption).
   python analysis/mitigation.py --base-stage 7 --mit-stage 10"""
import argparse, json, os, sys, numpy as np, pandas as pd
from scipy import stats as st
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
import model
from stats import load_valid

def welch(x, ref):
    x, ref = np.asarray(x, float), np.asarray(ref, float)
    diff = x.mean() - ref.mean(); se = np.sqrt(x.var(ddof=1) / len(x) + ref.var(ddof=1) / len(ref))
    dof = se**4 / ((x.var(ddof=1) / len(x))**2 / (len(x) - 1) + (ref.var(ddof=1) / len(ref))**2 / (len(ref) - 1)) if se > 0 else 1
    h = st.t.ppf(0.975, dof) * se
    return diff, diff - h, diff + h

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base-stage", default="7"); ap.add_argument("--mit-stage", default="10")
    a = ap.parse_args()
    b = load_valid(a.base_stage); m = load_valid(a.mit_stage)
    d = pd.concat([b, m]).dropna(subset=["epoch_total_s"]); d["resume"] = d["resume"].astype(str)
    cond = ["profile", "mode", "resume", "cfg", "clients", "rounds"]
    rows = []
    # (1) TCP-level mitigations: rows with initcwnd/rto changed vs default-TCP rows of the same condition
    for k, g in d.groupby(cond):
        ref = g[(g.initcwnd == 0) & (g.rto_min_ms == 0)].epoch_total_s.values
        for (iw, rto), gg in g.groupby(["initcwnd", "rto_min_ms"]):
            if (iw, rto) == (0, 0) or len(ref) < 2 or len(gg) < 2: continue
            diff, lo, hi = welch(gg.epoch_total_s.values, ref)
            rows.append(dict(zip(cond, k), mitigation="initcwnd=%s rto_min=%sms" % (iw or "default", rto or "default"), n=len(gg), n_base=len(ref),
                             base_mean_s=ref.mean(), mit_mean_s=gg.epoch_total_s.mean(), diff_s=diff, diff_ci_lo=lo, diff_ci_hi=hi,
                             diff_pct=100 * diff / ref.mean(), significant_95=bool(lo > 0 or hi < 0)))
    # (2) structural mitigations inside the baseline: persistent vs transient, resumption on vs off
    base = d[(d.initcwnd == 0) & (d.rto_min_ms == 0)]
    for (prof, cfg, C, R), g in base.groupby(["profile", "cfg", "clients", "rounds"]):
        for name, xa, xb in [("persistent vs transient", g[(g["mode"] == "native") & (g.resume == "off")], g[(g["mode"] == "reconnect") & (g.resume == "off")]),
                             ("resumption ON vs OFF (transient)", g[(g["mode"] == "reconnect") & (g.resume == "on")], g[(g["mode"] == "reconnect") & (g.resume == "off")])]:
            if len(xa) < 2 or len(xb) < 2: continue
            diff, lo, hi = welch(xa.epoch_total_s.values, xb.epoch_total_s.values)
            rows.append(dict(profile=prof, cfg=cfg, clients=C, rounds=R, mode="-", resume="-", mitigation=name, n=len(xa), n_base=len(xb),
                             base_mean_s=xb.epoch_total_s.mean(), mit_mean_s=xa.epoch_total_s.mean(), diff_s=diff, diff_ci_lo=lo, diff_ci_hi=hi,
                             diff_pct=100 * diff / xb.epoch_total_s.mean(), significant_95=bool(lo > 0 or hi < 0)))
    out = pd.DataFrame(rows); out.to_csv(os.path.join(ROOT, "results", "mitigation.csv"), index=False)
    print(out.round(3).to_string(index=False) if len(out) else "no comparable cells yet")
    # model prediction of the TCP-level effect, for validation (needs the fitted parameters)
    pj = os.path.join(ROOT, "results", "model_params.json")
    if os.path.exists(pj) and len(m):
        th = json.load(open(pj))["parameters"]; tab = model.load_hs_table(); comp = model.comp_table(d)
        rows = []
        for k, g in m.groupby(cond + ["initcwnd", "rto_min_ms"]):
            r = dict(zip(cond + ["initcwnd", "rto_min_ms"], k)); row = g.iloc[0].to_dict()
            p = model.predict_row(row, th, tab, comp, iw=r["initcwnd"] or model.IW_DEFAULT, rto_ms=r["rto_min_ms"] or model.RTO_DEFAULT_MS)
            rows.append(dict(r, meas_mean_s=g.epoch_total_s.mean(), model_s=p["total"], err_pct=100 * (p["total"] - g.epoch_total_s.mean()) / g.epoch_total_s.mean()))
        pd.DataFrame(rows).to_csv(os.path.join(ROOT, "results", "mitigation_model_check.csv"), index=False)
        print("saved results/mitigation_model_check.csv")
