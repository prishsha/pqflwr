#!/bin/bash
# Usage: bash env/02_build_openssl.sh 3.5.4      (use the newest 3.5.x if you like; the thesis used 3.5.7)
set -e
VER=${1:-3.5.4}
mkdir -p ~/src && cd ~/src
[ -f openssl-$VER.tar.gz ] || wget https://github.com/openssl/openssl/releases/download/openssl-$VER/openssl-$VER.tar.gz
rm -rf openssl-$VER && tar xf openssl-$VER.tar.gz && cd openssl-$VER
./Configure --prefix=/opt/openssl-3.5 --openssldir=/opt/openssl-3.5/ssl
make -j"$(nproc)"
sudo make install_sw install_ssldirs
echo "$VER" > ~/src/OPENSSL_VERSION
LIBDIR=$(ls -d /opt/openssl-3.5/lib64 /opt/openssl-3.5/lib 2>/dev/null | head -1)
grep -q openssl-3.5 ~/.bashrc || { echo "export PATH=/opt/openssl-3.5/bin:\$PATH" >> ~/.bashrc; echo "export LD_LIBRARY_PATH=$LIBDIR:\$LD_LIBRARY_PATH" >> ~/.bashrc; }
export LD_LIBRARY_PATH=$LIBDIR
/opt/openssl-3.5/bin/openssl version
echo "--- KEMs ---";       /opt/openssl-3.5/bin/openssl list -kem-algorithms | grep -i -E "mlkem|ml-kem"
echo "--- signatures ---"; /opt/openssl-3.5/bin/openssl list -signature-algorithms | grep -i "ml-dsa"
