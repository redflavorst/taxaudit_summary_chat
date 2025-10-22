import hashlib
import numpy as np
import uuid
from typing import Dict, Any

def l2_normalize(vecs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-12
    return vecs / norms

def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def clean_none(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}

def string_to_uuid(s: str) -> str:
    hash_bytes = hashlib.md5(s.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=hash_bytes))
