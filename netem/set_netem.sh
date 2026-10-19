#!/bin/bash
# Usage: set_netem.sh <one-way delay ms> <loss percent> [rate Mbit/s, 0 = unlimited]
#   RTT = 2 x delay.  Loss is applied on the server side only.  Rate limit is applied on both sides.
# If the kernel has no netem this is skipped silently for 0/0/0, and fails loudly otherwise.
D=${1:-0}; L=${2:-0}; R=${3:-0}
RATE=""; if awk "BEGIN{exit !($R>0)}"; then RATE="rate ${R}mbit"; fi
if ip netns exec cli tc qdisc replace dev veth-c root netem limit 20000 delay ${D}ms $RATE 2>/tmp/netem_err.txt && \
   ip netns exec srv tc qdisc replace dev veth-s root netem limit 20000 delay ${D}ms loss ${L}% $RATE 2>>/tmp/netem_err.txt; then
  exit 0
fi
if awk "BEGIN{exit !($D==0 && $L==0 && $R==0)}"; then exit 0; fi
echo "ERROR: network emulation (netem) is not available, so delay=${D}ms loss=${L}% rate=${R}Mbit cannot be applied." >&2
cat /tmp/netem_err.txt >&2
exit 1
