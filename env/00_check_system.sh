#!/bin/bash
# Run after env/01_install_deps.sh.  Tells you whether this machine can run the experiments.
echo "kernel : $(uname -r)"; grep -qi microsoft /proc/version && echo "type   : WSL (Windows)" || echo "type   : normal Linux"
echo "cores  : $(nproc)   (want 4)"; echo "memory : $(free -g | awk '/Mem:/{print $2}') GB   (want 8)"
echo "distro : $(lsb_release -ds 2>/dev/null)"
sudo ip netns del chk_a 2>/dev/null; sudo ip netns del chk_b 2>/dev/null
ok=1
sudo ip netns add chk_a && sudo ip netns add chk_b && echo "PASS network namespaces" || { echo "FAIL network namespaces"; ok=0; }
sudo ip link add chk-a type veth peer name chk-b 2>/dev/null && echo "PASS veth pair" || { echo "FAIL veth pair"; ok=0; }
sudo ip link set chk-a netns chk_a 2>/dev/null; sudo ip link set chk-b netns chk_b 2>/dev/null
if sudo ip netns exec chk_a tc qdisc replace dev chk-a root netem delay 10ms loss 1% 2>/dev/null; then echo "PASS netem (delay/loss emulation)"; else echo "FAIL netem  -> Stage-1 RTT/loss sweeps will NOT work (see WSL guide section 2b)"; fi
which tcpdump tshark nstat ethtool >/dev/null 2>&1 && echo "PASS tools tcpdump/tshark/nstat/ethtool" || { echo "FAIL missing tools (rerun 01_install_deps.sh)"; ok=0; }
sudo ip netns del chk_a 2>/dev/null; sudo ip netns del chk_b 2>/dev/null; sudo ip link del chk-a 2>/dev/null
[ $ok = 1 ] && echo "=> machine is usable (netem line tells you whether sweeps are possible)" || echo "=> machine NOT usable yet"
