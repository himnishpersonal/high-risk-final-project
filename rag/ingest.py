"""
One-time script to load clinical documents from rag/documents/ and store them in ChromaDB.

Usage:
    python -m rag.ingest
"""

from pathlib import Path
from typing import List, Dict

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

from api.config import settings


def infer_topic_from_filename(filename: str, phase: str) -> str:

    filename_lower = filename.lower()
    
    if "cdc" in filename_lower or "ssi" in filename_lower or "infection" in filename_lower:
        return "infection"
    elif "wells" in filename_lower or "dvt" in filename_lower:
        return "dvt"
    elif "pain" in filename_lower:
        return "pain"
    elif "aaos" in filename_lower or "acl" in filename_lower or "mobility" in filename_lower:
        return "mobility"
    elif "discharge" in filename_lower or "wound" in filename_lower:
        return "wound_care"
    elif phase == "pre_op":
        return "prep"
    else:
        return "general"


def load_documents_from_folder(folder_path: Path, phase: str) -> List[Dict]:

    documents = []
    
    if not folder_path.exists():
        print(f"Folder {folder_path} does not exist, skipping...")
        return documents
    
    for file_path in folder_path.iterdir():
        if not file_path.is_file():
            continue
        
        extension = file_path.suffix.lower()
        source_id = file_path.stem
        topic = infer_topic_from_filename(source_id, phase)
        
        try:
            if extension == ".pdf":
                loader = PyPDFLoader(str(file_path))
                pages = loader.load()
                content = "\n\n".join([page.page_content for page in pages])
            elif extension in [".txt", ".md"]:
                loader = TextLoader(str(file_path))
                loaded = loader.load()
                content = loaded[0].page_content if loaded else ""
            else:
                print(f"Skipping unsupported file type: {file_path}")
                continue
            
            documents.append({
                "content": content,
                "metadata": {
                    "phase": phase,
                    "source_id": source_id,
                    "topic": topic
                }
            })
            print(f"Loaded {file_path.name} → phase={phase}, topic={topic}")
        
        except Exception as e:
            print(f"Failed to load {file_path}: {e}")
    
    return documents


def main():

    print("=" * 60)
    print("ACL Agent — RAG Ingestion")
    print("=" * 60)
    print()
    
    base_path = Path(__file__).parent / "documents"
    pre_op_path = base_path / "pre_op"
    post_op_path = base_path / "post_op"
    
    print(f"Loading documents from {base_path}")
    print()
    
    print("Loading pre-op documents...")
    pre_op_docs = load_documents_from_folder(pre_op_path, phase="pre_op")
    
    print("\nLoading post-op documents...")
    post_op_docs = load_documents_from_folder(post_op_path, phase="post_op")
    
    all_documents = pre_op_docs + post_op_docs
    
    if not all_documents:
        print("\nNo documents found. Please add PDF or text files to:")
        print(f"   - {pre_op_path}")
        print(f"   - {post_op_path}")
        return
    
    print(f"\nLoaded {len(all_documents)} documents total")
    print()
    
    print("Chunking documents...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        length_function=len,
    )
    
    chunks = []
    for doc in all_documents:
        split_texts = text_splitter.split_text(doc["content"])
        for text in split_texts:
            chunks.append({
                "text": text,
                "metadata": doc["metadata"]
            })
    
    print(f"Created {len(chunks)} chunks")
    print()
    
    print("Embedding and storing in ChromaDB...")
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        openai_api_key=settings.openai_api_key
    )
    
    chroma_db_path = "./chroma_db"
    
    texts = [chunk["text"] for chunk in chunks]
    metadatas = [chunk["metadata"] for chunk in chunks]
    
    vectorstore = Chroma.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        collection_name="acl_knowledge",
        persist_directory=chroma_db_path
    )
    
    print(f"Stored {len(chunks)} chunks in ChromaDB at {chroma_db_path}")
    print()
    print("=" * 60)
    print("Ingestion complete!")
    print("=" * 60)
    print()

if __name__ == "__main__":
    main()
