# Private AI Code Assistant: Enterprise Infrastructure & TCO Report

**Version:** 2.0 | **Prepared:** April 2026  
**Audience:** Head of DevOps, Engineering Leadership, IT Decision Makers  
**Scope:** End-to-end infrastructure sizing and total cost of ownership for deploying a fully private, self-hosted AI coding assistant on Red Hat OpenShift

---

## 1. Executive Summary

Banking, financial services, government, and public sector organizations face sustained pressure to adopt AI-powered developer productivity tools. Parallel regulatory tightening—most notably the EU AI Act (high-risk obligations, **August 2026**), DORA operational resilience requirements (**enforcement from January 2025**), and U.S. federal expectations under **FedRAMP** and related programs—makes SaaS-first AI coding assistants structurally misaligned for many regulated estates. Primary risk themes: **source code and intellectual property** exposure to third-party AI operators; **data residency and sovereignty** failures when inference and logging leave approved jurisdictions; and **shadow AI**—**76% of organizations** are estimated to run **ungoverned** AI-generated code in production, amplifying supply-chain and security exposure. Sanctions under the EU framework can reach **up to €35 million or 7% of global annual turnover**, whichever is higher, in addition to operational and reputational loss.

**Problem statement.** These organizations need a **fully private** AI coding assistant: one where the **model weights, inference path, application logs, developer interactions, integrations, and operational tooling** are not merely contractually “ring-fenced” in a vendor’s multi-tenant cloud, but **architecturally isolated** on infrastructure the organization owns, locates, and audits end to end. That requirement extends from the IDE to the last GPU memory allocation.

**Solution positioning.** This report sizes a **Red Hat–centric** private stack: developer experience on **OpenShift DevSpaces** (cloud-hosted, standardized workspaces) with **VSCode** and compatible extensions (e.g., **Cline, OpenCode, Continue**); a governed inference plane comprising **Red Hat AI Gateway (GAIE)** for an **OpenAI-compatible** API with authentication and policy; **llm-d** (CNCF Sandbox) for KV-cache–aware scheduling and **prefix** reuse; **vLLM** for **PagedAttention**, continuous batching, and efficient quantization; and **OpenShift** on a managed service model—**ROSA (AWS)** or **OpenShift Dedicated (GCP)**—with **OpenShift AI** for model lifecycle, monitoring, and GPU placement.

**Key findings (this document):**

| Finding | Implication |
|--------|-------------|
| A single **NVIDIA L40S** GPU (illustrative on-demand **~$1.86/hr** in reference regions) can support **up to ~20 concurrent** developer workloads at **64K context** when paired with modern serving and batching. | Capital and cloud spend can be right-sized to measured concurrency, not headcount. |
| **Full stack** cost, including **OpenShift** and **OpenShift AI** subscriptions plus GPU and supporting compute at **50–200 developers**, typically ranges **~$18–41 per developer per month** at steady state (sensitive to model choice, SLO, and region). | TCO is predictable and defensible for finance and procurement. |
| **Hybrid MoE** models reduce **KV cache footprint** by roughly **75–95%** versus dense transformers of similar capability for many coding workloads. | Fewer GB/token of cache pressure improves batching, latency, and effective throughput. |
| Empirical team patterns: **peak concurrent** usage is often **15–20% of team size** across a **~10-hour** workday, not 1:1 with seats. | GPU counts should follow **concurrency and SLOs**, not org charts. |
| **PagedAttention** plus **prefix caching** (orchestrated at the gateway/scheduler) typically yields **~2.5–4×** **effective** concurrency versus naive static allocation for the same hardware. | Operational headroom without linear GPU scaling. |

---

## 2. The Case for Private AI Code Assistance

### 2.1 Market Drivers

| Driver | Relevance to AI coding assistants |
|--------|-----------------------------------|
| **EU AI Act** — high-risk use cases, including many **financial** AI systems; **August 2026** deadline for key obligations in scope | Product teams must show risk management, documentation, and oversight. Third-party “black box” APIs complicate defensibility. |
| **DORA** — in force; **Article 30** and broader ICT third-party and resilience themes push **sovereignty and exit** rigor for cloud and software supply chains (Jan 2025 enforcement context) | Contractual assurances are insufficient without **architectural** control and auditable operation. |
| **FedRAMP / DoD SRG** | U.S. public-sector adopters need **authorized** stacks, data boundaries, and logging aligned to agency baselines. |
| **Shadow AI** and **vibe coding** | Industry surveys point to a large share of teams using **public** AI in daily coding (**~35%** “vibe coding” in some enterprise samples); **1 in 8** breach narratives now reference **agentic** or AI-assisted code paths in vendor reporting—uncontrolled channels increase exfiltration and licensing risk. |
| **Private AI investment and adoption** | **~$109.1B** global private-AI–related spend in **2024**; enterprise “private AI” adoption estimates rose from **~55% to ~78%** in comparable survey windows—**control** and **residency** are no longer edge requirements. |

### 2.2 Customer Segments

| Segment | Primary regulatory / sector framework | Implications for AI coding |
|---------|----------------------------------------|----------------------------|
| **Banking / financial services** | **DORA**, **PCI DSS**, **Basel** data and resilience themes | All prompts, diffs, and tool logs must be governable; vendor clouds require exit and residency proofs. |
| **Government / defense** | **FedRAMP**, **ITAR**, classified programs | Air-gap, attested images, and strong identity boundaries; no incidental export of fragments to unapproved networks. |
| **Healthcare** | **HIPAA**; patient data in **EHR** and adjacent systems | Minimum-necessary flow; BAAs and audit; PHI must not cross unapproved paths—even in “code completion” if context can embed identifiers. |
| **Telecom / critical infrastructure** | **NIS2** (EU); sector-specific security rules | Uptime, incident reporting, and supply-chain security—tightly coupled to controlled CI/CD and model supply chain. |

