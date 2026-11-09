import time

import requests
from app.core.config import settings


class TorClient:
    def __init__(
        self,
        timeout: int = 60,
        retries: int = 3,
        retry_delay: int = 3,
    ):
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay
        proxy = f"socks5h://{settings.tor_host}:{settings.tor_socks_port}"

        self.proxies = {
            "http": proxy,
            "https": proxy,
        }

    def get(
        self,
        url: str,
    ) -> requests.Response:

        last_exception = None

        for attempt in range(
            1,
            self.retries + 1,
        ):
            try:
                response = requests.get(
                    url,
                    proxies=self.proxies,
                    timeout=self.timeout,
                )

                response.raise_for_status()

                return response

            except requests.exceptions.RequestException as exc:
                last_exception = exc

                if attempt == self.retries:
                    raise

                time.sleep(
                    self.retry_delay * attempt
                )

        raise last_exception

    def post(
        self,
        url: str,
        json: dict | None = None,
        **kwargs,
    ) -> requests.Response:

        last_exception = None

        for attempt in range(
            1,
            self.retries + 1,
        ):
            try:
                response = requests.post(
                    url,
                    proxies=self.proxies,
                    timeout=self.timeout,
                    json=json,
                    **kwargs,
                )

                response.raise_for_status()

                return response

            except requests.exceptions.RequestException as exc:
                last_exception = exc

                if attempt == self.retries:
                    raise

                time.sleep(
                    self.retry_delay * attempt
                )

        raise last_exception
