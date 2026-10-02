# Polymath HQ — AI Ecosystem Tool Registry

Updated: 2026-10-02

Purpose: a living catalogue of AI infrastructure and agent tools that HQ and downstream projects can consult before adding a dependency. `FREE` means open-source/self-hostable or a meaningful no-cost tier; it does **not** mean hosting, GPUs, third-party models, API calls, storage, or production infrastructure are necessarily free. Pricing and licenses must be rechecked before adoption.

## Selection rule

Prefer the smallest useful stack. Do not install every tool. HQ agents should check this registry during architecture planning, compare an existing dependency before adding a duplicate, keep provider adapters replaceable, keep secrets outside Git, and require human approval before enabling paid services.

## 1. Foundation models / inference

| Tool | Access label | Main use | Good fit for our projects |
|---|---|---|---|
| OpenAI GPT/API | PAID / product-dependent | reasoning, coding, multimodal, agents | HQ, AstroLab, Sajilo Retail, RateBridge, M&M, W2W |
| Anthropic Claude/API | PAID / product-dependent | reasoning, coding, long-context | HQ, coding/review workflows |
| Google Gemini API | FREE TIER + PAID | multimodal, reasoning, coding, large context | HQ, W2W, M&M, document/media workflows |
| Meta Llama | OPEN-WEIGHT, license-dependent | local/private LLM inference | HQ/local agents, privacy-sensitive workloads |
| Mistral | FREE MODE + PAID; some open models | efficient multilingual/coding/agent models | HQ, local/fallback inference, multilingual apps |
| Cohere | COMMERCIAL / trial or plan-dependent | enterprise language + embeddings/rerank | RAG-heavy enterprise apps |
| Hugging Face | FREE PLATFORM FEATURES + PAID COMPUTE | model/dataset hub, Spaces, inference | experimentation, open models, demos |
| Ollama | FREE / MIT SELF-HOSTED | run local models easily | **HQ local agent runtime; already strategically relevant** |
| vLLM | FREE / Apache-2.0 SELF-HOSTED | high-throughput model serving | later GPU/server deployment at scale |

Current verification notes: Gemini has a documented free API tier for selected models; Mistral has Free mode/API allowance; Hugging Face has free accounts/CPU Basic/ZeroGPU with limited inference credits; Ollama is MIT; vLLM is Apache-2.0. Hosted model use may still create compute/API cost.

## 2. Agent frameworks

| Tool | Access label | Main use | Recommended role |
|---|---|---|---|
| LangGraph / LangChain | OPEN SOURCE CORE + PAID LANGSMITH OPTIONS | stateful agent graphs, tools, RAG | strong candidate for explicit production workflows |
| CrewAI | OPEN-SOURCE ECOSYSTEM + FREE CLOUD BASIC + PAID ENTERPRISE | role-based multi-agent teams | useful for research/content/operations experiments |
| Microsoft AutoGen | FREE / MIT, MAINTENANCE MODE | multi-agent orchestration | reference/legacy only; do not choose for new HQ architecture |
| Microsoft Agent Framework | FREE / OPEN SOURCE SDK; provider costs separate | agents, workflows, tools, MCP, long-running tasks | **preferred Microsoft option for new agent work** |
| LlamaIndex Workflows | OPEN SOURCE CORE + hosted options | data/RAG-centric agents | knowledge-heavy applications |
| AWS Strands Agents | OPEN SOURCE SDK; AWS/model costs separate | model-driven agents/tools | useful if project moves onto AWS |
| CAMEL | OPEN SOURCE | multi-agent research/orchestration | experimentation/research |
| Agno | OPEN SOURCE CORE + commercial platform options | agent teams and multimodal apps | rapid prototypes |

Important: Microsoft's official AutoGen repository now says AutoGen is in maintenance mode and directs new users to Microsoft Agent Framework.

## 3. RAG / knowledge layer