### 2.3 Why SaaS Falls Short

SaaS AI coding products deliver speed to value but, for the segments above, often collide with **non-negotiables** in **data path**, **evidence**, and **commercial exposure**.

| Dimension | SaaS AI coding (e.g., hosted Copilot-class) | Private deployment (OpenShift + gateway + self-hosted models) |
|-----------|---------------------------------------------|-----------------------------------------------------------------|
| **Data residency** | Tied to vendor regions; subprocessors and data maps required | Residency enforced by **cluster region**, network policy, and storage—**no** third-party inference operator in the path by default |
| **IP control** | Vendor terms and DLP mitigations; limited visibility into training retention and abuse monitoring | Weights, logs, and backups remain **in customer** or designated sovereign footprint |
| **Model customization** | Finetune / private index features vary; often add-on and region-limited | **Open-weight** models; **RAG** and **fine-tune** on customer data **inside** the boundary |
| **Audit trail ownership** | Vendor-held logs; export APIs may be incomplete for forensic reconstruction | **Immutable** logging to customer SIEM; **correlate** IDE → gateway → model with internal IDs |
| **Air-gap capability** | Not generally available at parity | Feasible with **disconnected** registries, mirrored bases, and on-prem / isolated cloud |
| **Vendor lock-in risk** | API and IDE tie-in; org-wide workflow dependency | **OpenAI-compatible** surface; **portable** models and **GitOps**-style lifecycle |
| **Per-seat cost scaling** | **Linear** per user at published list (often **$19–39**/user/mo for common tiers) | **Sub-linear** with GPU pooling—cost tracks **concurrency and SLO**, not seat count |

---

## 3. Solution Architecture

### 3.1 End-to-End Stack Overview

**Frontend (developer experience).** Engineers use **VSCode** with AI extensions such as **Cline**, **OpenCode**, and **Continue**. Workspaces are delivered through **OpenShift DevSpaces**—**browser-accessible** or **local-IDE**—connected to the same **pre-approved** image and **secret** model so extension configuration is **standardized** and **auditable**. No local GPU is required: the heavy inference runs in the **cluster**. Extensions call the organization’s **private** **OpenAI-compatible** endpoint, not a public API.

**Backend (AI inference platform).** **Red Hat AI Gateway (GAIE)** fronts the service with an **OpenAI-compatible** API, **identity**, **rate limits**, and **model routing**. **llm-d** (CNCF Sandbox) performs **KV-cache–aware** request routing, improves **colocation** of related turns, and **reuses** **prefixes** (system prompts, repo snippets) to avoid redundant prefill. **vLLM** implements **PagedAttention**, **continuous batching**, and **FP8/INT8** execution paths to maximize tokens/sec per dollar. **GPU (or other accelerator) worker nodes** run **vLLM** pods; sizing references **NVIDIA L40S**, **H100**, **H200**, **B200**—or **approved alternatives** per procurement.

**Platform (infrastructure).** The cluster is **ROSA (Red Hat OpenShift on AWS)** or **OSD (OpenShift Dedicated on GCP)**. **Hosted control plane** options reduce day-0/1 toil. **OpenShift AI** provides **model** lifecycle, **observability**, and **GPU** scheduling integration. **Infrastructure worker nodes** (example pattern: **3× m5.2xlarge–class** nodes) host control-plane-adjacent and shared services, including elements of **OpenShift AI** and **gateway** when not on dedicated inferencing pools.

**Reference diagram (logical):**

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Developer Workstations                                                │
│  ┌──────────────────┐  ┌──────────────────┐       ┌────────────────┐  │
│  │ VSCode + Cline   │  │ VSCode + OpenCode│  ...  │ Developer N    │  │
│  └────────┬─────────┘  └────────┬─────────┘       └───────┬────────┘  │
└───────────┼──────────────────────┼─────────────────────────┼──────────┘
            │                      │                         │
┌───────────▼──────────────────────▼─────────────────────────▼──────────┐
│  ROSA Cluster (AWS) / OpenShift Dedicated (GCP)                       │
│                                                                       │
│  ┌─────────────────────────────────────────┐                         │
│  │  OpenShift DevSpaces                    │                         │
│  │  (Cloud-hosted VSCode workspaces)       │                         │
│  └────────────────┬────────────────────────┘                         │
│                   │                                                   │
│  ┌────────────────▼────────────────────────┐                         │
│  │  Red Hat AI Gateway (GAIE)              │                         │
│  │  OpenAI-compatible API / Auth / Routing │                         │
│  └────────────────┬────────────────────────┘                         │
│                   │                                                   │
│  ┌────────────────▼────────────────────────┐                         │
│  │  llm-d Scheduler (CNCF Sandbox)         │                         │
│  │  KV-cache-aware request routing         │                         │
│  │  Prefix cache reuse across turns        │                         │
│  └───┬────────────┬────────────┬───────────┘                         │
│      │            │            │                                      │
│  ┌───▼───┐   ┌────▼───┐   ┌───▼───┐                                 │
│  │ vLLM  │   │ vLLM   │   │ vLLM  │  GPU / Accelerator Worker Nodes │
│  │Pod GPU│   │Pod GPU │   │Pod GPU│                                  │
│  └───────┘   └────────┘   └───────┘                                  │
│                                                                       │
│  ┌───────────────────────────────────────┐                           │
│  │  Infrastructure Worker Nodes          │                           │
│  │  3× m5.2xlarge (OpenShift AI, etc.)   │                           │
│  └───────────────────────────────────────┘                           │
└───────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Roles

