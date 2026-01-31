import asyncio
import json
import logging
from datetime import datetime, timedelta

import aiohttp
import pytz

class RequestSender:
    """Handles sending HTTP requests to the Xiaomi bootloader unlock endpoint."""

    def __init__(self, url, headers, data, timeout_seconds=15):
        """Initialize with request details."""
        self.url = url
        self.headers = headers
        self.data = data
        self.timeout_seconds = timeout_seconds

    async def send_single_request(self, session, index, log_prefix="Request"):
        """Send a single async HTTP POST request and log the response."""
        try:
            start_time = datetime.now(pytz.UTC)
            async with session.post(self.url, headers=self.headers, json=self.data,
                                    timeout=self.timeout_seconds) as response:
                status = response.status
                text = await response.text()
                end_time = datetime.now(pytz.UTC)
                elapsed_ms = (end_time - start_time).total_seconds() * 1000
                estimated_arrival = start_time + timedelta(milliseconds=elapsed_ms)
                log_message = (
                    f"{log_prefix} {index}: Status={status}, "
                    f"Sent at={start_time.isoformat()}, "
                    f"Estimated arrival (Beijing)={estimated_arrival.astimezone(pytz.timezone('Asia/Shanghai')).isoformat()}, "
                    f"Latency={elapsed_ms:.2f}ms, Response={text}"
                )
                logging.info(log_message)
                return {"status": status, "text": text, "elapsed_ms": elapsed_ms}
        except Exception as e:
            error_message = f"{log_prefix} {index}: Error={str(e)}"
            logging.error(error_message)
            return {"status": None, "text": str(e), "elapsed_ms": None}

    async def send_request_wave(self, num_requests, stagger_ms, abort_event):
        """Send a wave of staggered requests, aborting only for unexpected responses."""
        async with aiohttp.ClientSession() as session:
            for i in range(num_requests):
                if abort_event.is_set():
                    logging.info("Wave aborted due to unexpected response.")
                    break

                # Send a single request and check its response
                response = await self.send_single_request(session, i)

                # Check response for abortion conditions
                if response["status"] is not None:  # Continue on timeout
                    try:
                        resp_json = json.loads(response["text"])
                        code = resp_json.get("code")
                        apply_result = resp_json.get("data", {}).get("apply_result")
                        deadline = resp_json.get("data", {}).get("deadline")
                        # Continue if code == 0, apply_result == 3, deadline == April 22, 2025
                        # Abort if code != 0, apply_result != 3, or deadline == April 23, 2025
                        if not (code == 0 and
                                apply_result == 3 and
                                deadline == 1745251200):  # April 22, 2025, 00:00:00 Beijing
                            logging.info(
                                f"Aborting wave: code={code}, apply_result={apply_result}, deadline={deadline}")
                            abort_event.set()
                            break
                    except json.JSONDecodeError:
                        logging.error("Invalid JSON response, continuing wave.")

                # Stagger the next request
                if i < num_requests - 1:  # No sleep after the last request
                    await asyncio.sleep(stagger_ms / 1000)  # Convert ms to seconds
