"""Measured vs model-predicted inflation, with threshold flags.  python analysis/crossover.py --stage 7
Reads results/stats_cells.csv (measured) and results/model_predictions.csv (model); writes results/crossover.csv"""
import argparse, os, numpy as np, pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ap = argparse.ArgumentParser(); ap.add_argument("--stage", required=True); a = ap.parse_args()
m = pd.read_csv(os.path.join(ROOT, "results", "stats_cells.csv")); m = m[(m.initcwnd == 0) & (m.rto_min_ms == 0)]
m["resume"] = m["resume"].astype(str)
base = ["profile", "mode", "clients", "rounds"]
plain = m[m.cfg == "PLAIN"].drop_duplicates(base)[base + ["epoch_total_s_mean"]].rename(columns={"epoch_total_s_mean": "plain_s"})
k1 = m[m.cfg == "K1"][base + ["resume", "epoch_total_s_mean"]].rename(columns={"epoch_total_s_mean": "k1_s"})
x = m[m.cfg != "PLAIN"].merge(plain, on=base, how="left").merge(k1, on=base + ["resume"], how="left")
x["meas_infl_vs_K1_pct"] = 100 * (x.epoch_total_s_mean - x.k1_s) / x.k1_s
x["meas_infl_vs_PLAIN_pct"] = 100 * (x.epoch_total_s_mean - x.plain_s) / x.plain_s
p = pd.read_csv(os.path.join(ROOT, "results", "model_predictions.csv")); p["resume"] = p["resume"].astype(str)
out = x.merge(p[["profile", "mode", "resume", "clients", "rounds", "cfg", "infl_vs_K1_pct", "infl_vs_PLAIN_pct"]].rename(
    columns={"infl_vs_K1_pct": "pred_infl_vs_K1_pct", "infl_vs_PLAIN_pct": "pred_infl_vs_PLAIN_pct"}),
    on=["profile", "mode", "resume", "clients", "rounds", "cfg"], how="left")
for t in (1, 5, 10):
    out["meas_ge_%d" % t] = out.meas_infl_vs_PLAIN_pct >= t; out["pred_ge_%d" % t] = out.pred_infl_vs_PLAIN_pct >= t
cols = base + ["resume", "cfg", "n_runs", "meas_infl_vs_K1_pct", "pred_infl_vs_K1_pct", "meas_infl_vs_PLAIN_pct", "pred_infl_vs_PLAIN_pct"] + ["%s_ge_%d" % (s, t) for t in (1, 5, 10) for s in ("meas", "pred")]
out[cols].to_csv(os.path.join(ROOT, "results", "crossover.csv"), index=False)
print(out[cols].round(2).to_string(index=False))
print("\nTHRESHOLD AGREEMENT (measured vs predicted, vs PLAIN):")
for t in (1, 5, 10): print("  theta=%d%%: agree in %.0f%% of cells" % (t, 100 * (out["meas_ge_%d" % t] == out["pred_ge_%d" % t]).mean()))
