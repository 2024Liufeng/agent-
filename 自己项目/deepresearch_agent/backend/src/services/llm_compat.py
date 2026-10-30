"""把反代返回的 DeepSeek 工具标记转换成 HelloAgents 0.2.9 的文本协议。"""

import json
import logging
import re

from hello_agents import HelloAgentsLLM

logger = logging.getLogger(__name__)
CALL_BLOCK = re.compile(r"<[|｜]+DSML[|｜]+\s+calls\b[^>]*>.*?</[|｜]+DSML[|｜]+\s+calls\s*>", re.DOTALL)
INVOKE = re.compile(r'''<[|｜]+DSML[|｜]+\s+invoke\s+name=["']([^:<>'"]+):''')


class ToolProtocolError(ValueError):
    """模型输出的工具调用格式无法安全解析。"""


def normalize_tool_protocol(text: str) -> str:
    """仅转换已确认的 name=工具名:JSON 格式；无法识别时明确报错。"""
    def replace(block):
        calls = []
        for match in INVOKE.finditer(block.group()):
            body = block.group()[match.end():].lstrip()
            try:
                parameters, _ = json.JSONDecoder().raw_decode(body)
            except ValueError as exc:
                # 只记录格式特征，不记录模型输出或工具参数正文。
                first = body[:1]
                shape = first if first in ('{', '[', '"') else ('empty' if not first else 'other')
                logger.warning("stage=tool_protocol status=invalid_json parameter_start=%s", shape)
                raise ToolProtocolError("反代返回的工具参数不是有效 JSON") from exc
            if not isinstance(parameters, dict):
                raise ToolProtocolError("反代工具参数必须是 JSON 对象")
            calls.append(f"[TOOL_CALL:{match.group(1)}:{json.dumps(parameters, ensure_ascii=False)}]")
        if not calls:
            raise ToolProtocolError("反代返回了未支持的 DSML 工具格式")
        logger.info("stage=tool_protocol status=normalized calls=%d", len(calls))
        return "\n".join(calls)

    normalized = CALL_BLOCK.sub(replace, text or "")
    if re.search(r"[|｜]+DSML[|｜]+", normalized):
        raise ToolProtocolError("反代返回了不完整的工具协议，不能作为研究正文")
    return normalized


class ResearchLLM(HelloAgentsLLM):
    def invoke(self, messages, **kwargs):
        current_messages = list(messages)
        for attempt in range(3):
            response = super().invoke(current_messages, **kwargs)
            try:
                return normalize_tool_protocol(response)
            except ToolProtocolError:
                logger.warning("stage=tool_protocol status=invalid attempt=%d", attempt + 1)
                if attempt == 2:
                    raise
                # 未执行不合法的工具调用，让模型按框架要求重新输出。
                current_messages = current_messages + [
                    {"role": "assistant", "content": response},
                    {"role": "user", "content": "上一条工具调用格式无法解析。请按 [TOOL_CALL:工具名:{JSON对象}] 格式重新输出；如无需工具，请直接回答。"},
                ]

    def stream_invoke(self, messages, **kwargs):
        # 完整收到一轮回复后再转换，避免 JSON 跨片段造成工具调用丢失。
        # HelloAgents 仍负责工具循环；SSE 继续发送任务、工具和总结事件。
        # 不使用框架 think()，因为它会把全部生成内容直接打印到日志控制台。
        yield self.invoke(messages, **kwargs)