| Component | Role | DevOps / leadership notes |
|-----------|------|---------------------------|
| **OpenShift DevSpaces** | Standardized cloud VSCode (and compatible) workspaces; injects org CA, secrets, and extension configuration | Repeatable onboarding; fewer “works on my machine” failures and ad hoc API keys on laptops |
| **VSCode + extensions (Cline, OpenCode, Continue)** | IDE-native chat, apply-patch, and agentic flows over the private endpoint | Central allowlisting of extension IDs and versions |
| **Red Hat AI Gateway (GAIE)** | OpenAI-compatible entry; authN/Z, quotas, model routing, observability | One policy and metering surface for all clients (IDE, CI, services) |
| **llm-d** | Schedules requests to vLLM with KV-cache locality; prefix/turn reuse | Better time-to-first-token and cost per token on multi-turn sessions |
| **vLLM** | PagedAttention, continuous batching, FP8/INT8 quantization (as configured) | Throughput and tail latency per accelerator dollar |
| **GPU / accelerator nodes** | Weights in VRAM; optional MIG or time-slicing | Most material cost line—size to observed concurrency, not headcount |
| **ROSA / OSD** | Managed OpenShift with consistent API and security model | FedRAMP-authorized service options where applicable (varies by offering/region) |
| **OpenShift AI** | Model catalog, deployment automation, monitoring | Reduces custom glue from GitOps/CI to live inference |
| **Infra workers (e.g., 3× m5.2xlarge)** | Control-plane–adjacent and shared services | Non-GPU footprint budgeted separately from accelerators |

### 3.3 Memory Efficiency: PagedAttention and Prefix Caching

**PagedAttention.** Dense transformer inference stores **key–value (KV) activations** for every token. Naive implementations **pre-allocate** long contiguous blocks per sequence—wasting **VRAM** when **contexts** are shorter than the maximum, and **stranding** memory when sessions **idle** between calls. **PagedAttention** maps KV storage to **non-contiguous** **pages** (analogous to **virtual memory**), allocating **on demand** as the sequence grows and **reclaiming** pages **immediately** when a **sequence** completes. **Effect:** **Near-zero** steady-state **VRAM** for **idle** users; much higher **packing** of active work onto the same GPU.

**Prefix caching and llm-d.** In multi-turn coding, a long shared prefix (system policy, org standards, frequently repeated file snippets) is often identical across turns and users. With gateway and scheduler configuration, **llm-d** can route related requests to workers that already hold a warmed prefix; **vLLM** can reuse those blocks in paged form. The net effect is less redundant prefill work and better batching on common prompt structures.

**Illustrative comparison: static pre-allocation vs. PagedAttention (200-person engineering organization)**

Assumptions (illustrative only): 32K working context cap in policy; 8-bit KV reference band; peak concurrent users ≈ 30% of the broader 200-person population (~60 active). Let **T** denote one notional “full static max-context KV reservation” for a single session at the org’s configured cap.

| Model | Static reservation strategy (illustrative) | PagedAttention + prefix-aware routing (illustrative) | Interpretation |
|-------|---------------------------------------------|------------------------------------------------------|----------------|
| **Dense 34B** (reference class) | ~200 × *T* (one max-context slot per licensed seat) | ~60 peak × 0.45–0.6 *T* ≈ 27–36 *T* equivalent at 30% peak | ≈5–7× lower VRAM pressure for the same org size when idle sessions release pages |
| **Hybrid MoE** (coding-tuned) | ~200 × 0.2 *T* (active experts only; ~75% KV reduction vs. dense at comparable quality tier) | ~60 peak × 0.09–0.12 *T* | MoE and paging compound; more concurrent streams per L40S / H100 class GPU |
| **Operational takeaway** | Over-provision accelerators to worst-case static KV | Size to measured p95 concurrent streams and SLO | Aligns spend to observed peaks (Section 1), not 1:1 with seat count |

*Note: Values use relative unit “T”; absolute VRAM in GB depends on model card, tensor-parallel width, vLLM page size, and quantization. Validate on target weights with representative production traces.*

---

## 4. Red Hat Solution Advantages

### 4.1 Advantage Summary

| Capability | Technical detail | Enterprise outcome |
|------------|------------------|--------------------|
| **No per-developer “AI tax” on the model** | Open-weight models; you pay for infrastructure and support, not a per-completer license | TCO tracks concurrency, not per-seat entitlements in LDAP or IdP |
| **Compounding efficiency** | Smaller active KV in MoE models, PagedAttention, prefix routing via llm-d, FP8/INT8 in vLLM | Fewer GPUs for the same SLO; lower time-to-first-token on warm prefixes |
| **Data isolation** | Code, prompts, and logs stay in-cluster and in customer logging sinks | Aligned to sovereignty, DORA, and cross-border data rules when architected to policy |
| **Hardening and crypto** | FIPS 140-2/3 where supported; CMEK at rest; mTLS between tiers (as deployed) | Maps cleanly to control frameworks and RFP language |
| **Transparent models** | Open weight artifacts, verifiable digests, no opaque remote model ID | Model governance, SBOM-style traceability, internal approval workflows |
| **Day-2 operations** | OpenShift AI for GPU node/driver coordination (within platform support boundaries), rollouts, observability | Shorter MTTR; less bespoke Kubernetes glue |
| **Vendor support** | 24×7 Red Hat production support; predictable release cadence | Clear operational backstop vs. pure DIY |

