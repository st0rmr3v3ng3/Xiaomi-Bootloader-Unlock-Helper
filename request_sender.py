import asyncio
import json
import logging
from datetime import datetime, timedelta

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

    @staticmethod
    def _should_abort(response):
        """
        Decide whether a response means we should stop the wave.

        Keep firing ONLY while the quota simply isn't ours yet, i.e.
        code == 0 and apply_result == 3 (quota exhausted / not open). Anything
        else means there is no point spamming further:
          apply_result == 1  -> approved (we won)
          apply_result == 4  -> account blocked
          code != 0          -> token/other error

        The previous implementation additionally required the response's
        `deadline` to equal a hard-coded Unix timestamp (April 22, 2025). That
        made the script abort on EVERY response on any other date, so the wave
        stopped after the first request. Matching on apply_result alone is
        date-agnostic and future-proof.
        """
        if response["status"] is None:
            return False  # network error / timeout -> keep trying
        try:
            resp_json = json.loads(response["text"])
        except json.JSONDecodeError:
            logging.error("Invalid JSON response, continuing wave.")
            return False
        code = resp_json.get("code")
        apply_result = resp_json.get("data", {}).get("apply_result")
        if code == 0 and apply_result == 3:
            return False  # quota not ours yet -> keep firing
        logging.info(f"Stopping wave: code={code}, apply_result={apply_result}")
        return True

    async def send_request_wave(self, session, num_requests, stagger_ms, abort_event):
        """
        Fire the wave CONCURRENTLY on a shared, pre-warmed session.

        The previous version awaited each request's full response before sending
        the next one. Because every round trip is ~200-300 ms, that serialised
        the "wave" into num_requests * RTT of wall-clock time (e.g. 100 requests
        ~= 25 s) — the packets dribbled out over tens of seconds and mostly
        arrived long after the quota was gone. Here every request is launched as
        its own task (optionally spread by a few ms via `stagger_ms`) and they
        all fly in parallel, so the whole burst lands inside the first fraction
        of a second after the quota opens.

        `session` is created and kept warm by the caller so the first (and most
        important) request does not pay for the TLS handshake at fire time.
        """
        async def fire(index):
            # Spread launches slightly so we don't emit every packet on the
            # exact same microsecond, but never wait on another request's reply.
            if stagger_ms:
                await asyncio.sleep(index * stagger_ms / 1000)
            if abort_event.is_set():
                return
            response = await self.send_single_request(session, index)
            if self._should_abort(response):
                abort_event.set()

        await asyncio.gather(*(fire(i) for i in range(num_requests)))
