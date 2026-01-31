import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
import pytz

from config_parser import ConfigParser
from latency_measurer import LatencyMeasurer
from request_sender import RequestSender
from scheduler import Scheduler

BASE_DIR = Path(__file__).resolve().parent
HEADERS_FILE = BASE_DIR / "headers.txt"
BODY_FILE = BASE_DIR / "body.json"

# Configure logging to file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('request_log.txt'),
        logging.StreamHandler()
    ]
)


async def initial_test_request(request_sender):
    """Send a single test request on startup to verify script functionality."""
    async with aiohttp.ClientSession() as session:
        response = await request_sender.send_single_request(session, 0, log_prefix="Test Request")
        logging.info(f"Initial test request completed: {response}")


async def initial_latency_measurement(latency_measurer):
    """Measure latency on startup and update LATENCY_MS."""
    latency = await latency_measurer.measure_latency()
    logging.info(f"Initial latency measurement completed: {latency:.2f}ms")


async def main():
    """Main entry point to start the scheduler and initial tasks."""
    # Request details
    # Parse config files
    header_config = ConfigParser.parse_headers_file(HEADERS_FILE)
    data = ConfigParser.parse_body_file(BODY_FILE)

    url = header_config["url"]
    headers = header_config["headers"]

    # Initialize components
    request_sender = RequestSender(url, headers, data, timeout_seconds=15)
    latency_measurer = LatencyMeasurer(url, headers, data, num_pings=5)

    # Run initial test request and latency measurement concurrently
    await asyncio.gather(
        initial_test_request(request_sender),
        initial_latency_measurement(latency_measurer)
    )

    # Update latency for scheduler
    latency_ms = latency_measurer.latency_ms

    # Set target time to 24:00:00 Beijing time
    beijing_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(beijing_tz).replace(tzinfo=None)
    target_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if target_time < now:
        target_time += timedelta(days=1)  # Schedule for next midnight
    target_time = beijing_tz.localize(target_time)

    # Initialize and run scheduler
    scheduler = Scheduler(
        target_time=target_time,
        latency_ms=latency_ms,
        num_requests=100,
        stagger_ms=15,
        check_interval_ms=5,
        request_sender=request_sender
    )

    # Warning: too many requests may trigger rate limits
    if scheduler.num_requests > 100:
        logging.warning("NUM_REQUESTS is high and may trigger rate limits.")

    await scheduler.schedule_requests()


# Run the main async function
if __name__ == "__main__":
    asyncio.run(main())
