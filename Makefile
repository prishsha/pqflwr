# Convenience targets.  Everything that touches the network needs sudo (it is called inside the targets).
PY=venv/bin/python
.PHONY: setup certs data netns test smoke stage0 matrix stats model mitigation clean-runs
setup:        ## build the environment (system packages, venv, OpenSSL 3.5.x, nginx)
	bash env/01_install_deps.sh && bash env/00_check_system.sh && bash env/02_build_openssl.sh $(OPENSSL_VER) && bash env/03_build_nginx.sh
certs:        ## ECDSA P-256 and ML-DSA-65 certificate chains
	bash pki/make_certs.sh
data:         ## CIC-IDS2017 preprocessing (CSV_DIR=~/cicids2017) or SYNTHETIC=1 for a pipeline test
	$(PY) fl/prepare_data.py $(if $(SYNTHETIC),--synthetic,--csv-dir $(CSV_DIR))
netns:        ## virtual client/server network (MTU 1500)
	bash env/04_netns_up.sh
test:         ## unit tests (no network needed)
	$(PY) -m pytest -q tests
smoke:        ## FL part only, loopback, no TLS
	$(PY) controller/run_experiment.py --cfg K1 --clients 3 --rounds 3 --local-test --stage test
stage0:
	bash stage0.sh
matrix:       ## resumable full matrix:  make matrix STAGE=7 REPEATS=10
	sudo $(PY) controller/matrix.py --stage $(STAGE) --repeats $(REPEATS)
stats:
	$(PY) analysis/stats.py --stage $(STAGE)
model:
	$(PY) analysis/model.py --stage $(STAGE)
mitigation:
	$(PY) analysis/mitigation.py --base-stage 7 --mit-stage 10
clean-runs:
	rm -rf runs/* results/*
