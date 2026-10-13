"""Turn a pcap (captured on the CLIENT side) into per-connection handshake metrics.

Handshake time  = first client payload packet (ClientHello)  ->  first client payload packet
                  sent AFTER the server's first payload (= client Finished). Same idea as the reference thesis.
Run:  python analysis/analyze_pcap.py runs/xxx/capture.pcap --port 4431 [--plain]
"""
import argparse, subprocess, sys
import numpy as np, pandas as pd

FIELDS = ["frame.number", "frame.time_epoch", "frame.len", "tcp.stream", "ip.src", "tcp.len",
          "tcp.flags.syn", "tcp.flags.ack", "tcp.flags.reset", "tls.handshake.type",
          "tls.handshake.extension.type", "tcp.analysis.retransmission", "tcp.analysis.fast_retransmission"]

def _b(x): return str(x).strip().lower() in ("1", "true")

def load(pcap, port, plain=False):
    cmd = ["tshark", "-r", pcap, "-Y", "tcp"]
    if not plain: cmd += ["-d", "tcp.port==%d,tls" % port]
    cmd += ["-T", "fields", "-E", "separator=/t", "-E", "occurrence=a", "-E", "aggregator=,"]
    for f in FIELDS: cmd += ["-e", f]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0: sys.exit("tshark failed: " + out.stderr[:500])
    rows = [l.split("\t") for l in out.stdout.splitlines() if l.strip()]
    rows = [r + [""] * (len(FIELDS) - len(r)) for r in rows]
    df = pd.DataFrame(rows, columns=FIELDS)
    if df.empty: return df
    df["no"] = df["frame.number"].astype(int); df["t"] = df["frame.time_epoch"].astype(float)
    df["len"] = df["frame.len"].astype(int); df["stream"] = df["tcp.stream"].astype(int)
    df["plen"] = pd.to_numeric(df["tcp.len"], errors="coerce").fillna(0).astype(int)
    df["syn"] = df["tcp.flags.syn"].map(_b); df["ack"] = df["tcp.flags.ack"].map(_b)
    df["rst"] = df["tcp.flags.reset"].map(_b)
    df["retx"] = df["tcp.analysis.retransmission"].astype(str).str.len().gt(0) | \
                 df["tcp.analysis.fast_retransmission"].astype(str).str.len().gt(0)
    return df.sort_values("no").reset_index(drop=True)

def per_stream(df):
    recs = []
    for sid, g in df.groupby("stream"):
        data = g[g.plen > 0]
        if data.empty: continue
        client = data.iloc[0]["ip.src"]
        syn = g[g.syn & ~g.ack]; synack = g[g.syn & g.ack]
        rtt = (synack.iloc[0].t - syn.iloc[0].t) * 1000 if len(syn) and len(synack) else np.nan
        types = ",".join(g["tls.handshake.type"].astype(str)).split(",")
        exts = ",".join(g[g["ip.src"] == client]["tls.handshake.extension.type"].astype(str)).split(",")
        r = {"stream": sid, "rtt_syn_ms": rtt, "n_clienthello": sum(t.strip() == "1" for t in types),
             "psk_in_clienthello": any(e.strip() == "41" for e in exts),
             "frames": len(g), "retx_stream": int(g.retx.sum()), "rst": int(g.rst.sum()),
             "duration_s": g.t.max() - g.t.min(), "bytes_stream": int(g.len.sum())}
        c1 = data.iloc[0]
        s_data = data[(data["ip.src"] != client) & (data.no > c1.no)]
        if len(s_data):
            s1 = s_data.iloc[0]
            c_after = data[(data["ip.src"] == client) & (data.no > s1.no)]
            if len(c_after):
                end = c_after.iloc[0]
                w = g[(g.no >= c1.no) & (g.no <= end.no)]
                wd = w[w.plen > 0]
                s2c = wd[wd["ip.src"] != client]
                r.update({"hs_ms": (end.t - c1.t) * 1000, "hs_frame_bytes": int(w.len.sum()),
                          "hs_payload_c2s": int(wd[wd["ip.src"] == client].plen.sum()),
                          "hs_payload_s2c": int(s2c.plen.sum()), "hs_segments_s2c": len(s2c),
                          "flight_span_ms": (s2c.t.max() - s1.t) * 1000, "retx_hs": int(w.retx.sum())})
        recs.append(r)
    return pd.DataFrame(recs)

def summary(df, ps):
    s = {"n_syn": int((df.syn & ~df.ack).sum()), "n_streams": len(ps),
         "n_clienthello": int((ps.n_clienthello > 0).sum()) if len(ps) else 0,
         "n_resumed_psk": int(ps.psk_in_clienthello.sum()) if len(ps) else 0,
         "n_rst": int(df.rst.sum()), "retx_total": int(df.retx.sum())}
    if "hs_ms" in ps and ps.hs_ms.notna().any():
        h = ps.hs_ms.dropna()
        s.update({"hs_n": len(h), "hs_mean_ms": h.mean(), "hs_median_ms": h.median(), "hs_p95_ms": h.quantile(.95),
                  "hs_p99_ms": h.quantile(.99), "hs_std_ms": h.std()})
        for c in ["hs_frame_bytes", "hs_payload_c2s", "hs_payload_s2c", "hs_segments_s2c", "flight_span_ms", "retx_hs"]:
            s[c + "_mean"] = ps[c].mean()
    if len(ps): s["rtt_syn_ms_mean"] = ps.rtt_syn_ms.mean()
    return s

def analyze(pcap, port, plain=False, out_csv=None):
    df = load(pcap, port, plain)
    if df.empty: return {"n_syn": 0, "n_streams": 0}, pd.DataFrame()
    ps = per_stream(df)
    if out_csv: ps.to_csv(out_csv, index=False)
    return summary(df, ps), ps

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("pcap"); ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--plain", action="store_true"); ap.add_argument("--csv")
    a = ap.parse_args()
    s, ps = analyze(a.pcap, a.port, a.plain, a.csv)
    for k, v in s.items(): print("%-24s %s" % (k, round(v, 3) if isinstance(v, float) else v))
