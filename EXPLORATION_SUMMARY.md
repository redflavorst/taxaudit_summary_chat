# Taxaudit Summary Chat - Codebase Exploration Summary

## Overview

This is a **Korean Tax Audit Document Q&A System** using LangGraph + Ollama + Elasticsearch + Qdrant. It processes user queries in Korean and returns relevant tax audit cases with detailed citations.

## Quick Reference

### Entry Point
- **File**: `/home/user/taxaudit_summary_chat/langgraph_agent/main.py`
- **Function**: `run_query(query: str) -> str`
- **Modes**:
  - Interactive: `python -m langgraph_agent.main`
  - Single Query: `python -m langgraph_agent.main "your question"`
  - Programmatic: Import `run_query` function

### Complete Query Processing Flow (11 Nodes)

```
USER QUERY (Korean text)
    ↓
[1] PREPROCESS → Text normalization, PII masking, stopword removal
    ↓
[2] PARSE_QUERY → Intent classification + LLM slot extraction
    ↓
[3] EXPAND_QUERY → Query expansion with domain vocabulary (Ollama)
    ↓
[4] ROUTE → Conditional branching (clarify/search/explain)
    ├→ [5] CLARIFY → Return clarification questions (END)
    ├→ [6-10] SEARCH PIPELINE
    │   ├→ RETRIEVE_FINDINGS → Hybrid search stage 1 (ES + Qdrant)
    │   ├→ RETRIEVE_CHUNKS → Hybrid search stage 2 by section
    │   ├→ PROMOTE_TO_BLOCKS → Aggregation + keyword filtering
    │   ├→ CONTEXT_PACK → Format blocks for LLM
    │   └→ [10] COMPOSE_ANSWER → LLM answer generation
    └→ [10] EXPLAIN → Direct answer (skip search)
    ↓
[11] VALIDATE → Quality check & fallback handling
    ↓
RETURN FINAL ANSWER
```

## Architecture Components

### 1. LangGraph Agent
- **File**: `langgraph_agent/graph.py`
- **State Type**: `AgentState` (complex TypedDict with 15+ fields)
- **11 Nodes**: Each transforms the state
- **Conditional Routing**: Routes to clarify/search/explain paths

### 2. Hybrid Retrieval System (RRF Fusion)
- **Stage 1**: Retrieve Findings (30 results)
  - Elasticsearch BM25 on `findings` index
  - Qdrant vector search on `findings_vectors` collection
  - Reciprocal Rank Fusion (RRF) merge
  - Document-level filtering (keyword intersection/union)

- **Stage 2**: Retrieve Chunks by Section (100-300 per section)
  - Two parallel searches: "조사착안" + "조사기법"
  - Both use hybrid search (ES + Qdrant)
  - Filtered to findings from stage 1

- **Stage 3**: Promote to Blocks (3 blocks max)
  - Group chunks by finding_id
  - Intersection priority (both sections present)
  - 5:5 blending if intersection small
  - Keyword filtering for multi-keyword queries

### 3. LLM Integration (Ollama)
- **Endpoint**: `http://localhost:11434/api/generate`
- **Model**: `gemma3:12b` (configurable)
- **Used In**:
  - ParseQuery: Slot extraction (industry, code, domain_tags)
  - ExpandQuery: Query expansion (must_have, should_have, related_terms)
  - ComposeAnswer: Final answer generation

### 4. Search Indices (Elasticsearch)
- **Indices**:
  - `findings`: Audit findings (finding_id, doc_id, item, code, reason_kw_norm)
  - `chunks`: Content chunks (chunk_id, finding_id, section, text, page, line)

### 5. Vector Collections (Qdrant)
- **Collections**:
  - `findings_vectors`: 1024-dim embeddings for findings
  - `chunks_vectors`: 1024-dim embeddings for chunks
- **Embedding Model**: `BAAI/bge-m3`
- **Storage**: Local path `./qdrant_storage` or server

