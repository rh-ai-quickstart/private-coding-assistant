import {
  BarChart,
  Callout,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  LineChart,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  useCanvasState,
  useHostTheme,
} from "cursor/canvas";

type Section = "overview" | "market" | "advantages" | "models" | "gpus" | "capacity" | "concurrency" | "recommendations" | "tco" | "alt" | "appendix";

function SectionNav({ active, onSelect }: { active: Section; onSelect: (s: Section) => void }) {
  const sections: { id: Section; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "market", label: "Market Case" },
    { id: "advantages", label: "Why Red Hat" },
    { id: "models", label: "Models" },
    { id: "gpus", label: "GPUs" },
    { id: "capacity", label: "Capacity" },
    { id: "concurrency", label: "Concurrency" },
    { id: "recommendations", label: "Recommendations" },
    { id: "tco", label: "Full-Stack TCO" },
    { id: "alt", label: "Alt Accelerators" },
    { id: "appendix", label: "30 tok/s" },
  ];
  return (
    <Row gap={6} wrap>
      {sections.map((s) => (
        <Pill key={s.id} active={active === s.id} onClick={() => onSelect(s.id)}>
          {s.label}
        </Pill>
      ))}
    </Row>
  );
}

function ArchitectureDiagram() {
  const theme = useHostTheme();
  const boxFill = theme.fill.tertiary;
  const boxStroke = theme.stroke.secondary;
  const accentFill = theme.accent.primary;
  const textPrimary = theme.text.primary;
  const textSecondary = theme.text.secondary;
  const textOnAccent = theme.text.onAccent;

  return (
    <svg viewBox="0 0 720 470" style={{ width: "100%", height: "auto" }}>
      <rect x="20" y="10" width="680" height="70" rx="8" fill={boxFill} stroke={boxStroke} strokeWidth="1" />
      <text x="360" y="32" textAnchor="middle" fill={textSecondary} fontSize="11" fontWeight="500">Developer Workstations</text>
      {[{ x: 80, label: "VSCode + Cline" }, { x: 300, label: "VSCode + OpenCode" }, { x: 530, label: "Developer N" }].map((d, i) => (
        <g key={i}>
          <rect x={d.x} y="42" width="130" height="28" rx="4" fill={theme.fill.secondary} stroke={boxStroke} strokeWidth="1" />
          <text x={d.x + 65} y="60" textAnchor="middle" fill={textPrimary} fontSize="10">{d.label}</text>
        </g>
      ))}
      <text x="460" y="60" textAnchor="middle" fill={textSecondary} fontSize="12">...</text>
      {[145, 365, 595].map((x, i) => (
        <line key={i} x1={x} y1="70" x2={x} y2="100" stroke={boxStroke} strokeWidth="1.5" markerEnd="url(#arrowhead)" />
      ))}
      <defs>
        <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill={boxStroke} />
        </marker>
      </defs>
      <rect x="20" y="100" width="680" height="360" rx="8" fill="none" stroke={accentFill} strokeWidth="1.5" strokeDasharray="6 3" />
      <text x="40" y="120" fill={accentFill} fontSize="11" fontWeight="600">ROSA (AWS) / OpenShift Dedicated (GCP)</text>
      <rect x="180" y="132" width="360" height="40" rx="6" fill={theme.fill.secondary} stroke={boxStroke} strokeWidth="1" />
      <text x="360" y="148" textAnchor="middle" fill={textPrimary} fontSize="11" fontWeight="500">OpenShift DevSpaces</text>
      <text x="360" y="163" textAnchor="middle" fill={textSecondary} fontSize="9">Cloud-hosted VSCode workspaces</text>
      <line x1="360" y1="172" x2="360" y2="192" stroke={boxStroke} strokeWidth="1.5" markerEnd="url(#arrowhead)" />
      <rect x="180" y="192" width="360" height="40" rx="6" fill={accentFill} stroke="none" />
      <text x="360" y="210" textAnchor="middle" fill={textOnAccent} fontSize="11" fontWeight="600">Red Hat AI Gateway (GAIE)</text>
      <text x="360" y="224" textAnchor="middle" fill={textOnAccent} fontSize="9" opacity="0.85">OpenAI-compatible API / Auth / Rate Limiting</text>
      <line x1="360" y1="232" x2="360" y2="252" stroke={boxStroke} strokeWidth="1.5" markerEnd="url(#arrowhead)" />
      <rect x="180" y="252" width="360" height="40" rx="6" fill={theme.fill.secondary} stroke={boxStroke} strokeWidth="1" />
      <text x="360" y="270" textAnchor="middle" fill={textPrimary} fontSize="11" fontWeight="500">llm-d Scheduler (CNCF Sandbox)</text>
      <text x="360" y="284" textAnchor="middle" fill={textSecondary} fontSize="9">KV-cache-aware routing / Prefix cache reuse</text>
      {[180, 360, 540].map((x, i) => (
        <line key={i} x1={x} y1="292" x2={x} y2="322" stroke={boxStroke} strokeWidth="1.5" markerEnd="url(#arrowhead)" />
      ))}
      {[{ x: 80, label: "vLLM Pod" }, { x: 280, label: "vLLM Pod" }, { x: 460, label: "vLLM Pod" }].map((d, i) => (
        <g key={i}>
          <rect x={d.x} y="322" width="180" height="50" rx="6" fill={theme.fill.tertiary} stroke={boxStroke} strokeWidth="1" />
          <text x={d.x + 90} y="340" textAnchor="middle" fill={textPrimary} fontSize="10" fontWeight="500">{d.label}</text>
          <text x={d.x + 90} y="358" textAnchor="middle" fill={accentFill} fontSize="9" fontWeight="500">GPU / Accelerator</text>
        </g>
      ))}
      <rect x="80" y="390" width="560" height="50" rx="6" fill={theme.fill.secondary} stroke={boxStroke} strokeWidth="1" />
      <text x="360" y="410" textAnchor="middle" fill={textPrimary} fontSize="10" fontWeight="500">Infrastructure Workers (3x m5.2xlarge)</text>
      <text x="360" y="426" textAnchor="middle" fill={textSecondary} fontSize="9">OpenShift AI, Monitoring, Registry, Gateway</text>
    </svg>
  );
}

