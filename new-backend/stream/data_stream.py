"""Data stream module — copy of the existing data_stream protocol.

Provides SSE formatting, DataStreamBuilder, and build_data_stream
for the Vercel AI SDK data stream protocol.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse


def format_sse_data(payload: dict[str, Any]) -> str:
    """Format a payload as a Server-Sent Event data message."""
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


def format_sse_done() -> str:
    """Format the stream termination marker."""
    return "data: [DONE]\n\n"


def patch_response_headers(response: StreamingResponse, protocol: str | None = "data") -> StreamingResponse:
    """Add required headers for AI SDK data stream protocol."""
    response.headers["x-vercel-ai-ui-message-stream"] = "v1"
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["Connection"] = "keep-alive"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Content-Type"] = "text/event-stream"
    if protocol:
        response.headers.setdefault("x-vercel-ai-protocol", protocol)
    return response


# ============================================================================
# Stream Part Builders
# ============================================================================

def create_message_start_part(message_id: str) -> dict[str, Any]:
    return {"type": "start", "messageId": message_id}

def create_text_start_part(text_id: str) -> dict[str, Any]:
    return {"type": "text-start", "id": text_id}

def create_text_delta_part(text_id: str, delta: str) -> dict[str, Any]:
    return {"type": "text-delta", "id": text_id, "delta": delta}

def create_text_end_part(text_id: str) -> dict[str, Any]:
    return {"type": "text-end", "id": text_id}

def create_reasoning_start_part(reasoning_id: str) -> dict[str, Any]:
    return {"type": "reasoning-start", "id": reasoning_id}

def create_reasoning_delta_part(reasoning_id: str, delta: str) -> dict[str, Any]:
    return {"type": "reasoning-delta", "id": reasoning_id, "delta": delta}

def create_reasoning_end_part(reasoning_id: str) -> dict[str, Any]:
    return {"type": "reasoning-end", "id": reasoning_id}

def create_source_url_part(source_id: str, url: str) -> dict[str, Any]:
    return {"type": "source-url", "sourceId": source_id, "url": url}

def create_source_document_part(source_id: str, media_type: str, title: str | None = None) -> dict[str, Any]:
    part: dict[str, Any] = {"type": "source-document", "sourceId": source_id, "mediaType": media_type}
    if title:
        part["title"] = title
    return part

def create_file_part(url: str, media_type: str) -> dict[str, Any]:
    return {"type": "file", "url": url, "mediaType": media_type}

def create_data_part(data_type: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"type": f"data-{data_type}", "data": data}

def create_error_part(error_text: str) -> dict[str, Any]:
    return {"type": "error", "errorText": error_text}

def create_tool_input_start_part(tool_call_id: str, tool_name: str) -> dict[str, Any]:
    return {"type": "tool-input-start", "toolCallId": tool_call_id, "toolName": tool_name}

def create_tool_input_delta_part(tool_call_id: str, input_text_delta: str) -> dict[str, Any]:
    return {"type": "tool-input-delta", "toolCallId": tool_call_id, "inputTextDelta": input_text_delta}

def create_tool_input_available_part(tool_call_id: str, tool_name: str, input: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool-input-available", "toolCallId": tool_call_id, "toolName": tool_name, "input": input}

def create_tool_output_available_part(tool_call_id: str, output: dict[str, Any] | str) -> dict[str, Any]:
    return {"type": "tool-output-available", "toolCallId": tool_call_id, "output": output}

def create_start_step_part() -> dict[str, Any]:
    return {"type": "start-step"}

def create_finish_step_part() -> dict[str, Any]:
    return {"type": "finish-step"}

def create_finish_part(message_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    if message_metadata:
        return {"type": "finish", "messageMetadata": message_metadata}
    return {"type": "finish"}

def create_abort_part(reason: str = "stream aborted") -> dict[str, Any]:
    return {"type": "abort", "reason": reason}


# ============================================================================
# Stream ID Generators
# ============================================================================

def generate_message_id() -> str:
    return f"msg-{uuid.uuid4().hex}"

def generate_text_id() -> str:
    return f"text-{uuid.uuid4().hex[:24]}"

def generate_reasoning_id() -> str:
    return f"reasoning-{uuid.uuid4().hex[:24]}"

def generate_tool_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:32]}"


# ============================================================================
# Data Stream Builder Class
# ============================================================================

class DataStreamBuilder:
    """Helper class to build data stream parts with proper ID management."""

    def __init__(self, message_id: str | None = None):
        self.message_id = message_id or generate_message_id()
        self._text_counter = 0
        self._reasoning_counter = 0

    def new_text_id(self) -> str:
        self._text_counter += 1
        return f"text-{self._text_counter}-{uuid.uuid4().hex[:16]}"

    def new_reasoning_id(self) -> str:
        self._reasoning_counter += 1
        return f"reasoning-{self._reasoning_counter}-{uuid.uuid4().hex[:16]}"

    @staticmethod
    def format(part: dict[str, Any]) -> str:
        return format_sse_data(part)

    @staticmethod
    def format_done() -> str:
        return format_sse_done()

    def create_message_start(self) -> dict[str, Any]:
        return create_message_start_part(self.message_id)

    def create_text_start(self, text_id: str) -> dict[str, Any]:
        return create_text_start_part(text_id)

    def create_text_delta(self, text_id: str, delta: str) -> dict[str, Any]:
        return create_text_delta_part(text_id, delta)

    def create_text_end(self, text_id: str) -> dict[str, Any]:
        return create_text_end_part(text_id)

    def create_reasoning_start(self, reasoning_id: str) -> dict[str, Any]:
        return create_reasoning_start_part(reasoning_id)

    def create_reasoning_delta(self, reasoning_id: str, delta: str) -> dict[str, Any]:
        return create_reasoning_delta_part(reasoning_id, delta)

    def create_reasoning_end(self, reasoning_id: str) -> dict[str, Any]:
        return create_reasoning_end_part(reasoning_id)

    @staticmethod
    def create_source_url(source_id: str, url: str) -> dict[str, Any]:
        return create_source_url_part(source_id, url)

    @staticmethod
    def create_source_document(source_id: str, media_type: str, title: str | None = None) -> dict[str, Any]:
        return create_source_document_part(source_id, media_type, title)

    @staticmethod
    def create_file(url: str, media_type: str) -> dict[str, Any]:
        return create_file_part(url, media_type)

    @staticmethod
    def create_data(data_type: str, data: dict[str, Any]) -> dict[str, Any]:
        return create_data_part(data_type, data)

    @staticmethod
    def create_error(error_text: str) -> dict[str, Any]:
        return create_error_part(error_text)

    @staticmethod
    def create_tool_input_start(tool_call_id: str, tool_name: str) -> dict[str, Any]:
        return create_tool_input_start_part(tool_call_id, tool_name)

    @staticmethod
    def create_tool_input_delta(tool_call_id: str, input_text_delta: str) -> dict[str, Any]:
        return create_tool_input_delta_part(tool_call_id, input_text_delta)

    @staticmethod
    def create_tool_input_available(tool_call_id: str, tool_name: str, input: dict[str, Any]) -> dict[str, Any]:
        return create_tool_input_available_part(tool_call_id, tool_name, input)

    @staticmethod
    def create_tool_output_available(tool_call_id: str, output: dict[str, Any] | str) -> dict[str, Any]:
        return create_tool_output_available_part(tool_call_id, output)

    @staticmethod
    def create_start_step() -> dict[str, Any]:
        return create_start_step_part()

    @staticmethod
    def create_finish_step() -> dict[str, Any]:
        return create_finish_step_part()

    @staticmethod
    def create_finish(message_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return create_finish_part(message_metadata)

    @staticmethod
    def create_abort(reason: str = "stream aborted") -> dict[str, Any]:
        return create_abort_part(reason)


# ============================================================================
# Data Stream Iterator
# ============================================================================

async def build_data_stream(
    request: Request,
    model_events: AsyncIterator[dict[str, Any]],
    ping_interval_seconds: float,
) -> AsyncIterator[str]:
    """Build a data stream from model events.

    Handles event types: delta, reasoning-delta, reasoning-end,
    tool-input-start, tool-input-delta, tool-input-available,
    tool-output, tool-complete, source-url, source-document,
    file, data, error, start-step, finish-step, usage.
    """
    builder = DataStreamBuilder()
    text_stream_id = builder.new_text_id()
    reasoning_stream_id: str | None = None
    current_tool_call_id: str | None = None
    finish_metadata: dict[str, Any] = {}
    active_tool_calls: dict[str, str] = {}

    yield builder.format(builder.create_message_start())
    yield builder.format(builder.create_text_start(text_stream_id))

    iterator = model_events.__aiter__()

    while True:
        if await request.is_disconnected():
            yield builder.format(builder.create_abort("client disconnected"))
            return

        try:
            event = await asyncio.wait_for(iterator.__anext__(), timeout=ping_interval_seconds)
        except asyncio.TimeoutError:
            yield ": ping\n\n"
            continue
        except StopAsyncIteration:
            break

        event_type = event.get("type")

        if event_type == "delta":
            delta = event.get("delta")
            if isinstance(delta, str) and delta:
                yield builder.format(builder.create_text_delta(text_stream_id, delta))

        elif event_type == "reasoning-delta":
            delta = event.get("delta")
            if isinstance(delta, str) and delta:
                if reasoning_stream_id is None:
                    yield builder.format(builder.create_text_end(text_stream_id))
                    reasoning_stream_id = builder.new_reasoning_id()
                    yield builder.format(builder.create_reasoning_start(reasoning_stream_id))
                yield builder.format(builder.create_reasoning_delta(reasoning_stream_id, delta))

        elif event_type == "reasoning-end":
            if reasoning_stream_id is not None:
                yield builder.format(builder.create_reasoning_end(reasoning_stream_id))
                reasoning_stream_id = None
                text_stream_id = builder.new_text_id()
                yield builder.format(builder.create_text_start(text_stream_id))

        elif event_type == "tool-input-start":
            tool_name = event.get("toolName", "unknown")
            tool_call_id = event.get("toolCallId") or generate_tool_call_id()
            active_tool_calls[tool_call_id] = tool_name
            current_tool_call_id = tool_call_id
            yield builder.format(builder.create_text_end(text_stream_id))
            yield builder.format(builder.create_tool_input_start(tool_call_id, tool_name))

        elif event_type == "tool-input-delta":
            tool_call_id = event.get("toolCallId") or current_tool_call_id
            if tool_call_id:
                delta = event.get("delta", "")
                yield builder.format(builder.create_tool_input_delta(tool_call_id, delta))

        elif event_type == "tool-input-available":
            tool_call_id = event.get("toolCallId") or current_tool_call_id
            tool_name = event.get("toolName") or (active_tool_calls.get(tool_call_id, "unknown") if tool_call_id else "unknown")
            tool_input = event.get("input", {})
            if tool_call_id:
                yield builder.format(builder.create_tool_input_available(tool_call_id, tool_name, tool_input))
                current_tool_call_id = None

        elif event_type == "tool-output":
            tool_call_id = event.get("toolCallId")
            output = event.get("output")
            if tool_call_id and output is not None:
                yield builder.format(builder.create_tool_output_available(tool_call_id, output))
                text_stream_id = builder.new_text_id()
                yield builder.format(builder.create_text_start(text_stream_id))

        elif event_type == "tool-complete":
            text_stream_id = builder.new_text_id()
            yield builder.format(builder.create_text_start(text_stream_id))

        elif event_type == "source-url":
            yield builder.format(builder.create_source_url(event.get("sourceId", ""), event.get("url", "")))

        elif event_type == "source-document":
            yield builder.format(builder.create_source_document(event.get("sourceId", ""), event.get("mediaType", "file"), event.get("title")))

        elif event_type == "file":
            yield builder.format(builder.create_file(event.get("url", ""), event.get("mediaType", "application/octet-stream")))

        elif event_type == "data":
            yield builder.format(builder.create_data(event.get("dataType", "custom"), event.get("data", {})))

        elif event_type == "error":
            yield builder.format(builder.create_error(event.get("error", "An error occurred")))

        elif event_type == "start-step":
            yield builder.format(builder.create_start_step())

        elif event_type == "finish-step":
            yield builder.format(builder.create_finish_step())

        elif event_type == "usage":
            usage = event.get("usage")
            if isinstance(usage, dict) and usage:
                finish_metadata["usage"] = usage

    if reasoning_stream_id is not None:
        yield builder.format(builder.create_reasoning_end(reasoning_stream_id))

    yield builder.format(builder.create_text_end(text_stream_id))

    if finish_metadata:
        yield builder.format(builder.create_finish(finish_metadata))
    else:
        yield builder.format(builder.create_finish())

    yield builder.format_done()