### 4.2 Security and Data Sovereignty

**Data flow (all inside the managed cluster boundary).**

1. **Developer** → (browser or local) **VSCode** in **OpenShift DevSpaces** or a corporate-managed endpoint  
2. **DevSpaces workspace** → private ClusterIP (or service mesh) path to **Red Hat AI Gateway (GAIE)**  
3. **AI Gateway** → **llm-d** (KV-aware scheduler and router)  
4. **llm-d** → **vLLM** on **GPU** workers (no public internet egress required for model inference)  
5. **Telemetry** to the organization’s **SIEM** and **OpenShift** monitoring, subject to policy  

**Comparative risk posture**

| Risk dimension | SaaS AI coding | DIY Kubernetes + ad hoc serving | **Red Hat** platform + gateway + OpenShift AI |
|----------------|----------------|--------------------------------|-------------------------------------------------|
| **Data path control** | Vendor-defined; subprocessors | Customer-owned, but high integration debt | Strong defaults; supported policy and egress patterns |
| **Provable logging** | Export-limited; forensic gaps | Feasible; you build the full chain | Cluster-native observability; SIEM integration with stable contracts |
| **Model supply chain** | Opaque weights | Customer-curated; no vendor K8s patch stream | Hardened base images; documented lifecycle and vendor support vs. DIY |
| **Time to compliant baseline** | Low | High (team-dependent) | Medium; usually faster than raw DIY for comparable scope |
| **Ongoing assurance** | Vendor attestations | Fully customer-owned | Shared responsibility with explicit boundaries (managed OpenShift) |

### 4.3 Operational Advantages

| Area | **Manual** / custom stack | **Red Hat** (OpenShift + OpenShift AI + supported gateway patterns) |
|------|---------------------------|----------------------------------------------------------------------|
| **GPU driver and node compatibility** | SRE-owned test matrix; outage risk on undisciplined upgrades | Certified paths; tested combinations for RHOAI-managed stacks |
| **Model deployment and rollback** | Custom Helm/Operators; inconsistent governance | OpenShift AI rollouts; GitOps-friendly patterns when adopted |
| **Horizontal scaling and queueing** | DIY HPA + bespoke queues; tuning burden | llm-d plus OpenShift autoscaling hooks (subject to GPU headroom) reduce custom code |
| **Security patching** | Full customer velocity for generic Kubernetes | RHEL core and OpenShift errata; less patch sprawl than generic Linux DIY |
| **Compliance evidence** | Scattered tickets and one-off scripts | API and audit trails in a single platform story |
| **Monitoring / SLOs** | Ad hoc Prometheus + Grafana | Integrated cluster observability; faster SLO dashboards |

### 4.4 Cost Structure Advantage

**Per-seat model licensing (typical public list bands).** Commercial SaaS AI coding products often publish **$19–39** per user per month for Individual or small-team tiers, with Enterprise (SSO, policy, org-wide) at or above that band depending on commit size and whether the product is bundled with a broader development platform. A **200-developer** team at **$39**/user is **$7,800**/month in licensing before any self-hosted controls for residency, logging, or model isolation.

**Private platform TCO (illustrative).** For pooled accelerators and efficient serving, all-in **OpenShift**, **OpenShift AI**, **GPU and non-GPU** workers, data transfer, backup, and SIEM attach for the reference architecture in this report frequently falls in the **~$18–41 per developer per month** range at **50–200** developers (Section 1), subject to model choice, region, reservation coverage, and SLO. Red Hat is not priced as “per completer for the model layer”; customers acquire subscriptions and bring GPU capacity—TCO is dominated by **concurrency and infrastructure**, not a per-developer **inference** meter from the model vendor.

**Illustrative monthly comparison: published Enterprise-style SaaS vs. private Red Hat–pattern TCO (midpoint)**

*Assumptions: SaaS list **$39**/user/mo; private stack **$29**/dev/mo (midpoint of the **$18–41** band from Section 1 for a notional reference footprint). Real deployments require a formal TCO with actual list prices, committed use, and FinOps for shared services.*

| Team size (developers) | SaaS @ $39/user/mo (illustrative) | Private stack @ $29/dev/mo (illustrative midpoint) | Delta (private − SaaS) / month |
|------------------------|------------------------------------|------------------------------------------------------|----------------------------------|
| 50 | $1,950 | $1,450 | −$500 (~−26% vs. list SaaS in this scenario) |
| 100 | $3,900 | $2,900 | −$1,000 |
| 200 | $7,800 | $5,800 | −$2,000 |

**GPU efficiency (quantified, composite).** In representative coding workloads, hybrid **MoE** models can cut active **KV** by **~75–95%** versus dense peers at a comparable capability tier. **PagedAttention** and **prefix** caching (Section 3.3) often yield **~2.5–4×** effective concurrency on the same fixed hardware. These effects are multiplicative in practice (model- and trace-dependent) and support the **~20** concurrent-developer class outcome on a **single** **L40S** at **64K** context in Section 1 when serving, batching, and policy are tuned to measured load.

---

## 5. Model Selection & Benchmarks

### 5.1 Model Specifications