function OverviewSection() {
  return (
    <Stack gap={16}>
      <H2>Executive Summary</H2>
      <Text>Infrastructure sizing and total cost of ownership for deploying a fully private, self-hosted AI coding assistant on Red Hat OpenShift — targeting regulated industries (banking, government, healthcare) requiring complete data sovereignty and IP control.</Text>
      <Grid columns={4} gap={12}>
        <Stat value="$18-41" label="Per Dev/Month (Full Stack)" tone="success" />
        <Stat value="6" label="Models Evaluated" />
        <Stat value="20 tok/s" label="Throughput Baseline" tone="info" />
        <Stat value="~20%" label="Peak Concurrency" tone="warning" />
      </Grid>
      <Divider />
      <H3>Architecture</H3>
      <ArchitectureDiagram />
      <Divider />
      <H3>Key Findings</H3>
      <Callout tone="success" title="Best Value — Full-Stack $18/dev/mo at 200 Developers">
        Qwen3.6-35B-A3B on L40S (g6e.xlarge) with full Red Hat stack including OpenShift subscriptions, OpenShift AI, Hosted Control Plane, and 3 infra nodes. At 100 devs: $29/dev/mo. At 50 devs: $41/dev/mo. These are complete costs — no hidden per-seat licensing.
      </Callout>
      <Callout tone="info" title="Architecture Advantage — MoE + DeltaNet">
        Hybrid MoE models reduce KV cache by 75-95% vs standard transformers, enabling 4-10x more concurrent users per GPU. VRAM is always the binding constraint for MoE — bandwidth is never the bottleneck.
      </Callout>
      <Callout tone="success" title="Memory Efficiency — PagedAttention + Prefix Caching">
        vLLM PagedAttention allocates KV dynamically and frees it instantly on completion. llm-d routes multi-turn conversations for prefix reuse. Together: 2.5-4x effective concurrency beyond worst-case limits.
      </Callout>
      <Callout tone="warning" title="Compatibility Trade-off">
        DeltaNet hybrid models (highest quality) require NVIDIA CUDA. Alternative accelerators (Trainium, TPU) are limited to standard MoE architectures with lower code quality scores.
      </Callout>
    </Stack>
  );
}

function MarketSection() {
  return (
    <Stack gap={16}>
      <H2>The Case for Private AI Code Assistance</H2>
      <Text>Regulated industries face an urgent need for AI developer productivity tools, but regulatory and security requirements prevent adoption of SaaS-based solutions.</Text>
      <H3>Market Drivers</H3>
      <Table
        headers={["Driver", "Deadline / Status", "Impact on AI Coding"]}
        rows={[
          ["EU AI Act", "August 2026 (high-risk)", "Third-party black-box APIs complicate compliance"],
          ["DORA (Financial)", "Enforcement Jan 2025", "Article 30: sovereignty over cloud vendors"],
          ["FedRAMP / DoD SRG", "Active", "Authorized stacks, data boundaries, logging"],
          ["Shadow AI Risk", "76% run ungoverned AI code", "Uncontrolled IP leakage via public AI"],
          ["Private AI Adoption", "$109B global spend (2024)", "55% to 78% enterprise adoption"],
        ]}
        rowTone={["danger", "danger", "warning", "danger", "success"]}
        striped
      />
      <Divider />
      <H3>Customer Segments</H3>
      <Table
        headers={["Segment", "Regulatory Framework", "Key AI Coding Concern"]}
        rows={[
          ["Banking / FS", "DORA, PCI DSS, Basel", "Prompts/logs must be governable; exit & residency proofs"],
          ["Government / Defense", "FedRAMP, ITAR", "Air-gap, attested images, no incidental data export"],
          ["Healthcare", "HIPAA, BAA", "PHI cannot cross unapproved paths — even in code context"],
          ["Telecom / CI", "NIS2 Directive", "Supply-chain security; controlled CI/CD and model chain"],
        ]}
        striped
      />
      <Divider />
      <H3>SaaS vs Private Deployment</H3>
      <Table
        headers={["Dimension", "SaaS AI Coding", "Private Red Hat Stack"]}
        rows={[
          ["Data residency", "Vendor-defined regions; subprocessors", "Cluster region + network policy"],
          ["IP control", "Vendor terms; limited visibility", "Weights, logs, backups in customer footprint"],
          ["Model customization", "Add-on, region-limited", "Open-weight; RAG + fine-tune inside boundary"],
          ["Audit trail", "Export-limited; forensic gaps", "Immutable logging to customer SIEM"],
          ["Air-gap capability", "Not generally available", "Disconnected registries, mirrored bases"],
          ["Cost scaling", "Linear per seat ($19-39/mo)", "Sub-linear — tracks concurrency, not headcount"],
        ]}
        rowTone={["danger", "danger", "warning", "danger", "danger", "success"]}
        striped
      />
      <Callout tone="info" title="Fines Up To EUR 35M / 7% Global Turnover">
        EU AI Act non-compliance can compound with GDPR and DORA penalties. Architecturally isolated deployment eliminates the regulatory risk of third-party AI data processing.
      </Callout>
    </Stack>
  );
}

