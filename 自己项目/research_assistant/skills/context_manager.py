import os

from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter


os.environ["DASHSCOPE_API_KEY"] = os.environ.get("DASHSCOPE_API_KEY", "")


def get_similar_content_by_query(
    query: str,
    pages: list[dict],
    k: int = 5,
) -> list[Document]:
    documents = [
        Document(
            page_content=page["raw_content"],
            metadata={
                "source": page["url"],
                "title": page.get("title", ""),
            },
        )
        for page in pages
    ]

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        add_start_index=True,
    )
    splits = text_splitter.split_documents(documents)

    embeddings = DashScopeEmbeddings(model="text-embedding-v4")
    vector_store = InMemoryVectorStore(embeddings)
    vector_store.add_documents(documents=splits)

    return vector_store.similarity_search(query, k=k)
