"""
Retrieves relevant clinical knowledge chunks from ChromaDB based on query and phase.
"""

from typing import List, Dict, Optional

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

from api.config import settings


def retrieve(query_text: str, phase: str, topic: Optional[str] = None) -> List[Dict[str, str]]:

    try:
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=settings.openai_api_key
        )
        
        vectorstore = Chroma(
            collection_name="acl_knowledge",
            embedding_function=embeddings,
            persist_directory="./chroma_db"
        )
        
        if topic:
            where_filter = {
                "$and": [
                    {"phase": {"$eq": phase}},
                    {"topic": {"$eq": topic}}
                ]
            }
        else:
            where_filter = {"phase": {"$eq": phase}}
        
        # Retrieve top 4 chunks
        results = vectorstore.similarity_search(
            query=query_text,
            k=4,
            filter=where_filter
        )
        
        chunks = []
        for doc in results:
            chunks.append({
                "text": doc.page_content,
                "source_id": doc.metadata.get("source_id", "unknown"),
                "topic": doc.metadata.get("topic", "general")
            })
        
        return chunks
    
    except Exception as e:
        # Return empty list if collection doesn't exist
        print(f"RAG retrieval failed: {e}")
        return []
