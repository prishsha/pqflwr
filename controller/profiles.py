"""Named network profiles.  delay_ms is ONE-WAY (RTT = 2 x delay).  loss is applied on the server side.
rate_mbit = 0 means unlimited (ideal LAN).  Edit here to change the whole study."""
PROFILES = {
    "LAN":    dict(delay_ms=0,  loss=0, rate_mbit=0),     # ideal LAN (virtual cable, RTT ~0.1 ms)
    "WAN50":  dict(delay_ms=25, loss=0, rate_mbit=20),    # RTT 50 ms, 20 Mbit/s edge link
    "WAN100": dict(delay_ms=50, loss=0, rate_mbit=20),    # RTT 100 ms
    "LOSS1":  dict(delay_ms=25, loss=1, rate_mbit=20),    # RTT 50 ms, 1 % loss
    "LOSS3":  dict(delay_ms=50, loss=3, rate_mbit=20),    # RTT 100 ms, 3 % loss
    "LOSS5":  dict(delay_ms=50, loss=5, rate_mbit=20),    # RTT 100 ms, 5 % loss
}