| Model | Architecture | Total Params | Active Params | FP8 Weights | KV/Token | vLLM Support |
|-------|-------------|-------------|---------------|-------------|----------|-------------|
| Qwen3.6-35B-A3B | DeltaNet hybrid MoE | 35.2B | 3.3B | 35.2 GB | ~10 KB | Yes (flash-linear-attention) |
| Qwen3.6-27B | DeltaNet hybrid Dense | 27.2B | 27.2B | 27.2 GB | ~10 KB | Yes |
| Qwen3-Coder-Next 80B | DeltaNet hybrid MoE | 79.6B | ~10B | ~78 GB | ~10 KB | Yes (vLLM 0.12+) |
| Qwen3-Coder-30B-A3B | Standard MoE | 30.5B | 3.3B | 30.5 GB | 48 KB | Yes |
| Gemma 4 27B-A4B | Standard MoE + SWA | 27.2B | ~4B | 27.2 GB | 80 KB | Yes |
| Nemotron Nano 30B-A3B | Mamba-2 + MoE | ~30B | 3.3B | ~30 GB | ~4 KB | Yes |

DeltaNet hybrid models replace 70-90% of attention layers with linear attention (O(1) state vs O(n) KV cache), dramatically reducing per-token memory for long contexts. Standard MoE models use full quadratic attention and accumulate proportionally larger KV caches.

### 5.2 Benchmark Scores (Software Development)

| Model | SWE-bench Verified | SWE-bench Pro | LiveCodeBench v6 | HumanEval |
|-------|--------------------|---------------|-------------------|-----------|
| Qwen3.6-27B (Dense) | **76.2%** | 37.0% | 49.2% | 92.1% |
| Qwen3.6-35B-A3B (MoE) | 73.4% | 35.2% | 47.8% | 90.2% |
| Qwen3-Coder-Next 80B | 65.4% | — | 42.1% | 87.8% |
| Qwen3-Coder-30B-A3B | — | — | 40.3% | — |
| Gemma 4 27B-A4B | 36.2% | — | 41.6% | 85.4% |
| Nemotron Nano 30B-A3B | 26.0% | — | 38.5% | 82.3% |

### 5.3 Code Quality Ranking

| Rank | Model | SWE-bench V. | Assessment | Deployment Trade-off |
|------|-------|-------------|------------|---------------------|
| 1 | Qwen3.6-27B (Dense) | 76.2% | Highest code quality | 9x compute per token vs MoE; impractical for multi-user on mid-tier GPUs |
| 2 | Qwen3.6-35B-A3B (MoE) | 73.4% | Near-best quality, best efficiency | **Recommended.** 95% quality of dense at 3B active params |
| 3 | Coder-Next 80B | 65.4% | Strong, needs premium GPU | Requires H200 (141 GB). Premium-tier option |
| 4 | Gemma 4 27B-A4B | ~40% est | Good synthesis | Heaviest KV cache limits concurrency |
| 5 | Nemotron Nano 30B-A3B | 26.0% | Moderate | Best capacity efficiency, lower code quality |
| 6 | Qwen3-Coder-30B-A3B | — | Limited coverage | Only model compatible with Trainium/TPU |

**Key insight:** Qwen3.6-35B-A3B (Rank 2) offers 95% of the code quality of the dense 27B while requiring only 3B active parameters — a 9x reduction in per-token compute that translates to 4-8x more concurrent users per GPU.

---

## 6. GPU & Accelerator Options

### 6.1 NVIDIA GPU Specifications

All pricing: US East (N. Virginia) / us-east-1. 3yr NU SP = 3-year No Upfront Savings Plan.

| GPU | VRAM | Memory BW | FP8 Compute | Best Instance | vCPUs | On-Demand $/hr | 3yr NU SP $/hr |
|-----|------|-----------|-------------|---------------|-------|---------------|----------------|
| L40S | 48 GB | 864 GB/s | 733 TF | g6e.xlarge (1 GPU) | 4 | $1.86 | $0.93 |
| A100 80GB | 80 GB | 2,039 GB/s | — (FP16: 624 TF) | p4de.24xlarge (8 GPU) | 96 | $27.45 | $14.27 |
| H100 80GB | 80 GB | 3,352 GB/s | 3,958 TF | p5.4xlarge (1 GPU) | 16 | $6.88 | ~$3.44 |
| H200 141GB | 141 GB | 4,800 GB/s | 3,958 TF | p5en.48xlarge (8 GPU) | 192 | $74.69 | $48.55 |
| B200 192GB | 192 GB | 8,000 GB/s | 9,000 TF | p6-b200.48xlarge (8 GPU) | 192 | $113.93 | ~$91.14 |

### 6.2 Instance Size Optimization

Single-GPU instances (g6e.xlarge, p5.4xlarge) are preferred when tensor parallelism is not required:
- Zero GPU waste for small teams
- Lower vCPU count reduces OpenShift subscription costs (fewer 4-vCPU license units)

| Instance | GPUs | Team ≤50 Needs | Idle GPUs | Wasted $/mo |
|----------|------|----------------|-----------|------------|
| g6e.xlarge | 1 | 1 | 0 | $0 |
| g6e.48xlarge | 8 | 1 | 7 | $4,767 |
| p5.4xlarge | 1 | 1 | 0 | $0 |
| p5.48xlarge | 8 | 1 | 7 | $17,570 |

### 6.3 Alternative Accelerators (Phase 2)

DeltaNet hybrid models (highest quality) require NVIDIA CUDA. Alternatives are limited to Qwen3-Coder-30B-A3B (standard MoE).

| Accelerator | Chip Mem | Instance | Chips | Slots @ 64K | $/hr | Platform |
|-------------|---------|----------|-------|-------------|------|----------|
| Inferentia2 | 32 GB | inf2.24xlarge | 6 | 29 | $6.49 | ROSA (AWS) |
| Trainium2 | 96 GB | trn2.48xlarge | 16 | 416 | $35.76 | ROSA (AWS) |
| TPU v6e | 32 GB | ct6e-standard-4t | 4 | 29 | $5.40 | OSD (GCP) |
| TPU v7 | 192 GB | 4-chip VM | 4 | 212 | $24.00 | OSD (GCP) |

