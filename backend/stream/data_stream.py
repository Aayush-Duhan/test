from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse


def format_sse_data(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


def patch_response_headers(response: StreamingResponse, protocol: str | None = "data") -> StreamingResponse:
    response.headers["x-vercel-ai-ui-message-stream"] = "v1"
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["Connection"] = "keep-alive"
    response.headers["X-Accel-Buffering"] = "no"

    if protocol:
        response.headers.setdefault("x-vercel-ai-protocol", protocol)

    return response


async def build_data_stream(
    request: Request,
    model_events: AsyncIterator[dict[str, Any]],
    ping_interval_seconds: float,
) -> AsyncIterator[str]:
    message_id = f"msg-{uuid.uuid4().hex}"
    text_stream_id = "text-1"
    finish_metadata: dict[str, Any] = {}

    yield format_sse_data({"type": "start", "messageId": message_id})
    yield format_sse_data({"type": "text-start", "id": text_stream_id})

    iterator = model_events.__aiter__()

    while True:
        if await request.is_disconnected():
            return

        try:
            event = await asyncio.wait_for(iterator.__anext__(), timeout=ping_interval_seconds)
        except TimeoutError:
            yield ": ping\n\n"
            continue
        except StopAsyncIteration:
            break

        event_type = event.get("type")

        if event_type == "delta":
            delta = event.get("delta")

            if isinstance(delta, str) and delta:
                yield format_sse_data({"type": "text-delta", "id": text_stream_id, "delta": delta})

        if event_type == "usage":
            usage = event.get("usage")

            if isinstance(usage, dict) and usage:
                finish_metadata["usage"] = usage

    yield format_sse_data({"type": "text-end", "id": text_stream_id})

    if finish_metadata:
        yield format_sse_data({"type": "finish", "messageMetadata": finish_metadata})
    else:
        yield format_sse_data({"type": "finish"})

    yield "data: [DONE]\n\n"