| Tool | Access label | Main use | Project fit |
|---|---|---|---|
| LangChain | OPEN SOURCE CORE | retrieval pipelines/connectors | HQ knowledge, AstroLab source grounding |
| LlamaIndex | OPEN SOURCE CORE | document/data indexing and retrieval | HQ, W2W curriculum knowledge, M&M research |
| Haystack | OPEN SOURCE CORE | RAG/search pipelines | research-heavy apps |
| DSPy | OPEN SOURCE | programmatic optimization of LM pipelines | later quality/evaluation optimization |
| RAGFlow | OPEN SOURCE + hosted options | document-centric RAG | large document libraries |
| GraphRAG | OPEN SOURCE implementation ecosystem | graph-based retrieval | complex linked knowledge; only when ordinary RAG is insufficient |
| Unstructured | OPEN SOURCE CORE + API/commercial options | parse PDFs/docs/web content | document ingestion |
| EmbedChain | OPEN SOURCE | simple RAG application layer | prototypes |

## 4. Embeddings

| Tool | Access label | Main use | Project fit |
|---|---|---|---|
| OpenAI Embeddings | PAID API | embeddings/search | production RAG where quality/cost fits |
| Cohere Embed | PAID / plan-dependent | embeddings + enterprise search | enterprise RAG |
| Voyage AI | PAID / possible trial credits | retrieval embeddings/reranking | high-quality RAG evaluation candidate |
| Sentence Transformers | FREE / OPEN SOURCE | local embeddings | **excellent default for low-cost local RAG** |
| BGE | FREE / OPEN-WEIGHT MODELS | local retrieval embeddings | **strong low-cost RAG candidate** |
| Google Vertex AI Embeddings | CLOUD PAID / credits may apply | managed embeddings | Google-cloud deployments |
| Azure OpenAI Embeddings | CLOUD PAID | managed embeddings | Azure deployments |

## 5. MCP / interoperability

| Tool | Access label | Main use | Project fit |
|---|---|---|---|
| MCP SDK | OPEN SOURCE | standard tool/context protocol | **HQ-wide interoperability layer** |
| FastMCP | OPEN SOURCE CORE | rapidly build MCP servers/clients | expose our internal tools to agents |
| MCP Registry | FREE/OPEN ECOSYSTEM | discover MCP servers | discovery only; security review before use |
| GitHub MCP Server | OPEN SOURCE / GitHub account limits apply | repository actions from agents | **HQ Builder/Engineer workflows** |
| Slack MCP Server | MIXED / Slack plan/API limits | workspace actions | future team operations |
| PostgreSQL MCP Server | OPEN SOURCE implementations | database access via MCP | controlled internal data tools |
| Filesystem MCP Server | OPEN SOURCE implementations | file access | local agent workflows; sandbox carefully |

Security rule: third-party MCP servers are untrusted code/integrations until reviewed. Scope tokens minimally and never expose production secrets by default.

## 6. AI security / guardrails

| Tool | Access label | Main use | Project fit |
|---|---|---|---|
| NVIDIA NeMo Guardrails | FREE / OPEN SOURCE | programmable conversational guardrails | public-facing AI features |
| Guardrails AI | OPEN SOURCE CORE + hosted/commercial options | validate structured/LLM outputs | AstroLab, RateBridge, retail workflows |
| Microsoft Presidio | FREE / OPEN SOURCE | PII detection/redaction | **HQ-wide privacy layer** |
| Lakera Guard | COMMERCIAL / tier-dependent | prompt injection/security | higher-risk public agents |
| Prompt Security | COMMERCIAL | prompt/data security | enterprise deployments |
| Protect AI | MIXED open-source/commercial security tooling | ML/AI supply-chain security | CI/security review |
| Azure AI Content Safety | CLOUD PAID / allowance-dependent | content moderation | public apps on Azure |
| AWS Bedrock Guardrails | CLOUD PAID | model safety controls | AWS-hosted agents |

## 7. Evaluation / observability

