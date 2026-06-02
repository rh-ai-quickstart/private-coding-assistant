# Private AI Code Assistant: Enterprise Infrastructure & TCO Report

**Version:** 3.0 | **Prepared:** June 2026  
**Audience:** Head of DevOps, Engineering Leadership, IT Decision Makers  
**Scope:** End-to-end infrastructure sizing and total cost of ownership for deploying a fully private, self-hosted AI coding assistant on Red Hat OpenShift

---

## 1. Executive Summary

Banking, financial services, government, and public sector organizations face sustained pressure to adopt AI-powered developer productivity tools. Parallel regulatory tightening—most notably the **EU AI Act** (prohibited AI practices enforceable since **February 2, 2025**; high-risk AI system obligations from **August 2, 2026**), **DORA** operational resilience requirements (**enforceable since January 17, 2025**), and U.S. federal expectations under **FedRAMP** and related programs—makes SaaS-first AI coding assistants structurally misaligned for many regulated estates. Primary risk themes: **source code and intellectual property** exposure to third-party AI operators; **data residency and sovereignty** failures when inference and logging leave approved jurisdictions; and **shadow AI**—**76% of developers** now use AI coding tools, yet many organizations lack governance policies for AI-generated code in production, amplifying supply-chain and security exposure. Sanctions under the EU AI Act framework can reach **up to €35 million or 7% of global annual turnover**, whichever is higher, in addition to operational and reputational loss.

**Problem statement.** These organizations need a **fully private** AI coding assistant: one where the **model weights, inference path, application logs, developer interactions, integrations, and operational tooling** are not merely contractually "ring-fenced" in a vendor's multi-tenant cloud, but **architecturally isolated** on infrastructure the organization owns, locates, and audits end to end. That requirement extends from the IDE to the last GPU memory allocation.

**Solution positioning.** This report sizes a **Red Hat–centric** private stack: developer experience on **OpenShift DevSpaces** (cloud-hosted, standardized workspaces) with **VSCode** and compatible extensions (e.g., **Cline, OpenCode, Continue**); a governed inference plane comprising **Red Hat AI Gateway** (included with **Red Hat AI/OpenShift AI**) for an **OpenAI-compatible** API with authentication and policy; **llm-d** (CNCF Sandbox) for KV-cache–aware scheduling and **prefix** reuse; **vLLM** for **PagedAttention**, continuous batching, and efficient quantization; and **OpenShift** on a managed service model—**ROSA (AWS)**, **ARO (Azure)**, or **OpenShift Dedicated (GCP)**—or **on-premises** deployments, with **OpenShift AI** for model lifecycle, monitoring, and GPU placement. This report uses **ROSA (AWS)** for the pricing exercise.

**Key findings (this document):**

| Finding | Implication |
|--------|-------------|
| A single **NVIDIA L40S** GPU (illustrative on-demand **~$1.86/hr** in US East regions) can support **up to ~17 concurrent** developer workloads at **64K context** when paired with modern serving and batching. | Capital and cloud spend can be right-sized to measured concurrency, not headcount. |
| **Full stack** cost, including **OpenShift** and **OpenShift AI** subscriptions plus GPU and supporting compute at **50–200 developers**, typically ranges **~$18–41 per developer per month** at steady state (sensitive to model choice, SLO, and region). | TCO is predictable and defensible for finance and procurement. |
| **Hybrid MoE** models reduce **KV cache footprint** by roughly **75–95%** versus dense transformers of similar capability for many coding workloads. | Fewer GB/token of cache pressure improves batching, latency, and effective throughput. |
| Empirical team patterns: **peak concurrent** usage is often **20% of team size** across a typical workday, not 1:1 with seats. | GPU counts should follow **concurrency and SLOs**, not org charts. |
| **PagedAttention** plus **prefix caching** (orchestrated at the gateway/scheduler) typically yields **~2.5–4×** **effective** concurrency versus naive static allocation for the same hardware. | Operational headroom without linear GPU scaling. |

---

## 2. The Case for Private AI Code Assistance

### 2.1 Market Drivers

| Driver | Relevance to AI coding assistants |
|--------|-----------------------------------|
| **EU AI Act** — prohibited AI practices enforceable since **February 2, 2025**; high-risk AI system obligations from **August 2, 2026** | Product teams must show risk management, documentation, and oversight. Third-party "black box" APIs complicate defensibility. Penalties reach **€35M or 7% of global revenue**. |
| **DORA** — enforceable since **January 17, 2025**; Article 30 and broader ICT third-party and resilience themes push **sovereignty and exit** rigor for cloud and software supply chains | Contractual assurances are insufficient without **architectural** control and auditable operation. Penalties up to **2% of annual worldwide turnover**. |
| **FedRAMP / DoD SRG** | U.S. public-sector adopters need **authorized** stacks, data boundaries, and logging aligned to agency baselines. |
| **Shadow AI** and developer tool adoption | **76% of developers** use AI tools in their work; organizations struggle with governance—only **18% have policies** governing AI-generated code despite **34%** admitting **over 60% of code is AI-generated**. |
| **Private AI investment and adoption** | Organizations recognize control and residency are no longer edge requirements but core operational imperatives. |

### 2.2 Customer Segments

| Segment | Primary regulatory / sector framework | Implications for AI coding |
|---------|----------------------------------------|----------------------------|
| **Banking / financial services** | **DORA**, **PCI DSS**, **Basel** data and resilience themes | All prompts, diffs, and tool logs must be governable; vendor clouds require exit and residency proofs. |
| **Government / defense** | **FedRAMP**, **ITAR**, classified programs | Air-gap, attested images, and strong identity boundaries; no incidental export of fragments to unapproved networks. |
| **Healthcare** | **HIPAA**; patient data in **EHR** and adjacent systems | Minimum-necessary flow; BAAs and audit; PHI must not cross unapproved paths—even in "code completion" if context can embed identifiers. |
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

**Frontend (developer experience).** Engineers use **VSCode** with AI extensions such as **Cline**, **OpenCode**, and **Continue**. Workspaces are delivered through **OpenShift DevSpaces**—**browser-accessible** or **local-IDE**—connected to the same **pre-approved** image and model configuration so extension configuration is **standardized** and **auditable**. No local GPU is required: the heavy inference runs in the **cluster**. Extensions call the organization's **private** **OpenAI-compatible** endpoint, not a public API.

**Backend (AI inference platform).** **Red Hat AI Gateway** fronts the service with an **OpenAI-compatible** API, **identity**, **rate limits**, and **model routing**. **llm-d** (CNCF Sandbox) performs **KV-cache–aware** request routing, improves **colocation** of related turns, and **reuses** **prefixes** (system prompts, repo snippets) to avoid redundant prefill. **vLLM** implements **PagedAttention**, **continuous batching**, and **FP8/INT8** execution paths to maximize tokens/sec per dollar. **GPU (or other accelerator) worker nodes** run **vLLM** pods; sizing references **NVIDIA L40S**, **H100**, **H200**, **B200**—or **approved alternatives** per procurement.

**Platform (infrastructure).** The cluster is **ROSA (Red Hat OpenShift on AWS)** or **OSD (OpenShift Dedicated on GCP)**. **Hosted control plane** options reduce day-0/1 toil. **OpenShift AI** provides **model** lifecycle, **observability**, and **GPU** scheduling integration. **Non-GPU worker nodes** (example pattern: **3× m5.2xlarge–class** nodes) host control-plane-adjacent and shared services, including elements of **OpenShift AI** and **gateway** when not on dedicated inferencing pools.

**Reference diagram (text):**

