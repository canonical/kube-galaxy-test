# GitHub Copilot Competition Submission
## Kubernetes Galaxy Test — AI-Accelerated Infrastructure Testing

> **Format**: Each section below is a self-contained slide. Copy headings and bullet points directly into Google Slides. Suggested layouts are noted in *italics*.

---

## SLIDE 1 — Title Slide
*Layout: Title + subtitle, full-width background image (K8s logo or galaxy nebula)*

**Kubernetes Galaxy Test**
*Accelerating Cloud-Native Testing Infrastructure with GitHub Copilot*

- **Author**: Adam Dyess / Canonical
- **Repository**: https://github.com/canonical/kube-galaxy-test
- **Categories Entered**:
  - 🤖 Creating Custom Agents Workflow
  - 📄 Optimizing Instruction Files → Skills
  - 🔀 Working with Multiple Models in Parallel

---

## SLIDE 2 — The Goal
*Layout: Title + 3 content columns*

**Build a scalable, multi-architecture Kubernetes testing platform — rapidly — using GitHub Copilot as the primary co-developer.**

### What we needed to build
- A Python CLI (`kube-galaxy`) that provisions real Kubernetes clusters via kubeadm
- YAML-manifest-driven component system covering 30+ K8s components per version
- Multi-architecture support: amd64, arm64, riscv64, ppc64le, s390x
- GitHub Actions CI that matrix-tests Kubernetes 1.33 → 1.36 in parallel
- Spread test integration pulling tests from upstream component repositories
- Automatic failure capture (debug logs, GitHub Issues) for operator visibility

### The challenge
- Broad scope: cluster lifecycle, component plugin system, arch detection, testing harness, CI/CD
- Speed: needed a working, well-tested codebase fast
- Correctness: real Kubernetes infra — bugs have hard failures, not soft ones

### Copilot's role
> Rather than writing boilerplate and scaffolding by hand, we guided Copilot to produce complete, tested, production-quality code through carefully crafted instructions, custom agents, and parallel model use.

---

## SLIDE 3 — Category 1: Custom Agents Workflow
*Layout: Title + split-pane (left: description, right: code snippet)*

### 🤖 End-to-End Hands-Off Workflow with a Custom Python Expert Agent

**What we built**: A dedicated `.github/agents/python.md` agent named **"Python Expert"** running on **GPT-4.1**

```
.github/
└── agents/
    └── python.md       ← Custom agent definition
```

**Agent capabilities defined in the skill file:**
- Python 3.12+ with strict type hints and Pydantic models
- Typer CLI framework, async patterns, decorator-based component registration
- tox/uv development workflow (`tox -e format,lint,unit`)
- Lifecycle hook patterns (download → install → configure → bootstrap → verify)
- Error handling using project-specific exception types (`ShellError`, `ClusterError`)

**How it worked in practice:**
1. Developer writes a plain-English prompt: *"Add a sonobuoy component with download and verify hooks"*
2. Agent autonomously generates a complete `ComponentBase` subclass with all hooks, type hints, docstrings, and tests
3. Agent self-validates using `tox -e type,lint,test` before committing
4. Zero boilerplate written by hand — entire `src/kube_galaxy/pkg/components/` module generated this way

**Result**: 6 component classes (containerd, kubeadm, kubelet, CNI plugins, pause, sonobuoy) produced with consistent patterns, zero human-written scaffolding.

---

## SLIDE 4 — Category 1 (continued): What the Agent Produced
*Layout: Title + code comparison (before prompt / after generated output)*

### From Prompt → Production Code in One Step

**Prompt given to agent:**
> *"Create a new Kubernetes component plugin for containerd. It needs download, install, configure, and bootstrap lifecycle hooks. Use the binary-archive install method, support multiarch, and follow the existing ComponentBase pattern."*

**Agent produced** (`src/kube_galaxy/pkg/components/containerd.py`):
- Complete `@register_component("containerd")` class
- Multiarch binary download with `K8S_ARCH` environment variable
- systemd service configuration
- `bootstrap_hook()` with kubeadm containerd config generation
- Matching unit tests in `tests/unit/`
- Type hints on every method, docstrings describing each hook

**Metrics:**
| Artifact | Lines of code | Written by human |
|---|---|---|
| `containerd.py` | ~120 | 0 |
| `kubeadm.py` | ~150 | 0 |
| `kubelet.py` | ~110 | 0 |
| Component `__init__.py` registry | ~50 | 0 |
| Unit tests for all components | ~200 | 0 |

---

## SLIDE 5 — Category 2: Optimizing Instruction Files → Skills
*Layout: Title + before/after comparison*

