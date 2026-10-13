#!/bin/bash
# Two network namespaces joined by a virtual cable, MTU 1500 (like a real network).
# cli (10.10.0.2) <---- veth ----> srv (10.10.0.1)
set -e
bash "$(dirname "$0")/05_netns_down.sh" 2>/dev/null || true
sudo ip netns add srv; sudo ip netns add cli
sudo ip link add veth-s type veth peer name veth-c
sudo ip link set veth-s netns srv; sudo ip link set veth-c netns cli
sudo ip netns exec srv ip addr add 10.10.0.1/24 dev veth-s
sudo ip netns exec cli ip addr add 10.10.0.2/24 dev veth-c
for ns in srv cli; do sudo ip netns exec $ns ip link set lo up; done
sudo ip netns exec srv ip link set veth-s up; sudo ip netns exec cli ip link set veth-c up
# turn off segmentation offloads so the capture shows real 1500-byte packets
sudo ip netns exec srv ethtool -K veth-s tso off gso off gro off 2>/dev/null || true
sudo ip netns exec cli ethtool -K veth-c tso off gso off gro off 2>/dev/null || true
bash "$(dirname "$0")/../netem/set_netem.sh" 0 0 || true
echo "Test (TCP-level, not ping):"; sudo ip netns exec cli ping -c 2 10.10.0.1 | tail -3
