# Taxaudit Summary Chat - Complete Query Processing Flow Analysis

## 1. ENTRY POINTS

### Main Entry Point: `/home/user/taxaudit_summary_chat/langgraph_agent/main.py`
- **Interactive Mode**: `python -m langgraph_agent.main` (prompts user for queries in a loop)
- **Single Query Mode**: `python -m langgraph_agent.main "your query here"` (processes one query and exits)
- **Programmatic Mode**: `from langgraph_agent.main import run_query; answer = run_query(query)`

### Function: `run_query(query: str) -> str`
- Creates initial `AgentState` with empty fields
- Invokes `agent_app` (the compiled LangGraph)
- Returns the `answer` field from final state
- Outputs formatted results to console

## 2. QUERY PROCESSING FLOW (LangGraph Pipeline)

The system uses LangGraph to orchestrate a multi-stage query processing pipeline. See `/home/user/taxaudit_summary_chat/langgraph_agent/graph.py`

### Complete Flow Diagram:
```
User Query (korean text)
    ↓
[preprocess] - Text normalization, PII masking, cleanup
    ↓
[parse_query] - Intent classification + LLM-based slot extraction
    ↓
[expand_query] - LLM-based query expansion (must_have, should_have, related_terms)
    ↓
[route] - Conditional routing based on intent & confidence
    ├→ "clarify" → [clarify] → END (low confidence)
    ├→ "search" → [retrieve_findings] → [retrieve_chunks] → [promote_blocks] → [context_pack] → [compose_answer] → [validate] → END
    └→ "explain" → [compose_answer] → [validate] → END
```

## 3. NODE DESCRIPTIONS

### Node 1: Preprocess (`langgraph_agent/nodes/preprocess.py`)
**Purpose**: Clean and normalize the user query

**Steps**:
1. Mask sensitive information (SSN, phone numbers, credit cards)
2. Detect language (Korean vs English)
3. Normalize text (whitespace, special characters, lowercase)
4. Expand abbreviations (VAT → 부가가치세)
5. Remove particles and stopwords (조사, 사례, 적출 등)

**Output State Changes**:
- `state["normalized_query"]` = cleaned query text

---

### Node 2: ParseQuery (`langgraph_agent/nodes/parse_query.py`)
**Purpose**: Analyze query intent and extract structured information

**Steps**:
1. Classify intent:
   - "case_lookup": Find audit cases (default)
   - "explain": Request definition/explanation
2. Extract slots using LLM (Ollama) via `/api/generate` endpoint:
   - `industry_sub`: Industries (manufacturing, wholesale, etc.)
   - `domain_tags`: Domain tags from vocabulary
   - `code`: Tax item codes (e.g., 11608, 10501)
   - `entities`: Company names, person names
   - `section_hints`: Keywords for "조사착안" (audit findings) or "조사기법" (investigation technique)
3. Fallback to rule-based extraction if LLM fails
4. Calculate confidence score (0.0-1.0)