Alternatives trail NVIDIA L40S on cost-per-developer (3-10x more expensive) due to larger minimum deployment units and lower model quality.

---

## 7. Recommendations by Team Size

### 7.1 Sizing Methodology

- **Peak concurrency** = 20% of team size (65% online × 25% actively generating × 1.2 buffer)
- **Minimum sustained throughput:** 20 tokens/second per active developer
- **Concurrent users per GPU** = min(VRAM_limit, Bandwidth_limit)
- **VRAM limit** = (GPU_VRAM − model_weights − 2 GB overhead) / KV_per_request
- For MoE models (3B active params), VRAM is always the binding constraint

### 7.2 Three Perspectives

#### Perspective A: Best Value (Lowest $/dev/mo)

**Model:** Qwen3.6-35B-A3B (DeltaNet MoE) | **GPU:** L40S (g6e.xlarge)

| Team | Peak Slots | GPUs (64K) | Instance Config | GPU $/mo (3yr SP) |
|------|-----------|-----------|-----------------|------------------|
| 1 dev | 1 | 1× L40S | 1× g6e.xlarge | $679 |
| 10 devs | 2 | 1× L40S | 1× g6e.xlarge | $679 |
| 20 devs | 4 | 1× L40S | 1× g6e.xlarge | $679 |
| 50 devs | 10 | 1× L40S | 1× g6e.xlarge | $679 |
| 100 devs | 20 | 2× L40S | 2× g6e.xlarge | $1,358 |
| 200 devs | 40 | 3× L40S | 3× g6e.xlarge | $2,037 |

17 concurrent users per L40S at 64K context.

#### Perspective B: Best Code Quality

**Model:** Qwen3-Coder-Next 80B (DeltaNet MoE, 65.4% SWE-bench) | **GPU:** H200 (p5en.48xlarge)

| Team | Peak Slots | Instance Config | Slots Available | GPU $/mo (3yr SP) |
|------|-----------|-----------------|----------------|------------------|
| 1-100 devs | 1-20 | 1× p5en.48xlarge | ~776 | $35,442 |
| 200 devs | 40 | 1× p5en.48xlarge | ~776 | $35,442 |

p5en.48xlarge has massive excess capacity for teams ≤200. Premium-tier option for organizations where code quality justifies the cost premium.

#### Perspective C: Best Balance (Recommended)

**Model:** Qwen3.6-35B-A3B (73.4% SWE-bench) | **GPU:** L40S for teams ≤200

Qwen3.6-35B-A3B achieves 73.4% SWE-bench — only 2.8 percentage points below the dense 27B — at a fraction of the infrastructure cost. Same infrastructure as Perspective A. **This is the recommended path for most organizations.**

### 7.3 Context Length Impact

| Team | Peak Slots | 32K GPUs | 64K GPUs | 128K GPUs |
|------|-----------|---------|---------|----------|
| 50 devs | 10 | 1× L40S | 1× L40S | 2× L40S |
| 100 devs | 20 | 1× L40S | 2× L40S | 3× L40S |
| 200 devs | 40 | 2× L40S | 3× L40S | 5× L40S |

Most agentic coding workloads operate within 32K-64K effective context. Reserve 128K for power users; use llm-d to route long-context traffic to appropriately sized replicas.

---

## 8. Technical Data Views

### 8.1 Per-Model Concurrency and Throughput (L40S, 64K Context)

| Model | Active Params | KV/Token | FP8 Weights | Avail VRAM | KV @ 64K | Max Users | Per-User tok/s | Binding |
|-------|--------------|----------|-------------|-----------|---------|-----------|---------------|---------|
| Qwen3.6-35B-A3B | 3.3 GB | ~10 KB | 35.2 GB | 10.8 GB | 0.63 GB | 17 | 25 | VRAM |
| Qwen3.6-27B | 27.2 GB | ~10 KB | 27.2 GB | 18.8 GB | 0.63 GB | 29 | 1.9 | Bandwidth |
| Qwen3-Coder-30B-A3B | 3.3 GB | 48 KB | 30.5 GB | 15.5 GB | 3.0 GB | 5 | 42 | VRAM |
| Gemma 4 27B-A4B | ~4 GB | 80 KB | 27.2 GB | 18.8 GB | 5.0 GB | 3 | 44 | VRAM |
| Nemotron Nano 30B | 3.3 GB | ~4 KB | ~30 GB | 16.0 GB | 0.25 GB | 64 | 13 | Bandwidth |

Qwen3.6-27B achieves only 1.9 tok/s per user at full batch on L40S — below the 20 tok/s minimum. Dense models require H100+ for multi-user serving.

### 8.2 Per-Context-Length View (Qwen3.6-35B-A3B on L40S)

| Context | KV/Request | Users/GPU | Per-User tok/s | 100-dev GPUs | 200-dev GPUs |
|---------|-----------|----------|---------------|-------------|-------------|
| 16K | 0.16 GB | 67 | 40 | 1 | 1 |
| 32K | 0.32 GB | 33 | 32 | 1 | 2 |
| 64K | 0.63 GB | 17 | 25 | 2 | 3 |
| 128K | 1.26 GB | 8 | 20 | 3 | 5 |
| 256K | 2.52 GB | 4 | 16* | 5 | 10 |

*Below 20 tok/s minimum at 256K — consider H100 for very large contexts.

### 8.3 Per-GPU View (Qwen3.6-35B-A3B, 64K Context)

