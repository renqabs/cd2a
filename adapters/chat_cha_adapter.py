import asyncio
import json
import re
import time
import uuid

import httpx
from fastapi import Request

from adapters.base_adapter import BaseAdapter


class ChatChaAdapter(BaseAdapter):
    def __init__(self, password, proxy, api_proxy):
        self.password = password
        self.last_time = None
        if proxy:
            self.proxies = {
                'http://': proxy,
                'https://': proxy,
            }
        else:
            self.proxies = None

        if api_proxy:
            self.api_base = api_proxy
        else:
            self.api_base = 'https://api.chandler.bet'

    @staticmethod
    def convert_messages_to_prompt(messages):
        content_array = []
        for message in messages:
            content = message["content"]
            content_array.append(content)
        return "\n---------\n".join(content_array)

    def convert_openai_data(self, openai_params):
        # openAI_models = ["gpt-3.5-turbo", "gpt-4-1106-preview", "gpt-4-pro-max"]

        messages = openai_params["messages"]
        temperature = openai_params.get("temperature", 1)
        top_p = openai_params.get("top_p", 1)
        text = self.convert_messages_to_prompt(messages)
        model: str = openai_params["model"]

        return {
            "uid": "yyds.edu.com",
            "prompt": text,
            "model_name": "gpt-4o",
            "request_timeout": 30,
            "global_timeout": 100,
            "max_retries": 1,
            "attachment_list": [],
            "parent_message_id": "",
            "conversation_id": "",
            "answer_again": False,
            "aireply": "",
            # "timestamp": 1716043989610,
            "status": "",
            "app_name": "crina",
            "web_url": "https://api.chandler.bet"
        }

    def convert_google_data(self, openai_params, model):
        # google_models = ["chat-bison", "text-bison", "codechat-bison"]

        messages = openai_params["messages"]
        temperature = openai_params.get("temperature", 1)
        text = self.convert_messages_to_prompt(messages)

        return {
            'sender': 'User',
            'text': text,
            'current': True,
            'isCreatedByUser': True,
            'parentMessageId': '00000000-0000-0000-0000-000000000000',
            'conversationId': None,
            'messageId': str(uuid.uuid4()),
            'error': False,
            'generation': '',
            'responseMessageId': None,
            'overrideParentMessageId': None,
            'endpoint': 'google',
            'model': model,
            'modelLabel': None,
            'promptPrefix': None,
            'temperature': temperature,
            'maxOutputTokens': 1024,
            'topP': 0.95,
            'topK': 40,
            'token': None,
            'isContinued': False,
            'isLimited': False,
        }

    async def chat(self, request: Request):
        openai_params = await request.json()
        headers = request.headers
        stream = openai_params.get("stream")
        model = openai_params.get("model")
        google_model_prefix = "google-"
        if model.startswith(google_model_prefix):
            google_model = model.removeprefix(google_model_prefix)
            json_data = self.convert_google_data(openai_params, google_model)
        else:
            json_data = self.convert_openai_data(openai_params)
        print(json_data)

        api_key = self.get_request_api_key(headers)
        if not api_key:
            raise Exception(f"Error: 密钥无效")

        headers = {
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Origin': 'https://mychandler.bet',
            'Referer': 'https://api.chandler.bet/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'accept': '*/*',
        }

        api_url = f'{self.api_base}/api/chat/Chat'
        last_text = ""
        last_incomplete_raw_text = ""
        last_time = time.time()
        async with httpx.AsyncClient(http2=False, timeout=120.0, verify=False, proxies=self.proxies) as client:
            async with client.stream(
                    method="POST",
                    url=api_url,
                    headers=headers,
                    json=json_data
            ) as response:
                if response.is_error:
                    raise Exception(f"Error: {response.status_code}")

                # print(response.headers)
                if stream:
                    yield self.to_openai_response_stream_begin(model=model)
                async for raw_data in response.aiter_text():
                    if raw_data:
                        # print('raw_data: ' + raw_data)
                        try:
                            if last_incomplete_raw_text != "":
                                text = self.take_text(last_incomplete_raw_text + raw_data)
                            else:
                                text = self.take_text(raw_data)
                        except json.JSONDecodeError as ex:
                            print("incomplete!!! ", ex)
                            last_incomplete_raw_text += raw_data
                            # print("last_incomplete_raw_text: " + last_incomplete_raw_text)
                            continue

                        last_incomplete_raw_text = ""
                        if text == "":
                            continue
                        # print('take text: ' + text)

                        # new_text = text[len(last_text):]
                        last_text = last_text + text
                        if stream:
                            yield self.to_openai_response_stream(model=model, content=text)
                        await self.rate_limit_sleep_async(last_time)
                        last_time = time.time()
                if stream:
                    await asyncio.sleep(1)
                    yield self.to_openai_response_stream_end(model=model)
                    yield "[DONE]"
                else:
                    yield self.to_openai_response(model=model, content=last_text)


    @staticmethod
    def take_text(raw_data: str) -> str:
        text = ""
        lines = raw_data.split("\n\n")

        for line in lines:
            if not line:
                continue

            # print(line)
            if line.startswith("event:message"):
                json_data = json.loads(line.lstrip("event:message\ndata:"))

                if json_data.get("delta"):
                    text = json_data["delta"]

        return text
