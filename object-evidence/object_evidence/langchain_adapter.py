"""Optional Document bridge. Does not start a model or upload any content."""

from .engine import EvidenceIndex
from .errors import EvidenceError


class ObjectEvidenceLoader:
    def __init__(self, index: EvidenceIndex):
        self.index = index

    def lazy_load(self):
        try:
            from langchain_core.documents import Document
        except ImportError:
            raise EvidenceError("langchain_core_not_installed") from None
        for chunk in self.index.documents_for_adapter():
            metadata = {key: value for key, value in chunk.items() if key != "text"}
            yield Document(page_content=chunk["text"], metadata=metadata)

    def load(self):
        return list(self.lazy_load())
