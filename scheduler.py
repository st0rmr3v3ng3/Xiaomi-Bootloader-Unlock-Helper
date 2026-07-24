import asyncio
import logging
import time
from datetime import datetime, timedelta

import pytz

class Scheduler:
    """Schedules and manages the request wave for bootloader unlock."""

    # How long before the shot to prime the connection pool, and how many
    # connections to warm. Warming keeps live keep-alive sockets in aiohttp's
    # pool so the first (most important) request of the wave reuses an open TLS
    # connection instead of paying for a fresh handshake at fire time.
    WARM_LEAD_S = 3.0
    WARM_COUNT_CAP = 8

    def __init__(self, target_time, latency_ms, num_requests, stagger_ms,
                 check_interval_ms, request_sender, session, ntp_offset=0.0):
        """Initialize with scheduling parameters and request sender."""
        self.target_time = target_time
        self.latency_ms = latency_ms          # MINIMUM round-trip latency (ms)
        self.num_requests = num_requests
        self.stagger_ms = stagger_ms
        self.check_interval_ms = check_interval_ms
        self.request_sender = request_sender
        self.session = session
        self.ntp_offset = ntp_offset           # (true_time - local_time), seconds
        self.beijing_tz = pytz.timezone('Asia/Shanghai')
        self.local_tz = pytz.timezone('Europe/Paris')  # GMT+1 with summer time
        self.abort_event = asyncio.Event()

    def _now_beijing(self):
        """Current Beijing time corrected by the measured NTP offset."""
        corrected = time.time() + self.ntp_offset
        return datetime.fromtimestamp(corrected, tz=pytz.UTC).astimezone(self.beijing_tz)

    async def schedule_requests(self):
        """Schedule the request wave, adjusting for latency and wave duration."""
        # Localize target time if naive
        if self.target_time.tzinfo is None:
            self.target_time = self.beijing_tz.localize(self.target_time)

        # Calculate total wave duration
        wave_duration_ms = (self.num_requests - 1) * self.stagger_ms

        # Send so packets ARRIVE at the target: subtract the ONE-WAY latency
        # (half the round-trip), not the full round-trip. Subtracting the full
        # RTT would make the packets arrive one one-way-trip *before* the quota
        # opens, where they are simply rejected. Also center the launch window.
        one_way_ms = self.latency_ms / 2
        adjusted_time = self.target_time - timedelta(
            milliseconds=(one_way_ms + wave_duration_ms // 2)
        )

        logging.info(f"NTP offset applied: {self.ntp_offset * 1000:+.1f} ms")
        logging.info(f"Target time (Beijing): {self.target_time}")
        logging.info(f"One-way latency used: {one_way_ms:.1f} ms")
        logging.info(f"Adjusted send time (Beijing): {adjusted_time}")
        logging.info(f"Adjusted send time (UTC): {adjusted_time.astimezone(pytz.UTC)}")
        logging.info(f"Adjusted send time (Local, GMT+1): {adjusted_time.astimezone(self.local_tz)}")

        warm_time = adjusted_time - timedelta(seconds=self.WARM_LEAD_S)
        warmed = False

        # Wait until the adjusted send time (NTP-corrected clock)
        while True:
            now = self._now_beijing()

            # Prime the connection pool shortly before firing.
            if not warmed and now >= warm_time:
                warmed = True
                await self._prewarm()

            if now >= adjusted_time:
                logging.info("Sending request wave...")
                await self.request_sender.send_request_wave(
                    self.session, self.num_requests, self.stagger_ms, self.abort_event
                )
                break
            await asyncio.sleep(self.check_interval_ms / 1000)  # Check every 5ms

    async def _prewarm(self):
        """
        Open a small pool of keep-alive connections just before the shot.

        These pre-midnight requests harmlessly return "quota not open yet"
        (apply_result == 3); their only purpose is to leave warm TLS sockets in
        aiohttp's connection pool so the real burst reuses them.
        """
        count = min(self.num_requests, self.WARM_COUNT_CAP)
        logging.info(f"Pre-warming {count} connection(s) ~{self.WARM_LEAD_S:.0f}s before shot...")
        await asyncio.gather(*(
            self.request_sender.send_single_request(self.session, i, log_prefix="Warmup")
            for i in range(count)
        ))
