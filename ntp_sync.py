import logging
import socket
import struct
import time

# Public NTP servers, tried in order.
NTP_SERVERS = ("pool.ntp.org", "time.cloudflare.com", "time.google.com")
NTP_PORT = 123
NTP_TIMEOUT = 2
# Seconds between 1900-01-01 (NTP epoch) and 1970-01-01 (Unix epoch).
NTP_UNIX_DELTA = 2208988800


def _query_ntp(server):
    """Return the true UTC time (Unix seconds) from a single NTP server."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(NTP_TIMEOUT)
        # LI=0, VN=3, Mode=3 (client) -> first byte 0x1b, rest zero.
        sock.sendto(b"\x1b" + 47 * b"\0", (server, NTP_PORT))
        data, _ = sock.recvfrom(48)
        seconds = struct.unpack("!I", data[40:44])[0]
        fraction = struct.unpack("!I", data[44:48])[0]
        return seconds + fraction / 2 ** 32 - NTP_UNIX_DELTA
    finally:
        sock.close()


def get_ntp_offset():
    """
    Return (ntp_time - local_time) in seconds.

    The whole strategy hinges on firing at Beijing midnight *to the millisecond*.
    The local system clock is routinely tens to hundreds of milliseconds off
    (especially on laptops that just woke up), which is enough to miss the quota
    entirely. Measuring the offset once against NTP and correcting for it makes
    the schedule independent of local clock drift.

    Returns 0.0 if every NTP server is unreachable (falls back to local clock).
    """
    for server in NTP_SERVERS:
        try:
            offset = _query_ntp(server) - time.time()
            logging.info(f"NTP offset from {server}: {offset * 1000:+.1f} ms")
            return offset
        except Exception as e:  # noqa: BLE001 - any failure -> try the next server
            logging.warning(f"NTP query to {server} failed: {e}")
    logging.warning("All NTP servers unreachable - using local clock (no correction).")
    return 0.0