function AdvantagesSection() {
  return (
    <Stack gap={16}>
      <H2>Solution Advantages: Red Hat AI Platform</H2>
      <H3>Cost Advantages</H3>
      <Table
        headers={["Capability", "Technical Detail", "Cost Impact"]}
        rows={[
          ["No per-seat AI license", "Open-weight models; infrastructure cost only", "TCO tracks concurrency, not seat count"],
          ["PagedAttention (vLLM)", "Dynamic per-token KV; idle users hold zero VRAM", "2.5-4x more users per GPU"],
          ["MoE model support", "3B active params per token vs 27-80B dense", "4-8x reduction in GPU requirements"],
          ["llm-d prefix caching", "Shared system prompts + KV-aware routing", "20-40% fewer GPUs needed"],
          ["FP8 quantization", "2x parameter density with <1% quality loss", "Smaller GPUs viable for same model"],
        ]}
        rowTone={["success", "success", "success", "success", "success"]}
        striped
      />
      <Divider />
      <H3>Full-Stack Cost: Private vs SaaS</H3>
      <Table
        headers={["Team", "Full-Stack Private (3yr SP)", "SaaS Enterprise ($39/dev)", "Annual Savings"]}
        rows={[
          ["50 devs", "$2,065/mo ($41/dev)", "$1,950/mo", "+$115 (break-even)"],
          ["100 devs", "$2,864/mo ($29/dev)", "$3,900/mo", "$12K/yr savings"],
          ["200 devs", "$3,662/mo ($18/dev)", "$7,800/mo", "$50K/yr savings"],
        ]}
        rowTone={["warning", "success", "success"]}
        columnAlign={["left", "right", "right", "right"]}
        striped
      />
      <Text size="small" tone="secondary">Private stack includes EC2 GPU + infra + OpenShift subscription + OpenShift AI + Hosted Control Plane. SaaS at $39/dev/mo list (Copilot Enterprise).</Text>
      <Divider />
      <H3>Security & Data Sovereignty</H3>
      <Table
        headers={["Risk", "SaaS AI", "Private Red Hat"]}
        rows={[
          ["Source code sent to third parties", "Yes — includes full context", "No — all inference within VPC"],
          ["Model trains on customer data", "Depends on agreement", "Impossible — open-weight, static local"],
          ["Regulatory compliance", "Limited FedRAMP/HIPAA", "ROSA FedRAMP Moderate + FIPS crypto"],
          ["Vendor price increases", "Uncontrollable", "Locked to infra; 3yr savings plan"],
          ["Audit trail ownership", "Vendor-held; export limited", "Full ownership; customer SIEM"],
        ]}
        rowTone={["danger", "danger", "warning", "warning", "danger"]}
        striped
      />
      <Divider />
      <H3>Operational Advantages</H3>
      <Table
        headers={["Task", "DIY K8s + vLLM", "Red Hat AI Platform"]}
        rows={[
          ["GPU driver updates", "Manual node-by-node", "Machine Config Operator — atomic"],
          ["Model deployment", "Custom Dockerfiles", "Model Registry + ServingRuntime CRD"],
          ["Scaling replicas", "Custom HPA metrics", "KNative autoscaler with GPU metrics"],
          ["Security patching", "Track CVEs manually", "RHSA with SLA-backed response times"],
          ["Compliance auditing", "Custom logging pipeline", "Compliance Operator (CIS, NIST, PCI)"],
          ["Support", "Community only", "24x7 Red Hat enterprise support"],
        ]}
        rowTone={["warning", "warning", "warning", "warning", "warning", "danger"]}
        striped
      />
    </Stack>
  );
}

