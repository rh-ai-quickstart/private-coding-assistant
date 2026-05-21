import {
  BarChart,
  Callout,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Row,
  Select,
  Stack,
  Stat,
  Table,
  Text,
  useCanvasState,
  useHostTheme,
} from "cursor/canvas";

// ── Static data ──────────────────────────────────────────────────────

interface ModelSpec {
  label: string;
  arch: "moe" | "dense" | "moe-deltanet" | "mamba-moe" | "moe-swa";
  totalParams: number;
  activeParams: number;
  attnLayers: number;
  totalLayers: number;
  kvHeads: number;
  headDim: number;
  fp8WeightGB: number;
  kvBytesPerTokenFP8: number;
  kvBytesPerTokenFP16: number;
  needsCuda: boolean;
  benchSwe: string;
}

const MODELS: Record<string, ModelSpec> = {
  "qwen3-coder-30b": {
    label: "Qwen3-Coder-30B-A3B",
    arch: "moe",
    totalParams: 30.5,
    activeParams: 3.3,
    attnLayers: 48,
    totalLayers: 48,
    kvHeads: 4,
    headDim: 128,
    fp8WeightGB: 30.5,
    kvBytesPerTokenFP8: 48 * 1024,
    kvBytesPerTokenFP16: 96 * 1024,
    needsCuda: false,
    benchSwe: "--",
  },
  "qwen36-35b": {
    label: "Qwen3.6-35B-A3B",
    arch: "moe-deltanet",
    totalParams: 35,
    activeParams: 3,
    attnLayers: 10,
    totalLayers: 40,
    kvHeads: 2,
    headDim: 256,
    fp8WeightGB: 35,
    kvBytesPerTokenFP8: 10 * 1024,
    kvBytesPerTokenFP16: 20 * 1024,
    needsCuda: true,
    benchSwe: "73.4%",
  },
  "qwen36-27b": {
    label: "Qwen3.6-27B (Dense)",
    arch: "dense",
    totalParams: 27,
    activeParams: 27,
    attnLayers: 16,
    totalLayers: 64,
    kvHeads: 4,
    headDim: 256,
    fp8WeightGB: 27,
    kvBytesPerTokenFP8: 32 * 1024,
    kvBytesPerTokenFP16: 64 * 1024,
    needsCuda: true,
    benchSwe: "77.2%",
  },
  "coder-next-80b": {
    label: "Qwen3-Coder-Next-80B",
    arch: "moe-deltanet",
    totalParams: 80,
    activeParams: 3,
    attnLayers: 12,
    totalLayers: 48,
    kvHeads: 2,
    headDim: 256,
    fp8WeightGB: 80,
    kvBytesPerTokenFP8: 12 * 1024,
    kvBytesPerTokenFP16: 24 * 1024,
    needsCuda: true,
    benchSwe: "70.6%",
  },
  "nemotron-nano-30b": {
    label: "Nemotron Nano 30B-A3B",
    arch: "mamba-moe",
    totalParams: 30,
    activeParams: 3.5,
    attnLayers: 6,
    totalLayers: 52,
    kvHeads: 2,
    headDim: 128,
    fp8WeightGB: 30,
    kvBytesPerTokenFP8: 3 * 1024,
    kvBytesPerTokenFP16: 6 * 1024,
    needsCuda: true,
    benchSwe: "--",
  },
  "gemma4-27b": {
    label: "Gemma 4 27B-A4B",
    arch: "moe-swa",
    totalParams: 26.5,
    activeParams: 4,
    attnLayers: 30,
    totalLayers: 30,
    kvHeads: 0,
    headDim: 0,
    fp8WeightGB: 26.5,
    kvBytesPerTokenFP8: 110 * 1024,
    kvBytesPerTokenFP16: 220 * 1024,
    needsCuda: false,
    benchSwe: "--",
  },
};

interface InstanceOption {
  name: string;
  gpuCount: number;
  onDemandPerHr: number;
  savingsPlan3yrNU_discount: number;
}

interface GpuSpec {
  label: string;
  vramGB: number;
  bwGBs: number;
  hasFP8Native: boolean;
  hasFP8Marlin: boolean;
  instances: InstanceOption[];
}

