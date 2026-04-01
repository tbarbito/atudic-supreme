from pathlib import Path

# Singleton cache: one PersistentClient per directory
_client_cache: dict[str, object] = {}


def get_shared_client(persist_dir: Path):
    """Return a shared PersistentClient for the given directory.
    Lazy import to avoid loading sentence-transformers at startup."""
    key = str(persist_dir.resolve())
    if key not in _client_cache:
        import chromadb
        persist_dir.mkdir(parents=True, exist_ok=True)
        _client_cache[key] = chromadb.PersistentClient(path=key)
    return _client_cache[key]


class VectorStore:
    def __init__(self, persist_dir: Path):
        self.persist_dir = persist_dir
        self._client = None

    def initialize(self):
        self._client = get_shared_client(self.persist_dir)

    def _get_or_create(self, name: str):
        return self._client.get_or_create_collection(name=name)

    def add_source_chunks(self, collection_name: str, chunks: list[dict]):
        collection = self._get_or_create(collection_name)
        ids = [c["id"] for c in chunks]
        documents = [c["content"] for c in chunks]
        metadatas = [{k: v for k, v in c.items() if k not in ("id", "content")} for c in chunks]
        collection.add(ids=ids, documents=documents, metadatas=metadatas)

    def search(self, collection_name: str, query: str, n_results: int = 5, where: dict = None) -> list[dict]:
        collection = self._get_or_create(collection_name)
        kwargs = {"query_texts": [query], "n_results": n_results}
        if where:
            kwargs["where"] = where
        results = collection.query(**kwargs)
        output = []
        for i in range(len(results["ids"][0])):
            output.append({
                "id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else 0,
            })
        return output

    def delete_by_filter(self, collection_name: str, where: dict):
        collection = self._get_or_create(collection_name)
        collection.delete(where=where)

    def reset_collection(self, collection_name: str):
        try:
            self._client.delete_collection(collection_name)
        except Exception:
            pass
