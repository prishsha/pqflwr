"""Unit tests (no network needed):   pytest -q tests"""
import os, sys, numpy as np, pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for d in ("analysis", "controller"): sys.path.insert(0, os.path.join(ROOT, d))
import model, stats, analyze_pcap as A
from profiles import PROFILES

def synth(tmp_path, seed=0, noise=0.03, reps=10):
    rng = np.random.default_rng(seed)
    st = []
    for cfg, t1, s2c, segs in [("K1", .0009, 800, 2), ("H1", .0011, 1900, 3), ("H2", .0022, 10400, 9), ("P1", .0021, 10300, 9)]:
        for res, f in ((False, 1.0), (True, .3)):
            st.append(dict(cfg=cfg, resume=res, delay_ms=0, loss_pct=0, rate_mbit=0, initcwnd=0, rto_min_ms=0, hs_mean_ms=t1 * 1000 * f,
                           cpu_srv_per_hs_ms=t1 * 400 * f, hs_payload_s2c_mean=s2c * f, hs_segments_s2c_mean=segs * f))
    p = tmp_path / "stage1.csv"; pd.DataFrame(st).to_csv(p, index=False)
    tab = model.load_hs_table(str(p))
    truth = dict(kappa_reg=2.0, tau_cp=0.25, kappa_pay_pers=0.5, kappa_pay_trans=3.0, theta_ser=0.002, theta_tls=0.0005, tau_data=0.06)
    comp = {10: 0.30}; rows = []; n = 0
    for prof, q in PROFILES.items():
        for mode in ("native", "reconnect"):
            for cfg in ("PLAIN", "K1", "H1", "H2", "P1"):
                for res in (("off",) if cfg == "PLAIN" else ("off", "on")):
                    for rep in range(reps):
                        rho = 0.0 if (res == "off" or mode == "native" or cfg == "PLAIN") else 0.9
                        row = dict(profile=prof, mode=mode, resume=res, cfg=cfg, clients=10, rounds=10, rtt_ms=2 * q["delay_ms"], loss_pct=q["loss"],
                                   rate_mbit=q["rate_mbit"], model_bytes_one_way=73992, n_clienthello=100 if mode == "reconnect" else 10,
                                   n_resumed_psk=rho * (100 if mode == "reconnect" else 10))
                        pr = model.predict_row(row, truth, tab, comp, rho=rho)
                        n += 1
                        row.update(run_id="r%d" % n, stage="t", local_test=False, tcpdump_dropped=0, initcwnd=0, rto_min_ms=0,
                                   cp_total_s=pr["cp"] * rng.normal(1, noise), data_total_s=pr["data"] * rng.normal(1, noise),
                                   train_total_s=comp[10] * 10 * 0.8, agg_total_s=comp[10] * 10 * 0.2)
                        row["epoch_total_s"] = row["cp_total_s"] + row["data_total_s"] + row["train_total_s"] + row["agg_total_s"]
                        rows.append(row)
    return pd.DataFrame(rows), tab, comp, truth

def test_k_extra():
    assert model.k_extra(800, 10) == 0 and model.k_extra(10400, 10) == 0      # 8 segments fit in IW 10
    assert model.k_extra(10400, 4) == 1                                        # IW 4 -> one extra round trip
    assert model.k_extra(16000, 4) == 1 and model.k_extra(20000, 4) == 2

def test_model_recovers_parameters(tmp_path):
    d, tab, comp, truth = synth(tmp_path)
    th = model.fit(d, tab, comp); e = model.evaluate(d, th, tab, comp); m, _ = model.metrics(e)
    assert m["total"]["MAPE_pct"] < 6 and m["cp"]["R2"] > 0.95
    assert abs(th["kappa_reg"] - truth["kappa_reg"]) < 0.4 and abs(th["tau_cp"] - truth["tau_cp"]) < 0.1
    cv = model.leave_one_profile_out(d, tab, comp); assert cv.total_MAPE.max() < 15

def test_stats_ci_and_vs_k1(tmp_path):
    m, sd, lo, hi = stats.ci95([10, 11, 9, 10, 10, 11, 9, 10, 10, 10]); assert lo < m < hi and sd > 0
    d, *_ = synth(tmp_path, reps=10); v = stats.vs_k1(d)
    assert len(v) > 0 and set(["diff_ci_lo", "mannwhitney_p", "cliffs_delta"]) <= set(v.columns)

def test_pcap_stream_logic():
    F = A.FIELDS
    def row(no, t, ln, src, pl, syn=0, ack=1, hs="", ext=""):
        d = {f: "" for f in F}; d.update({"frame.number": no, "frame.time_epoch": t, "frame.len": ln, "tcp.stream": 0, "ip.src": src, "tcp.len": pl,
            "tcp.flags.syn": syn, "tcp.flags.ack": ack, "tcp.flags.reset": 0, "tls.handshake.type": hs, "tls.handshake.extension.type": ext}); return d
    C, S = "c", "s"
    rows = [row(1, 0, 74, C, 0, 1, 0), row(2, 0.050, 74, S, 0, 1, 1), row(3, .0501, 66, C, 0), row(4, .0502, 1514, C, 1448),
            row(5, .0503, 246, C, 180, hs="1", ext="41"), row(6, .100, 1514, S, 1448, hs="2"), row(7, .1001, 1514, S, 1448),
            row(8, .150, 1514, S, 1448), row(9, .200, 120, C, 54)]          # server flight in two bursts (stall of one RTT)
    df = pd.DataFrame(rows)
    df["no"] = df["frame.number"].astype(int); df["t"] = df["frame.time_epoch"].astype(float); df["len"] = df["frame.len"].astype(int)
    df["stream"] = 0; df["plen"] = pd.to_numeric(df["tcp.len"]).astype(int); df["syn"] = df["tcp.flags.syn"].map(A._b)
    df["ack"] = df["tcp.flags.ack"].map(A._b); df["rst"] = False; df["retx"] = False
    ps = A.per_stream(df).iloc[0]
    assert abs(ps.hs_ms - 149.5) < 1 and ps.psk_in_clienthello and abs(ps.rtt_syn_ms - 50) < 1 and ps.hs_s2c_bursts == 2