function pickOptimalInstances(gpu: GpuSpec, gpusNeeded: number): { config: string; totalGpus: number; totalOnDemandPerHr: number; avgDiscount: number } {
  const sorted = [...gpu.instances].sort((a, b) => (a.onDemandPerHr / a.gpuCount) - (b.onDemandPerHr / b.gpuCount));
  let remaining = gpusNeeded;
  const picks: { inst: InstanceOption; count: number }[] = [];
  for (const inst of sorted) {
    if (remaining <= 0) break;
    const count = Math.ceil(remaining / inst.gpuCount);
    picks.push({ inst, count });
    remaining -= count * inst.gpuCount;
  }
  if (picks.length === 0) {
    const smallest = sorted[0];
    picks.push({ inst: smallest, count: 1 });
  }
  const totalGpus = picks.reduce((s, p) => s + p.count * p.inst.gpuCount, 0);
  const totalCost = picks.reduce((s, p) => s + p.count * p.inst.onDemandPerHr, 0);
  const weightedDiscount = picks.reduce((s, p) => s + p.count * p.inst.onDemandPerHr * p.inst.savingsPlan3yrNU_discount, 0) / totalCost;
  const config = picks.map(p => `${p.count}× ${p.inst.name}`).join(" + ");
  return { config, totalGpus, totalOnDemandPerHr: totalCost, avgDiscount: weightedDiscount };
}

const GPUS: Record<string, GpuSpec> = {
  l40s: {
    label: "L40S",
    vramGB: 48,
    bwGBs: 864,
    hasFP8Native: true,
    hasFP8Marlin: true,
    instances: [
      { name: "g6e.xlarge", gpuCount: 1, onDemandPerHr: 1.86, savingsPlan3yrNU_discount: 0.50 },
      { name: "g6e.12xlarge", gpuCount: 4, onDemandPerHr: 10.49, savingsPlan3yrNU_discount: 0.50 },
      { name: "g6e.48xlarge", gpuCount: 8, onDemandPerHr: 30.13, savingsPlan3yrNU_discount: 0.50 },
    ],
  },
  a100: {
    label: "A100 80GB",
    vramGB: 80,
    bwGBs: 2039,
    hasFP8Native: false,
    hasFP8Marlin: true,
    instances: [
      { name: "p4de.24xlarge", gpuCount: 8, onDemandPerHr: 27.45, savingsPlan3yrNU_discount: 0.48 },
    ],
  },
  h100: {
    label: "H100 80GB",
    vramGB: 80,
    bwGBs: 3350,
    hasFP8Native: true,
    hasFP8Marlin: true,
    instances: [
      { name: "p5.4xlarge", gpuCount: 1, onDemandPerHr: 6.88, savingsPlan3yrNU_discount: 0.50 },
      { name: "p5.48xlarge", gpuCount: 8, onDemandPerHr: 55.04, savingsPlan3yrNU_discount: 0.50 },
    ],
  },
  h200: {
    label: "H200 141GB",
    vramGB: 141,
    bwGBs: 4800,
    hasFP8Native: true,
    hasFP8Marlin: true,
    instances: [
      { name: "p5en.48xlarge", gpuCount: 8, onDemandPerHr: 74.69, savingsPlan3yrNU_discount: 0.35 },
    ],
  },
  b200: {
    label: "B200 (GB200) 192GB",
    vramGB: 192,
    bwGBs: 8000,
    hasFP8Native: true,
    hasFP8Marlin: true,
    instances: [
      { name: "p6-b200.48xlarge", gpuCount: 8, onDemandPerHr: 113.93, savingsPlan3yrNU_discount: 0.20 },
    ],
  },
  b300: {
    label: "B300 (GB300) 288GB",
    vramGB: 288,
    bwGBs: 8000,
    hasFP8Native: true,
    hasFP8Marlin: true,
    instances: [
      { name: "p6-b300.48xlarge", gpuCount: 8, onDemandPerHr: 150.00, savingsPlan3yrNU_discount: 0.15 },
    ],
  },
};

const CONTEXT_OPTIONS = [
  { value: "16384", label: "16K" },
  { value: "32768", label: "32K" },
  { value: "65536", label: "64K" },
  { value: "131072", label: "128K" },
  { value: "262144", label: "256K" },
];

const DEV_OPTIONS = [
  { value: "1", label: "1" },
  { value: "10", label: "10" },
  { value: "20", label: "20" },
  { value: "50", label: "50" },
  { value: "100", label: "100" },
  { value: "200", label: "200" },
];

const THROUGHPUT_OPTIONS = [
  { value: "20", label: "20 tok/s" },
  { value: "30", label: "30 tok/s" },
];

// ── Calculation engine ───────────────────────────────────────────────