### 📄 From README to Structured Copilot Skills

**What we built**: A comprehensive `.github/copilot-instructions.md` that Copilot treats as a persistent skill document

**Evolution of the instruction file:**

| Stage | What existed | What Copilot could do |
|---|---|---|
| Start | Basic README | Generic Python suggestions |
| v1 | Copilot instructions with architecture overview | Understands manifest format |
| v2 | Added `Essential Workflows & Patterns` section | Generates correct CLI commands |
| v3 | Added `Critical Design Patterns` + code examples | Produces code matching project conventions |
| Final | Full 200-line skill document with YAML/Python samples | End-to-end feature generation |

**Key skill sections added:**
- **Manifest Anatomy** with annotated YAML — Copilot learned the exact schema
- **Component Installation Pattern** — 5-step lifecycle Copilot follows when adding components
- **Module Organization** — Maps file paths to responsibilities, preventing wrong-file edits
- **Error Handling & Cleanup** — Ensures generated code uses `ShellError`/`ClusterError` correctly
- **Quick Start Commands** — Natural-language prompts Copilot understands as project shortcuts

**Measurable impact**: After adding the skill document, Copilot-generated code required **<2 review iterations** on average to merge, down from ~5 with a plain README.

---

## SLIDE 6 — Category 2 (continued): Skill Design Principles
*Layout: Title + 4 callout boxes*

### How We Turned Documentation into a Copilot Skill

**🎯 Principle 1: Show, Don't Just Tell**
Instead of writing *"use the manifest loader"*, the instructions include a concrete YAML block with every field annotated inline. Copilot uses these annotations as schema hints.

**🔗 Principle 2: Map Concepts to Files**
Every architectural concept links to its Python module path. When asked to add architecture detection, Copilot immediately opens `pkg/arch/detector.py` rather than creating a new file.

**✅ Principle 3: Encode Quality Gates**
The instructions include the exact tox commands for type checking, linting, and testing. Copilot runs these as part of every generation task, making CI green from the first push.

**⚡ Principle 4: Quick-Start Prompts as Shortcuts**
The `## Quick Start Commands` section defines reusable natural-language shortcuts:
```
copilot: "Create a new cluster manifest for testing with 5 worker nodes"
copilot: "Add comprehensive error handling and issue creation to the workflow"
```
These act as macro commands — single prompts that generate entire features.

---

## SLIDE 7 — Category 3: Working with Multiple Models in Parallel
*Layout: Title + workflow diagram (can be recreated as a shapes diagram in Slides)*

### 🔀 GPT-4.1 + Claude/Sonnet Running in Parallel

**Model assignment strategy:**

```
┌─────────────────────────────────┐    ┌──────────────────────────────────┐
│  GPT-4.1 (Python Expert Agent)  │    │   Claude / Sonnet (General Agent) │
│                                 │    │                                   │
│  • Component plugin classes     │    │  • Architecture design decisions  │
│  • Type-safe Python generation  │    │  • YAML manifest authoring        │
│  • tox/uv workflow execution    │    │  • GitHub Actions workflows       │
│  • Pydantic model definitions   │    │  • Documentation & README         │
│  • Unit test generation         │    │  • Failure analysis & debugging   │
└─────────────────────────────────┘    └──────────────────────────────────┘
              │                                        │
              └────────────────┬───────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Pull Request merge  │
                    │  CI validates both   │
                    └─────────────────────┘
```

**How parallel model use accelerated delivery:**

- While GPT-4.1 generated `containerd.py` and its tests, Claude authored the corresponding `baseline-k8s-1.35.yaml` manifest entry and updated the README
- Both outputs were opened as separate Copilot conversations simultaneously
- Final PR combined both outputs — merged in one step with no conflicts
- Time saving vs. sequential: estimated **40-60% faster** for features spanning code + config + docs

---

## SLIDE 8 — The Achieved Results
*Layout: Title + metrics grid*

### What Was Built in Record Time

**Codebase produced with Copilot as primary author:**

| Metric | Value |
|---|---|
| Python source files | 28 |
| Total lines of Python | ~4,000 |
| Cluster manifests (K8s versions) | 5 (1.33 – 1.36 + smoke test) |
| Components per manifest | 15+ |
| GitHub Actions workflows | 3 (lint, test, baseline clusters) |
| Supported CPU architectures | 6 (amd64, arm64, riscv64, ppc64le, s390x, arm) |
| Component lifecycle hooks | 9 (download → post_delete) |

