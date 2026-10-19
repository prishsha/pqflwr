#!/bin/bash
# Run once:  bash env/01_install_deps.sh
set -e
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update
sudo apt-get install -y build-essential perl git curl wget ca-certificates python3-venv python3-pip \
     tcpdump tshark iproute2 ethtool iperf3 linux-tools-common libpcre2-dev zlib1g-dev
sudo apt-get install -y linux-tools-generic linux-tools-$(uname -r) || echo "perf not installed (optional)"
cd "$(dirname "$0")/.."
python3 -m venv venv
. venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "DONE. Versions:"; pip list 2>/dev/null | grep -i -E "^(flwr|grpcio|numpy|pandas) "
