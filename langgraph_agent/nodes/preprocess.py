"""
Preprocess Node: 질의 전처리 및 정규화
"""

import re
from typing import Optional
from ..state import AgentState


SENSITIVE_PATTERNS = [
    (r'\b\d{6}-\d{7}\b', '[주민번호]'),  # 주민등록번호
    (r'\b\d{3}-\d{2}-\d{5}\b', '[사업자번호]'),  # 사업자등록번호
    (r'\b\d{4}-\d{4}-\d{4}-\d{4}\b', '[카드번호]'),  # 카드번호
    (r'\b\d{2,3}-\d{3,4}-\d{4}\b', '[전화번호]'),  # 전화번호
]


def normalize_text(text: str) -> str:
    """텍스트 정규화"""
    text = text.strip()
    
    text = re.sub(r'\s+', ' ', text)
    
    text = re.sub(r'[^\w\s가-힣]', ' ', text)
    
    text = text.lower()
    
    return text.strip()


def mask_sensitive_info(text: str) -> str:
    """민감 정보 마스킹"""
    masked = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        masked = re.sub(pattern, replacement, masked)
    return masked


def detect_language(text: str) -> str:
    """언어 감지 (간단 휴리스틱)"""
    korean_chars = len(re.findall(r'[가-힣]', text))
    total_chars = len(re.findall(r'\w', text))
    
    if total_chars == 0:
        return "unknown"
    
    korean_ratio = korean_chars / total_chars
    
    if korean_ratio > 0.3:
        return "ko"
    else:
        return "en"


def expand_abbreviations(text: str) -> str:
    """약어 확장"""
    abbreviations = {
        '법인세': '법인세',
        '부가세': '부가가치세',
        '종소세': '종합소득세',
        '양도세': '양도소득세',
        '취득세': '취득세',
        'VAT': '부가가치세',
    }
    
    for abbr, full in abbreviations.items():
        text = re.sub(rf'\b{re.escape(abbr)}\b', full, text, flags=re.IGNORECASE)
    
    return text


def remove_particles_and_stopwords(text: str) -> str:
    """
    조사 및 불용어 제거
    
    - 조사: ~시, ~에, ~의, ~를, ~을, ~가, ~이, ~와, ~과
    - 불용어: 사례, 조사, 적출, 관련, 있어, 알려줘 등
    - 복합명사: 적출사례, 조사사례 등
    """
    # 복합명사 먼저 제거 (단어 경계 없이)
    compound_noise = [
        "적출사례", "조사사례", "적발사례", 
        "세무조사", "세무사례"
    ]
    
    cleaned = text
    for compound in compound_noise:
        cleaned = re.sub(re.escape(compound), '', cleaned, flags=re.IGNORECASE)
    
    # 단일 불용어 제거
    noise_keywords = [
        "사례", "사건", "적발", "적출", "조사", "예시", "예제",
        "알려줘", "알려주세요", "찾아줘", "검색", "보여줘", "관련",
        "있어", "있나요", "있습니까", "케이스"
    ]
    
    for noise in noise_keywords:
        cleaned = re.sub(rf'\b{re.escape(noise)}\b', '', cleaned, flags=re.IGNORECASE)
    
    particles = ["시", "에", "의", "를", "을", "가", "이", "와", "과", "도"]
    for particle in particles:
        cleaned = re.sub(rf'(?<=[가-힣]){re.escape(particle)}\s+', ' ', cleaned)
    
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned


def preprocess(state: AgentState) -> AgentState:
    """
    Preprocess 노드: 질의 전처리
    
    1. 민감정보 마스킹
    2. 언어 감지
    3. 정규화 (공백, 특수문자)
    4. 약어 확장
    5. 조사 및 불용어 제거
    """
    query = state["user_query"]
    
    masked = mask_sensitive_info(query)
    
    lang = detect_language(masked)
    
    if lang != "ko":
        print(f"[Preprocess] 경고: 한국어가 아닌 질의 감지 (언어: {lang})")
    
    normalized = normalize_text(masked)
    
    expanded = expand_abbreviations(normalized)
    
    cleaned = remove_particles_and_stopwords(expanded)
    
    state["normalized_query"] = cleaned
    
    print(f"[Preprocess] 원본: {query}")
    print(f"[Preprocess] 핵심어 추출: {cleaned}")
    
    return state