| GPU | VRAM | Avail | Users/GPU | Per-User tok/s | Instance | $/hr (3yr SP) | $/user/mo |
|-----|------|-------|----------|---------------|---------|--------------|----------|
| L40S | 48 GB | 10.8 GB | 17 | 25 | g6e.xlarge | $0.93 | $40 |
| A100 | 80 GB | 42.8 GB | 68 | 30 | p4de.24xlarge* | $14.27 | $26 |
| H100 | 80 GB | 42.8 GB | 68 | 49 | p5.4xlarge | $3.44 | $37 |
| H200 | 141 GB | 103.8 GB | 166 | 52 | p5en.48xlarge* | $48.55 | $36 |
| B200 | 192 GB | 154.8 GB | 248 | 53 | p6-b200.48xlarge* | $91.14 | $45 |

*Multi-GPU instances (8 GPUs). For small teams, excess GPUs are wasted.

### 8.4 Alternative Accelerator View (Qwen3-Coder-30B-A3B, 64K)

Limited to Qwen3-Coder-30B-A3B (standard MoE) — DeltaNet models not supported.

| Accelerator | Instance | $/hr | Slots @ 64K | $/dev/mo @ 100 | $/dev/mo @ 200 |
|-------------|---------|------|-------------|---------------|---------------|
| Inf2 | inf2.24xlarge | $6.49 | 29 | $47 | $47 |
| TPU v6e | ct6e-standard-4t | $5.40 | 29 | $39 | $39 |
| Trn2 | trn2.48xlarge | $35.76 | 416 | $261 | $131 |
| TPU v7 | 4-chip VM | $24.00 | 212 | $175 | $88 |
| **L40S (ref)** | **g6e.xlarge** | **$0.93** | **17** | **$14** | **$10** |

L40S reference uses 3yr SP with superior Qwen3.6-35B-A3B model.

---

## 9. Total Cost of Ownership (3-Year)

### 9.1 Cost Components

Every deployment consists of a single OpenShift cluster:

| Component | Description | Pricing Model |
|-----------|-------------|---------------|
| **Hosted Control Plane** | ROSA/OSD management plane | Flat $0.25/hr (not discountable) |
| **GPU Worker Nodes** | EC2 instances with GPUs | 3yr No Upfront Savings Plan |
| **Infrastructure Worker Nodes** | 3× m5.2xlarge for OpenShift AI, monitoring, registry | 3yr No Upfront Savings Plan |
| **OpenShift Subscription** | ROSA/OSD worker node licensing per 4 vCPUs | $667/4-vCPU/yr (3yr plan) |
| **OpenShift AI Subscription** | AI platform licensing for all worker nodes | $0.022/vCPU/hr |

**Pricing assumptions:**
- AWS region: US East (N. Virginia) / us-east-1
- OpenShift subscription tiers: PayGo $1,500/4-vCPU/yr | 1yr $1,000/4-vCPU/yr | **3yr $667/4-vCPU/yr** (used)
- m5.2xlarge: 8 vCPUs, $0.384/hr on-demand, $0.166/hr 3yr SP (57% discount)
- g6e.xlarge: 4 vCPUs, $1.86/hr on-demand, $0.93/hr 3yr SP (50% discount)
- Same subscription pricing model for both ROSA (AWS) and OSD (GCP)

### 9.2 Full-Stack TCO: Best Value Configuration

**Qwen3.6-35B-A3B on L40S (g6e.xlarge), 64K context, 3-year commitment**

| Component | 1 dev | 10 devs | 20 devs | 50 devs | 100 devs | 200 devs |
|-----------|-------|---------|---------|---------|----------|----------|
| GPU Nodes | 1× g6e.xl | 1× g6e.xl | 1× g6e.xl | 1× g6e.xl | 2× g6e.xl | 3× g6e.xl |
| GPU vCPUs | 4 | 4 | 4 | 4 | 8 | 12 |
| Infra Nodes | 3× m5.2xl | 3× m5.2xl | 3× m5.2xl | 3× m5.2xl | 3× m5.2xl | 3× m5.2xl |
| Infra vCPUs | 24 | 24 | 24 | 24 | 24 | 24 |
| **Total vCPUs** | **28** | **28** | **28** | **28** | **32** | **36** |
| | | | | | | |
| Hosted Control Plane | $183 | $183 | $183 | $183 | $183 | $183 |
| EC2 GPU (3yr SP) | $679 | $679 | $679 | $679 | $1,358 | $2,037 |
| EC2 Infra (3yr SP) | $364 | $364 | $364 | $364 | $364 | $364 |
| OCP Subscription (3yr) | $389 | $389 | $389 | $389 | $445 | $500 |
| OCP AI Subscription | $450 | $450 | $450 | $450 | $514 | $578 |
| **Total Monthly** | **$2,065** | **$2,065** | **$2,065** | **$2,065** | **$2,864** | **$3,662** |
| **Per Developer / Month** | $2,065 | $207 | $103 | **$41** | **$29** | **$18** |
| **3-Year TCO** | $74,340 | $74,340 | $74,340 | $74,340 | $103,104 | $131,832 |

**Calculation details:**
- OCP Subscription: ceil(total_vCPUs / 4) × $667/yr ÷ 12
- OCP AI: total_vCPUs × $0.022/hr × 730 hr/mo
- HCP: $0.25/hr × 730 = $182.50/mo

### 9.3 Full-Stack TCO: Premium Quality Configuration

**Qwen3-Coder-Next 80B on H200 (p5en.48xlarge, 8× H200), 64K context**

