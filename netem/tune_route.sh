#!/bin/bash
# Usage: tune_route.sh <initcwnd segments, 0 = kernel default (10)> <rto_min ms, 0 = kernel default (200)>
# Mitigation knobs for the TCP stack between the two namespaces.  Called by the controller for every run so that
# every run starts from a known state.
IW=${1:-0}; RTO=${2:-0}
opts=""
[ "$IW" != "0" ] && opts="$opts initcwnd $IW"
[ "$RTO" != "0" ] && opts="$opts rto_min ${RTO}ms"
rc=0
for spec in "srv veth-s 10.10.0.1" "cli veth-c 10.10.0.2"; do
  read ns dev ip <<< "$spec"
  sudo ip netns exec $ns ip route change 10.10.0.0/24 dev $dev proto kernel scope link src $ip $opts 2>/tmp/route_err.txt || rc=1
done
if [ $rc != 0 ]; then echo "ERROR: could not set route options ($opts)" >&2; cat /tmp/route_err.txt >&2; exit 1; fi
exit 0
