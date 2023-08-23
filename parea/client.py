import uuid

from attrs import asdict, define, field

from parea.api_client import HTTPClient
from parea.parea_logger import parea_logger
from parea.schemas.models import Completion, CompletionResponse, FeedbackRequest, UseDeployedPrompt, UseDeployedPromptResponse
from parea.trace_utils.trace import trace_context

COMPLETION_ENDPOINT = "/completion"
DEPLOYED_PROMPT_ENDPOINT = "/deployed-prompt"
RECORD_FEEDBACK_ENDPOINT = "/feedback"


@define
class Parea:
    api_key: str = field(init=True, default="")
    _client: HTTPClient = field(init=False, default=HTTPClient())

    def __attrs_post_init__(self):
        self._client.set_api_key(self.api_key)
        parea_logger.set_client(self._client)

    def completion(self, data: Completion) -> CompletionResponse:
        data.inference_id = trace_context.get()[-1]
        r = self._client.request(
            "POST",
            COMPLETION_ENDPOINT,
            data=asdict(data),
        )
        return CompletionResponse(**r.json())

    async def acompletion(self, data: Completion) -> CompletionResponse:
        trace_id = trace_context.get()[-1]
        data.trace_id = trace_id
        r = await self._client.request_async(
            "POST",
            COMPLETION_ENDPOINT,
            data=asdict(data),
        )
        return CompletionResponse(**r.json())

    def get_prompt(self, data: UseDeployedPrompt) -> UseDeployedPromptResponse:
        r = self._client.request(
            "POST",
            DEPLOYED_PROMPT_ENDPOINT,
            data=asdict(data),
        )
        return UseDeployedPromptResponse(**r.json())

    async def aget_prompt(self, data: UseDeployedPrompt) -> UseDeployedPromptResponse:
        r = await self._client.request_async(
            "POST",
            DEPLOYED_PROMPT_ENDPOINT,
            data=asdict(data),
        )
        return UseDeployedPromptResponse(**r.json())

    def record_feedback(self, data: FeedbackRequest) -> None:
        self._client.request(
            "POST",
            RECORD_FEEDBACK_ENDPOINT,
            data=asdict(data),
        )

    async def arecord_feedback(self, data: FeedbackRequest) -> None:
        await self._client.request_async(
            "POST",
            RECORD_FEEDBACK_ENDPOINT,
            data=asdict(data),
        )

    # def record_log(self, data: LogRequest) -> None:
    #     print(f"Logging to database: {data}")
    #     db_entries.append(data)
    #     # self._client.request(
    #     #     "POST",
    #     #     LOG_ENDPOINT,
    #     #     data=asdict(data),
    #     # )
    #
    # async def arecord_log(self, data: LogRequest) -> None:
    #     print(f"Logging to database: {data}")
    #     db_entries.append(data)
    #     # await self._client.request_async(
    #     #     "POST",
    #     #     LOG_ENDPOINT,
    #     #     data=asdict(data),
    #     # )


def gen_trace_id() -> str:
    """Generate a unique trace id for each chain of requests"""
    return str(uuid.uuid4())
