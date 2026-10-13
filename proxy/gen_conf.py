"""Render nginx stream configs.   python proxy/gen_conf.py  (used by the controller)"""
import os
PROXY_LOCAL = 9093      # clients talk plaintext to this port (inside the client namespace)
FLOWER_PORT = 9092      # Flower server (inside the server namespace)
CERT_NAME = "testserver"
CIPHER = "TLS_AES_256_GCM_SHA384"

def server_conf(rundir, certdir, port, group, chain, srv_ip="10.10.0.1", local=False):
    listen = "127.0.0.1:%d" % port if local else "%s:%d" % (srv_ip, port)
    if group is None:
        ssl = ""; listen_s = listen
        logv = "$time_iso8601 $remote_addr $status $bytes_sent $bytes_received $session_time"
    else:
        listen_s = listen + " ssl"
        ssl = f"""
    ssl_certificate {certdir}/server-{chain}.crt;
    ssl_certificate_key {certdir}/server-{chain}.key;
    ssl_protocols TLSv1.3;
    ssl_conf_command Ciphersuites {CIPHER};
    ssl_conf_command Groups {group};
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1h;
    ssl_session_tickets on;"""
        logv = "$time_iso8601 $remote_addr $status $bytes_sent $bytes_received $session_time $ssl_protocol $ssl_cipher $ssl_session_reused"
    return f"""worker_processes 1;
pid {rundir}/srv.pid;
error_log {rundir}/srv_error.log info;
events {{ worker_connections 1024; }}
stream {{
  log_format m '{logv}';
  access_log {rundir}/srv_access.log m;
  server {{
    listen {listen_s};{ssl}
    proxy_timeout 1h;
    proxy_pass 127.0.0.1:{FLOWER_PORT};
  }}
}}
"""

def client_conf(rundir, certdir, port, group, chain, resume, srv_ip="10.10.0.1", local=False):
    upstream = "127.0.0.1:%d" % port if local else "%s:%d" % (srv_ip, port)
    if group is None:
        ssl = ""
    else:
        ssl = f"""
    proxy_ssl on;
    proxy_ssl_protocols TLSv1.3;
    proxy_ssl_conf_command Ciphersuites {CIPHER};
    proxy_ssl_conf_command Groups {group};
    proxy_ssl_verify on;
    proxy_ssl_trusted_certificate {certdir}/ca-{chain}.crt;
    proxy_ssl_name {CERT_NAME};
    proxy_ssl_server_name on;
    proxy_ssl_session_reuse {"on" if resume else "off"};"""
    return f"""worker_processes 1;
pid {rundir}/cli.pid;
error_log {rundir}/cli_error.log info;
events {{ worker_connections 1024; }}
stream {{
  log_format c '$time_iso8601 $status $upstream_bytes_sent $upstream_bytes_received $upstream_connect_time $upstream_session_time';
  access_log {rundir}/cli_access.log c;
  server {{
    listen 127.0.0.1:{PROXY_LOCAL};
    proxy_pass {upstream};{ssl}
    proxy_timeout 1h;
    proxy_connect_timeout 10s;
  }}
}}
"""
