from typing import Any, Dict, List, Optional

import asyncio
import contextvars
import inspect
import json
import logging
import threading
import time
from collections import ChainMap
from datetime import datetime
from functools import wraps
from uuid import uuid4

from attrs import asdict

from parea.parea_logger import parea_logger
from parea.schemas.models import CompletionResponse, TraceLog

logger = logging.getLogger()


# Context variable to maintain the current trace context stack
trace_context = contextvars.ContextVar("trace_context", default=[])

# A dictionary to hold trace data for each trace
trace_data = contextvars.ContextVar("trace_data", default={})


def to_date_and_time_string(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S %Z").strip()


def merge(old, new):
    if isinstance(old, dict) and isinstance(new, dict):
        return dict(ChainMap(new, old))
    if isinstance(old, list) and isinstance(new, list):
        return old + new
    return new


def trace_insert(data: dict[str, Any]):
    current_trace_id = trace_context.get()[-1]
    current_trace_data: TraceLog = trace_data.get()[current_trace_id]

    for key, new_value in data.items():
        print(key, new_value)
        existing_value = current_trace_data.__getattribute__(key)
        current_trace_data.__setattr__(key, merge(existing_value, new_value) if existing_value else new_value)


def traceable(
    name: Optional[str] = None,
    tags: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
    target: Optional[str] = None,
    end_user_identifier: Optional[str] = None,
):
    def init_trace(func_name, args, kwargs, func):
        start_time = time.time()
        trace_id = str(uuid4())
        trace_context.get().append(trace_id)

        sig = inspect.signature(func)
        parameters = sig.parameters

        inputs = {k: v for k, v in zip(parameters.keys(), args)}
        inputs.update(kwargs)

        trace_data.get()[trace_id] = TraceLog(
            trace_id=trace_id,
            start_timestamp=to_date_and_time_string(start_time),
            trace_name=name or func_name,
            end_user_identifier=end_user_identifier,
            metadata=metadata,
            target=target,
            tags=tags,
            inputs=inputs,
        )
        parent_trace_id = trace_context.get()[-2] if len(trace_context.get()) > 1 else None
        if parent_trace_id:
            trace_data.get()[parent_trace_id].children.append(trace_id)

        return trace_id

    def cleanup_trace(trace_id):
        logging_thread = threading.Thread(
            target=parea_logger.record_log,
            kwargs={"data": trace_data.get()[trace_id]},
        )
        logging_thread.start()
        trace_context.get().pop()

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            trace_id = init_trace(func.__name__, args, kwargs, func)
            try:
                result = await func(*args, **kwargs)
                end_time = time.time()
                trace_data.get()[trace_id].end_timestamp = to_date_and_time_string(end_time)
                output = asdict(result) if isinstance(result, CompletionResponse) else result
                trace_data.get()[trace_id].output = json.dumps(output)
            except Exception as e:
                logger.exception(f"Error occurred in function {func.__name__}")
                raise e
            finally:
                cleanup_trace(trace_id)
            return result

        @wraps(func)
        def wrapper(*args, **kwargs):
            trace_id = init_trace(func.__name__, args, kwargs, func)
            try:
                result = func(*args, **kwargs)
                end_time = time.time()
                trace_data.get()[trace_id].end_timestamp = to_date_and_time_string(end_time)
                output = asdict(result) if isinstance(result, CompletionResponse) else result
                trace_data.get()[trace_id].output = json.dumps(output)
            except Exception as e:
                logger.exception(f"Error occurred in function {func.__name__}")
                raise e
            finally:
                cleanup_trace(trace_id)
            return result

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper

    if callable(name):
        func = name
        name = None
        return decorator(func)

    return decorator


@traceable
def run_child1(x):
    return 1 + x


@traceable
def run_child2(y):
    return run_grand_child1(y) + y


@traceable
def run_grand_child1(z):
    # Add metadata to the trace data for this function
    trace_insert({"metadata": {"internal": True, "tokens": 3}})
    return 3 * z


@traceable
def parent(x, y):
    answer1 = run_child1(x)
    answer2 = run_child2(y)
    return (answer1 + answer2) / 2


@traceable
def parent2(x, y):
    return (x + y) / 2


@traceable
async def arun_child1(x):
    await asyncio.sleep(1)  # simulate IO-bound operation
    return 1 + x


@traceable
async def arun_child2(y):
    res = await arun_grand_child1(y)
    return res + y


@traceable
async def arun_grand_child1(z):
    await asyncio.sleep(1)  # simulate IO-bound operation
    current_trace_id = trace_context.get()[-1]
    trace_data.get()[current_trace_id]["metadata"] = {
        "internal": True,
        "tokens": 3,
    }
    return 3 * z


@traceable
async def aparent(x, y):
    answer1 = await arun_child1(x)
    answer2 = await arun_child2(y)
    return (answer1 + answer2) / 2


@traceable
async def aparent2(x, y):
    return (x + y) / 2