### 6. PostgreSQL Database
- **Purpose**: Metadata storage during data ingestion
- **Database**: `ragdb` (postgresql://localhost:5432)
- **Tables**: documents, table_rows, findings, chunks, row_finding_map

## Key Features

### Multi-Stage Retrieval
1. **Document Filtering**: Keyword intersection for multi-keyword queries
2. **Hybrid Search**: Combine BM25 (lexical) + Vector (semantic) via RRF
3. **Section-Based Retrieval**: Separate "findings" vs "techniques"
4. **Block Aggregation**: Group chunks, rank by composite score
5. **Keyword Filtering**: Filter blocks by block-level keywords (2+ keyword queries)

### Query Understanding
- **Intent Classification**: "case_lookup" vs "explain"
- **Slot Extraction**: industry, code, domain_tags, entities, section_hints
- **Query Expansion**: LLM extracts must_have/should_have keywords with boost weights
- **Confidence Scoring**: 0.0-1.0 confidence triggers clarification

### Response Generation
- **Context Formatting**: Packed markdown with multiple blocks
- **Citation Management**: Page/line references for all content
- **Search Strategy Explanation**: Shows keyword priority & match counts
- **Additional Information**: Excluded blocks shown as supplementary info

## Configuration

**File**: `langgraph_agent/config.py`

Key Parameters:
- `OLLAMA_BASE_URL` = "http://localhost:11434"
- `OLLAMA_MODEL` = "gemma3:12b"
- `ES_URL` = "http://localhost:9200"
- `QDRANT_PATH` = "./qdrant_storage"
- `BLOCK_FINAL_TOP_N` = 3 (blocks in answer)
- `CONFIDENCE_THRESHOLD` = 0.4 (for clarification)
- `QDRANT_SCORE_THRESHOLD` = 0.35 (vector match threshold)

## Error Handling

- **Elasticsearch down**: Fall back to vector-only search
- **Qdrant down**: Fall back to BM25-only search
- **Ollama timeout**: Use rule-based fallback for slot extraction
- **Empty results**: Return "no matching cases" message
- **No blocks found**: Show clarification request

## Performance Optimizations

- **Embedding Cache**: LRU cache for query embeddings (100 max)
- **Keyword Frequency Cache**: Cached aggregation results
- **Single Aggregation Query**: ES aggregation reduces 15 queries → 1 query (15x improvement)
- **Lazy Loading**: Chunk text retrieved on-demand from ES if missing from Qdrant

## Data Flow Example

**Query**: "제조업에서 매출누락 조사기법은?"

1. **Preprocess**: Remove stopwords, normalize → "제조업 매출누락 조사기법"
2. **ParseQuery**: industry_sub=["제조업"], confidence=0.7
3. **ExpandQuery**: must_have=["제조업", "매출누락"], boost_weights={...}
4. **Route**: confidence > 0.4 & intent="case_lookup" → search
5. **RetrieveFindings**: Find docs with "제조업" AND "매출누락" (intersection) → 15-30 findings
6. **RetrieveChunks**: Search chunks with section="조사기법" → 100-300 chunks
7. **PromoteToBlocks**: Filter blocks containing "매출누락" → 3 blocks
8. **ContextPack**: Format 3 blocks with sections & citations
9. **ComposeAnswer**: LLM generates answer covering all cases
10. **Validate**: Verify answer quality
11. **Return**: Markdown answer with search strategy, cases, and references

## Important Files

| File | Purpose |
|------|---------|
| `langgraph_agent/main.py` | Entry point, CLI interface |
| `langgraph_agent/graph.py` | LangGraph pipeline definition |
| `langgraph_agent/state.py` | AgentState definition (15+ fields) |
| `langgraph_agent/config.py` | All configuration parameters |
| `langgraph_agent/retrieval.py` | HybridRetriever class (ES + Qdrant integration) |
| `langgraph_agent/nodes/*.py` | 11 processing nodes (preprocess to validate) |
| `langgraph_agent/logger.py` | Logging setup |
| `create_db/create_database.py` | Data ingestion pipeline |
| `create_db/vectorstore/` | Embedding & Qdrant integration |

## State Transformation

The `AgentState` is progressively enriched through the pipeline:

**Input Stage**:
- `user_query`: Original Korean question
- `normalized_query`: Cleaned/processed query
- `intent`: "case_lookup" or "explain"

**Processing Stage**:
- `slots`: Extracted industry, code, domain_tags, etc.
- `expansion`: Query expansion with must_have/should_have keywords

**Retrieval Stage**:
- `findings_candidates`: Top 30 findings from stage 1
- `chunks_candidates`: Unique chunks from stage 2
- `block_ranking`: Final 3 ranked blocks for answer
- `excluded_blocks`: Blocks filtered out by keyword matching

**Output Stage**:
- `context`: Packed text + citations for LLM
- `answer`: Final markdown answer
- `error`: Error message (if any)

## Testing the System

### Interactive Mode
```bash
cd /home/user/taxaudit_summary_chat
python -m langgraph_agent.main
# Prompts for query input in a loop
```

### Single Query
```bash
python -m langgraph_agent.main "제조업 매출누락 적출사례"
```

### Python Script
```python
from langgraph_agent.main import run_query
answer = run_query("제조업 매출누락 적출사례")
print(answer)
```

## System Requirements

- **Elasticsearch**: Running on port 9200 (BM25 text search)
- **Qdrant**: Local path ./qdrant_storage or server on port 6333
- **Ollama**: Running on port 11434 with gemma3:12b model
- **PostgreSQL**: rabdb database (for data ingestion)
- **Python**: 3.10+ with dependencies from requirements.txt

## Documentation Files Created

1. **CODEBASE_ANALYSIS.md** (673 lines)
   - Detailed analysis of all 11 nodes
   - Component integration details
   - Configuration parameters
   - Error handling strategies
   - Performance optimizations

2. **ARCHITECTURE_DIAGRAM.txt**
   - Visual system architecture
   - Pipeline flow
   - Component relationships
   - Configuration parameters

3. **EXPLORATION_SUMMARY.md** (this file)
   - Quick reference guide
   - Data flow example
   - File index
   - System requirements

---

**Generated**: 2025-10-23
**Analysis Level**: Very Thorough (11 nodes, 4 backends, complete flow mapping)