function peakSlots(devs: number): number {
  if (devs <= 1) return 1;
  return Math.ceil(devs * 0.20);
}

function kvPerRequestGB(model: ModelSpec, contextLen: number, quant: "fp8" | "fp16"): number {
  const bytesPerToken = quant === "fp8" ? model.kvBytesPerTokenFP8 : model.kvBytesPerTokenFP16;
  return (bytesPerToken * contextLen) / (1024 * 1024 * 1024);
}

function modelWeightGB(model: ModelSpec, quant: "fp8" | "fp16"): number {
  return quant === "fp8" ? model.fp8WeightGB : model.fp8WeightGB * 2;
}

function availableVRAM(gpu: GpuSpec, model: ModelSpec, quant: "fp8" | "fp16"): number {
  const weights = modelWeightGB(model, quant);
  const overhead = 2;
  return Math.max(0, gpu.vramGB - weights - overhead);
}

function vramSlots(gpu: GpuSpec, model: ModelSpec, quant: "fp8" | "fp16", contextLen: number): number {
  const avail = availableVRAM(gpu, model, quant);
  const kvReq = kvPerRequestGB(model, contextLen, quant);
  if (kvReq <= 0) return 0;
  return Math.floor(avail / kvReq);
}

function bwLimitSlots(gpu: GpuSpec, model: ModelSpec, quant: "fp8" | "fp16", contextLen: number, targetTokS: number): number {
  const activeGB = quant === "fp8" ? model.activeParams : model.activeParams * 2;
  const kvReq = kvPerRequestGB(model, contextLen, quant);
  const maxBytes = gpu.bwGBs / targetTokS;
  if (maxBytes <= activeGB) return 0;
  const n = (maxBytes - activeGB) / kvReq;
  return Math.floor(n);
}

function effectiveSlots(gpu: GpuSpec, model: ModelSpec, quant: "fp8" | "fp16", contextLen: number, targetTokS: number): number {
  const vram = vramSlots(gpu, model, quant, contextLen);
  const bw = bwLimitSlots(gpu, model, quant, contextLen, targetTokS);
  return Math.min(vram, bw);
}

function modelFitsGpu(gpu: GpuSpec, model: ModelSpec, quant: "fp8" | "fp16"): boolean {
  return availableVRAM(gpu, model, quant) > 0;
}

function gpuSupportsQuant(gpu: GpuSpec, quant: "fp8" | "fp16"): boolean {
  if (quant === "fp16") return true;
  return gpu.hasFP8Native || gpu.hasFP8Marlin;
}

function smallestInstanceGpuCount(gpu: GpuSpec): number {
  return Math.min(...gpu.instances.map(i => i.gpuCount));
}

function bindingConstraint(gpu: GpuSpec, model: ModelSpec, quant: "fp8" | "fp16", contextLen: number, targetTokS: number): string {
  const vram = vramSlots(gpu, model, quant, contextLen);
  const bw = bwLimitSlots(gpu, model, quant, contextLen, targetTokS);
  if (vram <= bw) return "VRAM";
  return "Bandwidth";
}

function perDevThroughput(gpu: GpuSpec, model: ModelSpec, quant: "fp8" | "fp16", contextLen: number, batchSize: number): number {
  const activeGB = quant === "fp8" ? model.activeParams : model.activeParams * 2;
  const kvReq = kvPerRequestGB(model, contextLen, quant);
  const totalBytes = activeGB + batchSize * kvReq;
  if (totalBytes <= 0) return 0;
  return gpu.bwGBs / totalBytes;
}

// ── Components ───────────────────────────────────────────────────────