function ModelsSection() {
  return (
    <Stack gap={16}>
      <H2>Model Specifications & Benchmarks</H2>
      <Table
        headers={["Model", "Architecture", "Params (Total/Active)", "KV/Token", "FP8 Size", "vLLM"]}
        rows={[
          ["Qwen3.6-35B-A3B", "MoE + DeltaNet", "35B / 3.3B", "~10 KB", "35.2 GB", "Yes"],
          ["Qwen3.6-27B", "Dense + DeltaNet", "27B / 27B", "~10 KB", "27.2 GB", "Yes"],
          ["Coder-Next 80B", "MoE + DeltaNet", "80B / ~10B", "~10 KB", "~78 GB", "Yes (0.12+)"],
          ["Qwen3-Coder-30B-A3B", "Standard MoE", "30.5B / 3.3B", "48 KB", "30.5 GB", "Yes"],
          ["Gemma 4 27B-A4B", "MoE + SWA", "27B / ~4B", "80 KB", "27.2 GB", "Yes"],
          ["Nemotron Nano 30B", "Mamba-2 + MoE", "~30B / 3.3B", "~4 KB", "~30 GB", "Yes"],
        ]}
        rowTone={["success", "info", undefined, undefined, undefined, undefined]}
        striped
      />
      <Text size="small" tone="secondary">Green: recommended. Blue: highest quality (dense).</Text>
      <Divider />
      <H3>Code Quality Benchmarks</H3>
      <Table
        headers={["Model", "SWE-bench Verified", "SWE-bench Pro", "LiveCodeBench v6", "HumanEval"]}
        rows={[
          ["Qwen3.6-27B (Dense)", "76.2%", "37.0%", "49.2%", "92.1%"],
          ["Qwen3.6-35B-A3B (MoE)", "73.4%", "35.2%", "47.8%", "90.2%"],
          ["Coder-Next 80B", "65.4%", "--", "42.1%", "87.8%"],
          ["Qwen3-Coder-30B-A3B", "--", "--", "40.3%", "--"],
          ["Gemma 4 27B-A4B", "36.2%", "--", "41.6%", "85.4%"],
          ["Nemotron Nano 30B", "26.0%", "--", "38.5%", "82.3%"],
        ]}
        columnAlign={["left", "center", "center", "center", "center"]}
        rowTone={["info", "success", undefined, undefined, undefined, "warning"]}
        striped
      />
      <Divider />
      <H3>SWE-bench Verified Scores</H3>
      <BarChart
        categories={["Qwen3.6-27B", "Qwen3.6-35B", "Coder-Next 80B", "Gemma 4", "Nemotron Nano", "Coder-30B"]}
        series={[{ name: "SWE-bench Verified (%)", data: [76.2, 73.4, 65.4, 36.2, 26, 0] }]}
        height={220}
        valueSuffix="%"
      />
      <Divider />
      <H3>Code Quality Ranking</H3>
      <Table
        headers={["Rank", "Model", "SWE-bench V.", "Assessment", "Deployment Trade-off"]}
        rows={[
          ["#1", "Qwen3.6-27B (Dense)", "76.2%", "Highest quality", "9x compute per token; impractical on mid-tier GPUs"],
          ["#2 ★", "Qwen3.6-35B-A3B", "73.4%", "Best all-round", "95% quality at 3B active params"],
          ["#3", "Coder-Next 80B", "65.4%", "Premium agentic", "Requires H200+ (78 GB weights)"],
          ["#4", "Gemma 4 27B-A4B", "~40%", "Good synthesis", "Heaviest KV cache limits concurrency"],
          ["#5", "Nemotron Nano 30B", "26.0%", "Moderate", "Best capacity, lower code quality"],
          ["#6", "Qwen3-Coder-30B-A3B", "--", "Weakest coverage", "Only model for Trainium/TPU"],
        ]}
        columnAlign={["center", "left", "center", "left", "left"]}
        rowTone={["info", "success", undefined, undefined, "warning", "warning"]}
        striped
      />
      <Callout tone="success">Qwen3.6-35B-A3B delivers 95% of top-ranked dense model quality at 9x lower compute — the optimal balance of quality, concurrency, and cost.</Callout>
    </Stack>
  );
}

function GpuSection() {
  return (
    <Stack gap={16}>
      <H2>GPU Specifications (us-east-1)</H2>
      <Table
        headers={["GPU", "VRAM", "Mem BW", "FP8", "Instance", "vCPUs", "OD $/hr", "3yr SP $/hr"]}
        rows={[
          ["L40S", "48 GB", "864 GB/s", "733 TF", "g6e.xlarge (1x)", "4", "$1.86", "$0.93"],
          ["A100 80GB", "80 GB", "2,039 GB/s", "-- (FP16)", "p4de.24xlarge (8x)", "96", "$27.45", "$14.27"],
          ["H100 80GB", "80 GB", "3,352 GB/s", "3,958 TF", "p5.4xlarge (1x)", "16", "$6.88", "$3.44"],
          ["H200 141GB", "141 GB", "4,800 GB/s", "3,958 TF", "p5en.48xlarge (8x)", "192", "$74.69", "$48.55"],
          ["B200 192GB", "192 GB", "8,000 GB/s", "9,000 TF", "p6-b200.48xlarge (8x)", "192", "$113.93", "$91.14"],
        ]}
        columnAlign={["left", "right", "right", "right", "left", "center", "right", "right"]}
        rowTone={["success", undefined, undefined, undefined, undefined]}
        striped
      />
      <Divider />
      <H3>Instance Size Optimization</H3>
      <Text>Single-GPU instances minimize both GPU waste and OpenShift subscription costs (fewer vCPUs to license).</Text>
      <Table
        headers={["Instance", "GPUs", "vCPUs", "Idle if 1 GPU Needed", "Wasted $/mo"]}
        rows={[
          ["g6e.xlarge", "1", "4", "0 GPUs", "$0"],
          ["g6e.48xlarge", "8", "192", "7 GPUs", "$4,767"],
          ["p5.4xlarge", "1", "16", "0 GPUs", "$0"],
          ["p5.48xlarge", "8", "192", "7 GPUs", "$17,570"],
        ]}
        rowTone={["success", "danger", "success", "danger"]}
        striped
      />
      <Callout tone="success" title="Key Insight">
        L40S and H100 offer single-GPU instances. A100, H200, and B200 force 8-GPU purchases with 192 vCPUs — dramatically increasing OpenShift subscription costs even if only 1 GPU is needed.
      </Callout>
      <Divider />
      <H3>Memory Bandwidth</H3>
      <BarChart
        categories={["L40S", "A100", "H100", "H200", "B200"]}
        series={[{ name: "Memory BW (GB/s)", data: [864, 2039, 3352, 4800, 8000] }]}
        height={200}
        valueSuffix=" GB/s"
      />
    </Stack>
  );
}

