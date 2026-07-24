import logging
import time
import aiohttp

class LatencyMeasurer:
    """Measures latency to the endpoint to update LATENCY_MS dynamically."""

    def __init__(self, url, headers, data, num_pings=5):
        """Initialize with request details and target IP."""
        self.url = url
        self.headers = headers
        self.data = data
        self.num_pings = num_pings
        self.latency_ms = 1200      # Default average round-trip latency
        self.min_latency_ms = 1200  # Default *minimum* round-trip latency

    async def measure_latency(self):
        """
        Measure HTTP round-trip latency by sending test requests.

        We keep both the average (for logging) and the MINIMUM round-trip time.
        Scheduling should use the minimum, not the average: the minimum is the
        closest estimate of the true network floor, so using it never makes us
        fire *late*, whereas the average is inflated by occasional slow samples
        and would push the send time earlier than the packet actually needs.
        """
        async with aiohttp.ClientSession() as session:
            latencies = []
            for i in range(self.num_pings):
                try:
                    start_time = time.time()
                    async with session.post(self.url, headers=self.headers, json=self.data, timeout=15) as response:
                        elapsed_ms = (time.time() - start_time) * 1000
                        latencies.append(elapsed_ms)
                        logging.info(f"Latency measurement {i}: {elapsed_ms:.2f}ms")
                except Exception as e:
                    logging.error(f"Latency measurement {i} failed: {str(e)}")
            if latencies:
                self.latency_ms = sum(latencies) / len(latencies)
                self.min_latency_ms = min(latencies)
                logging.info(
                    f"Latency avg={self.latency_ms:.2f}ms, min={self.min_latency_ms:.2f}ms "
                    f"(scheduling uses min)"
                )
            return self.min_latency_ms