function InputPanel({
  modelId, setModelId,
  gpuId, setGpuId,
  quant, setQuant,
  contextLen, setContextLen,
  devCount, setDevCount,
  targetTokS, setTargetTokS,
}: {
  modelId: string; setModelId: (v: string) => void;
  gpuId: string; setGpuId: (v: string) => void;
  quant: string; setQuant: (v: string) => void;
  contextLen: string; setContextLen: (v: string) => void;
  devCount: string; setDevCount: (v: string) => void;
  targetTokS: string; setTargetTokS: (v: string) => void;
}) {
  const model = MODELS[modelId];
  const gpu = GPUS[gpuId];

  const modelOptions = Object.entries(MODELS).map(([k, m]) => ({
    value: k,
    label: m.label,
  }));

  const gpuOptions = Object.entries(GPUS).map(([k, g]) => ({
    value: k,
    label: g.label,
    disabled: !modelFitsGpu(g, model, quant as "fp8" | "fp16"),
  }));

  const quantOptions = [
    { value: "fp8", label: "FP8 (1 byte/param)", disabled: !gpuSupportsQuant(gpu, "fp8") },
    { value: "fp16", label: "FP16 (2 bytes/param)" },
  ];

  return (
    <Stack gap={12}>
      <H3>Configuration</H3>
      <Grid columns={2} gap={12}>
        <Stack gap={4}>
          <Text size="small" weight="semibold">Model</Text>
          <Select value={modelId} onChange={setModelId} options={modelOptions} />
        </Stack>
        <Stack gap={4}>
          <Text size="small" weight="semibold">GPU</Text>
          <Select value={gpuId} onChange={setGpuId} options={gpuOptions} />
        </Stack>
        <Stack gap={4}>
          <Text size="small" weight="semibold">Quantization</Text>
          <Select value={quant} onChange={setQuant} options={quantOptions} />
        </Stack>
        <Stack gap={4}>
          <Text size="small" weight="semibold">Context Length</Text>
          <Select value={contextLen} onChange={setContextLen} options={CONTEXT_OPTIONS} />
        </Stack>
        <Stack gap={4}>
          <Text size="small" weight="semibold">Team Size</Text>
          <Select value={devCount} onChange={setDevCount} options={DEV_OPTIONS} />
        </Stack>
        <Stack gap={4}>
          <Text size="small" weight="semibold">Throughput Target</Text>
          <Select value={targetTokS} onChange={setTargetTokS} options={THROUGHPUT_OPTIONS} />
        </Stack>
      </Grid>
      {model.needsCuda && (
        <Callout tone="warning" title="CUDA Required">
          {model.label} requires NVIDIA CUDA (DeltaNet/Mamba kernels). Not compatible with Trainium or TPU.
        </Callout>
      )}
    </Stack>
  );
}