function CapacitySection() {
  const [selectedModel, setSelectedModel] = useCanvasState<string>("cap-model-v2", "qwen36-35b");

  const models: Record<string, { label: string; tone?: "success" | "info" | "warning"; rows: string[][] }> = {
    "qwen36-35b": {
      label: "Qwen3.6-35B-A3B (Recommended)",
      tone: "success",
      rows: [
        ["16K", "0.16", "67", "275", "275", "665", "992"],
        ["32K", "0.32", "33", "137", "137", "332", "496"],
        ["64K", "0.63", "17", "68", "68", "166", "248"],
        ["128K", "1.26", "8", "34", "34", "83", "124"],
        ["256K", "2.52", "4", "17", "17", "41", "62"],
      ],
    },
    "qwen3-coder-30b": {
      label: "Qwen3-Coder-30B-A3B",
      rows: [
        ["16K", "0.75", "20", "63", "63", "144", "212"],
        ["32K", "1.50", "10", "31", "31", "72", "106"],
        ["64K", "3.00", "5", "15", "15", "36", "53"],
        ["128K", "6.00", "2", "7", "7", "18", "26"],
        ["256K", "12.00", "1", "3", "3", "9", "13"],
      ],
    },
    "coder-next-80b": {
      label: "Coder-Next 80B (H200+ only)",
      tone: "info",
      rows: [
        ["16K", "0.19", "--", "--", "--", "314", "586"],
        ["32K", "0.38", "--", "--", "--", "157", "293"],
        ["64K", "0.75", "--", "--", "--", "78", "146"],
        ["128K", "1.50", "--", "--", "--", "39", "73"],
        ["256K", "3.00", "--", "--", "--", "19", "36"],
      ],
    },
    "gemma4-27b": {
      label: "Gemma 4 27B-A4B",
      tone: "warning",
      rows: [
        ["16K", "1.72", "11", "29", "29", "65", "95"],
        ["32K", "3.44", "5", "14", "14", "32", "47"],
        ["64K", "6.88", "2", "7", "7", "16", "23"],
        ["128K", "13.75", "1", "3", "3", "8", "11"],
        ["256K", "27.50", "--", "1", "1", "4", "5"],
      ],
    },
  };

  const sel = models[selectedModel];

  return (
    <Stack gap={16}>
      <H2>VRAM Capacity Analysis</H2>
      <Text>Maximum concurrent sessions per single GPU. FP8 weights + FP8 KV cache.</Text>
      <Row gap={6} wrap>
        {Object.entries(models).map(([key, m]) => (
          <Pill key={key} active={selectedModel === key} tone={m.tone} onClick={() => setSelectedModel(key)}>
            {m.label}
          </Pill>
        ))}
      </Row>
      <Table
        headers={["Context", "KV/Req (GB)", "L40S", "A100", "H100", "H200", "B200"]}
        rows={sel.rows}
        columnAlign={["left", "right", "right", "right", "right", "right", "right"]}
        striped
      />
      <Divider />
      <H3>Max Concurrent Users at 64K (by GPU)</H3>
      <BarChart
        categories={["L40S", "A100", "H100", "H200", "B200"]}
        series={[
          { name: "Qwen3.6-35B", data: [17, 68, 68, 166, 248], tone: "success" },
          { name: "Coder-30B", data: [5, 15, 15, 36, 53] },
          { name: "Coder-Next 80B", data: [0, 0, 0, 78, 146], tone: "info" },
        ]}
        height={240}
      />
      <Divider />
      <H3>Context Window Impact (Qwen3.6-35B on L40S)</H3>
      <BarChart
        categories={["16K", "32K", "64K", "128K", "256K"]}
        series={[{ name: "Concurrent devs per L40S", data: [67, 33, 17, 8, 4], tone: "success" }]}
        height={200}
      />
      <Text size="small" tone="secondary">Doubling context halves concurrency. 64K accommodates most agentic workflows.</Text>
    </Stack>
  );
}

function ConcurrencySection() {
  return (
    <Stack gap={16}>
      <H2>Concurrency & Throughput</H2>
      <H3>Workday Concurrency Model</H3>
      <Table
        headers={["Factor", "Value", "Derivation"]}
        rows={[
          ["Peak-hour online rate", "65%", "10-hour workday, staggered starts"],
          ["Active inference rate", "25%", "10-15% GPU duty cycle per session"],
          ["Base concurrency", "~16%", "0.65 x 0.25 = 0.163"],
          ["Burst headroom", "+20%", "Correlated bursts (post-standup)"],
          ["Design factor", "~20%", "0.163 x 1.20 = 0.20"],
        ]}
        rowTone={[undefined, undefined, undefined, "warning", "info"]}
        striped
      />
      <H3>Peak Concurrent Slots by Team</H3>
      <BarChart
        categories={["1", "10", "20", "50", "100", "200"]}
        series={[{ name: "Peak Slots", data: [1, 2, 4, 10, 20, 40], tone: "info" }]}
        height={180}
      />
      <Divider />
      <H3>Why 20 Tokens/Second Baseline</H3>
      <Table
        headers={["Throughput", "Developer Experience", "Impact"]}
        rows={[
          ["< 10 tok/s", "Frustratingly slow; devs abandon", "Severe"],
          ["10-15 tok/s", "Noticeably slow but usable", "Moderate"],
          ["15-25 tok/s", "Comfortable; developer stays engaged", "Low"],
          ["25-40 tok/s", "Fast; faster than reading speed", "Minimal"],
          ["> 40 tok/s", "Near-instantaneous", "None"],
        ]}
        rowTone={["danger", "warning", "success", undefined, undefined]}
        striped
      />
      <Callout tone="info">
        Average code reading speed is ~3-5 tokens/second. At 20 tok/s, output is 4-6x faster than reading. For MoE models, 20 vs 30 tok/s produces identical GPU requirements (VRAM-bound, not bandwidth-bound).
      </Callout>
      <Divider />
      <H3>PagedAttention & Prefix Caching</H3>
      <Table
        headers={["Technique", "How It Works", "Concurrency Impact"]}
        rows={[
          ["PagedAttention", "KV allocated per-token, freed on completion", "2.5-4x effective multiplier"],
          ["Dynamic allocation", "64K cap only uses actual tokens (~18K avg)", "~72% less VRAM per request"],
          ["Prefix caching (llm-d)", "Multi-turn routed to same pod; shared prompts", "40-70% TTFT reduction"],
          ["Cross-user sharing", "Identical system prompts share KV pages", "N users x 1 copy, not N copies"],
        ]}
        rowTone={["success", "success", "info", "info"]}
        striped
      />
      <Callout tone="success" title="Conservative Sizing">
        GPU counts in this report represent worst-case peak load. Real deployments typically need 20-40% fewer GPUs.
      </Callout>
    </Stack>
  );
}

