from attrs import asdict, define, field

from parea.api_client import HTTPClient
from parea.schemas.models import TraceLog

LOG_ENDPOINT = "/trace_log"


@define
class PareaLogger:
    _client: HTTPClient = field(init=False)

    def set_client(self, client: HTTPClient) -> None:
        self._client = client

    def record_log(self, data: TraceLog) -> None:
        print(f"Logging to database: {data}")
        self._client.request(
            "POST",
            LOG_ENDPOINT,
            data=asdict(data),
        )


parea_logger = PareaLogger()