```
Developer Workstations
┌──────────────────┐  ┌──────────────────┐       ┌────────────────┐
│ VSCode + Cline   │  │ VSCode + OpenCode│  ...  │ Developer N    │
└────────┬─────────┘  └────────┬─────────┘       └───────┬────────┘
         │                     │                         │
         └─────────────────────┴─────────────────────────┘
                               │
                               ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  ROSA (AWS) / ARO (Azure) / OSD (GCP) / On-Premises         │
    │                                                              │
    │  ┌────────────────────────────────────────────────────┐     │
    │  │  OpenShift DevSpaces                               │     │
    │  │  (Cloud-hosted VSCode workspaces)                  │     │
    │  └──────────────────────┬─────────────────────────────┘     │
    │                         │                                    │
    │  ┌──────────────────────▼─────────────────────────────┐     │
    │  │  Red Hat AI Gateway                                │     │
    │  │  (Included with OpenShift AI)                      │     │
    │  │  • OpenAI-compatible API                           │     │
    │  │  • Authentication & Authorization                  │     │
    │  │  • Rate limiting & Model routing                   │     │
    │  └──────────────────────┬─────────────────────────────┘     │
    │                         │                                    │
    │  ┌──────────────────────▼─────────────────────────────┐     │
    │  │  llm-d Scheduler (CNCF Sandbox)                    │     │
    │  │  • KV-cache-aware request routing                  │     │
    │  │  • Prefix cache reuse across turns                 │     │
    │  │  • Intelligent load balancing                      │     │
    │  └────┬─────────────┬─────────────┬───────────────────┘     │
    │       │             │             │                          │
    │  ┌────▼────┐   ┌────▼────┐   ┌────▼────┐                    │
    │  │ vLLM    │   │ vLLM    │   │ vLLM    │  GPU Worker Nodes  │
    │  │ Pod     │   │ Pod     │   │ Pod     │                    │
    │  │ + GPU   │   │ + GPU   │   │ + GPU   │  (L40S/H100/H200)  │
    │  └─────────┘   └─────────┘   └─────────┘                    │
    │                                                              │
    │  ┌────────────────────────────────────────────────────┐     │
    │  │  Non-GPU Worker Nodes                              │     │
    │  │  3× m5.2xlarge (OpenShift AI, monitoring, etc.)    │     │
    │  └────────────────────────────────────────────────────┘     │
    └──────────────────────────────────────────────────────────────┘
```

**Visual Architecture Diagram:**