**LLM Integration**: 
- URL: `config.ollama_base_url` (default: http://localhost:11434)
- Model: `config.ollama_model` (default: gemma3:12b)
- Request type: POST to `/api/generate` with JSON format

**Output State Changes**:
- `state["intent"]` = "case_lookup" or "explain"
- `state["slots"]` = Slots dict with extracted fields
- `state["needs_clarification"]` = False initially

---

### Node 3: ExpandQuery (`langgraph_agent/nodes/expand_query.py`)
**Purpose**: Expand query with domain knowledge for better retrieval

**Steps**:
1. Only runs if intent == "case_lookup"
2. Calls Ollama LLM with domain vocabulary context
3. Extracts:
   - `must_have`: Core keywords explicitly mentioned
   - `should_have`: Related keywords (optional)
   - `related_terms`: Synonyms from vocabulary
   - `boost_weights`: Scoring weights for each keyword (1.0-3.0)
4. Fallback expansion if LLM fails

**Query Expansion Strategy**:
- First keyword = document-level context (e.g., "합병법인" = merger company)
- Remaining keywords = block-level filters (e.g., ["미환류소득", "대리납부"])

**Output State Changes**:
- `state["slots"]["expansion"]` = Dict with must_have, should_have, related_terms, boost_weights

---

### Node 4: Route (`langgraph_agent/nodes/route.py`)
**Purpose**: Conditional routing based on intent and confidence

**Decision Logic**:
```
if should_clarify(state):
    return "clarify"
elif intent == "case_lookup":
    return "search"
elif intent == "explain":
    return "explain"
```

**Clarify Conditions**:
- confidence < 0.4 (CONFIDENCE_THRESHOLD)
- No must_have keywords from expansion
- Missing essential slots (industry, domain_tags, code)

**Output**: Routes to one of three paths

---

### Node 5: Clarify (`langgraph_agent/nodes/clarify.py`)
**Purpose**: Request additional information if query is ambiguous

**Steps**:
1. Generate clarification question based on missing slots
2. Ask for: industry, domain tags, codes, entities
3. Return clarification message to user

**Output State Changes**:
- `state["clarification_question"]` = Question text
- `state["needs_clarification"]` = True
- `state["answer"]` = Formatted clarification message
- **PIPELINE ENDS** (goes to END, does not continue to search)

---

### Node 6: RetrieveFindings (`langgraph_agent/nodes/retrieve_findings.py`)
**Purpose**: First-stage retrieval - find relevant "findings" (audit items)

**Uses**: HybridRetriever from `langgraph_agent/retrieval.py`

**Retrieval Strategy**:
1. **Keyword-based Document Filtering**:
   - For each keyword in `must_have`, search for documents containing it
   - If 2+ keywords: Find intersection documents (documents containing ALL keywords)
   - If intersection empty: Use union (documents containing ANY keyword)
   - If 1 keyword: Use that keyword's documents

2. **Hybrid Search** (Elasticsearch + Qdrant):
   - **Elasticsearch (BM25)**: Text search on `item`, `reason_kw_norm`, `item_detail` fields
   - **Qdrant (Vector Search)**: Semantic search using embeddings (when 2+ keywords)
   - **RRF Fusion**: Combine ES and vector rankings using Reciprocal Rank Fusion
   - Score Threshold: 0.35 (or 0.65 for multi-keyword to avoid over-matching)

3. **Filtering**:
   - Apply code filters (if provided)
   - Apply industry filters (if provided)
   - Apply domain tag filters (if provided)

**Output State Changes**:
- `state["findings_candidates"]` = List[FindingHit] (top_n=30 by default)
- `state["target_doc_ids"]` = Document IDs (from keyword filtering)
- `state["keyword_freq"]` = Keyword frequency in target documents

---

### Node 7: RetrieveChunks (`langgraph_agent/nodes/retrieve_chunks.py`)
**Purpose**: Second-stage retrieval - extract detailed chunks by section

**Process**:
1. For each finding from previous stage, retrieve chunks in two sections:
   - "조사착안" (Investigation Findings) - what was found
   - "조사기법" (Investigation Technique) - how it was found

2. **Hybrid Search per Section**:
   - Query includes section hints + free text
   - Filtered to findings from stage 1
   - Top-k per section: 300 from ES, 300 from Qdrant
   - RRF merge (k=60)

3. **Document-level Filtering**:
   - If target_doc_ids available from keyword filtering, restrict to those documents
   - Ensures semantic relevance within keyword-filtered document set

**Output State Changes**:
- `state["chunks_candidates"]` = Unique chunk list
- `state["section_groups"]` = {"착안": [...], "기법": [...]}

---

### Node 8: PromoteToBlocks (`langgraph_agent/nodes/promote_blocks.py`)
**Purpose**: Aggregate chunks into ranked blocks and apply keyword filtering

**Process**:
1. **Group chunks by finding_id**:
   - Intersection: Findings with chunks in BOTH sections (착안 + 기법)
   - Union: Findings with chunks in either section

2. **Ranking Strategy**:
   - If intersection >= 2 blocks: Use intersection (prioritize complete coverage)
   - Else: Use union with 5:5 blending (equal weight to both sections)
   - Block score = average of top-3 chunk scores

3. **Keyword-based Filtering** (when 2+ keywords):
   - First keyword = document-level context (already filtered)
   - Remaining keywords = must appear in block text (OR relationship)
   - Full match: Block contains any block-level keyword → Include in main answer
   - Partial match: Block contains doc-level keyword only → Exclude
   - No match: → Exclude

4. **Tracking**:
   - `keyword_block_counts`: Count matches per keyword
   - `excluded_blocks`: Blocks that don't match filters (shown as "additional info")

**Output State Changes**:
- `state["block_ranking"]` = Ranked blocks for answer (top 3 by default)
- `state["excluded_blocks"]` = Filtered-out blocks (shown as supplementary info)
- `state["keyword_block_counts"]` = {keyword: count}

---

### Node 9: ContextPack (`langgraph_agent/nodes/context_pack.py`)
**Purpose**: Format and pack blocks into context for LLM

**Process**:
1. Iterate through ranked blocks
2. For each block:
   - Create header with doc_id, finding_id, item, code, sections
   - Group chunks by section with defined order: 조사기법 → 과세논리 → 증빙 및 리스크 → 조사착안
   - Merge adjacent chunks if enabled
   - Include page/line citations for each chunk
3. Respect token budget (4000 tokens by default)
4. Create citations list for reference section

**Output State Changes**:
- `state["context"]` = ContextData{packed_text, citations}
  - `packed_text`: Formatted markdown with all block content
  - `citations`: List[Citation] with doc_id, page, line numbers

---

### Node 10: ComposeAnswer (`langgraph_agent/nodes/compose_answer.py`)
**Purpose**: Generate final answer using LLM

**LLM Call**:
- Model: Ollama (same as ParseQuery)
- Temperature: 0.1 (low, deterministic)
- Prompt template includes:
  - User's original question
  - Packed context from previous node
  - Instructions to include all cases, create card format, cite sources

**Answer Structure**:
1. Optional search strategy explanation (if 2+ keywords)
   - Shows which keywords were used for filtering
   - Shows keyword-to-case match counts
2. LLM-generated answer (main content)
3. Citation section (document references with page/line)
4. Additional information section (if blocks were excluded due to filtering)

**Output State Changes**:
- `state["answer"]` = Formatted final answer
- `state["error"]` = Error message if LLM call fails

---

### Node 11: Validate (`langgraph_agent/nodes/validate.py`)
**Purpose**: Final validation and fallback handling

**Checks**:
1. If error exists: Return as-is
2. If no answer: Return fallback message
3. If no citations: Add warning
4. If no ranked blocks: Return "no results" message

**Output State Changes**:
- May modify `state["answer"]` with warnings or fallback messages

## 4. COMPONENT INTEGRATION

### Elasticsearch (BM25 Full-Text Search)
**Location**: `langgraph_agent/retrieval.py` - `HybridRetriever` class

**Indices**:
- `findings`: Document-level audit findings
  - Fields: finding_id, doc_id, item, code, reason_kw_norm, industry_sub, domain_tags
- `chunks`: Section-level content chunks
  - Fields: chunk_id, finding_id, section, text, page, start_line, end_line

**Connection**:
```python
self.es = Elasticsearch(
    config.es_url,
    basic_auth=(config.es_user, config.es_password),
    request_timeout=30
)
```

**Search Operations**:
1. `_find_docs_by_keyword()`: Get document IDs matching a keyword
2. `retrieve_findings()`: Hybrid search on findings index
3. `retrieve_chunks_by_section()`: Hybrid search on chunks index with section filter
4. `_calculate_keyword_frequency()`: Aggregation query for keyword statistics

---

### Qdrant (Vector Search)
**Location**: `langgraph_agent/retrieval.py` - Vector search section

**Collections**:
- `findings_vectors`: Embeddings for findings (1024-dim by default)
- `chunks_vectors`: Embeddings for chunks (1024-dim by default)

**Connection**:
```python
self.qdrant = QdrantClient(path=config.qdrant_path)
```

**Embedding Model**: 
- Default: `BAAI/bge-m3` (1024 dimensions)
- Loaded via `create_db.vectorstore.embedder.get_embedder()`

**Vector Search Operations**:
1. Query embedding: `self._get_query_embedding_cached(query)`
2. Similarity search: `qdrant.search()` with score_threshold
3. Filtering: Qdrant `Filter` objects with field conditions

---

### Ollama LLM
**Location**: Used in multiple nodes for text generation

**Endpoints**:
- `/api/generate`: POST request for text generation
  - Request: `{model, prompt, stream, format, options}`
  - Response: `{response, done_reason}`
  - Timeout: 60 seconds

**Models Used**:
- `gemma3:12b` (default, configurable)

**Temperature**: 0.1 (low, deterministic output)

**Calls Made**:
1. `parse_query()`: LLM slot extraction
2. `expand_query()`: Query expansion with domain vocabulary
3. `compose_answer()`: Final answer generation

---

### PostgreSQL Database
**Location**: `create_db/pg_dao.py` (data ingestion) + `create_db/config.py`

**Purpose**: Store extracted findings, chunks, rows, and metadata

**Tables**:
- `documents`: Document metadata (title, source path)
- `table_rows`: Raw table row data
- `findings`: Extracted findings with metadata
- `chunks`: Content chunks with section information
- `row_finding_map`: Mapping between rows and findings

**Connection**:
```python
pg_dsn = "postgresql://postgres:root@localhost:5432/ragdb"
```

---

## 5. DATA STRUCTURES

### AgentState (State Flow)
```python
{
    # Input
    "user_query": str,                     # Original user question
    
    # Preprocessing
    "normalized_query": Optional[str],     # Cleaned query
    
    # Intent & Parsing
    "intent": Optional[str],               # "case_lookup" or "explain"
    "slots": Slots{                        # Extracted information
        "industry_sub": List[str],
        "domain_tags": List[str],
        "code": List[str],
        "entities": List[str],
        "section_hints": {"착안": [...], "기법": [...]},
        "free_text": str,
        "confidence": float,               # 0.0-1.0
        "expansion": {                     # From LLM expansion
            "must_have": List[str],
            "should_have": List[str],
            "related_terms": List[str],
            "boost_weights": Dict[str, float]
        }
    },
    
    # Clarification
    "needs_clarification": bool,
    "clarification_question": Optional[str],
    
    # Retrieval Results
    "target_doc_ids": Optional[List[str]],      # From keyword filtering
    "keyword_freq": Optional[Dict[str, int]],   # Keyword frequencies
    "keyword_block_counts": Optional[Dict],     # Per-keyword block counts
    "findings_candidates": List[FindingHit],    # Stage 1 results
    "chunks_candidates": List[ChunkHit],        # Stage 2 results
    "section_groups": {"착안": [...], "기법": [...]},
    
    # Ranking
    "block_ranking": List[RankedBlock],         # Final ranked blocks
    "excluded_blocks": List[RankedBlock],       # Filtered out blocks
    
    # Answer
    "context": ContextData{
        "packed_text": str,                     # Formatted context
        "citations": List[Citation]
    },
    "answer": Optional[str],                    # Final answer
    
    # Error Handling
    "error": Optional[str]
}
```

---

### FindingHit
```python
@dataclass
class FindingHit:
    finding_id: str
    doc_id: str
    item: Optional[str]              # Audit finding name
    item_detail: Optional[str]       # Detailed description
    code: Optional[str]              # Tax code
    score_bm25: float                # BM25 score
    score_vector: float              # Vector similarity
    score_combined: float             # Combined score
```

### ChunkHit
```python
@dataclass
class ChunkHit:
    chunk_id: str
    finding_id: str                  # Parent finding
    doc_id: str
    section: str                     # "조사착안" or "조사기법"
    section_order: int
    chunk_order: int
    code: Optional[str]
    item: Optional[str]
    page: Optional[int]
    start_line: Optional[int]
    end_line: Optional[int]
    text: str                        # Chunk content
    score_combined: float
```

### RankedBlock
```python
@dataclass
class RankedBlock:
    finding_id: str
    doc_id: str
    item: Optional[str]
    code: Optional[str]
    score: float                     # Block ranking score
    chunks: List[ChunkHit]           # Constituent chunks
    source_sections: List[str]       # ["조사착안", "조사기법"] etc.
```

---

## 6. CONFIGURATION

**File**: `/home/user/taxaudit_summary_chat/langgraph_agent/config.py`

**Key Parameters**:
```python
# LLM
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma3:12b"
OLLAMA_TEMPERATURE = 0.1

# Elasticsearch
ES_URL = "http://localhost:9200"
ES_USER = "elastic"
ES_PASSWORD = (from env)

# Qdrant
QDRANT_PATH = "./qdrant_storage"
QDRANT_COLLECTION_FINDINGS = "findings_vectors"
QDRANT_COLLECTION_CHUNKS = "chunks_vectors"

# Retrieval
FINDINGS_TOP_K_ES = 150
FINDINGS_TOP_K_VEC = 150
FINDINGS_RRF_K = 60
FINDINGS_FINAL_TOP_N = 30
CHUNKS_TOP_K_ES = 300
CHUNKS_TOP_K_VEC = 300

# Ranking & Filtering
BLOCK_TOP_K_CHUNKS = 3              # Chunks per block
BLOCK_INTERSECTION_MIN = 2           # Min blocks for intersection
BLOCK_FINAL_TOP_N = 3                # Max blocks in answer
MAX_BLOCKS_PER_DOC = 2               # Diversity across documents

# Scoring Weights
ALPHA_BM25 = 0.5
BETA_VECTOR = 0.4
GAMMA_FIELD = 0.1

# Section Weights (기본 5:5)
WEIGHT_SECTION_CHAKAN = 0.5
WEIGHT_SECTION_GIHUB = 0.5

# Context
CONTEXT_TOKEN_BUDGET = 4000
CONTEXT_CHUNKS_PER_BLOCK = 3
CONTEXT_MERGE_ADJACENT = True
```

---

## 7. ERROR HANDLING & FALLBACK STRATEGIES

### Elasticsearch Connection Failures
- Caught in `HybridRetriever.__init__()` and `_hybrid_search()`
- Fallback: Return empty results, allow vector-only search
- Logged to `logs/retrieval.log`

### Qdrant Connection Failures
- Caught in `HybridRetriever.__init__()`
- Fallback: Disable vector search, use BM25 only
- Timeout handling: 10-30 second timeouts

### Ollama LLM Failures
- **parse_query()**: Falls back to rule-based slot extraction
- **expand_query()**: Returns fallback expansion with domain_tags
- **compose_answer()**: Returns error message with HTTP status

### Query Expansion Failures
- JSON parsing errors → Fallback expansion
- Connection timeout → Returns minimal expansion
- HTTP errors (4xx, 5xx) → Fallback mode

### Empty Results
- No findings → Skip to chunk retrieval (empty list)
- No chunks → Return "no results" message
- No blocks after ranking → Show "no matching cases" message

---

## 8. PERFORMANCE OPTIMIZATIONS

### Caching
- **Embedding cache**: MD5 hash-based LRU cache (100 max)
- **Keyword frequency cache**: LRU cache for repeated queries

### Aggregation Optimization
- `_calculate_keyword_frequency()`: Single ES aggregation query instead of N queries
- Reduces keyword frequency from 15 queries → 1 query (15x improvement)

### RRF Fusion
- Reciprocal Rank Fusion combines ES + Qdrant rankings
- Weight = 1/(k + rank), where k=60 by default
- Merges before top-k filtering

### Lazy Loading
- Chunk text retrieved on-demand from ES if missing from Qdrant payload
- Reduces Qdrant payload size

---

## 9. SEARCH STRATEGY VARIATIONS

### Single Keyword Query
- Use keyword to filter documents
- Search all findings in those documents
- No keyword filtering at block level
- Return all matching blocks

### Multi-Keyword Query (2+)
- First keyword: Document-level intersection filter
- Remaining keywords: Block-level OR filter (at least one must match)
- Hybrid search (BM25 + Vector)
- Stronger vector similarity threshold (0.65 vs 0.35)
- Show search strategy in answer
- Include "additional information" section with excluded blocks

---

## 10. OUTPUT DELIVERY

### Console Output
- Real-time logging from each node
- Progress messages: `[NodeName] message`
- Final answer printed with formatting
- Debug info for retrieval decisions

### Answer Format
```markdown
[Optional Search Strategy]
> 💡 **검색 전략**: 'keyword1' 문서 내에서 'keyword2' 포함 사례를 검색했습니다.

[LLM-Generated Answer]
## 적출 블록 1
...content...

## 참고 문헌
- [doc_id] finding_id (p.page, Lstart-end)
```

---

## 11. KEY FILES SUMMARY

| File | Purpose |
|------|---------|
| `langgraph_agent/main.py` | Entry point, CLI interface |
| `langgraph_agent/graph.py` | LangGraph definition |
| `langgraph_agent/state.py` | State definitions |
| `langgraph_agent/config.py` | Configuration management |
| `langgraph_agent/retrieval.py` | Hybrid search logic |
| `langgraph_agent/nodes/*.py` | 10 processing nodes |
| `langgraph_agent/logger.py` | Logging setup |
| `create_db/create_database.py` | Data ingestion pipeline |
| `create_db/vectorstore/` | Embedding + Qdrant integration |

---

## 12. WORKFLOW EXAMPLE

**User Query**: "제조업에서 매출누락 조사기법은?"

1. **Preprocess**: "제조업에서 매출누락 조사기법은?" → "제조업 매출누락 조사기법"
2. **ParseQuery**: Extract slots
   - intent: "case_lookup"
   - industry_sub: ["제조업"]
   - free_text: "제조업 매출누락 조사기법"
   - section_hints: {"기법": ["조사기법"]}
   - confidence: 0.7
3. **ExpandQuery**: LLM expansion
   - must_have: ["제조업", "매출누락"]
   - should_have: []
   - related_terms: ["매출", "누락"]
   - boost_weights: {"제조업": 3.0, "매출누락": 3.0}
4. **Route**: intent="case_lookup" + confidence>0.4 → search
5. **RetrieveFindings**: 
   - Find docs with "제조업" AND "매출누락" (intersection)
   - Hybrid search on findings
   - Return 15-30 findings
6. **RetrieveChunks**:
   - Search chunks with section="조사기법" (from section_hints)
   - Top 100-300 chunks
7. **PromoteToBlocks**:
   - Group chunks by finding_id
   - Filter: Only blocks containing "매출누락" at block level
   - Rank by score
   - Keep top 3
8. **ContextPack**: Format 3 blocks with citations
9. **ComposeAnswer**: LLM generates answer covering all 3 blocks
10. **Validate**: Check answer quality, add warnings if needed
11. **Return**: Final markdown answer with 3 audit cases + citations