function ResultsPanel({
  modelId, gpuId, quant, contextLen, devCount, targetTokS,
}: {
  modelId: string; gpuId: string; quant: string; contextLen: number; devCount: number; targetTokS: number;
}) {
  const theme = useHostTheme();
  const model = MODELS[modelId];
  const gpu = GPUS[gpuId];
  const q = quant as "fp8" | "fp16";

  const fits = modelFitsGpu(gpu, model, q);
  if (!fits) {
    return (
      <Callout tone="danger" title="Model Does Not Fit">
        {model.label} ({modelWeightGB(model, q).toFixed(1)} GB weights) exceeds available VRAM on {gpu.label} ({gpu.vramGB} GB). Select a larger GPU or use FP8 quantization.
      </Callout>
    );
  }

  const kvReq = kvPerRequestGB(model, contextLen, q);
  const avail = availableVRAM(gpu, model, q);
  const vSlots = vramSlots(gpu, model, q, contextLen);
  const bSlots = bwLimitSlots(gpu, model, q, contextLen, targetTokS);
  const eSlots = effectiveSlots(gpu, model, q, contextLen, targetTokS);
  const binding = bindingConstraint(gpu, model, q, contextLen, targetTokS);
  const slots = peakSlots(devCount);
  const gpusNeeded = Math.max(1, Math.ceil(slots / Math.max(1, eSlots)));
  const optimal = pickOptimalInstances(gpu, gpusNeeded);
  const totalGpus = optimal.totalGpus;

  const monthlyOD = optimal.totalOnDemandPerHr * 730;
  const monthlySP = monthlyOD * (1 - optimal.avgDiscount);
  const tco3yr = monthlySP * 36;
  const perDevMonth = monthlySP / devCount;
  const utilPct = totalGpus > 0 ? Math.round((gpusNeeded / totalGpus) * 100) : 0;

  const isDense = model.arch === "dense";
  const archLabel = model.arch === "moe" ? "Standard MoE" :
    model.arch === "moe-deltanet" ? "MoE + DeltaNet" :
    model.arch === "dense" ? "Dense + DeltaNet" :
    model.arch === "mamba-moe" ? "Mamba-2 + MoE" : "MoE + SWA";

  const actualTokS = perDevThroughput(gpu, model, q, contextLen, eSlots);
  const tokSDisplay = actualTokS >= 1000 ? ">999" : actualTokS.toFixed(1);
  const throughputOk = actualTokS >= targetTokS;

  return (
    <Stack gap={16}>
      <Grid columns={3} gap={12}>
        <Stat value={eSlots.toString()} label="Concurrent Users / GPU" tone={eSlots >= slots ? "success" : "warning"} />
        <Stat value={`${tokSDisplay} tok/s`} label="Per-Developer Throughput" tone={throughputOk ? "success" : "danger"} />
        <Stat value={gpusNeeded.toString()} label="GPUs Required" tone="info" />
      </Grid>
      <Grid columns={3} gap={12}>
        <Stat value={`$${Math.round(monthlySP).toLocaleString()}`} label="Total Monthly Cost (3yr SP)" tone="success" />
        <Stat value={`$${perDevMonth < 1 ? perDevMonth.toFixed(2) : Math.round(perDevMonth).toLocaleString()}`} label="Per Developer / Month (3yr SP)" />
        <Stat value={`$${Math.round(tco3yr).toLocaleString()}`} label="3-Year TCO" tone="info" />
      </Grid>

      <Divider />
      <H3>Sizing Detail</H3>
      <Table
        headers={["Parameter", "Value"]}
        rows={[
          ["Model", `${model.label} (${archLabel})`],
          ["Active Parameters", `${model.activeParams} B (${isDense ? "dense — all params active" : "MoE sparse"})`],
          ["Weight Size", `${modelWeightGB(model, q).toFixed(1)} GB (${q.toUpperCase()})`],
          ["GPU", `${gpu.label} (${gpu.vramGB} GB VRAM, ${gpu.bwGBs.toLocaleString()} GB/s)`],
          ["── VRAM Budget ──", "──────────"],
          ["  Total VRAM", `${gpu.vramGB.toFixed(1)} GB`],
          ["  − Model Weights", `${modelWeightGB(model, q).toFixed(1)} GB`],
          ["  − Runtime Overhead", "2.0 GB"],
          ["  = Available for KV Cache", `${avail.toFixed(1)} GB`],
          ["── KV Cache Sizing ──", "──────────"],
          ["  KV Cache / Token", `${(q === "fp8" ? model.kvBytesPerTokenFP8 : model.kvBytesPerTokenFP16).toLocaleString()} bytes`],
          ["  KV Cache / Request", `${kvReq.toFixed(2)} GB`],
          ["  Max Users from VRAM", `⌊${avail.toFixed(1)} / ${kvReq.toFixed(2)}⌋ = ${vSlots}`],
          ["  Max Users from BW (@ ${targetTokS} tok/s)", `${bSlots}`],
          ["── Result ──", "──────────"],
          ["  Binding Constraint", binding],
          ["  Concurrent Users / GPU", `${eSlots}`],
          ["  Per-User Throughput @ Full Load", `${tokSDisplay} tok/s (min ${targetTokS} required)`],
          ["  Peak Concurrent Users (team)", `${slots} (${devCount} devs × 20% peak factor)`],
          ["  GPUs Required", `${gpusNeeded}`],
          ["── AWS Instance Selection ──", "──────────"],
          ["  Optimal Config", optimal.config],
          ["  GPUs Purchased", `${totalGpus}${totalGpus > gpusNeeded ? ` (${gpusNeeded} needed, ${totalGpus - gpusNeeded} idle)` : ""}`],
          ["  Instance Utilization", `${utilPct}%${utilPct < 50 ? " ⚠ consider smaller GPU class" : ""}`],
          ["  Per Dev / Month (3yr SP)", `$${perDevMonth < 1 ? perDevMonth.toFixed(2) : Math.round(perDevMonth).toLocaleString()}`],
        ]}
        striped
      />
      {totalGpus > gpusNeeded && (
        <Callout tone="warning" title={`Instance Granularity: ${totalGpus - gpusNeeded} Idle GPU${totalGpus - gpusNeeded > 1 ? "s" : ""}`}>
          {gpu.label} is only available in {gpu.instances.map(i => `${i.gpuCount}-GPU (${i.name})`).join(" or ")} configurations. You need {gpusNeeded} GPU{gpusNeeded > 1 ? "s" : ""} but must purchase {totalGpus}. The {totalGpus - gpusNeeded} unused GPU{totalGpus - gpusNeeded > 1 ? "s" : ""} can host additional model replicas, a secondary model (e.g., autocomplete), or serve as hot standby capacity.
        </Callout>
      )}
      <Callout tone="info" title="KV Cache Lifecycle">
        vLLM uses PagedAttention: KV cache is allocated in pages per active request and freed immediately on completion. Idle users consume zero GPU VRAM. The calculator models worst case — all peak concurrent users at full context length simultaneously. In practice, llm-d's KV-cache-aware routing and prefix caching further reduce actual VRAM usage.
      </Callout>

      <Divider />
      <H3>Cost Breakdown</H3>
      <Table
        headers={["Metric", "On-Demand", "3yr No Upfront SP"]}
        rows={[
          ["Hourly", `$${optimal.totalOnDemandPerHr.toFixed(2)}`, `$${(optimal.totalOnDemandPerHr * (1 - optimal.avgDiscount)).toFixed(2)}`],
          ["Monthly", `$${Math.round(monthlyOD).toLocaleString()}`, `$${Math.round(monthlySP).toLocaleString()}`],
          ["Annual", `$${Math.round(monthlyOD * 12).toLocaleString()}`, `$${Math.round(monthlySP * 12).toLocaleString()}`],
          ["3-Year TCO", `$${Math.round(monthlyOD * 36).toLocaleString()}`, `$${Math.round(tco3yr).toLocaleString()}`],
          ["Per Dev / Month", `$${Math.round(monthlyOD / devCount).toLocaleString()}`, `$${perDevMonth < 1 ? perDevMonth.toFixed(2) : Math.round(perDevMonth).toLocaleString()}`],
          ["Savings Plan Discount", "--", `${(optimal.avgDiscount * 100).toFixed(0)}%`],
        ]}
        columnAlign={["left", "right", "right"]}
        striped
      />
      {gpu.instances.length > 1 && (
        <Callout tone="info" title="Instance Size Optimization">
          {gpu.label} is available in multiple instance sizes: {gpu.instances.map(i => `${i.name} (${i.gpuCount}× GPU, $${i.onDemandPerHr}/hr)`).join(", ")}. The calculator selects the lowest cost-per-GPU configuration for independent model replicas (no inter-GPU NVLink required).
        </Callout>
      )}

      {binding === "Bandwidth" && (
        <Callout tone="warning" title="Bandwidth Constrained">
          {model.label} ({model.activeParams} GB active weights) is bandwidth-limited on {gpu.label} at {targetTokS} tok/s. Max concurrent users reduced from {vSlots} (VRAM capacity) to {eSlots} (bandwidth floor) to maintain {targetTokS} tok/s per user. {isDense ? "Consider MoE alternatives for higher concurrency." : ""}
        </Callout>
      )}
    </Stack>
  );
}

