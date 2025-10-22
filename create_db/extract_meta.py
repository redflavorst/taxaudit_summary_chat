import re
import math
import yaml
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple

VOCAB_DIR = Path(__file__).parent / "vocab"

def tokenize_ko(text: str) -> List[str]:
    return re.findall(r"[가-힣A-Za-z0-9]+", text)

def cos_sim(a: Set[str], b: Set[str]) -> float:
    inter = len(a & b)
    if not inter: 
        return 0.0
    return inter / math.sqrt(len(a) * len(b))

def build_vocab(vocab_dict: Dict) -> Tuple[Dict[str, Set[str]], Dict[str, str]]:
    canon = {}
    inv = {}
    for k, meta in vocab_dict.items():
        canon[k] = set(tokenize_ko(k))
        for syn in meta.get("synonyms", []):
            inv[syn] = k
    return canon, inv

def normalize_candidates(cands: List[str], canon: Dict[str, Set[str]], threshold: float = 0.6) -> List[str]:
    normed = set()
    for c in cands:
        tc = set(tokenize_ko(c))
        best, score = None, 0.0
        for name, tcanon in canon.items():
            s = cos_sim(tc, tcanon)
            if s > score:
                best, score = name, s
        if best and score >= threshold:
            normed.add(best)
    return sorted(normed)

class VocabLoader:
    def __init__(self):
        self.industry_vocab = {}
        self.domain_tags_vocab = {}
        self.actions_vocab = {}
        
        self.canon_industry = {}
        self.canon_domain = {}
        self.canon_actions = {}
        
        self.inv_industry = {}
        self.inv_domain = {}
        self.inv_actions = {}
        
        self._load_all()
    
    def _load_all(self):
        industry_path = VOCAB_DIR / "industry.yaml"
        domain_path = VOCAB_DIR / "domain_tags.yaml"
        actions_path = VOCAB_DIR / "actions.yaml"
        
        if industry_path.exists():
            with open(industry_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "industry" in data:
                    for ind in data["industry"]:
                        name = ind["name"]
                        subs = ind.get("subs", [])
                        self.industry_vocab[name] = {"subs": subs}
        
        if domain_path.exists():
            with open(domain_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "domain_tags" in data:
                    self.domain_tags_vocab = data["domain_tags"]
        
        if actions_path.exists():
            with open(actions_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "actions" in data:
                    self.actions_vocab = data["actions"]
        
        self.canon_domain, self.inv_domain = build_vocab(self.domain_tags_vocab)
        self.canon_actions, self.inv_actions = build_vocab(self.actions_vocab)

vocab_loader = VocabLoader()

def extract_reason_kw_norm(reason_raw: str, stopwords: Set[str] = None) -> List[str]:
    """
    적출요지에서 키워드 추출 (사전 불필요, TF 기반)
    → ES의 BM25/임베딩이 검색하므로 원문 키워드만 추출
    """
    if stopwords is None:
        stopwords = {"및", "등", "관련", "경우", "대상", "처분", "금액", "손금", "누락", "과다", 
                     "산출", "계상", "인정", "부인", "미포함", "제외", "오류"}
    
    toks = tokenize_ko(reason_raw)
    base = [t for t in toks if t not in stopwords and len(t) >= 2]
    
    seen = set()
    top = []
    for w in base:
        if w not in seen:
            seen.add(w)
            top.append(w)
        if len(top) >= 6:
            break
    return top

def extract_domain_tags(text: str, threshold: float = 0.6) -> List[str]:
    """
    도메인 태그 추출 (사전 기반 분류 레이블만)
    → 최소한의 패턴 매칭으로 필터링용 태그만 추출
    """
    cand = set()
    for k, meta in vocab_loader.domain_tags_vocab.items():
        pats = [k] + meta.get("synonyms", [])
        if any(p in text for p in pats):
            cand.add(k)
    return sorted(cand)

def extract_actions(text: str, threshold: float = 0.6) -> List[str]:
    """
    행위 태그 추출 (사전 기반 분류 레이블만)
    → 통계/필터링용 고정 레이블만 추출 (30-50개 수준)
    """
    cand = set()
    for k, meta in vocab_loader.actions_vocab.items():
        pats = [k] + meta.get("synonyms", [])
        if any(p in text for p in pats):
            cand.add(k)
    return sorted(cand)

def decide_industry_sub(overview_text: str, code_list: List[str]) -> Tuple[str, float]:
    txt = overview_text.lower()
    
    if any(c.startswith("102") for c in code_list):
        if "시행사" in txt or "시공사" in txt or "건설" in txt:
            return "건설시행", 0.8
    
    if "의류" in txt:
        if "플랫폼" in txt or "29cm" in txt or "온라인" in txt or "오픈마켓" in txt:
            return "의류도매", 0.75
        elif "제조" in txt:
            return "의류제조", 0.75
    
    if "피부과" in txt or "치과" in txt or "한의원" in txt or "의원" in txt:
        return "보건업", 0.8
    
    if "음식점" in txt or "카페" in txt or "주점" in txt:
        return "음식점업", 0.75
    
    if "소프트웨어" in txt or "앱개발" in txt or "it서비스" in txt:
        return "소프트웨어개발", 0.75
    
    if "도소매" in txt or "판매업" in txt or "전자상거래" in txt:
        return "도소매", 0.7
    
    return None, 0.0

def extract_all_meta(overview_text: str, reason_rows: List[str], findings_text: str, code_list: List[str] = None) -> Dict:
    if code_list is None:
        code_list = []
    
    reason_kw = set()
    for r in reason_rows:
        reason_kw.update(extract_reason_kw_norm(r))
    
    full_text = overview_text + "\n" + findings_text
    domain_tags = extract_domain_tags(full_text)
    actions = extract_actions(full_text)
    industry_sub, conf = decide_industry_sub(overview_text, code_list)
    
    entities = []
    entity_patterns = [
        r"(29CM|쿠팡|네이버|카카오|KT|SK|LG)",
        r"([가-힣]{2,}(?:은행|증권|보험|카드))",
    ]
    for pat in entity_patterns:
        matches = re.findall(pat, full_text)
        entities.extend(matches)
    entities = list(set(entities))[:10]
    
    return {
        "overview_keywords_norm": sorted(reason_kw)[:6],
        "domain_tags": domain_tags,
        "actions": actions,
        "industry_sub": industry_sub,
        "industry_sub_conf": conf,
        "entities": entities
    }
