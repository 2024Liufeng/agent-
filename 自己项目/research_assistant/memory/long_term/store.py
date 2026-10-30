import os

from langchain_community.embeddings import DashScopeEmbeddings
from langgraph.store.memory import InMemoryStore


os.environ["DASHSCOPE_API_KEY"] = os.environ.get("DASHSCOPE_API_KEY", "")


embeddings = DashScopeEmbeddings(
    model="text-embedding-v4",
)

store = InMemoryStore(
    index={
        "embed": embeddings,
        "dims": 1024,
    }
)
