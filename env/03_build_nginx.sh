#!/bin/bash
# Builds nginx 1.27.4 statically linked against YOUR OpenSSL 3.5.x source (so nginx really uses it).
set -e
VER=$(cat ~/src/OPENSSL_VERSION)
cd ~/src
[ -f nginx-1.27.4.tar.gz ] || wget https://nginx.org/download/nginx-1.27.4.tar.gz
rm -rf nginx-1.27.4 openssl-$VER-ngx && tar xf nginx-1.27.4.tar.gz
mkdir openssl-$VER-ngx && tar xf openssl-$VER.tar.gz -C openssl-$VER-ngx --strip-components=1
cd nginx-1.27.4
./configure --prefix=/opt/nginx --with-stream --with-stream_ssl_module --with-http_ssl_module \
            --with-openssl=$HOME/src/openssl-$VER-ngx
make -j"$(nproc)"
sudo make install
/opt/nginx/sbin/nginx -V 2>&1 | head -3
