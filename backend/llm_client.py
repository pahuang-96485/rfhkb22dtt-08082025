# llm_client.py

import os
import json
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()


# OpenAI setup
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def call_llm_json(system_prompt: str, messages: list[dict]) -> dict:
    try:
        response = client.chat.completions.create(
            model="gpt-4-1106-preview",
            messages=[
                {"role": "system", "content": system_prompt},
                *messages
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "extract_intent",
                        "description": "Extracts structured user intent and arguments.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "action": {"type": "string"},
                                "arguments": {
                                    "type": "object",
                                    "properties": {
                                        "slot_index": {"type": "integer"},
                                        "description": {"type": "string"},
                                        "preferred_date": {"type": "string"},
                                        "preferred_time": {"type": "string"},
                                        "target": {"type": "string"},
                                        "target_date": {"type": "string"},
                                        "from_date": {"type": "string"},
                                        "to_date": {"type": "string"},
                                        "start_date": {"type": "string"},
                                        "days_ahead": {"type": "integer"},
                                        "slot_time": {"type": "string"},
                                        "type": {"type": "string"},  # for general_chat
                                        "time_pref": {"type": "string"}
                                    },
                                    "required": [] 
                                }
                            },
                            "required": ["action", "arguments"]
                        }
                    }
                }
            ],
            tool_choice={"type": "function", "function": {"name": "extract_intent"}},
            temperature=0
        )

        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            args_json_str = tool_calls[0].function.arguments
            return json.loads(args_json_str)

        print("[WARN] No tool_calls returned")
        return {}
    except Exception as e:
        print("[LLM ERROR] call_llm_json failed:", e)
        return {}



def call_llm(system_prompt: str, messages: list[dict]) -> str:

    try:
        response = client.chat.completions.create(
            model="gpt-4-1106-preview",
            messages=[
                {"role": "system", "content": system_prompt},
                *messages
            ],
            temperature=0.5
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print("[LLM ERROR] call_llm failed:", e)
        return ""