| Tool | Access label | Main use | Project fit |
|---|---|---|---|
| LangSmith | FREE DEVELOPER TIER + PAID | tracing, evaluation, debugging | **HQ agent observability candidate** |
| Langfuse | OPEN SOURCE + hosted tiers | LLM tracing/evaluation | **strong self-hostable alternative** |
| Arize Phoenix | OPEN SOURCE + commercial ecosystem | tracing/evals | RAG/agent quality monitoring |
| Weights & Biases Weave | FREE/PAID depending plan | tracing/evaluation | experiments and model/app evaluation |
| TruLens | OPEN SOURCE CORE | RAG/LLM evaluation | RAG quality testing |
| Ragas | OPEN SOURCE | RAG evaluation | **useful for HQ knowledge/RAG test suites** |
| Promptfoo | OPEN SOURCE CORE | prompt/model red-team and evals | **CI evaluation/security tests** |
| Helicone | OPEN SOURCE + hosted plans | LLM observability/gateway | API-heavy applications |

## 8. Memory

| Tool | Access label | Main use | Project fit |
|---|---|---|---|
| Mem0 | OPEN SOURCE CORE + hosted paid options | long-term agent/user memory | HQ agents; compare with our existing memoryhub first |
| Zep | OPEN SOURCE/COMMERCIAL offerings | conversational/agent memory | long-running assistants |
| Letta | OPEN SOURCE CORE | stateful agents/memory | research candidate for persistent agents |
| LangGraph Memory | OPEN SOURCE CORE | workflow state/memory | useful if LangGraph becomes orchestration layer |
| Redis | OPEN SOURCE/COMMERCIAL variants | fast state/cache/vector data | production state/cache |
| PostgreSQL | OPEN SOURCE | durable relational + agent state | **preferred general durable store where appropriate** |
| Mem0/Chrome-style browser memory products | PRODUCT-DEPENDENT | personal/browser memory | evaluate case-by-case; avoid sensitive data without review |

## 9. Agent SDKs

| Tool | Access label | Main use | Project fit |
|---|---|---|---|
| OpenAI Agents SDK | OPEN SOURCE SDK; model/API usage may be paid | tool-using agents/handoffs/tracing | HQ and app agents using OpenAI models |
| LangChain Agents | OPEN SOURCE CORE | general tool agents | broad Python/JS agent projects |
| PydanticAI | OPEN SOURCE | typed Python agents | **excellent for reliable structured Python agents** |
| Semantic Kernel | OPEN SOURCE | enterprise agent/application SDK | Microsoft ecosystem; for new orchestration also evaluate Agent Framework |
| Google ADK | OPEN SOURCE SDK; provider/cloud costs separate | Google-oriented agents | Gemini/Google deployments |
| AWS Strands Agents | OPEN SOURCE SDK; provider costs separate | provider-flexible agent building | AWS or local model workflows |
| Azure AI Foundry Agent Service | MANAGED COMMERCIAL / cloud pricing | hosted enterprise agents | later enterprise deployment, not default |

## 10. Automation / workflow orchestration

| Tool | Access label | Main use | Project fit |
|---|---|---|---|
| n8n | SOURCE-AVAILABLE SELF-HOST + PAID CLOUD | app/API workflow automation | **very useful for M&M publishing, retail operations, notifications** |
| Zapier | FREE LIMITED + PAID | SaaS automation | quick integrations when self-hosting is unnecessary |
| Make | FREE LIMITED + PAID | visual automation | marketing/content workflows |
| Microsoft Power Automate | PAID / Microsoft licensing dependent | Microsoft 365 workflows | HR/office workflows rather than core HQ runtime |
| Temporal | OPEN SOURCE + CLOUD PAID | durable long-running workflows | **strong future choice for reliable autonomous jobs** |
| Apache Airflow | FREE / OPEN SOURCE | scheduled data pipelines | ETL/research pipelines |
| Prefect | OPEN SOURCE + CLOUD TIERS | Python workflow orchestration | data/research jobs |
| Kestra | OPEN SOURCE + commercial edition | event/scheduled orchestration | complex backend automation |
| Windmill | OPEN SOURCE + cloud tiers | scripts/workflows/internal tools | operations automation |