function utilizationLabel(pct: number): string {
  if (pct >= 60) return `${pct}% — Good`;
  if (pct >= 30) return `${pct}% — Moderate`;
  if (pct >= 10) return `${pct}% — Low`;
  return `${pct}% — Wasteful`;
}

function ComparisonPanel({ modelId, quant, contextLen, devCount, targetTokS }: {
  modelId: string; quant: string; contextLen: number; devCount: number; targetTokS: number;
}) {
  const model = MODELS[modelId];
  const q = quant as "fp8" | "fp16";
  const slots = peakSlots(devCount);

  const gpuKeys = Object.keys(GPUS).filter(k => modelFitsGpu(GPUS[k], model, q));

  const compData = gpuKeys.map(k => {
    const gpu = GPUS[k];
    const eSlots = effectiveSlots(gpu, model, q, contextLen, targetTokS);
    const binding = bindingConstraint(gpu, model, q, contextLen, targetTokS);
    const gpusNeeded = Math.max(1, Math.ceil(slots / Math.max(1, eSlots)));
    const optimal = pickOptimalInstances(gpu, gpusNeeded);
    const totalGpus = optimal.totalGpus;
    const monthlySP = optimal.totalOnDemandPerHr * 730 * (1 - optimal.avgDiscount);

    const totalCapacity = totalGpus * eSlots;
    const slotUtilPct = totalCapacity > 0 ? Math.round((slots / totalCapacity) * 100) : 0;
    const gpuUtilPct = totalGpus > 0 ? Math.round((gpusNeeded / totalGpus) * 100) : 0;
    const overallUtilPct = Math.round((slotUtilPct * gpuUtilPct) / 100);

    return { k, gpu, eSlots, binding, gpusNeeded, optimal, totalGpus, monthlySP, slotUtilPct, gpuUtilPct, overallUtilPct };
  });

  const rows = compData.map(d => [
    d.gpu.label,
    d.eSlots.toString(),
    d.binding,
    d.totalGpus === d.gpusNeeded ? d.gpusNeeded.toString() : `${d.gpusNeeded} used / ${d.totalGpus} purchased`,
    d.optimal.config,
    utilizationLabel(d.overallUtilPct),
    `$${Math.round(d.monthlySP).toLocaleString()}`,
    `$${Math.round(d.monthlySP * 36).toLocaleString()}`,
  ]);

  const rowTones = compData.map(d =>
    d.overallUtilPct >= 60 ? "success" as const :
    d.overallUtilPct >= 30 ? undefined :
    d.overallUtilPct >= 10 ? "warning" as const : "danger" as const
  );

  const chartCategories = compData.map(d => d.gpu.label);
  const chartSlots = compData.map(d => d.eSlots);
  const chartCost = compData.map(d => Math.round(d.monthlySP));
  const chartUtil = compData.map(d => d.overallUtilPct);

  const wastefulGpus = compData.filter(d => d.overallUtilPct < 30 && d.totalGpus > d.gpusNeeded);

  return (
    <Stack gap={16}>
      <H3>GPU Comparison for {model.label}</H3>
      <Table
        headers={["GPU", "Users/GPU", "Binding", "GPUs", "AWS Config", "Utilization", "Monthly (SP)", "3yr TCO"]}
        rows={rows}
        rowTone={rowTones}
        columnAlign={["left", "right", "center", "left", "left", "left", "right", "right"]}
        striped
      />
      <Text size="small" tone="secondary">Utilization = (peak concurrent users needed) ÷ (total capacity of purchased GPUs). Multi-GPU instances (A100/H100/H200/B200/B300 = 8 GPUs per instance) may include unused GPUs that still incur cost.</Text>
      {wastefulGpus.length > 0 && (
        <Callout tone="warning" title="Over-provisioned GPUs Detected">
          {wastefulGpus.map(d => d.gpu.label).join(", ")} {wastefulGpus.length === 1 ? "has" : "have"} utilization below 30% for this team size. {wastefulGpus.some(d => d.totalGpus > d.gpusNeeded)
            ? `Multi-GPU instances force purchasing ${wastefulGpus.find(d => d.totalGpus > d.gpusNeeded)!.totalGpus} GPUs when only ${wastefulGpus.find(d => d.totalGpus > d.gpusNeeded)!.gpusNeeded} ${wastefulGpus.find(d => d.totalGpus > d.gpusNeeded)!.gpusNeeded === 1 ? "is" : "are"} needed — the remaining GPUs sit idle but still incur cost.`
            : "Each GPU has far more capacity than this workload requires."}
          {" "}Consider a smaller GPU class or using the spare capacity for additional models/replicas.
        </Callout>
      )}
      <Grid columns={3} gap={16}>
        <Stack gap={4}>
          <Text size="small" weight="semibold">Concurrent Users per GPU</Text>
          <BarChart
            categories={chartCategories}
            series={[{ name: "Users / GPU", data: chartSlots, tone: "info" }]}
            height={180}
          />
        </Stack>
        <Stack gap={4}>
          <Text size="small" weight="semibold">Utilization (%)</Text>
          <BarChart
            categories={chartCategories}
            series={[{ name: "Utilization %", data: chartUtil, tone: "warning" }]}
            height={180}
            valueSuffix="%"
          />
        </Stack>
        <Stack gap={4}>
          <Text size="small" weight="semibold">Monthly Cost (3yr No Upfront SP)</Text>
          <BarChart
            categories={chartCategories}
            series={[{ name: "$/month", data: chartCost, tone: "success" }]}
            height={180}
            valueSuffix="$"
          />
        </Stack>
      </Grid>
    </Stack>
  );
}

