import asyncio
import logging
from datetime import datetime, timedelta

import pytz

class Scheduler:
    """Schedules and manages the request wave for bootloader unlock."""

    def __init__(self, target_time, latency_ms, num_requests, stagger_ms, check_interval_ms, request_sender):
        """Initialize with scheduling parameters and request sender."""
        self.target_time = target_time
        self.latency_ms = latency_ms
        self.num_requests = num_requests
        self.stagger_ms = stagger_ms
        self.check_interval_ms = check_interval_ms
        self.request_sender = request_sender
        self.beijing_tz = pytz.timezone('Asia/Shanghai')
        self.local_tz = pytz.timezone('Europe/Paris')  # GMT+1 with summer time
        self.abort_event = asyncio.Event()

    async def schedule_requests(self):
        """Schedule the request wave, adjusting for latency and wave duration."""
        # Localize target time if naive
        if self.target_time.tzinfo is None:
            self.target_time = self.beijing_tz.localize(self.target_time)

        target_time_utc = self.target_time.astimezone(pytz.UTC)
        target_time_local = self.target_time.astimezone(self.local_tz)

        # Calculate total wave duration
        wave_duration_ms = (self.num_requests - 1) * self.stagger_ms

        # Adjust send time to center the wave around the target time
        adjusted_time = self.target_time - timedelta(milliseconds=(self.latency_ms + wave_duration_ms // 2))

        logging.info(f"Target time (Beijing): {self.target_time}")
        logging.info(f"Adjusted send time (Beijing): {adjusted_time}")
        logging.info(f"Adjusted send time (UTC): {adjusted_time.astimezone(pytz.UTC)}")
        logging.info(f"Adjusted send time (Local, GMT+1): {adjusted_time.astimezone(self.local_tz)}")

        # Wait until the adjusted send time
        while True:
            now = datetime.now(self.beijing_tz)
            if now >= adjusted_time:
                logging.info("Sending request wave...")
                await self.request_sender.send_request_wave(self.num_requests, self.stagger_ms, self.abort_event)
                break
            await asyncio.sleep(self.check_interval_ms / 1000)  # Check every 5ms
