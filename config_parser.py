import re
import json
import logging


class ConfigParser:
    @staticmethod
    def parse_headers_file(file_path):
        """
        Parse headers.txt into hostname, url, and headers dict.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = [line.rstrip() for line in f]

            method = None
            raw_url = None
            hostname = None
            headers = {}

            current_header = None
            in_headers = False

            i = 0
            while i < len(lines):
                line = lines[i].strip()

                # METHOD
                if line.startswith("METHOD:"):
                    method = line.split(":", 1)[1].strip()

                # URL (URL is on its own line, value on next line)
                elif line == "URL":
                    raw_url = lines[i + 1].strip()
                    i += 1

                # HEADERS section
                elif line == "HEADERS":
                    in_headers = True

                elif in_headers:
                    # Header key line (ends with :)
                    if line.endswith(":"):
                        current_header = line[:-1]
                        headers[current_header] = ""

                    # Header value line
                    elif current_header and line:
                        headers[current_header] = line
                        current_header = None

                i += 1

            # Extract hostname
            hostname = headers.get("Host")
            if not hostname:
                raise ValueError("Host not found in headers")

            # Build URL using hostname
            if not raw_url:
                raise ValueError("URL not found")

            path = re.sub(r"^https?://[^/]+", "", raw_url)
            url = f"https://{hostname}{path}"

            # Remove Content-Length (aiohttp sets it automatically)
            headers.pop("Content-Length", None)

            return {
                "hostname": hostname,
                "url": url,
                "headers": headers,
            }

        except Exception as e:
            logging.error(f"Failed to parse headers file: {e}")
            raise

    @staticmethod
    def parse_body_file(file_path):
        """Parse body.json file into a dictionary."""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to parse body file: {str(e)}")
            raise
