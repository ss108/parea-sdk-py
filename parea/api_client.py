from typing import Any, Callable, Optional

import asyncio
import json
import time
from collections.abc import AsyncIterable
from functools import wraps

import httpx

MAX_RETRIES = 5
BACKOFF_FACTOR = 0.5


def retry_on_502(func: Callable[..., Any]) -> Callable[..., Any]:
    if asyncio.iscoroutinefunction(func):

        @wraps(func)
        async def wrapper(*args, **kwargs):
            for retry in range(MAX_RETRIES):
                try:
                    return await func(*args, **kwargs)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code != 502 or retry == MAX_RETRIES - 1:
                        raise
                    await asyncio.sleep(BACKOFF_FACTOR * (2**retry))

        return wrapper
    else:

        @wraps(func)
        def wrapper(*args, **kwargs):
            for retry in range(MAX_RETRIES):
                try:
                    return func(*args, **kwargs)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code != 502 or retry == MAX_RETRIES - 1:
                        raise
                    time.sleep(BACKOFF_FACTOR * (2**retry))

        return wrapper


class HTTPClient:
    _instance = None
    base_url = "http://localhost:8000/api/parea/v1"  # "https://parea-ai-backend-us-9ac16cdbc7a7b006.onporter.run/api/parea/v1"
    api_key = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.sync_client = httpx.Client(base_url=cls.base_url, timeout=60 * 3.0)
            cls._instance.async_client = httpx.AsyncClient(base_url=cls.base_url, timeout=60 * 3.0)
        return cls._instance

    def set_api_key(self, api_key: str):
        self.api_key = api_key

    @retry_on_502
    def request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        api_key: Optional[str] = None,
    ) -> httpx.Response:
        """
        Makes an HTTP request to the specified endpoint.
        """
        headers = {"x-api-key": self.api_key} if self.api_key else api_key
        try:
            response = self.sync_client.request(method, endpoint, json=data, headers=headers, params=params)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error {e.response.status_code} for {e.request.url}: {e.response.text}")
            raise

    @retry_on_502
    async def request_async(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        api_key: Optional[str] = None,
    ) -> httpx.Response:
        """
        Makes an asynchronous HTTP request to the specified endpoint.
        """
        headers = {"x-api-key": self.api_key} if self.api_key else api_key
        try:
            response = await self.async_client.request(method, endpoint, json=data, headers=headers, params=params)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error {e.response.status_code} for {e.request.url}: {e.response.text}")
            raise

    @retry_on_502
    def stream_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        api_key: Optional[str] = None,
        chunk_size: Optional[int] = None,
    ):
        """
        Makes a streaming HTTP request to the specified endpoint, yielding chunks of data.
        """
        headers = {"x-api-key": self.api_key} if self.api_key else api_key
        try:
            with self.sync_client.stream(method, endpoint, json=data, headers=headers, params=params, timeout=None) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(chunk_size):
                    yield parse_event_data(chunk)
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error {e.response.status_code} for {e.request.url}: {e.response.text}")
            raise

    @retry_on_502
    async def stream_request_async(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        api_key: Optional[str] = None,
        chunk_size: Optional[int] = None,
    ) -> AsyncIterable[bytes]:
        """
        Makes an asynchronous streaming HTTP request to the specified endpoint, yielding chunks of data.
        """
        headers = {"x-api-key": self.api_key} if self.api_key else api_key
        try:
            async with self.async_client.stream(method, endpoint, json=data, headers=headers, params=params, timeout=None) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size):
                    yield parse_event_data(chunk)
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error {e.response.status_code} for {e.request.url}: {e.response.text}")
            raise

    def close(self):
        """
        Closes the synchronous HTTP client.
        """
        self.sync_client.close()

    async def close_async(self):
        """
        Closes the asynchronous HTTP client.
        """
        await self.async_client.aclose()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_async()


def parse_event_data(byte_data):
    # Decode bytes to string
    decoded_data = byte_data.decode("utf-8")

    # Find the JSON part of the data
    try:
        # Assuming the format is consistent, splitting by '\n' and taking the part with 'data: '
        json_str = [line for line in decoded_data.split("\r\n") if line.startswith("data:")][0]
        # Removing 'data: ' to isolate the JSON string
        json_str = json_str.replace("data: ", "")
        if json_str.startswith("ID_START"):
            return ""
        # Convert JSON string to Python dictionary
        data_dict = json.loads(json_str)
        return data_dict["chunk"]
    except Exception as e:
        print(f"Error parsing event data: {e}")
        return None
