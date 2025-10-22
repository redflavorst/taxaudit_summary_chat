# create_db/linker.py
import re
from typing import List, Dict
from collections import defaultdict

def jaccard(a: str, b: str) -> float:
    ta = set(re.findall(r"[가-힣A-Za-z0-9]+", a))
    tb = set(re.findall(r"[가-힣A-Za-z0-9]+", b))
    if not ta or not tb: return 0.0
    return len(ta & tb) / len(ta | tb)

def link_rows_findings(rows: List[Dict], findings: List[Dict]):
    maps=[]
    for r in rows:
        for f in findings:
            code_exact = 1 if (r.get("code") and f.get("code") and r["code"]==f["code"]) else 0
            code_mismatch = bool(r.get("code") and f.get("code") and r["code"]!=f["code"])
            name_overlap = jaccard(r.get("item",""), f.get("item",""))
            reason_overlap = jaccard(r.get("reason_kw_raw",""), f.get("item",""))
            page_prox = 0  # 페이지 주면 0/1로 계산
            score = 5*code_exact + 2*name_overlap + 1*reason_overlap + 1*page_prox
            needs_review = (3 <= score < 6)
            if score >= 2:   # 너무 낮은 건 제외
                maps.append(dict(
                    map_id=f'{r["row_id"]}→{f["finding_id"]}',
                    row_id=r["row_id"], finding_id=f["finding_id"],
                    score=round(score,3),
                    code_mismatch=code_mismatch,
                    needs_review=needs_review
                ))
    # 하나의 row가 다수 finding과 연결될 수 있음(후속 단계에서 상위 1건만 사용)
    return maps
