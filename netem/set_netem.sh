#!/bin/bash
# Usage: set_netem.sh <one-way delay ms> <loss percent>     RTT = 2 x delay.  Loss is applied on the server side only.
# If the kernel has no netem (common on default WSL2) this is silently skipped for 0/0, and fails loudly otherwise.
D=${1:-0}; L=${2:-0}
if sudo ip netns exec cli tc qdisc replace dev veth-c root netem delay ${D}ms 2>/tmp/netem_err.txt && \
   sudo ip netns exec srv tc qdisc replace dev veth-s root netem delay ${D}ms loss ${L}% 2>>/tmp/netem_err.txt; then
  exit 0
fi
if awk "BEGIN{exit !($D==0 && $L==0)}"; then exit 0; fi
echo "ERROR: network emulation (netem) is not available in this kernel, so delay=${D}ms loss=${L}% cannot be applied." >&2
cat /tmp/netem_err.txt >&2
exit 1
