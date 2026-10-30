import json
import os
import unittest
from unittest.mock import patch

from spider_agent.advisor import advise


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return json.dumps(self.payload).encode()


class AdvisorTest(unittest.TestCase):
    def test_tool_call_then_model_suggestion(self):
        responses = [
            Response({"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "get_trial_summary", "arguments": "{}"}}]}}], "usage": {"prompt_tokens": 20, "completion_tokens": 5}}),
            Response({"choices": [{"message": {"role": "assistant", "content": "检查变更公告栏目"}}], "usage": {"prompt_tokens": 40, "completion_tokens": 8}}),
        ]
        events = []
        with patch.dict(os.environ, {"LLM_BASE_URL": "https://example.test/v1", "LLM_API_KEY": "secret", "LLM_MODEL": "test"}), patch("spider_agent.advisor.urlopen", side_effect=responses):
            result = advise([{"name": "变更公告", "status": "failed"}], lambda *a, **kw: events.append((a, kw)))
        self.assertEqual(result, "检查变更公告栏目")
        self.assertEqual([e[0][0] for e in events], ["model_call", "agent_tool", "model_call"])
        self.assertNotIn("secret", repr(events))


if __name__ == "__main__":
    unittest.main()