function RecommendationsSection() {
  return (
    <Stack gap={16}>
      <H2>Recommendations — Three Perspectives</H2>
      <Text>All recommendations use Qwen3.6-35B-A3B at 64K context with FP8 quantization, 20 tok/s sustained baseline.</Text>

      <H3>Perspective A: Best Value (Lowest $/dev/mo)</H3>
      <Table
        headers={["Team", "Peak Slots", "GPU Config", "Instance", "GPU $/mo (3yr SP)"]}
        rows={[
          ["1 dev", "1", "1x L40S", "1x g6e.xlarge", "$679"],
          ["10 devs", "2", "1x L40S", "1x g6e.xlarge", "$679"],
          ["20 devs", "4", "1x L40S", "1x g6e.xlarge", "$679"],
          ["50 devs", "10", "1x L40S", "1x g6e.xlarge", "$679"],
          ["100 devs", "20", "2x L40S", "2x g6e.xlarge", "$1,358"],
          ["200 devs", "40", "3x L40S", "3x g6e.xlarge", "$2,037"],
        ]}
        striped
      />
      <Text size="small" tone="secondary">17 concurrent users per L40S at 64K. GPU cost only — see Full-Stack TCO tab for complete pricing.</Text>

      <Divider />
      <H3>Perspective B: Best Code Quality</H3>
      <Table
        headers={["Team", "Model", "Instance", "Slots", "GPU $/mo (3yr SP)"]}
        rows={[
          ["Any ≤200", "Coder-Next 80B", "1x p5en.48xlarge (8x H200)", "~776", "$35,442"],
        ]}
        striped
      />
      <Callout tone="warning" title="Premium Tier">
        p5en.48xlarge has massive excess capacity for ≤200 devs. No smaller H200 instance exists. 192 vCPUs drive high OpenShift subscription costs ($3,002/mo OCP + $3,470/mo OCP AI). Total full-stack: $42,461/mo.
      </Callout>

      <Divider />
      <H3>Perspective C: Best Balance (Recommended)</H3>
      <Callout tone="success" title="Qwen3.6-35B-A3B on L40S">
        73.4% SWE-bench — only 2.8pp below the dense 27B — at a fraction of the premium option cost. Same infrastructure as Perspective A. This is the recommended path for most organizations.
      </Callout>

      <Divider />
      <H3>Context Length Impact (L40S GPUs Needed)</H3>
      <Table
        headers={["Team", "Peak Slots", "32K", "64K", "128K"]}
        rows={[
          ["50 devs", "10", "1x L40S", "1x L40S", "2x L40S"],
          ["100 devs", "20", "1x L40S", "2x L40S", "3x L40S"],
          ["200 devs", "40", "2x L40S", "3x L40S", "5x L40S"],
        ]}
        striped
      />
      <Text size="small" tone="secondary">Most agentic workloads operate within 32K-64K effective context.</Text>
    </Stack>
  );
}