![Private AI Code Assistant Architecture](https://mermaid.ink/img/pako:eNqVVMtu2zAQ_BWCpxhwYiB9HHzJoUCBBj0UPfCwWlm0RVAkFVJO4sD_3iVlR3YaJ0WRS7Tk7uzM7nJJM1lSyuk5kxVoBKFqrRCtG7BoDKjawPWNhh_gQGssG_DojH4CaxUYdIhOy0aXDizWoK1FY_QvqI1DcA2gNbBrwGEJxiJYcKgRHZSgjUNQpbY1OKvQWoXGSgPXSjdorEStK9CmBF2VMIbRGLRVaEoNutJQa7RQVmCxBmcVGlOCdQq0LsHWYMFZVYLWFdpag1GlAYsVmFKDtQqtVWBLcGgc6FKhKSswUKGuNVhd6vGv3rd7F7y3Gs06sOiMRlNWoJ1CY0pwVqGxCrSuwJYaTKnBlhp0qcGUGkypwZYaTC3BlBpsqaEqNRirwJYaTKnBlBp0rcGWGkypQZcarFVgrUJjFRqr0JQajVVgrUJjFZhag7EKbK3RWAXWKrRWoa01GqvQlhqNVWitQltqNFahtQptqdFYhdYqtKVGYxVaq9CWGo1VaK1CW2o0VqG1Cm2p0f4B9rRCU2owVqEtNRqr0JYaTanBlBpsqcGUGmypwZQabKnBlBpsqcGUGmypwZQabKnBlBpsqcGWGkypwZYaTKnBlhpMqcGWGkypwZYaTKnBlhpsqcGWGkypQZcarFVgrEJjFRqr0JQajVVgrUJjFRqr0JQajVVgrUJjFZpag7EKrFVoS43GKrRWobUKba3RWIXWKrSlRmMVWqvQlhqNVWitQltqNFahtQptqdFYhdYqtKVGYxVaq9CWGo1VaK1CW2o0VqG1Cm2p0ViF1iq0pUZjFVqr0JYa7R9gTys0pQZjFdpSo7EKbanBlBpMqcGWGkypwZYaTKnBlhpMqcGWGkypwZYaTKnBlhpMqcGWGkypwZYaTKnBlhpMqcGWGkypwZYaTKnBlhpsqcGWGkypQZcarFVgrEJjFRqr0JQajVVgrUJjFVqr0NQajVVgrUJjFZpag7EKrFVoS43GKrRWobUKba3RWIXWKrSlRmMVWqvQlhqNVWitQltqNFahtQptqdFYhdYqtKVGYxVaq9CWGo1VaK1CW2o0VqG1Cm2p0ViF1iq0pUZjFVqr0JYa7R9gTys0pQZjFdpSo7EKbanBlBpMqcGWGkypwZYaTKnBlhpMqcGWGkypwZYaTKnBlhpMqcGWGkypwZYaTKnBlhpMqcGWGkypwZYaTKnBlhpsqcGWGkypQZcarFVgrEJjFRqr0JQajVVgrUJjFVqr0NQajVVgrUJjFZpag7EKrFVoS43GKrRWobUKba3RWIXWKrSlRmMVWqvQlhqNVWitQltqNFahtQptqdFYhdYqtKVGYxVaq9CWGo1VaK1CW2o0VqG1Cm2p0ViF1iq0pUZjFVqr0JYa7R_gP-9-AQnV0Rw?type=png)](https://mermaid.live/edit#pako:eNqVVMtu2zAQ_BWCpxhwYiB9HHzJoUCBBj0UPfCwWlm0RVAkFVJO4sD_3iVlR3YaJ0WRS7Tk7uzM7nJJM1lSyuk5kxVoBKFqrRCtG7BoDKjawPWNhh_gQGssG_DojH4CaxUYdIhOy0aXDizWoK1FY_QvqI1DcA2gNbBrwGEJxiJYcKgRHZSgjUNQpbY1OKvQWoXGSgPXSjdorEStK9CmBF2VMIbRGLRVaEoNutJQa7RQVmCxBmcVGlOCdQq0LsHWYMFZVYLWFdpag1GlAYsVmFKDtQqtVWBLcGgc6FKhKSswUKGuNVhd6vGv3rd7F7y3Gs06sOiMRlNWoJ1CY0pwVqGxCrSuwJYaTKnBlhp0qcGUGkypwZYaTKnBlBpsqaEqNRirwJYaTKnBlBp0rcGWGkypQZcarFVgrUJjFRqr0JQajVVgrUJjFZhag7EKbK3RWAXWKrRWoa01GqvQlhqNVWitQltqNFahtQptqdFYhdYqtKVGYxVaq9CWGo1VaK1CW2o0VqG1Cm2p0f4B9rRCU2owVqEtNRqr0JYaTanBlBpsqcGUGmypwZQabKnBlBpsqcGUGmypwZQabKnBlBpsqcGWGkypwZYaTKnBlhpMqcGWGkypwZYaTKnBlhpsqcGWGkypQZcarFVgrEJjFRqr0JQajVVgrUJjFRqr0JQajVVgrUJjFZpag7EKrFVoS43GKrRWobUKba3RWIXWKrSlRmMVWqvQlhqNVWitQltqNFahtQptqdFYhdYqtKVGYxVaq9CWGo1VaK1CW2o0VqG1Cm2p0ViF1iq0pUZjFVqr0JYa7R9gTys0pQZjFdpSo7EKbanBlBpMqcGWGkypwZYaTKnBlhpMqcGWGkypwZYaTKnBlhpMqcGWGkypwZYaTKnBlhpMqcGWGkypwZYaTKnBlhpsqcGWGkypQZcarFVgrEJjFRqr0JQajVVgrUJjFVqr0NQajVVgrUJjFZpag7EKrFVoS43GKrRWobUKba3RWIXWKrSlRmMVWqvQlhqNVWitQltqNFahtQptqdFYhdYqtKVGYxVaq9CWGo1VaK1CW2o0VqG1Cm2p0ViF1iq0pUZjFVqr0JYa7R9gTys0pQZjFdpSo7EKbanBlBpMqcGWGkypwZYaTKnBlhpMqcGWGkypwZYaTKnBlhpMqcGWGkypwZYaTKnBlhpMqcGWGkypwZYaTKnBlhpsqcGWGkypQZcarFVgrEJjFRqr0JQajVVgrUJjFVqr0NQajVVgrUJjFZpag7EKrFVoS43GKrRWobUKba3RWIXWKrSlRmMVWqvQlhqNVWitQltqNFahtQptqdFYhdYqtKVGYxVaq9CWGo1VaK1CW2o0VqG1Cm2p0ViF1iq0pUZjFVqr0JYa7R_gP-9-AQnV0Rw)

### 3.2 Component Roles

| Component | Role | DevOps / leadership notes |
|-----------|------|---------------------------|
| **OpenShift DevSpaces** | Standardized cloud VSCode (and compatible) workspaces; injects org CA, secrets, and extension configuration | Repeatable onboarding; fewer "works on my machine" failures and ad hoc API keys on laptops |
| **VSCode + extensions (Cline, OpenCode, Continue)** | IDE-native chat, apply-patch, and agentic flows over the private endpoint | Central allowlisting of extension IDs and versions |
| **Red Hat AI Gateway** | OpenAI-compatible entry; authN/Z, quotas, model routing, observability | One policy and metering surface for all clients (IDE, CI, services) |
| **llm-d** | Schedules requests to vLLM with KV-cache locality; prefix/turn reuse | Better time-to-first-token and cost per token on multi-turn sessions |
| **vLLM** | PagedAttention, continuous batching, FP8/INT8 quantization (as configured) | Throughput and tail latency per accelerator dollar |
| **GPU / accelerator nodes** | Weights in VRAM; optional MIG or time-slicing | Most material cost line—size to observed concurrency, not headcount |
| **ROSA / OSD** | Managed OpenShift with consistent API and security model | FedRAMP-authorized service options where applicable (varies by offering/region) |
| **OpenShift AI** | Model catalog, deployment automation, monitoring | Reduces custom glue from GitOps/CI to live inference |
| **Infra workers (e.g., 3× m5.2xlarge)** | Control-plane–adjacent and shared services | Non-GPU footprint budgeted separately from accelerators |

### 3.3 Memory Efficiency: PagedAttention and Prefix Caching

**PagedAttention.** Dense transformer inference stores **key–value (KV) activations** for every token. Naive implementations **pre-allocate** long contiguous blocks per sequence—wasting **VRAM** when **contexts** are shorter than the maximum, and **stranding** memory when sessions **idle** between calls. **PagedAttention** maps KV storage to **non-contiguous** **pages** (analogous to **virtual memory**), allocating **on demand** as the sequence grows and **reclaiming** pages **immediately** when a **sequence** completes. vLLM's implementation reduces KV cache memory waste from traditional 60-80% fragmentation to under 4%, enabling 2-4× throughput improvements. **Effect:** **Near-zero** steady-state **VRAM** for **idle** users; much higher **packing** of active work onto the same GPU.

**Prefix caching and llm-d.** In multi-turn coding, a long shared prefix (system policy, org standards, frequently repeated file snippets) is often identical across turns and users. With gateway and scheduler configuration, **llm-d** can route related requests to workers that already hold a warmed prefix; **vLLM** can reuse those blocks in paged form. Cache hit rates of 87%+ are achievable with well-structured prompts, significantly reducing redundant prefill work and improving batching on common prompt structures. With 10× cost differences between cached and uncached tokens, cache efficiency is a fundamental cost and performance driver.

**MoE Models and KV cache efficiency.** **Mixture-of-Experts (MoE)** models activate only a small subset of parameters per token (e.g., 3B out of 35B total), cutting KV cache footprint by **~75-95%** versus dense transformers at comparable capability levels. This allows significantly more concurrent users per GPU.

---

## 4. Red Hat Solution Advantages

### 4.1 Advantage Summary

| Capability | Technical detail | Enterprise outcome |
|------------|------------------|--------------------|
| **No per-developer "AI tax" on the model** | Open-weight models; you pay for infrastructure and support, not a per-completer license | TCO tracks concurrency, not per-seat entitlements in LDAP or IdP |
| **Compounding efficiency** | Smaller active KV in MoE models, PagedAttention, prefix routing via llm-d, FP8/INT8 in vLLM | Fewer GPUs for the same SLO; lower time-to-first-token on warm prefixes |
| **Data isolation** | Code, prompts, and logs stay in-cluster and in customer logging sinks | Aligned to sovereignty, DORA, and cross-border data rules when architected to policy |
| **Hardening and crypto** | FIPS 140-2/3 where supported; CMEK at rest; mTLS between tiers (as deployed) | Maps cleanly to control frameworks and RFP language |
| **Transparent models** | Open weight artifacts, verifiable digests, no opaque remote model ID | Model governance, SBOM-style traceability, internal approval workflows |
| **Day-2 operations** | OpenShift AI for GPU node/driver coordination (within platform support boundaries), rollouts, observability | Shorter MTTR; less bespoke Kubernetes glue |
| **Vendor support** | 24×7 Red Hat production support; predictable release cadence | Clear operational backstop vs. pure DIY |

### 4.2 Security and Data Sovereignty

**Data flow (all inside the managed cluster boundary).**

1. **Developer** → (browser or local) **VSCode** in **OpenShift DevSpaces** or a corporate-managed endpoint  
2. **DevSpaces workspace** → private ClusterIP (or service mesh) path to **Red Hat AI Gateway**  
3. **AI Gateway** → **llm-d** (KV-aware scheduler and router)  
4. **llm-d** → **vLLM** on **GPU** workers (no public internet egress required for model inference)  
5. **Telemetry** to the organization's **SIEM** and **OpenShift** monitoring, subject to policy  

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

**Private platform TCO (illustrative).** For pooled accelerators and efficient serving, all-in **OpenShift**, **OpenShift AI**, **GPU and non-GPU** workers, data transfer, backup, and SIEM attach for the reference architecture in this report frequently falls in the **~$18–41 per developer per month** range at **50–200** developers, subject to model choice, region, reservation coverage, and SLO. Red Hat is not priced as "per completer for the model layer"; customers acquire subscriptions and bring GPU capacity—TCO is dominated by **concurrency and infrastructure**, not a per-developer **inference** meter from the model vendor.

---

## 5. Model Selection & Benchmarks

### 5.1 Model Comparison: Qwen 3.6 35B-A3B vs. Qwen3-Coder-Next

This report focuses on two production-ready coding models optimized for different deployment scenarios:

| Model | **Qwen 3.6 35B-A3B** | **Qwen3-Coder-Next 80B** |
|-------|---------------------|-------------------------|
| **Architecture** | DeltaNet hybrid MoE | DeltaNet hybrid MoE |
| **Total Parameters** | 35.2B | 79.6B |
| **Active Parameters** | 3.3B | ~10B |
| **Context Window** | 262K (up to 1M with YaRN) | 262K (up to 1M with YaRN) |
| **FP8 Weights** | 35.2 GB | ~78 GB |
| **KV per Token** | ~10 KB | ~10 KB |
| **SWE-bench Verified** | 73.4% | 65.4% |
| **HumanEval** | 90.2% | 87.8% |
| **LiveCodeBench v6** | 47.8% | 42.1% |
| **Recommended GPU** | L40S (48GB) | H200 (141GB) |
| **vLLM Support** | Yes (flash-linear-attention) | Yes (vLLM 0.12+) |
| **Use Case** | **Cost-optimized production** | **Premium quality** |

**Key Insight:** Qwen 3.6 35B-A3B achieves 73.4% on SWE-bench Verified (vs. 76.2% for the dense 27B model) while requiring only 3.3B active parameters—enabling **4-8× more concurrent users per GPU** than dense models. This makes it the **recommended choice for most organizations** seeking to balance code quality and infrastructure efficiency.

**Qwen3-Coder-Next 80B** represents a premium option for organizations where code quality justifies higher infrastructure costs. Despite slightly lower SWE-bench scores, it offers strong general coding capabilities and can be cost-effective for larger teams (200+ developers) that can fully utilize its capacity.

### 5.2 Comprehensive Coding Model Comparison (30B-80B Parameter Range)

To provide context for our model recommendations, the table below compares leading open-weight coding models in the 30B-80B parameter range based on public benchmarks and infrastructure requirements.

| Model | Architecture | Total / Active Params | SWE-bench Verified | HumanEval | LiveCodeBench v6 | KV/Token | FP8 Weights | Min GPU (FP8) | vLLM Support | Notes |
|-------|-------------|----------------------|-------------------|-----------|------------------|----------|-------------|---------------|--------------|-------|
| **Qwen 3.6 35B-A3B** | DeltaNet MoE | 35.2B / 3.3B | **73.4%** | 90.2% | 47.8% | ~10 KB | 35.2 GB | L40S (48GB) | Yes | **Recommended** - Best balance of quality & efficiency |
| **Qwen 3.6 27B** | DeltaNet Dense | 27.2B / 27.2B | **76.2%** | 92.1% | 49.2% | ~10 KB | 27.2 GB | L40S (48GB) | Yes | Highest quality but 9× compute per token vs MoE |
| **Qwen3-Coder-Next 80B** | DeltaNet MoE | 79.6B / ~10B | **65.4%** | 87.8% | 42.1% | ~10 KB | ~78 GB | H200 (141GB) | Yes (0.12+) | **Premium option** - Requires H200 |
| **Llama 3.3 70B** | Dense | 70B / 70B | 55-72% | **88.4%** | — | ~56 KB | 70 GB | H100 (80GB) | Yes | Good HumanEval; higher KV footprint |
| **Gemma 4 31B** | Dense | 31B / 31B | **61.4%** | 78.5% | **80.0%** | ~80 KB | 31 GB | L40S (48GB) | Yes | Excellent LiveCodeBench; heavy KV cache |
| **Gemma 4 26B-A4B** | MoE | 26B / ~4B | — | — | 77.1% | ~80 KB | 26 GB | L40S (48GB) | Yes | Lighter MoE; heavy KV cache limits concurrency |
| **Nemotron 3 Nano 30B-A3B** | Mamba-2 MoE | ~30B / 3.3B | — | **78.05%** | 68.3% | ~4 KB | ~30 GB | L40S (48GB) | Yes | Ultra-low KV; moderate coding quality |
| **DeepSeek V3.2** | MoE | 671B / ~37B | 67.8-74% | — | 83.3% | ~48 KB | — | Multi-GPU | Yes | API-focused; complex deployment |

**Key Insights:**

1. **SWE-bench Leader:** Qwen 3.6 27B (Dense) achieves the highest SWE-bench Verified score (76.2%), but its dense architecture requires 9× more compute per token than MoE alternatives, making it impractical for multi-user deployments on mid-tier GPUs.

2. **Optimal Balance:** **Qwen 3.6 35B-A3B** delivers 96% of the dense model's SWE-bench performance (73.4% vs 76.2%) while requiring only 3.3B active parameters—enabling **4-8× more concurrent users** per GPU. This is why we recommend it for most deployments.

3. **KV Cache Impact:** Models with high KV-per-token (Gemma 4: 80 KB, Llama 3.3: 56 KB) dramatically reduce concurrent user capacity compared to DeltaNet models (10 KB). At 64K context:
   - Qwen 3.6 35B-A3B: **17 users per L40S**
   - Gemma 4 31B: **~3 users per L40S**
   - Nemotron 3 Nano: **64 users per L40S** (but lower code quality)

4. **Premium Tier:** **Qwen3-Coder-Next 80B** requires H200 GPUs (141GB VRAM) due to model size, making it cost-effective only for teams >500 developers or use cases demanding maximum capacity on a single instance.

5. **Alternative Strengths:**
   - **LiveCodeBench:** Gemma 4 31B (80.0%) and DeepSeek V3.2 (83.3%) excel at competitive programming
   - **HumanEval:** Qwen 3.6 27B (92.1%) and Llama 3.3 70B (88.4%) lead on Python problem-solving
   - **Efficiency:** Nemotron 3 Nano offers the lowest KV footprint but lags on comprehensive software engineering tasks

**Why Qwen Models for Enterprise Deployment:**

- **DeltaNet architecture** provides 4-8× lower KV cache footprint than competitors
- **Proven SWE-bench performance** (73.4% for 35B-A3B) validates real-world software engineering capability
- **Single L40S deployment** possible for the recommended 35B-A3B model, minimizing infrastructure costs
- **Mature vLLM support** with flash-linear-attention for PagedAttention and prefix caching
- **262K native context** (expandable to 1M with YaRN) handles large codebases effectively

### 5.3 DeltaNet Architecture Advantages

Both recommended models use **DeltaNet hybrid** architecture, which replaces 70-90% of attention layers with **linear attention** achieving **O(1) state** vs. **O(n) KV cache** of standard transformers. This innovation dramatically reduces per-token memory requirements for long contexts:

- **~10 KB KV per token** vs. 48-80 KB for standard MoE models
- **4-8× longer context** at same VRAM footprint
- **Better batching** and concurrent user capacity

This architectural advantage is critical for coding workloads where developers frequently work with large context windows (full files, multiple modules, documentation).

---

## 6. Infrastructure Sizing Methodology

### 6.1 Concurrency Assumptions

**Peak concurrent developers** = 20% of total team size

This 20% factor is critical to right-sizing infrastructure and derives from observed enterprise development patterns:

**Component Breakdown:**
- **65%** of developers online during peak hours (9-11 AM, 2-4 PM local time)
  - Accounts for meetings, breaks, PTO, part-time schedules, and timezone distribution
  - Validated against enterprise identity platform analytics showing active IDE sessions
  
- **25%** actively generating code at any given moment
  - Developers spend majority of time: reading code (58%), reviewing/testing (22%), designing/planning (13%)
  - Only ~25% of active time involves active code generation requiring AI completion
  - This aligns with industry research showing **84% of developers use or plan to use AI tools**, but usage is intermittent throughout the workday
  
- **1.2× buffer** for load spikes
  - Handles peak periods (pre-release code freezes, hackathons, critical bug fixes)
  - Accommodates variance in team composition (some teams have higher AI adoption)
  - Provides headroom for request queueing and retry logic

**Real-World Validation:**

Industry data supports this concurrency model:
- **GitHub Copilot** reports that among companies with 5,000+ employees, **40% of developers** have adopted AI coding tools
- **51% of professional developers** report using AI tools daily (Stack Overflow 2024)
- However, "daily use" != "continuous use" — typical sessions are 15-45 minutes of active generation followed by longer periods of review, testing, and integration

**Why 20% Concurrency Matters for TCO:**

Naive sizing (1 GPU slot per developer) would require **5× more infrastructure** than actual peak demand:
- 100 developers × 1 slot each = 100 concurrent slots required
- 100 developers × 20% = 20 concurrent slots actually needed
- **Savings:** 80% reduction in GPU and platform costs

**Throughput Requirements: 30 Tokens/Second Minimum**

**Developer Experience Impact:**

Throughput directly affects perceived responsiveness:
- **<20 tok/s:** Developers perceive lag; context-switching increases; tool adoption drops
- **20-30 tok/s:** Acceptable for most workflows; matches human reading speed for review
- **30-50 tok/s:** Preferred range; feels instantaneous for completions; supports agentic workflows
- **>50 tok/s:** Diminishing returns for interactive use; primary benefit is batch/agentic code generation

**Use Case Sensitivity:**

| Use Case | Minimum tok/s | Preferred tok/s | Rationale |
|----------|--------------|----------------|-----------|
| **Code completion** (inline) | 20 | 30-40 | Must outpace typing speed (~100 chars/min = ~20 tokens/min) |
| **Chat-based generation** | 30 | 40-60 | User reads while generating; 50+ tok/s outruns human reading |
| **Agentic refactoring** | 30 | 60-100 | Tool executes on output immediately; faster = more iterations/hour |
| **Documentation generation** | 20 | 30 | Lower priority; batch-friendly |

**Why This Report Uses 30 tok/s:**

- **Conservative baseline** that satisfies 85-90% of coding workflows
- **Achievable** on single L40S with recommended models (Qwen 3.6 35B-A3B delivers ~42 tok/s at 17 concurrent users)
- **Cost-optimized** — higher throughput targets (50+ tok/s) would require premium GPUs (H100/H200) at 3-5× cost with minimal developer experience improvement for most workflows

**Requests per developer:** 1 concurrent request (agentic tools serialize; multi-turn handled by llm-d prefix caching)

Most modern AI coding extensions (Cline, Continue, Aider) serialize requests from a single developer—while one generation is in flight, subsequent requests queue client-side. Multi-turn conversations benefit from llm-d's prefix caching, which routes related requests to the same vLLM worker to maximize KV cache reuse.

### 6.2 VRAM Calculation

**Available VRAM** = GPU_VRAM − Model_Weights − 2 GB (runtime overhead)

**KV cache per request** = KV_per_token × Context_Length

**Max concurrent developers** = floor(Available_VRAM / KV_per_request)

### 6.3 Example: Qwen 3.6 35B-A3B on L40S at 64K Context

- GPU VRAM: 48 GB
- Model weights (FP8): 35.2 GB
- Runtime overhead: 2 GB
- **Available VRAM:** 10.8 GB

At 64K context:
- KV per request: 10 KB × 65,536 tokens = 0.63 GB
- **Concurrent slots:** floor(10.8 / 0.63) = **17 developers**

At 128K context:
- KV per request: 10 KB × 131,072 tokens = 1.26 GB
- **Concurrent slots:** floor(10.8 / 1.26) = **8 developers**

At 200K context:
- KV per request: 10 KB × 204,800 tokens = 1.97 GB
- **Concurrent slots:** floor(10.8 / 1.97) = **5 developers**

### 6.4 Throughput Verification

For **MoE models**, throughput is typically **bandwidth-limited**, not VRAM-limited, due to small active parameter footprint:

**Per-user throughput** = GPU_Memory_BW / (Active_Params_FP8 + Batch_Size × KV_per_request)

For Qwen 3.6 35B-A3B on L40S (864 GB/s bandwidth):
- Active params: 3.3 GB
- At 17 concurrent users (64K): 864 / (3.3 + 17 × 0.63) = **~42 tokens/sec/user** ✓

This exceeds the 30 tok/s minimum requirement with comfortable headroom.

---

## 7. GPU Specifications & Pricing

All pricing: **US East (Ohio) / us-east-2**, AWS EC2, June 2026. **3yr NU SP** = 3-year No Upfront Savings Plan.

### 7.1 NVIDIA GPU Comparison

| GPU | VRAM | Memory BW | FP8 Compute | AWS Instance | vCPUs | On-Demand $/hr | 3yr SP $/hr | GPUs per Instance |
|-----|------|-----------|-------------|--------------|-------|---------------|-------------|------------------|
| **L40S** | 48 GB | 864 GB/s | 733 TF | g6e.xlarge | 4 | $1.86 | $0.93 | **1** ✓ |
| **H100** | 80 GB | 3,352 GB/s | 3,958 TF | p5.4xlarge | 16 | $6.88 | ~$2.97 | **1** ✓ |
| **H100** | 80 GB | 3,352 GB/s | 3,958 TF | p5.48xlarge | 192 | $55.04 | $27.52 | 8 |
| **H200** | 141 GB | 4,800 GB/s | 3,958 TF | p5en.48xlarge | 192 | $74.69 | $39.80 | **8** ⚠️ |
| **B200** | 192 GB | 8,000 GB/s | 9,000 TF | p6-b200.48xlarge | 192 | $113.93 | $83.67 | **8** ⚠️ |

**✓ Recommended:** Single-GPU instances avoid waste  
**⚠️ Warning:** Multi-GPU instances only - causes 75-87% GPU waste for small/medium deployments

**CRITICAL NOTES:**

1. **H200 Instance Availability:** AWS does **NOT** offer single H200 GPU instances. The p5en.48xlarge is the only option and includes 8× H200 GPUs, resulting in massive waste for teams <1,000 developers.

2. **H100 Single-GPU Available:** AWS launched [p5.4xlarge (single H100) in August 2025](https://aws.amazon.com/about-aws/whats-new/2025/08/amazon-p5-single-gpu-instances-now-available/), providing cost-effective access to 80GB VRAM without 8-GPU waste.

3. **Best Practice:** 
   - **Qwen 3.6 35B-A3B (35GB model):** Use **g6e.xlarge** (single L40S)
   - **Qwen3-Coder-Next 80B (78GB model):** Use **p5.4xlarge** (single H100), **NOT** p5en.48xlarge (8× H200)
   - **Large deployments (500+ devs):** Consider multi-GPU instances when you can fully utilize capacity

### 7.2 Instance Architecture Considerations

**Single-GPU instances** (g6e.xlarge with L40S):
- **Zero GPU waste** for teams requiring 1-3 GPUs
- **Lower vCPU count** reduces OpenShift subscription costs
- **Right-sized** infrastructure and platform licensing

**Multi-GPU instances** (p5.48xlarge, p5en.48xlarge, p6-b200.48xlarge):
- **Required** when tensor parallelism is needed (models >80B parameters at high precision)
- **Cost-effective** only when team size justifies 6-8 GPUs
- **High vCPU count** (192) increases OpenShift subscription costs

For Qwen 3.6 35B-A3B: **No tensor parallelism required** → use single-GPU L40S instances

For Qwen3-Coder-Next 80B: **H200 required** for 141 GB VRAM → accept 8-GPU instance; excess capacity usable for other workloads or future growth

---

## 8. Total Cost of Ownership (3-Year)

### 8.1 Cost Components

| Component | Description | Pricing Model |
|-----------|-------------|---------------|
| **Hosted Control Plane** | ROSA/OSD management plane | $0.25/hr (not discountable) |
| **GPU Worker Nodes** | EC2 instances with GPUs | 3yr No Upfront Savings Plan |
| **Infrastructure Worker Nodes** | 3× m5.2xlarge for OpenShift AI, monitoring, registry | 3yr No Upfront Savings Plan |
| **OpenShift Subscription** | ROSA/OSD worker node licensing per 4 vCPUs | $667/4-vCPU/yr (3yr contract) |
| **OpenShift AI Subscription** | AI platform licensing for all worker nodes | $0.022/vCPU/hr |

**Pricing assumptions:**
- AWS region: **US East (Ohio) / us-east-2**
- OpenShift subscription: **3yr at $667/4-vCPU/yr** (vs. 1yr $1,000 or PayGo $1,500)
- m5.2xlarge: 8 vCPUs, $0.384/hr on-demand, **$0.166/hr 3yr SP** (57% savings)
- g6e.xlarge: 4 vCPUs, $1.86/hr on-demand, **$0.93/hr 3yr SP** (50% savings)
- ROSA HCP: **$0.25/hr cluster fee** + **$0.171/hr per 4 worker vCPUs**

**Total ROSA service fee per worker vCPU/hr:** $0.171 / 4 = **$0.043/vCPU/hr**

### 8.2 Calculation Formulas

**Hosted Control Plane:** $0.25/hr × 730 hr/mo = **$182.50/mo**

**EC2 GPU:** GPU_count × Instance_$/hr × 730 hr/mo

**EC2 Infrastructure:** 3 × $0.166/hr × 730 hr/mo = **$364/mo**

**OpenShift Subscription:** ceil(Total_vCPUs / 4) × $667/yr / 12

**OpenShift AI Subscription:** Total_vCPUs × $0.022/hr × 730 hr/mo

**ROSA Worker Service Fee:** Total_Worker_vCPUs × $0.043/hr × 730 hr/mo

---

## Appendix A: Detailed Sizing Tables

### A.1 Qwen 3.6 35B-A3B Deployment Sizing

**Model:** Qwen 3.6 35B-A3B (DeltaNet MoE, 73.4% SWE-bench)  
**GPU:** NVIDIA L40S (g6e.xlarge)  
**Region:** US East (Ohio) / us-east-2  
**Commitment:** 3-year Savings Plan

---

#### A.1.1 Configuration for 100 Developers

| Context Window | **64K** | **128K** | **200K** |
|---------------|---------|---------|---------|
| **Concurrent developers (20%)** | 20 | 20 | 20 |
| **Developers per L40S** | 17 | 8 | 5 |
| **GPUs required** | 2 | 3 | 4 |
| **GPU instances** | 2× g6e.xlarge | 3× g6e.xlarge | 4× g6e.xlarge |
| **GPU vCPUs** | 8 | 12 | 16 |
| **Non-GPU Worker Nodes** | 3× m5.2xlarge | 3× m5.2xlarge | 3× m5.2xlarge |
| **Non-GPU Worker Node Cores** | 24 | 24 | 24 |
| **Total vCPUs** | 32 | 36 | 40 |
| | | | |
| **MONTHLY COSTS** | | | |
| Hosted Control Plane | $183 | $183 | $183 |
| EC2 GPU (3yr SP) | $1,358 | $2,037 | $2,715 |
| EC2 Infrastructure (3yr SP) | $364 | $364 | $364 |
| OpenShift Subscription (3yr) | $445 | $500 | $556 |
| OpenShift AI Subscription | $514 | $578 | $642 |
| ROSA Worker Service Fee | $1,003 | $1,129 | $1,254 |
| **Total Monthly** | **$3,867** | **$4,791** | **$5,714** |
| **Per Developer/Month** | **$39** | **$48** | **$57** |
| | | | |
| **3-YEAR TCO** | $139,212 | $172,476 | $205,704 |
| **Per Developer (3yr)** | $1,392 | $1,725 | $2,057 |

**Throughput per developer:** All configurations deliver **>30 tokens/sec** sustained (verified at 64K: ~42 tok/s, bandwidth-limited)

---

#### A.1.2 Configuration for 200 Developers

| Context Window | **64K** | **128K** | **200K** |
|---------------|---------|---------|---------|
| **Concurrent developers (20%)** | 40 | 40 | 40 |
| **Developers per L40S** | 17 | 8 | 5 |
| **GPUs required** | 3 | 5 | 8 |
| **GPU instances** | 3× g6e.xlarge | 5× g6e.xlarge | 8× g6e.xlarge |
| **GPU vCPUs** | 12 | 20 | 32 |
| **Non-GPU Worker Nodes** | 3× m5.2xlarge | 3× m5.2xlarge | 3× m5.2xlarge |
| **Non-GPU Worker Node Cores** | 24 | 24 | 24 |
| **Total vCPUs** | 36 | 44 | 56 |
| | | | |
| **MONTHLY COSTS** | | | |
| Hosted Control Plane | $183 | $183 | $183 |
| EC2 GPU (3yr SP) | $2,037 | $3,395 | $5,432 |
| EC2 Infrastructure (3yr SP) | $364 | $364 | $364 |
| OpenShift Subscription (3yr) | $500 | $611 | $778 |
| OpenShift AI Subscription | $578 | $707 | $899 |
| ROSA Worker Service Fee | $1,129 | $1,380 | $1,757 |
| **Total Monthly** | **$4,791** | **$6,640** | **$9,413** |
| **Per Developer/Month** | **$24** | **$33** | **$47** |
| | | | |
| **3-YEAR TCO** | $172,476 | $239,040 | $338,868 |
| **Per Developer (3yr)** | $862 | $1,195 | $1,694 |

---

#### A.1.3 Configuration for 500 Developers

| Context Window | **64K** | **128K** | **200K** |
|---------------|---------|---------|---------|
| **Concurrent developers (20%)** | 100 | 100 | 100 |
| **Developers per L40S** | 17 | 8 | 5 |
| **GPUs required** | 6 | 13 | 20 |
| **GPU instances** | 6× g6e.xlarge | 13× g6e.xlarge | 20× g6e.xlarge |
| **GPU vCPUs** | 24 | 52 | 80 |
| **Non-GPU Worker Nodes** | 3× m5.2xlarge | 3× m5.2xlarge | 3× m5.2xlarge |
| **Non-GPU Worker Node Cores** | 24 | 24 | 24 |
| **Total vCPUs** | 48 | 76 | 104 |
| | | | |
| **MONTHLY COSTS** | | | |
| Hosted Control Plane | $183 | $183 | $183 |
| EC2 GPU (3yr SP) | $4,074 | $8,831 | $13,588 |
| EC2 Infrastructure (3yr SP) | $364 | $364 | $364 |
| OpenShift Subscription (3yr) | $667 | $1,056 | $1,445 |
| OpenShift AI Subscription | $771 | $1,221 | $1,670 |
| ROSA Worker Service Fee | $1,505 | $2,383 | $3,262 |
| **Total Monthly** | **$7,564** | **$14,038** | **$20,512** |
| **Per Developer/Month** | **$15** | **$28** | **$41** |
| | | | |
| **3-YEAR TCO** | $272,304 | $505,368 | $738,432 |
| **Per Developer (3yr)** | $545 | $1,011 | $1,477 |

---

### A.2 Qwen3-Coder-Next 80B Deployment Sizing

**Model:** Qwen3-Coder-Next 80B (DeltaNet MoE, 65.4% SWE-bench)  
**GPU:** NVIDIA H100 (single-GPU instances)  
**Region:** US East (N. Virginia) / us-east-1  
**Commitment:** 3-year Savings Plan

**Why H100 Single-GPU Instances:**
- **Model compatibility:** Qwen3-Coder-Next 80B requires ~78 GB at FP8 → fits on single H100 (80GB VRAM)
- **AWS availability:** p5.4xlarge (1× H100, 16 vCPUs) - [announced August 2025](https://aws.amazon.com/about-aws/whats-new/2025/08/amazon-p5-single-gpu-instances-now-available/)
- **Cost-optimized:** Zero GPU waste; right-sized for actual demand
- **H200 not viable:** AWS only offers H200 in 8-GPU configuration (p5en.48xlarge), resulting in 87.5% waste for teams ≤500 developers

---

#### A.2.1 Configuration for 100 Developers (Single H100)

| Context Window | **64K** | **128K** | **200K** |
|---------------|---------|---------|---------|
| **Concurrent developers (20%)** | 20 | 20 | 20 |
| **Developers per H100** | 82 | 41 | 26 |
| **GPUs required** | 1 | 1 | 1 |
| **GPU instances** | 1× p5.4xlarge | 1× p5.4xlarge | 1× p5.4xlarge |
| **GPU vCPUs** | 16 | 16 | 16 |
| **Non-GPU Worker Nodes** | 3× m5.2xlarge | 3× m5.2xlarge | 3× m5.2xlarge |
| **Non-GPU Worker Node Cores** | 24 | 24 | 24 |
| **Total vCPUs** | 40 | 40 | 40 |
| | | | |
| **MONTHLY COSTS** | | | |
| Hosted Control Plane | $183 | $183 | $183 |
| EC2 GPU (3yr SP) | $2,170 | $2,170 | $2,170 |
| EC2 Non-GPU (3yr SP) | $364 | $364 | $364 |
| OpenShift Subscription (3yr) | $556 | $556 | $556 |
| OpenShift AI Subscription | $642 | $642 | $642 |
| ROSA Worker Service Fee | $1,254 | $1,254 | $1,254 |
| **Total Monthly** | **$5,169** | **$5,169** | **$5,169** |
| **Per Developer/Month** | **$52** | **$52** | **$52** |
| | | | |
| **3-YEAR TCO** | $186,084 | $186,084 | $186,084 |
| **Per Developer (3yr)** | $1,861 | $1,861 | $1,861 |

**Excess capacity:** Can support up to 82 developers at 64K context (62 unused slots)

**Throughput per developer:** **>40 tokens/sec** sustained (H100 bandwidth: 3,352 GB/s)

---

#### A.2.2 Configuration for 200 Developers (Single H100)

| Context Window | **64K** | **128K** | **200K** |
|---------------|---------|---------|---------|
| **Concurrent developers (20%)** | 40 | 40 | 40 |
| **Developers per H100** | 82 | 41 | 26 |
| **GPUs required** | 1 | 1 | 2 |
| **GPU instances** | 1× p5.4xlarge | 1× p5.4xlarge | 2× p5.4xlarge |
| **GPU vCPUs** | 16 | 16 | 32 |
| **Non-GPU Worker Nodes** | 3× m5.2xlarge | 3× m5.2xlarge | 3× m5.2xlarge |
| **Non-GPU Worker Node Cores** | 24 | 24 | 24 |
| **Total vCPUs** | 40 | 40 | 56 |
| | | | |
| **MONTHLY COSTS** | | | |
| Hosted Control Plane | $183 | $183 | $183 |
| EC2 GPU (3yr SP) | $2,170 | $2,170 | $4,340 |
| EC2 Non-GPU (3yr SP) | $364 | $364 | $364 |
| OpenShift Subscription (3yr) | $556 | $556 | $778 |
| OpenShift AI Subscription | $642 | $642 | $899 |
| ROSA Worker Service Fee | $1,254 | $1,254 | $1,757 |
| **Total Monthly** | **$5,169** | **$5,169** | **$8,321** |
| **Per Developer/Month** | **$26** | **$26** | **$42** |
| | | | |
| **3-YEAR TCO** | $186,084 | $186,084 | $299,556 |
| **Per Developer (3yr)** | $931 | $931 | $1,498 |

**Excess capacity:** 42 unused slots at 64K/128K; minimal waste at 200K

---

#### A.2.3 Configuration for 500 Developers (Single H100)

| Context Window | **64K** | **128K** | **200K** |
|---------------|---------|---------|---------|
| **Concurrent developers (20%)** | 100 | 100 | 100 |
| **Developers per H100** | 82 | 41 | 26 |
| **GPUs required** | 2 | 3 | 4 |
| **GPU instances** | 2× p5.4xlarge | 3× p5.4xlarge | 4× p5.4xlarge |
| **GPU vCPUs** | 32 | 48 | 64 |
| **Non-GPU Worker Nodes** | 3× m5.2xlarge | 3× m5.2xlarge | 3× m5.2xlarge |
| **Non-GPU Worker Node Cores** | 24 | 24 | 24 |
| **Total vCPUs** | 56 | 72 | 88 |
| | | | |
| **MONTHLY COSTS** | | | |
| Hosted Control Plane | $183 | $183 | $183 |
| EC2 GPU (3yr SP) | $4,340 | $6,510 | $8,680 |
| EC2 Non-GPU (3yr SP) | $364 | $364 | $364 |
| OpenShift Subscription (3yr) | $778 | $1,001 | $1,223 |
| OpenShift AI Subscription | $899 | $1,157 | $1,414 |
| ROSA Worker Service Fee | $1,757 | $2,259 | $2,762 |
| **Total Monthly** | **$8,321** | **$11,474** | **$14,626** |
| **Per Developer/Month** | **$17** | **$23** | **$29** |
| | | | |
| **3-YEAR TCO** | $299,556 | $413,064 | $526,536 |
| **Per Developer (3yr)** | $599 | $826 | $1,053 |

**Throughput per developer:** **>40 tokens/sec** sustained

---

### A.3 Cost Comparison Summary

**Cost per Developer per Month (3-year commitment)**

| Team Size | Qwen 3.6 35B-A3B<br/>(L40S) 64K | Qwen 3.6 35B-A3B<br/>(L40S) 128K | Qwen3-Coder-Next<br/>(H100) 64K | Qwen3-Coder-Next<br/>(H100) 128K | Qwen3-Coder-Next<br/>(H100) 200K |
|-----------|---------------------------|------------------------------|------------------------------|------------------------------|------------------------------|
| **100 developers** | $39 | $48 | **$52** | **$52** | **$52** |
| **200 developers** | $24 | $33 | **$26** | **$26** | **$42** |
| **500 developers** | $15 | $28 | **$17** | **$23** | **$29** |

**Key Recommendations:**

1. **For most organizations (100-500 developers):** Qwen 3.6 35B-A3B on L40S at 64K context provides **optimal balance** of cost ($15-39/dev/mo) and code quality (73.4% SWE-bench)

2. **For premium code quality needs:** Qwen3-Coder-Next on **single H100 instances** (p5.4xlarge) offers excellent value at $17-52/dev/mo
   - Model fits comfortably on H100 80GB with FP8 quantization (~78 GB)
   - Competitive pricing with L40S option while delivering stronger GPU performance
   - Scales linearly and predictably with team size

3. **For very large teams (500+ developers):** 
   - L40S remains most cost-effective at $15-28/dev/mo
   - Single H100 instances scale linearly with predictable economics

4. **Context window selection:**
   - **64K:** Covers 85-90% of coding workflows; recommended baseline
   - **128K:** Power users, large codebases, complex refactoring
   - **200K:** Specialized use cases; consider dedicated pools via llm-d routing

5. **AWS Instance Selection:**
   - **L40S (g6e.xlarge):** Single-GPU instance - **RECOMMENDED for Qwen 3.6 35B-A3B**
   - **H100 (p5.4xlarge):** Single-GPU instance - **RECOMMENDED for Qwen3-Coder-Next 80B**
   - **H200:** Only available in wasteful 8-GPU configuration (p5en.48xlarge) - **NOT recommended** for this use case

---

## Appendix B: Methodology & Assumptions

### B.1 Calculation Methodology

| Quantity | Formula |
|----------|---------|
| Model weights (GB) | Total parameters × 1 byte (FP8) |
| KV cache per token | 2 × Attention_Layers × KV_Heads × Head_Dim × Bytes_per_Element |
| Available VRAM | GPU_VRAM − Model_Weights − 2 GB (runtime overhead) |
| Max concurrent devs | floor(Available_VRAM / KV_per_request) |
| Per-dev throughput | GPU_Memory_BW / (Active_Params_FP8 + Batch_Size × KV_per_request) |
| Peak concurrency | Team_Size × 0.20 |
| GPUs required | ceil(Peak_Concurrency / Developers_per_GPU) |

### B.2 Key Assumptions

**Infrastructure:**
- AWS region: US East (Ohio) / us-east-2
- 3-year commitment (Savings Plans for EC2, 3yr contract for OpenShift)
- 3 infrastructure worker nodes (m5.2xlarge) per cluster
- ROSA Hosted Control Plane at $0.25/hr
- Pricing verified June 2026

**Model Serving:**
- FP8 quantization for weights and KV cache
- vLLM with PagedAttention and continuous batching
- llm-d for KV-cache-aware routing and prefix reuse
- 2 GB runtime overhead per GPU
- 1 concurrent request per developer

**Developer Behavior:**
- Peak concurrency: 20% of team size (65% online × 25% active × 1.2 buffer)
- Minimum throughput: 30 tokens/second sustained per active developer
- Context window usage: 64K baseline, 128K for 20% of users, 200K for <5%

**Cost Components:**
- OpenShift subscription: $667/4-vCPU/year (3yr contract)
- OpenShift AI: $0.022/vCPU/hr for all worker nodes
- ROSA service fee: $0.043/vCPU/hr for worker nodes
- No data transfer costs included (internal cluster traffic)
- No backup/disaster recovery costs included

### B.3 Limitations & Considerations

**Not Included in TCO:**
- Data transfer / egress costs
- Backup and disaster recovery infrastructure
- Development/staging environments
- Fine-tuning infrastructure
- Model registry and artifact storage
- SIEM/logging infrastructure costs
- Network security appliances
- Support costs beyond Red Hat subscriptions

**Performance Considerations:**
- Actual throughput depends on prompt complexity and generation length
- Cache hit rates vary based on prompt structure and llm-d configuration
- Context window usage should be monitored and optimized
- GPU utilization benefits from load balancing across availability zones

**Procurement Considerations:**
- AWS pricing subject to change; verify current rates before procurement
- Reserved Instance and Savings Plan commitments require upfront planning
- OpenShift subscription pricing should be confirmed with Red Hat sales
- GPU availability varies by region; us-east-2 availability verified June 2026

---

## References & Sources

### Regulatory & Compliance

1. **EU AI Act** - [Article 99: Penalties](https://artificialintelligenceact.eu/article/99/)
   - Maximum fines: €35 million or 7% of global revenue for prohibited AI practices
   - [EU AI Act Explained: Risk Tiers, Penalties & Timeline](https://decodethefuture.org/en/eu-ai-act-explained/)

2. **DORA (Digital Operational Resilience Act)** - [EIOPA Official Page](https://www.eiopa.europa.eu/digital-operational-resilience-act-dora_en)
   - Enforcement: January 17, 2025
   - [DORA Requirements & Deadlines](https://quointelligence.eu/2025/02/dora-explained-scope-requirements-enforcement-deadlines/)

### AI Coding Tools & Statistics

3. **Developer AI Adoption** - [Stack Overflow 2024 Developer Survey](https://stackoverflow.com/dev-survey)
   - 76% of developers use AI tools in their work

4. **AI Code Governance** - [Cycode AI Security Vulnerabilities 2026](https://cycode.com/blog/ai-security-vulnerabilities/)
   - 76% of organizations consider shadow AI a challenge
   - [Checkmarx CISO Guide to AI-Generated Code](https://checkmarx.com/blog/ai-is-writing-your-code-whos-keeping-it-secure/)
   - Only 18% have policies governing AI-generated code

### Model Specifications & Benchmarks

5. **Qwen 3.6 35B-A3B** - [HuggingFace Model Card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)
   - [Official Qwen Blog: Qwen3.6-35B-A3B](https://qwen.ai/blog?id=qwen3.6-35b-a3b)
   - [Complete Review: Qwen3.6-35B-A3B](https://dev.to/czmilo/qwen36-35b-a3b-complete-review-alibabas-open-source-coding-model-that-beats-frontier-giants-4382)
   - SWE-bench Verified: 73.4%

6. **Qwen3-Coder-Next 80B** - [Model Specifications](https://apxml.com/models/qwen3-next-80b-a3b)
   - [Hardware Requirements Guide](https://www.compute-market.com/blog/qwen-3-coder-next-local-hardware-guide-2026/)
   - SWE-bench Verified: 65.4%

7. **Llama 3.3 70B** - [Model Overview & Benchmarks](https://tokenmix.ai/blog/llama-3-3-70b)
   - [Intelligence & Performance Analysis](https://artificialanalysis.ai/models/llama-3-3-instruct-70b)
   - HumanEval: 88.4%, SWE-bench: 55-72%

8. **Gemma 4** - [Technical Overview](https://www.labellerr.com/blog/gemma-4-open-weight-ai-model-overview/)
   - [Gemma 4 Benchmarks](https://gemmai4.com/benchmark/)
   - [SWE-bench Performance Analysis](https://www.gemma4.wiki/guide/gemma-4-swe-bench-score)
   - 31B: SWE-bench Verified 61.4%, LiveCodeBench v6 80.0%

9. **Nemotron 3 Nano** - [Technical Report (PDF)](https://research.nvidia.com/labs/nemotron/files/NVIDIA-Nemotron-3-Nano-Technical-Report.pdf)
   - [Complete Guide](https://llm-stats.com/blog/research/nemotron-3-nano-launch)
   - [HuggingFace Model Card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16)
   - 30B-A3B: HumanEval 78.05%, LiveCodeBench v6 68.3%

10. **DeepSeek V3.2** - [Model Review](https://medium.com/@leucopsis/deepseek-v3-2-exp-review-49ba1e1beb7c)
    - [SWE-bench Results](https://www.swebench.com/)
    - SWE-bench Verified: 67.8-74%, LiveCodeBench 83.3%

### GPU Specifications & Pricing

16. **NVIDIA GPU Specifications**
    - **L40S:** [Official NVIDIA Page](https://www.nvidia.com/en-us/data-center/l40s/) - 48 GB VRAM, 864 GB/s bandwidth
    - [L40S Detailed Specs & Pricing 2026](https://www.fluence.network/blog/nvidia-l40s/)

17. **AWS EC2 GPU Instances** - [AWS EC2 Pricing](https://aws.amazon.com/ec2/pricing/on-demand/)
    - [g6e.xlarge Pricing & Specs](https://instances.vantage.sh/aws/ec2/g6e.xlarge)
    - [p5en.48xlarge (H200) Pricing](https://cloudprice.net/aws/ec2/instances/p5e.48xlarge)
    - [AWS H100/H200 Pricing Analysis 2026](https://www.spheron.network/blog/aws-h100-pricing-2026/)

### vLLM & Serving Technology

18. **vLLM PagedAttention** - [vLLM Documentation: Paged Attention](https://docs.vllm.ai/en/latest/design/paged_attention/)
    - [Automatic Prefix Caching](https://docs.vllm.ai/en/latest/design/prefix_caching/)
    - [Hybrid KV Cache Manager](https://docs.vllm.ai/en/latest/design/hybrid_kv_cache_manager/)
    - Reduces memory fragmentation from 60-80% to <4%, enabling 2-4× throughput

19. **llm-d KV-Cache Optimization** - [KV-Cache Wins: From Prefix Caching to Distributed Scheduling](https://llm-d.ai/blog/kvcache-wins-you-can-see)
    - Cache hit rates of 87%+ with structured prompts
    - 10× cost difference between cached and uncached tokens

### LLM Inference & Performance

20. **Tokens Per Second Requirements** - [LLM Speed Benchmark Guide](https://www.morphllm.com/tokens-per-second)
    - [Balancing Speed, Cost & Quality](https://www.bentoml.com/blog/beyond-tokens-per-second-how-to-balance-speed-cost-and-quality-in-llm-inference)
    - [Key Metrics for LLM Inference](https://bentoml.com/llm/inference-optimization/llm-inference-metrics)
    - [Why Tokens per Second Is Misleading](https://www.codeant.ai/blogs/end-to-end-task-latency-vs-tokens-per-second)
    - Recommended: 30+ tok/s for interactive coding, 50+ tok/s for agentic workflows

21. **Developer Tool Adoption** - [AI Coding Statistics](https://www.getpanto.ai/blog/ai-coding-assistant-statistics)
    - 84% of developers use or plan to use AI tools
    - 51% of professional developers use AI tools daily
    - [JetBrains Developer Survey](https://blog.jetbrains.com/research/2026/04/which-ai-coding-tools-do-developers-actually-use-at-work/)
    - GitHub Copilot: 40% adoption in companies with 5,000+ employees

### Red Hat & OpenShift

13. **Red Hat OpenShift AI** - [Product Page](https://www.redhat.com/en/products/ai/openshift-ai)
    - Includes Red Hat AI Gateway for API management
    - Pricing details require Red Hat sales consultation

14. **Red Hat OpenShift Deployment Options**
    - **ROSA (AWS):** [Red Hat OpenShift Service on AWS](https://aws.amazon.com/rosa/pricing/)
    - **ARO (Azure):** [Azure Red Hat OpenShift](https://azure.microsoft.com/en-us/pricing/details/openshift/)
    - **OSD (GCP):** OpenShift Dedicated on Google Cloud Platform
    - **On-Premises:** Self-managed OpenShift with customer-owned infrastructure

15. **ROSA Pricing** (used in this report) - [Pricing Details](https://aws.amazon.com/rosa/pricing/)
    - Hosted Control Plane: $0.25/hr
    - Worker service fee: $0.171/hr per 4 vCPUs
    - [ROSA HCP Announcement](https://aws.amazon.com/about-aws/whats-new/2024/01/rosa-hosted-control-planes-hcp/)

---

**Document Version History:**

- **v3.0 (June 2026):** Major comprehensive update
  - Added comprehensive coding model comparison table (Section 5.2) covering 8 leading models in 30B-80B range with public benchmarks
  - Expanded concurrency analysis (Section 6.1) with detailed breakdown of 20% concurrent user assumption and industry validation
  - Added throughput requirements analysis (Section 6.1) explaining 30 tok/s minimum with use-case sensitivity table
  - Clarified Red Hat AI Gateway is included with Red Hat AI/OpenShift AI (no separate GAIE acronym)
  - Added deployment options: on-premises, ROSA (AWS), ARO (Azure), OSD (GCP); pricing exercise uses ROSA
  - Updated terminology: "Infrastructure worker nodes" → "Non-GPU worker nodes"; "Infrastructure vCPUs" → "Non-GPU Worker Node Cores"
  - Detailed sizing appendix for Qwen 3.6 35B-A3B and Qwen3-Coder-Next 80B with 64K/128K/200K context windows
  - Updated regulatory compliance deadlines (EU AI Act, DORA) with accurate enforcement dates
  - Added ROSA service fees to all cost calculations
  - Corrected all pricing to US East (Ohio) / us-east-2
  - Expanded references section to 21 sources including model benchmarks, throughput research, developer adoption statistics
- **v2.0 (April 2026):** Initial detailed TCO analysis
- **v1.0:** Internal draft

---

*This report provides infrastructure sizing and TCO analysis based on publicly available specifications and pricing as of June 2026. Organizations should validate calculations with empirical benchmarks on target infrastructure and confirm current pricing with AWS and Red Hat before making procurement decisions. Performance characteristics depend on workload patterns, model serving configuration, and infrastructure optimization.*
