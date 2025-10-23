import sys
import os

# create_db 디렉토리를 sys.path에 추가
create_db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if create_db_dir not in sys.path:
    sys.path.insert(0, create_db_dir)

from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List
from config import settings
from vectorstore.utils import l2_normalize

class Embedder:
    def __init__(self, model_name: str = None, normalize: bool = True):
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.normalize = normalize
        self._model = None
    
    @property
    def model(self):
        if self._model is None:
            print(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
        return self._model
    
    def encode(self, texts: List[str], batch_size: int = 64, show_progress: bool = True) -> np.ndarray:
        if not texts:
            return np.array([])
        
        vecs = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=False,
            convert_to_numpy=True
        ).astype("float32")
        
        return l2_normalize(vecs) if self.normalize else vecs
    
    def embed_query(self, text: str) -> List[float]:
        """단일 쿼리 임베딩"""
        vec = self.encode([text], batch_size=1, show_progress=False)
        return vec[0].tolist()


_embedder_instance = None

def get_embedder() -> Embedder:
    """싱글톤 Embedder 인스턴스 반환"""
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = Embedder()
    return _embedder_instance