function TcoSection() {
  return (
    <Stack gap={16}>
      <H2>Full-Stack Total Cost of Ownership (3-Year)</H2>
      <Text>Complete deployment cost including GPU compute, infrastructure, OpenShift subscriptions, OpenShift AI, and Hosted Control Plane. 3-year No Upfront Savings Plan pricing.</Text>

      <H3>Cost Components (Per Cluster)</H3>
      <Table
        headers={["Component", "Description", "Pricing"]}
        rows={[
          ["Hosted Control Plane", "ROSA/OSD management plane", "Flat $0.25/hr ($183/mo)"],
          ["GPU Worker Nodes", "EC2 instances with accelerators", "3yr No Upfront SP"],
          ["Infrastructure Workers", "3x m5.2xlarge (OpenShift AI, monitoring)", "$0.166/hr ea (3yr SP)"],
          ["OpenShift Subscription", "ROSA/OSD per 4 vCPUs, all workers", "$667/4-vCPU/yr (3yr)"],
          ["OpenShift AI", "AI platform license, all worker nodes", "$0.022/vCPU/hr"],
        ]}
        rowTone={[undefined, "info", undefined, "warning", "warning"]}
        striped
      />
      <Text size="small" tone="secondary">Region: US East (N. Virginia) / us-east-1. Same subscription model for ROSA (AWS) and OSD (GCP).</Text>

      <Divider />
      <H3>Best Value: Full-Stack TCO (Qwen3.6-35B on L40S, 64K)</H3>
      <Table
        headers={["Component", "1 dev", "10 devs", "20 devs", "50 devs", "100 devs", "200 devs"]}
        rows={[
          ["GPU Nodes", "1x g6e.xl", "1x g6e.xl", "1x g6e.xl", "1x g6e.xl", "2x g6e.xl", "3x g6e.xl"],
          ["Total vCPUs", "28", "28", "28", "28", "32", "36"],
          ["Hosted CP", "$183", "$183", "$183", "$183", "$183", "$183"],
          ["EC2 GPU", "$679", "$679", "$679", "$679", "$1,358", "$2,037"],
          ["EC2 Infra", "$364", "$364", "$364", "$364", "$364", "$364"],
          ["OCP Sub (3yr)", "$389", "$389", "$389", "$389", "$445", "$500"],
          ["OCP AI Sub", "$450", "$450", "$450", "$450", "$514", "$578"],
          ["Total Monthly", "$2,065", "$2,065", "$2,065", "$2,065", "$2,864", "$3,662"],
          ["Per Dev / Month", "$2,065", "$207", "$103", "$41", "$29", "$18"],
          ["3-Year TCO", "$74,340", "$74,340", "$74,340", "$74,340", "$103,104", "$131,832"],
        ]}
        columnAlign={["left", "right", "right", "right", "right", "right", "right"]}
        rowTone={[undefined, undefined, undefined, undefined, undefined, undefined, undefined, "info", "success", undefined]}
        striped
      />
      <Callout tone="success" title="Economies of Scale">
        Platform overhead (HCP, infra, subscriptions) is ~$1,386/mo fixed. Adding 150 more developers (50 to 200) only increases cost by $1,597/mo (from $2,065 to $3,662). Per-developer cost drops from $41 to $18.
      </Callout>

      <Divider />
      <H3>Cost Component Breakdown (100 Devs, 64K)</H3>
      <BarChart
        categories={["EC2 GPU", "OCP AI Sub", "OCP Sub", "EC2 Infra", "Hosted CP"]}
        series={[{ name: "Monthly Cost ($)", data: [1358, 514, 445, 364, 183], tone: "info" }]}
        height={200}
        valueSuffix="$"
      />
      <Grid columns={5} gap={8}>
        <Stat value="47%" label="EC2 GPU" tone="info" />
        <Stat value="18%" label="OCP AI" tone="warning" />
        <Stat value="16%" label="OCP Sub" tone="warning" />
        <Stat value="13%" label="EC2 Infra" />
        <Stat value="6%" label="Hosted CP" />
      </Grid>
      <Text size="small" tone="secondary">GPU compute is 47% of total. Platform subscriptions (OCP + OCP AI) are 34% combined.</Text>

      <Divider />
      <H3>Per-Developer Monthly Cost (Full-Stack, 3yr SP)</H3>
      <LineChart
        categories={["1 dev", "10 devs", "20 devs", "50 devs", "100 devs", "200 devs"]}
        series={[
          { name: "Full-Stack $/dev", data: [2065, 207, 103, 41, 29, 18], tone: "success" },
        ]}
        height={200}
        valueSuffix="$/dev"
      />

      <Divider />
      <H3>Context Length Impact on TCO</H3>
      <Table
        headers={["Team", "32K Total / Dev", "64K Total / Dev", "128K Total / Dev"]}
        rows={[
          ["50 devs", "$2,065 / $41", "$2,065 / $41", "$2,864 / $57"],
          ["100 devs", "$2,065 / $21", "$2,864 / $29", "$3,662 / $37"],
          ["200 devs", "$2,864 / $14", "$3,662 / $18", "$5,259 / $26"],
        ]}
        columnAlign={["left", "right", "right", "right"]}
        striped
      />

      <Divider />
      <H3>Premium Quality TCO (Coder-Next 80B on H200)</H3>
      <Table
        headers={["Component", "1-100 devs", "200 devs"]}
        rows={[
          ["Instance", "1x p5en.48xlarge", "1x p5en.48xlarge"],
          ["Total vCPUs", "216", "216"],
          ["EC2 GPU (3yr SP)", "$35,442", "$35,442"],
          ["EC2 Infra", "$364", "$364"],
          ["OCP + OCP AI + HCP", "$6,655", "$6,655"],
          ["Total Monthly", "$42,461", "$42,461"],
          ["Per Dev @ 50", "$849", "--"],
          ["Per Dev @ 100", "$425", "--"],
          ["Per Dev @ 200", "--", "$212"],
        ]}
        columnAlign={["left", "right", "right"]}
        rowTone={[undefined, undefined, undefined, undefined, "warning", "danger", undefined, undefined, undefined]}
        striped
      />
      <Callout tone="warning" title="10-15x Cost Premium">
        Premium quality (Coder-Next 80B) costs $425/dev vs $29/dev at 100 developers. The 192-vCPU p5en.48xlarge drives $6,655/mo in platform subscriptions alone. Justified only when code quality definitively outweighs cost.
      </Callout>

      <Divider />
      <H3>GPU-Only vs Full-Stack TCO (3-Year)</H3>
      <Table
        headers={["Team (64K)", "GPU-Only 3yr", "Full-Stack 3yr", "Platform Overhead %"]}
        rows={[
          ["1 dev", "$24,444", "$74,340", "204%"],
          ["10 devs", "$24,444", "$74,340", "204%"],
          ["50 devs", "$24,444", "$74,340", "204%"],
          ["100 devs", "$48,888", "$103,104", "111%"],
          ["200 devs", "$73,332", "$131,832", "80%"],
        ]}
        columnAlign={["left", "right", "right", "center"]}
        striped
      />
      <Text size="small" tone="secondary">Platform overhead is ~$50K over 3 years (fixed). Percentage drops as GPU spend scales.</Text>
    </Stack>
  );
}

