"""Small JSON-RPC adapter with bounded retries and chain identity checks."""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class RpcError(RuntimeError):
    pass


class RpcClient:
    def __init__(self, url: str, timeout: float = 15, max_retries: int = 4) -> None:
        if not url.startswith(("http://", "https://")):
            raise ValueError("RPC URL must use HTTP or HTTPS")
        self.url = url
        self.timeout = timeout
        self.max_retries = max_retries
        self._request_id = 0

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        self._request_id += 1
        payload = json.dumps({
            "jsonrpc": "2.0", "id": self._request_id,
            "method": method, "params": params or [],
        }).encode()
        request = urllib.request.Request(
            self.url, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "ORBIS/0.1"},
            method="POST",
        )
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = json.loads(response.read())
                if body.get("error"):
                    error = body["error"]
                    message = str(error.get("message", ""))
                    if attempt < self.max_retries and any(term in message.lower() for term in
                            ("rate limit", "too many requests", "temporarily unavailable")):
                        delay = min(30.0, 0.25 * (2 ** attempt) + random.uniform(0, 0.2))
                        logger.warning("RPC provider requested retry", extra={"method": method,
                                                                              "attempt": attempt + 1,
                                                                              "delay_seconds": delay})
                        time.sleep(delay)
                        continue
                    raise RpcError(f"{method} RPC error {error.get('code')}: {error.get('message')}")
                if "result" not in body:
                    raise RpcError(f"{method} response is missing result")
                return body["result"]
            except urllib.error.HTTPError as exc:
                # Authentication, authorization and malformed requests will not
                # improve on retry; 429 and server errors may be transient.
                if exc.code not in (429, 500, 502, 503, 504) or attempt >= self.max_retries:
                    raise RpcError(f"{method} HTTP {exc.code}") from exc
                retry_after = exc.headers.get("Retry-After")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt >= self.max_retries:
                    # Avoid echoing the configured endpoint: it may contain credentials.
                    raise RpcError(f"{method} failed after {attempt + 1} attempt(s) ({type(exc).__name__})") from exc
                retry_after = None
            delay = min(30.0, float(retry_after) if retry_after and retry_after.isdigit()
                        else (0.25 * (2 ** attempt) + random.uniform(0, 0.2)))
            logger.warning("RPC retry", extra={"method": method, "attempt": attempt + 1, "delay_seconds": delay})
            time.sleep(delay)
        raise AssertionError("unreachable")

    @staticmethod
    def quantity(value: str) -> int:
        if not isinstance(value, str) or not value.startswith("0x"):
            raise RpcError(f"Invalid Ethereum quantity: {value!r}")
        return int(value, 16)

    def chain_id(self) -> int:
        return self.quantity(self.call("eth_chainId"))

    def block_number(self) -> int:
        return self.quantity(self.call("eth_blockNumber"))

    def block(self, number: int) -> dict[str, Any] | None:
        return self.call("eth_getBlockByNumber", [hex(number), True])

    def receipt(self, tx_hash: str) -> dict[str, Any] | None:
        return self.call("eth_getTransactionReceipt", [tx_hash])

    def logs(self, start: int, end: int) -> list[dict[str, Any]]:
        return self.call("eth_getLogs", [{"fromBlock": hex(start), "toBlock": hex(end)}])
