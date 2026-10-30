"""补充 DashScope 的错误信息，避免失败时只看到空结果。"""

import logging
import re
import time

from hello_agents.memory.embedding import DashScopeEmbedding

logger = logging.getLogger(__name__)


class ResearchDashScopeEmbedding(DashScopeEmbedding):
    def encode(self, texts):
        # 自定义 REST 地址仍交给框架处理；这里补充官方 SDK 模式的错误信息。
        if self.base_url:
            return super().encode(texts)

        from dashscope import TextEmbedding

        single = isinstance(texts, str)
        inputs = [texts] if single else list(texts)
        for attempt in range(3):
            response = TextEmbedding.call(model=self.model_name, input=inputs)
            output = response.get('output') if isinstance(response, dict) else getattr(response, 'output', None)
            embeddings = output.get('embeddings') if isinstance(output, dict) else getattr(output, 'embeddings', None)
            if embeddings:
                vectors = [item.get('embedding') or item.get('vector') for item in embeddings]
                return vectors[0] if single else vectors

            # 只记录状态与错误代码，不记录 API 密钥、请求正文或响应正文。
            status = getattr(response, 'status_code', None)
            code = getattr(response, 'code', None)
            if isinstance(response, dict):
                status = status or response.get('status_code')
                code = code or response.get('code')
            try:
                status = int(status) if status is not None else None
            except (TypeError, ValueError):
                status = None
            code = str(code or '')
            code = code if re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', code) else 'unknown'
            logger.warning('stage=embedding status=failed http_status=%s error_code=%s attempt=%d',
                           status, code, attempt + 1)
            # 临时限流或服务端错误才重试；配置和鉴权错误直接返回。
            if attempt < 2 and status is not None and (status == 429 or status >= 500):
                time.sleep(0.8 * (attempt + 1))
                continue
            raise RuntimeError(f'DashScope Embedding 失败：HTTP {status or "unknown"}，错误代码 {code}')
