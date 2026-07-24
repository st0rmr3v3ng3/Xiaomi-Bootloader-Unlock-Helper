import asyncio
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
import pytz

from config_parser import ConfigParser
from latency_measurer import LatencyMeasurer
from ntp_sync import get_ntp_offset
from request_sender import RequestSender
from scheduler import Scheduler

BASE_DIR = Path(__file__).resolve().parent
HEADERS_FILE = BASE_DIR / "headers.txt"
BODY_FILE = BASE_DIR / "body.json"

NUM_REQUESTS = 100
STAGGER_MS = 15
CHECK_INTERVAL_MS = 5

# Configure logging to file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('request_log.txt'),
        logging.StreamHandler()
    ]
)


async def initial_test_request(request_sender, session):
    """Send a single test request on startup to verify script functionality."""
    response = await request_sender.send_single_request(session, 0, log_prefix="Test Request")
    logging.info(f"Initial test request completed: {response}")


async def initial_latency_measurement(latency_measurer):
    """Measure latency on startup and update LATENCY_MS."""
    latency = await latency_measurer.measure_latency()
    logging.info(f"Initial latency measurement completed: {latency:.2f}ms")


async def main():
    """Main entry point to start the scheduler and initial tasks."""
    # Parse config files
    header_config = ConfigParser.parse_headers_file(HEADERS_FILE)
    data = ConfigParser.parse_body_file(BODY_FILE)

    url = header_config["url"]
    headers = header_config["headers"]

    # Measure the local clock's offset from real time once, up front. Every
    # timing decision below is made against this corrected clock.
    ntp_offset = await asyncio.get_event_loop().run_in_executor(None, get_ntp_offset)

    # Initialize components
    request_sender = RequestSender(url, headers, data, timeout_seconds=15)
    latency_measurer = LatencyMeasurer(url, headers, data, num_pings=5)

    # A single shared session for warm-up + the wave, with a connection pool
    # large enough to hold all concurrent requests as keep-alive sockets.
    connector = aiohttp.TCPConnector(
        limit=NUM_REQUESTS + Scheduler.WARM_COUNT_CAP,
        keepalive_timeout=30,
    )
    async with aiohttp.ClientSession(connector=connector) as session:
        # Run initial test request and latency measurement concurrently
        await asyncio.gather(
            initial_test_request(request_sender, session),
            initial_latency_measurement(latency_measurer)
        )

        # Scheduling uses the MINIMUM measured round-trip latency
        latency_ms = latency_measurer.min_latency_ms

        # Set target to the next Beijing midnight, on the NTP-corrected clock
        beijing_tz = pytz.timezone('Asia/Shanghai')
        corrected_now = datetime.fromtimestamp(time.time() + ntp_offset, tz=pytz.UTC).astimezone(beijing_tz)
        target_time = corrected_now.replace(hour=0, minute=0, second=0, microsecond=0)
        if target_time <= corrected_now:
            target_time += timedelta(days=1)  # Schedule for next midnight

        # Warning: too many requests may trigger rate limits
        if NUM_REQUESTS > 100:
            logging.warning("NUM_REQUESTS is high and may trigger rate limits.")

        # Initialize and run scheduler
        scheduler = Scheduler(
            target_time=target_time,
            latency_ms=latency_ms,
            num_requests=NUM_REQUESTS,
            stagger_ms=STAGGER_MS,
            check_interval_ms=CHECK_INTERVAL_MS,
            request_sender=request_sender,
            session=session,
            ntp_offset=ntp_offset,
        )

        await scheduler.schedule_requests()


# Run the main async function
if __name__ == "__main__":
    asyncio.run(main())