function AltAcceleratorsSection() {
  return (
    <Stack gap={16}>
      <H2>Phase 2: Alternative Accelerators</H2>
      <Callout tone="warning" title="Model Limitation">
        DeltaNet hybrid models (highest quality) require CUDA. Alternatives limited to Qwen3-Coder-30B-A3B (standard MoE) — lower benchmarks than Qwen3.6-35B-A3B.
      </Callout>
      <Table
        headers={["Accelerator", "Memory", "Instance", "Slots @ 64K", "$/hr", "Platform"]}
        rows={[
          ["Inferentia2", "32 GB", "inf2.24xlarge (6 chips)", "29", "$6.49", "ROSA (AWS)"],
          ["Trainium2", "96 GB", "trn2.48xlarge (16 chips)", "416", "$35.76", "ROSA (AWS)"],
          ["TPU v6e", "32 GB", "ct6e-standard-4t (4 chips)", "29", "$5.40", "OSD (GCP)"],
          ["TPU v7", "192 GB", "4-chip VM", "212", "$24.00", "OSD (GCP)"],
        ]}
        striped
      />
      <Divider />
      <H3>Cost Comparison: GPU-Only (100-Dev Team, 64K)</H3>
      <Table
        headers={["Option", "Model", "Instance", "Monthly"]}
        rows={[
          ["L40S (ref)", "Qwen3.6-35B (DeltaNet)", "2x g6e.xlarge", "$1,358"],
          ["Inferentia2", "Coder-30B (Std MoE)", "1x inf2.24xlarge", "$4,738"],
          ["TPU v6e", "Coder-30B (Std MoE)", "1x ct6e-standard-4t", "$3,942"],
          ["TPU v7", "Coder-30B (Std MoE)", "1x 4-chip VM", "$17,520"],
          ["Trainium2", "Coder-30B (Std MoE)", "1x trn2.48xlarge", "$26,105"],
        ]}
        columnAlign={["left", "left", "left", "right"]}
        rowTone={["success", undefined, undefined, "warning", "danger"]}
        striped
      />
      <Text size="small" tone="secondary">L40S reference uses 3yr SP with superior DeltaNet model. Alternatives at on-demand pricing with standard MoE. L40S wins on both cost and quality.</Text>
    </Stack>
  );
}

function AppendixSection() {
  return (
    <Stack gap={16}>
      <H2>Appendix A: 30 tok/s Baseline</H2>
      <Callout tone="success" title="Key Finding">
        For Qwen3.6-35B-A3B (MoE), 20 vs 30 tok/s produces identical GPU requirements. VRAM is always the bottleneck, not bandwidth.
      </Callout>
      <Table
        headers={["GPU", "BW Limit @ 30 tok/s", "VRAM Limit", "Effective", "Binding"]}
        rows={[
          ["L40S", "42", "17", "17", "VRAM"],
          ["A100", "104", "68", "68", "VRAM"],
          ["H100", "174", "68", "68", "VRAM"],
          ["H200", "249", "166", "166", "VRAM"],
          ["B200", "419", "248", "248", "VRAM"],
        ]}
        columnAlign={["left", "right", "right", "right", "center"]}
        striped
      />
      <Text size="small" tone="secondary">Bandwidth limit far exceeds VRAM limit in all cases. TCO tables are valid for both 20 and 30 tok/s.</Text>
    </Stack>
  );
}

export default function GpuCapacityReportV2() {
  const [section, setSection] = useCanvasState<Section>("section-v2", "overview");

  const renderSection = () => {
    switch (section) {
      case "overview": return <OverviewSection />;
      case "market": return <MarketSection />;
      case "advantages": return <AdvantagesSection />;
      case "models": return <ModelsSection />;
      case "gpus": return <GpuSection />;
      case "capacity": return <CapacitySection />;
      case "concurrency": return <ConcurrencySection />;
      case "recommendations": return <RecommendationsSection />;
      case "tco": return <TcoSection />;
      case "alt": return <AltAcceleratorsSection />;
      case "appendix": return <AppendixSection />;
    }
  };

  return (
    <Stack gap={16}>
      <H1>Private AI Code Assistant: Enterprise Report v2</H1>
      <Text tone="secondary" size="small">April 2026 — Full-stack TCO including Red Hat OpenShift subscriptions, OpenShift AI, and infrastructure nodes</Text>
      <SectionNav active={section} onSelect={setSection} />
      <Divider />
      {renderSection()}
      <Divider />
      <Text tone="tertiary" size="small">AWS pricing: us-east-1 (April 2026). OpenShift: 3yr plan at $667/4-vCPU/yr. OCP AI: $0.022/vCPU/hr. HCP: $0.25/hr flat. 3x m5.2xlarge infra nodes per cluster. Validate with Red Hat sales and empirical benchmarks before procurement.</Text>
    </Stack>
  );
}