function ContextSweep({ modelId, gpuId, quant, devCount, targetTokS }: {
  modelId: string; gpuId: string; quant: string; devCount: number; targetTokS: number;
}) {
  const model = MODELS[modelId];
  const gpu = GPUS[gpuId];
  const q = quant as "fp8" | "fp16";
  const slots = peakSlots(devCount);

  const contexts = [16384, 32768, 65536, 131072, 262144];
  const labels = ["16K", "32K", "64K", "128K", "256K"];

  const rows = contexts.map((ctx, i) => {
    const eSlots = effectiveSlots(gpu, model, q, ctx, targetTokS);
    const gpusNeeded = Math.max(1, Math.ceil(slots / Math.max(1, eSlots)));
    const optimal = pickOptimalInstances(gpu, gpusNeeded);
    const monthlySP = optimal.totalOnDemandPerHr * 730 * (1 - optimal.avgDiscount);
    return [
      labels[i],
      kvPerRequestGB(model, ctx, q).toFixed(2) + " GB",
      eSlots.toString(),
      `${gpusNeeded}${optimal.totalGpus > gpusNeeded ? ` (${optimal.totalGpus} purchased)` : ""}`,
      optimal.config,
      `$${Math.round(monthlySP).toLocaleString()}`,
      `$${Math.round(monthlySP * 36).toLocaleString()}`,
    ];
  });

  const slotData = contexts.map(ctx => effectiveSlots(gpu, model, q, ctx, targetTokS));
  const costData = contexts.map(ctx => {
    const eSlots = effectiveSlots(gpu, model, q, ctx, targetTokS);
    const gpusNeeded = Math.max(1, Math.ceil(slots / Math.max(1, eSlots)));
    const optimal = pickOptimalInstances(gpu, gpusNeeded);
    return Math.round(optimal.totalOnDemandPerHr * 730 * (1 - optimal.avgDiscount));
  });

  return (
    <Stack gap={16}>
      <H3>Context Length Impact ({gpu.label}, {devCount} devs)</H3>
      <Table
        headers={["Context", "KV/Req", "Users/GPU", "GPUs", "AWS Config", "Monthly (SP)", "3yr TCO"]}
        rows={rows}
        columnAlign={["left", "right", "right", "left", "left", "right", "right"]}
        striped
      />
      <Grid columns={2} gap={16}>
        <Stack gap={4}>
          <Text size="small" weight="semibold">Concurrent Users per GPU by Context</Text>
          <BarChart
            categories={labels}
            series={[{ name: "Users / GPU", data: slotData, tone: "info" }]}
            height={180}
          />
        </Stack>
        <Stack gap={4}>
          <Text size="small" weight="semibold">Monthly Cost by Context</Text>
          <BarChart
            categories={labels}
            series={[{ name: "$/month", data: costData, tone: "success" }]}
            height={180}
            valueSuffix="$"
          />
        </Stack>
      </Grid>
    </Stack>
  );
}