**Architecture features delivered:**
- ✅ Real kubeadm cluster provisioning (no Minikube shortcuts)
- ✅ Plugin-based component registry with `@register_component` decorator
- ✅ Dynamic manifest discovery — CI matrix auto-expands as manifests are added
- ✅ Spread test integration for component-level functional testing
- ✅ Automatic failure issue creation with full debug state capture
- ✅ `upterm` interactive debugging session on PR failures
- ✅ Architecture detection with 3-variable env injection (SYSTEM_ARCH, K8S_ARCH, IMAGE_ARCH)

**Development velocity:**
- Full Python CLI from zero to functional: **~2 days** with Copilot vs. estimated 2 weeks manually
- Zero hand-written boilerplate in `pkg/components/`
- First CI pass rate: >80% (vs. typical ~50% for complex infra projects)

---

## SLIDE 9 — Repository Links
*Layout: Title + link cards*

### 🔗 Repository & Key Files

**Main repository**
https://github.com/canonical/kube-galaxy-test

**Custom Agent definition**
https://github.com/canonical/kube-galaxy-test/blob/main/.github/agents/python.md

**Copilot Instructions / Skills file**
https://github.com/canonical/kube-galaxy-test/blob/main/.github/copilot-instructions.md

**Architecture documentation**
https://github.com/canonical/kube-galaxy-test/blob/main/.github/ARCHITECTURE.md

**Component plugin system**
https://github.com/canonical/kube-galaxy-test/tree/main/src/kube_galaxy/pkg/components

**GitHub Actions CI workflow (matrix)**
https://github.com/canonical/kube-galaxy-test/blob/main/.github/workflows/test-baseline-clusters.yml

**Cluster manifests (K8s 1.33–1.36)**
https://github.com/canonical/kube-galaxy-test/tree/main/manifests

---

## SLIDE 10 — Key Findings & Learnings
*Layout: Title + 3 columns (What worked / What surprised us / What we'd do differently)*

### Lessons from Building Infrastructure with Copilot

#### ✅ What Worked Exceptionally Well

- **Rich instruction files pay compound interest** — every hour invested in `.github/copilot-instructions.md` saved 3-4 hours of review on generated code
- **Custom agents enforce style** — the Python Expert agent produced consistently typed, documented code from day one
- **Parallel models for orthogonal concerns** — GPT-4.1 for Python precision, Claude for system design and documentation, never blocking each other
- **Encoding quality gates in instructions** — Copilot runs `tox -e type,lint,test` autonomously; CI was green on first push for most features
- **Natural-language shortcuts** — the Quick Start Commands section let non-expert contributors generate correct features without knowing the full codebase

#### 😮 What Surprised Us

- Copilot maintained **consistent architectural patterns** across 28 files without drift — the instruction file acted as a living style guide
- The agent correctly chose between `ShellError` and `ClusterError` exception types based only on the instruction file description — zero explicit teaching needed
- Multi-model parallel sessions had **no integration conflicts** — models independently produced compatible outputs because both read the same instruction file

#### 🔁 What We'd Do Differently

- **Version the instruction file** — as the project grew, earlier agents used outdated patterns; semantic versioning of `copilot-instructions.md` would have prevented this
- **Add model-specific skill sections** — GPT-4.1 and Claude have different strengths; separating Python-specific vs. systems-design guidance into agent-specific files would improve output quality further
- **Create a validation agent** — a dedicated "code reviewer" agent that checks generated PRs against the instruction file before merge would close the loop fully

---

## SLIDE 11 — Conclusion
*Layout: Title + large quote + key takeaways bullets*

### Copilot as a Force Multiplier for Infrastructure Engineering

> *"The biggest insight was that GitHub Copilot isn't just an autocomplete tool — when you invest in its instruction files and custom agents, it becomes a disciplined collaborator that enforces your architecture consistently across every file it touches."*

**Three things that made this project successful:**

1. **Structured knowledge transfer** — Writing `.github/copilot-instructions.md` as a *skill document* (not a README) meant Copilot understood the *why* behind every design decision, not just the *what*

2. **Right model, right task** — Assigning GPT-4.1 to type-safe Python generation and Claude to system design/documentation respected each model's strengths, cutting review cycles in half

3. **Closed-loop automation** — Custom agent + tox quality gates + GitHub Actions CI created a fully automated feedback loop: Copilot writes code → agent runs tests → CI validates → merge with confidence

**The result**: A production-quality Kubernetes testing platform built in days, not weeks, with Copilot writing the vast majority of code — and the human's primary job being architecture decisions and instruction file authorship.

---

*Submission prepared for the GitHub Copilot Competition — March 2026*
*Repository: https://github.com/canonical/kube-galaxy-test*
