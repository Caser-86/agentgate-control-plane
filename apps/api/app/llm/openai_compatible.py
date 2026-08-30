import json
from typing import Any, cast

from openai import AsyncOpenAI

from app.llm.base import ModelProtocolError, ModelProviderError, ModelTurn, ToolCall


class OpenAICompatibleProvider:
    provider_name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    async def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> ModelTurn:
        try:
            client = cast(Any, self.client)
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
            )
        except Exception as exc:
            raise ModelProviderError("model provider request failed") from exc

        try:
            message = response.choices[0].message
            text = message.content if isinstance(message.content, str) else None
            calls: list[ToolCall] = []
            serialized_calls: list[dict[str, object]] = []
            for raw_call in message.tool_calls or []:
                arguments_raw = raw_call.function.arguments
                try:
                    arguments = json.loads(arguments_raw)
                except (TypeError, json.JSONDecodeError) as exc:
                    raise ModelProtocolError("tool arguments are not valid JSON") from exc
                if not isinstance(arguments, dict):
                    raise ModelProtocolError("tool arguments must be a JSON object")
                call = ToolCall(raw_call.id, raw_call.function.name, arguments)
                calls.append(call)
                serialized_calls.append(
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(arguments, ensure_ascii=False),
                        },
                    }
                )
            assistant_message: dict[str, Any] = {"role": "assistant", "content": text}
            if serialized_calls:
                assistant_message["tool_calls"] = serialized_calls
            return ModelTurn(assistant_message, text, tuple(calls))
        except ModelProtocolError:
            raise
        except (IndexError, AttributeError, TypeError) as exc:
            raise ModelProtocolError("model response did not match the tool protocol") from exc