## 11. Vector databases / search

| Tool | Access label | Main use | Project fit |
|---|---|---|---|
| Pinecone | FREE STARTER + PAID | managed vector database | quick hosted RAG |
| Weaviate | OPEN SOURCE + CLOUD PAID | vector/hybrid search | substantial RAG systems |
| Qdrant | OPEN SOURCE + CLOUD FREE/PAID tiers | vector search | **strong self-host/local RAG choice** |
| Milvus | OPEN SOURCE + managed Zilliz options | large-scale vector search | high-scale future workloads |
| Chroma | OPEN SOURCE + cloud options | simple vector store | prototypes/local RAG |
| pgvector | FREE / OPEN SOURCE PostgreSQL extension | vectors inside Postgres | **excellent default when we already use PostgreSQL** |
| Elasticsearch | FREE/paid licensing depends distribution/features | search + vectors + analytics | search-heavy production systems |
| Redis | OPEN SOURCE/COMMERCIAL variants | vectors + cache/state | low-latency systems |
| MongoDB Atlas Vector Search | COMMERCIAL with Atlas free/paid tiers | vectors with document DB | MongoDB-based applications |

## HQ default shortlist

Before adding anything new, evaluate these first because they cover most of our likely needs with relatively low lock-in:

1. **Ollama** — local inference.
2. **Microsoft Agent Framework or LangGraph** — explicit agent/workflow orchestration; compare against our existing HQ architecture rather than replacing it automatically.
3. **MCP + GitHub MCP** — standardized tool integration.
4. **PydanticAI** — typed Python agents where reliability matters.
5. **PostgreSQL + pgvector** — durable data + vectors before adding a separate vector DB.
6. **Sentence Transformers/BGE** — local embeddings.
7. **Langfuse or LangSmith** — observability/evaluation.
8. **Ragas + Promptfoo** — automated quality, regression and adversarial tests.
9. **Microsoft Presidio + Guardrails AI/NeMo Guardrails** — privacy/output safety where applicable.
10. **n8n** — external SaaS/content automation; **Temporal** when jobs must be durable and recoverable.
11. **Qdrant** — when pgvector is no longer sufficient.
12. **Gemini/Mistral free allowances** — development/fallback experiments, never assume production usage remains free.

## Project routing examples

- **Polymath HQ:** Ollama, Agent Framework/LangGraph, MCP, GitHub MCP, PydanticAI, PostgreSQL/pgvector, Langfuse/LangSmith, Promptfoo, Ragas, Presidio, Temporal.
- **Sajilo Retail:** PostgreSQL/pgvector, PydanticAI, n8n, Presidio/guardrails, observability; vector search only for semantic catalogue/support features.
- **AstroLab:** structured PydanticAI/guardrails, PostgreSQL, evaluation/tracing; RAG only for sourced interpretive knowledge, never as a replacement for deterministic chart calculations.
- **Mind & Mythos:** n8n for publishing/monitoring, RAG for research library, local/open models where economical, R2/media storage architecture separately.
- **Wonder to Wisdom:** RAG for curriculum/source library, content safety/evals, n8n publishing automation, open embeddings/vector store.
- **RateBridge:** reliable workflows, PostgreSQL, observability/security; AI output must not become an unverified financial truth source.
- **AI learning repo:** Hugging Face, Ollama, LangChain/LangGraph, PydanticAI, RAG/eval tools are good hands-on learning targets.

## Cost governance

Every integration record should ultimately store: license, self-host availability, current free allowance, paid trigger, data/privacy implications, operational cost, project owner, approved use cases, alternatives, and last-verified date. Agents must re-check official pricing/license pages before implementation. No agent may activate billing, upgrade a plan, or commit credentials without explicit human approval.