// ── Main ─────────────────────────────────────────────────────────────

export default function GpuSizingCalculator() {
  const [modelId, setModelId] = useCanvasState("model", "qwen36-35b");
  const [gpuId, setGpuId] = useCanvasState("gpu", "l40s");
  const [quant, setQuant] = useCanvasState("quant", "fp8");
  const [contextLen, setContextLen] = useCanvasState("ctx", "65536");
  const [devCount, setDevCount] = useCanvasState("devs", "100");
  const [targetTokS, setTargetTokS] = useCanvasState("toks", "20");

  const ctxNum = parseInt(contextLen);
  const devNum = parseInt(devCount);
  const tokNum = parseInt(targetTokS);

  return (
    <Stack gap={20}>
      <H1>GPU Sizing Calculator</H1>
      <Text tone="secondary" size="small">Interactive infrastructure calculator for private AI coding assistant deployment</Text>

      <InputPanel
        modelId={modelId} setModelId={setModelId}
        gpuId={gpuId} setGpuId={setGpuId}
        quant={quant} setQuant={setQuant}
        contextLen={contextLen} setContextLen={setContextLen}
        devCount={devCount} setDevCount={setDevCount}
        targetTokS={targetTokS} setTargetTokS={setTargetTokS}
      />

      <Divider />
      <H2>Results</H2>
      <ResultsPanel
        modelId={modelId} gpuId={gpuId} quant={quant}
        contextLen={ctxNum} devCount={devNum} targetTokS={tokNum}
      />

      <Divider />
      <ComparisonPanel
        modelId={modelId} quant={quant}
        contextLen={ctxNum} devCount={devNum} targetTokS={tokNum}
      />

      <Divider />
      <ContextSweep
        modelId={modelId} gpuId={gpuId} quant={quant}
        devCount={devNum} targetTokS={tokNum}
      />

      <Divider />
      <Text tone="tertiary" size="small">VRAM Budget: Available = GPU_VRAM − Model_Weights − 2 GB overhead → Users/GPU = Available ÷ KV_per_request. Throughput: tok/s = Memory_BW ÷ (Active_Params + N × KV_per_request). Peak concurrency = 20% of team size. KV cache freed on request completion (PagedAttention). Instance selection optimizes for lowest cost-per-GPU across available sizes (e.g., p5.4xlarge 1×H100 vs p5.48xlarge 8×H100). AWS 3yr No Upfront Savings Plan pricing. B300 pricing estimated — verify at procurement.</Text>
    </Stack>
  );
}
