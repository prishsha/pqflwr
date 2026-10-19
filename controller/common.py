"""Shared helpers: namespaces, nginx, tcpdump, netem, CPU, manifest."""
import json, os, platform, signal, subprocess, sys, time
import psutil

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OPENSSL = os.environ.get("OPENSSL_BIN", "/opt/openssl-3.5/bin/openssl")
OPENSSL_LIB = os.environ.get("OPENSSL_LIB", "/opt/openssl-3.5/lib64:/opt/openssl-3.5/lib")
NGINX = os.environ.get("NGINX_BIN", "/opt/nginx/sbin/nginx")
SRV_IP = "10.10.0.1"
CFGS = {   # label: (port, key-exchange group, certificate chain)
    "PLAIN": (4430, None, None),
    "K1": (4431, "x25519", "ecdsa"),
    "H1": (4432, "X25519MLKEM768", "ecdsa"),
    "H2": (4433, "X25519MLKEM768", "mldsa65"),
    "P1": (4434, "MLKEM768", "mldsa65"),
}

def nsx(ns, cmd, local=False):
    return list(cmd) if local else ["ip", "netns", "exec", ns] + list(cmd)

def sh(cmd, **kw):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, **kw)
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", "command not found")

def set_netem(delay_ms, loss_pct, rate_mbit=0):
    """One-way delay on BOTH sides (RTT = 2*delay); loss on the server side only; optional rate limit (Mbit/s)."""
    r = sh(["bash", os.path.join(ROOT, "netem", "set_netem.sh"), str(delay_ms), str(loss_pct), str(rate_mbit)])
    if r.returncode != 0:
        raise RuntimeError("netem failed: " + r.stderr)

def tune_route(initcwnd=0, rto_min_ms=0):
    r = sh(["bash", os.path.join(ROOT, "netem", "tune_route.sh"), str(int(initcwnd)), str(int(rto_min_ms))])
    if r.returncode != 0:
        raise RuntimeError("route tuning failed: " + r.stderr)

def start_nginx(ns, conf, rundir, tag, local=False):
    p = subprocess.Popen(nsx(ns, [NGINX, "-p", rundir, "-c", conf, "-e", os.path.join(rundir, tag + "_boot.log"),
                                  "-g", "daemon off;"], local),
                         stdout=subprocess.DEVNULL, stderr=open(os.path.join(rundir, tag + "_stderr.log"), "w"))
    time.sleep(1.0)
    if p.poll() is not None:
        raise RuntimeError("nginx (%s) died; read %s/%s_stderr.log and %s_error.log" % (tag, rundir, tag, tag))
    return p

def start_capture(pcap, port, errfile):
    return subprocess.Popen(nsx("cli", ["tcpdump", "-i", "veth-c", "-s", "0", "-U", "-w", pcap, "tcp port %d" % port]),
                            stdout=subprocess.DEVNULL, stderr=open(errfile, "w"))

def stop_proc(p, sig=signal.SIGINT):
    if p and p.poll() is None:
        p.send_signal(sig)
        try: p.wait(timeout=10)
        except subprocess.TimeoutExpired: p.kill()

def tcpdump_drops(errfile):
    txt = open(errfile).read()
    for line in txt.splitlines():
        if "dropped by kernel" in line: return int(line.split()[0])
    return -1

def tree_cpu(pid):
    """user+system CPU seconds of a process and all its children (nginx master + worker)."""
    try:
        procs = [psutil.Process(pid)] + psutil.Process(pid).children(recursive=True)
        return sum(sum(p.cpu_times()[:2]) for p in procs)
    except psutil.Error:
        return float("nan")

def tcp_retrans(ns, local=False):
    """Kernel counter of TCP retransmitted segments inside a namespace (absolute value)."""
    out = sh(nsx(ns, ["nstat", "-az", "TcpRetransSegs"], local)).stdout
    for line in out.splitlines():
        if line.startswith("TcpRetransSegs"): return int(line.split()[1])
    return -1

def write_manifest(path, extra):
    def first(cmd):
        try: return sh(cmd).stdout.strip().splitlines()[0]
        except Exception: return "n/a"
    m = {"time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "host": platform.node(), "kernel": platform.release(), "python": sys.version.split()[0],
         "cpu": first(["bash", "-c", "lscpu | grep 'Model name' | sed 's/.*: *//'"]),
         "openssl": first([OPENSSL, "version"]), "nginx": first([NGINX, "-v"]) if os.path.exists(NGINX) else "n/a",
         "pip": first(["bash", "-c", "pip list 2>/dev/null | grep -i -E '^(flwr|grpcio|numpy) ' | tr '\\n' ' '"]),
         "cmdline": " ".join(sys.argv)}
    m.update(extra)
    json.dump(m, open(path, "w"), indent=2)
