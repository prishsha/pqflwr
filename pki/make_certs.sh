#!/bin/bash
# Creates two CA+server certificate chains: ECDSA P-256 and ML-DSA-65.
set -e
OSSL=/opt/openssl-3.5/bin/openssl
export LD_LIBRARY_PATH=$(ls -d /opt/openssl-3.5/lib64 /opt/openssl-3.5/lib 2>/dev/null | head -1)
cd "$(dirname "$0")"; rm -rf certs; mkdir certs; cd certs
echo "subjectAltName=DNS:testserver" > san.cnf
mk() {  # $1=name  $2..=genpkey args   $3=digest option for classical
  name=$1; shift; dig=$1; shift
  $OSSL genpkey "$@" -out ca-$name.key
  $OSSL req -x509 -new -key ca-$name.key $dig -days 365 -subj "/CN=TestCA-$name" -addext "basicConstraints=critical,CA:TRUE" -out ca-$name.crt
  $OSSL genpkey "$@" -out server-$name.key
  $OSSL req -new -key server-$name.key -subj "/CN=testserver" -out server-$name.csr
  $OSSL x509 -req -in server-$name.csr -CA ca-$name.crt -CAkey ca-$name.key -CAcreateserial -days 365 $dig -extfile san.cnf -out server-$name.crt
}
mk ecdsa "-sha256" -algorithm EC -pkeyopt ec_paramgen_curve:P-256
mk mldsa65 "" -algorithm ML-DSA-65
echo "=== certificate sizes (DER bytes) and signature algorithms ===" | tee cert_sizes.txt
for f in ca-ecdsa ca-mldsa65 server-ecdsa server-mldsa65; do
  echo "$f.crt  DER=$($OSSL x509 -in $f.crt -outform DER | wc -c) bytes  sig=$($OSSL x509 -in $f.crt -noout -text | grep -m1 'Signature Algorithm' | sed 's/.*: *//')" | tee -a cert_sizes.txt
done
for n in ecdsa mldsa65; do $OSSL verify -CAfile ca-$n.crt server-$n.crt; done