| Component | 1-100 devs | 200 devs |
|-----------|-----------|----------|
| GPU Nodes | 1× p5en.48xl | 1× p5en.48xl |
| GPU vCPUs | 192 | 192 |
| Infra Nodes | 3× m5.2xl | 3× m5.2xl |
| Total vCPUs | 216 | 216 |
| | | |
| Hosted Control Plane | $183 | $183 |
| EC2 GPU (3yr SP) | $35,442 | $35,442 |
| EC2 Infra (3yr SP) | $364 | $364 |
| OCP Subscription (3yr) | $3,002 | $3,002 |
| OCP AI Subscription | $3,470 | $3,470 |
| **Total Monthly** | **$42,461** | **$42,461** |
| Per Dev @ 50 | $849 | — |
| Per Dev @ 100 | $425 | — |
| Per Dev @ 200 | — | $212 |

p5en.48xlarge provides ~776 concurrent slots — massive excess for ≤200 teams. Consider only when code quality justifies the 10-15x cost premium.

### 9.4 Context Length Impact on TCO (Best Value)

| Team | 32K Total/Dev | 64K Total/Dev | 128K Total/Dev |
|------|-------------|-------------|--------------|
| 50 devs | $2,065 / $41 | $2,065 / $41 | $2,864 / $57 |
| 100 devs | $2,065 / $21 | $2,864 / $29 | $3,662 / $37 |
| 200 devs | $2,864 / $14 | $3,662 / $18 | $5,259 / $26 |

### 9.5 Cost Component Breakdown (100 Developers, 64K)

```
Total Monthly: $2,864

EC2 GPU (g6e.xlarge × 2)  ████████████████████████  $1,358  (47%)
OCP AI Subscription        ██████████████████        $514    (18%)
OCP Subscription (3yr)     ███████████████           $445    (16%)
EC2 Infra (m5.2xl × 3)    ████████████              $364    (13%)
Hosted Control Plane       ██████                    $183    (6%)
```

GPU compute is the largest cost component (47%), but platform subscriptions (OCP + OCP AI) collectively represent 34%.

### 9.6 GPU-Only vs Full-Stack TCO Comparison

| Team (64K) | GPU-Only 3yr | Full-Stack 3yr | Platform Overhead | Overhead % |
|------------|-------------|---------------|-------------------|-----------|
| 1 dev | $24,444 | $74,340 | $49,896 | 204% |
| 10 devs | $24,444 | $74,340 | $49,896 | 204% |
| 50 devs | $24,444 | $74,340 | $49,896 | 204% |
| 100 devs | $48,888 | $103,104 | $54,216 | 111% |
| 200 devs | $73,332 | $131,832 | $58,500 | 80% |

Platform overhead is ~$50K over 3 years regardless of GPU count — proportionally smaller as GPU spend scales.

---

## 10. Methodology & Sources

### 10.1 Calculation Methodology

| Quantity | Formula |
|----------|---------|
| Model weights (GB) | Total parameters × 1 byte (FP8) |
| KV cache per token | 2 × Attention_Layers × KV_Heads × Head_Dim × Bytes_per_Element |
| Available VRAM | GPU_VRAM − Model_Weights − 2 GB (runtime overhead) |
| Max concurrent devs | floor(Available_VRAM / KV_per_request) |
| Per-dev throughput | GPU_Memory_BW / (Active_Params_FP8 + Batch_Size × KV_per_request) |

### 10.2 Assumptions

- 1 concurrent inference request per developer (agentic tools serialize)
- FP8 for both weights and KV cache (A100 uses Marlin W8A16 dequantization)
- 2 GB runtime overhead per GPU/chip
- Peak concurrency: 20% of team size
- Minimum throughput: 20 tokens/second sustained per active developer
- AWS pricing region: US East (N. Virginia) / us-east-1
- OpenShift subscription: 3yr at $667/4-vCPU/yr
- OpenShift AI: $0.022/vCPU/hr for all worker nodes
- 3 infrastructure worker nodes (m5.2xlarge) per cluster
- Hosted Control Plane: $0.25/hr flat

### 10.3 Sources

| Data Point | Source |
|-----------|--------|
| Model configs | HuggingFace config.json (Qwen3.6-35B-A3B, Qwen3-Coder-30B-A3B, etc.) |
| GPU specifications | NVIDIA datasheets (A100, H100, H200, L40S, B200) |
| vLLM FP8/INT8 | vLLM documentation, Marlin PR #5975 |
| AWS instance pricing | AWS EC2 Pricing, April 2026 |
| EU AI Act | Regulation 2024/1689, financialregulations.eu |
| DORA | Digital Operational Resilience Act, Article 30 |
| Developer throughput | Industry benchmarks; TokenMix, DEV Community |
| Shadow AI statistics | Digital Applied, AgileSoftLabs, 2026 |

---

## Appendix A: Recommendations at 30 Tokens/Second Baseline

For the recommended Qwen3.6-35B-A3B (MoE), the 20 vs 30 tok/s throughput target has **no impact on infrastructure sizing**. The MoE architecture's small active parameter footprint (3 GB) means bandwidth headroom far exceeds VRAM capacity at all context lengths.

At 64K context on L40S:
- Bandwidth limit at 30 tok/s: 42 users
- VRAM limit: 17 users
- Effective: 17 (VRAM-bound, identical to 20 tok/s baseline)

**Conclusion:** The TCO tables in Section 9 are valid for both 20 and 30 tok/s targets when using the recommended MoE model.

---

*Report generated April 2026. All calculations based on publicly available model configurations, GPU specifications, and Red Hat pricing. Actual performance should be validated with empirical benchmarks on the target infrastructure before procurement decisions. AWS pricing verified April 2026; OpenShift subscription rates should be confirmed with Red Hat sales.*
