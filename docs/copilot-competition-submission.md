# Gemini Instructions: GitHub Copilot Competition Slide Deck
## "Kubernetes Galaxy Test — AI-Accelerated Infrastructure Testing"

---

> **How to use this file**: Paste the entire contents into Gemini and send it as a single prompt. Gemini will generate a complete, visually designed Google Slides presentation. Each numbered section below is one slide. Follow every instruction exactly — content, layout, visuals, background, and imagery are all specified.

---

## GLOBAL DESIGN SYSTEM

Apply these settings to every slide in the deck before building individual slides.

**Colour palette** — use these four colours exclusively:
- Deep space navy `#0D1B2A` — primary background and dark sections
- Electric cyan `#00C8FF` — headings, accent lines, highlight text, icons
- Warm white `#F0F4F8` — body text and light-section backgrounds
- Bright amber `#FFB700` — call-out boxes, key metrics, emphasis labels

**Typography**:
- Slide titles: **Inter ExtraBold**, 40 pt, electric cyan `#00C8FF`
- Section headings inside slides: **Inter SemiBold**, 24 pt, warm white `#F0F4F8`
- Body text: **Inter Regular**, 16 pt, warm white `#F0F4F8`
- Code snippets: **Fira Code Regular**, 13 pt, amber `#FFB700` text on a `#1A2A3A` dark panel with 6 px rounded corners
- Hyperlinks: underlined, electric cyan `#00C8FF`

**Slide dimensions**: 16:9 widescreen (33.87 cm × 19.05 cm).

**Consistent footer** on every slide (except the title slide): a 0.4 cm tall navy bar at the very bottom spanning full width. Inside it, left-aligned in 10 pt Inter Regular warm white: `Kubernetes Galaxy Test · GitHub Copilot Competition 2026`. Right-aligned in the same style: `github.com/canonical/kube-galaxy-test`.

**Accent line**: place a 3 px horizontal line in electric cyan directly beneath every slide title, spanning 60% of the slide width from the left edge.

**Transition**: set a subtle "Fade" transition (0.3 s) on all slides.

---

## SLIDE 1 — Title Slide

**Layout**: Full-bleed background image; large centred title block; four small category badge pills at the bottom.

**Background image**: Generate a cinematic deep-space nebula scene. The nebula should glow in electric cyan and cobalt blue hues against a near-black void, with a stylised Kubernetes helm-wheel logo subtly composited into the centre of the nebula at 30% opacity in white, as if it were a star cluster. Scattered bright star points in warm amber add depth. The overall mood is vast, technical, and awe-inspiring. Fill the entire 16:9 slide canvas with this image. Apply a very subtle dark vignette around the edges (bottom 25% should be darker, fading to near-black `#050D14`) so the text at the top and bottom reads clearly.

**Title text block** (vertically centred, horizontally centred):
- Main title in **Inter ExtraBold 64 pt**, warm white, with a soft cyan text-glow effect: `Kubernetes Galaxy Test`
- Subtitle directly below in **Inter Light Italic 28 pt**, warm white at 85% opacity: `Accelerating Cloud-Native Testing Infrastructure with GitHub Copilot`

**Author/repo line** (below subtitle, 20 pt Inter Regular warm white): `Adam Dyess · Canonical · March 2026`

**Category badge pills** (place as a horizontal row near the bottom of the slide, above the vignette zone, centred): create three rounded-rectangle pill shapes (height 36 px, auto-width, 18 px corner radius) in amber `#FFB700` with deep navy text at 14 pt Inter SemiBold. The three pills contain:
1. `🤖  Custom Agents Workflow`
2. `📄  Instruction Files → Skills`
3. `🔀  Multiple Models in Parallel`

Do **not** add the standard footer to this slide.

---

## SLIDE 2 — The Goal

**Layout**: Title at top; three equal-width vertical columns below separated by thin cyan dividers (1 px lines).

**Background**: Solid deep space navy `#0D1B2A`. In the top-right corner, place a faint watermark illustration of interconnected hexagons (representing a cluster topology) rendered in electric cyan at 6% opacity, large enough to fill roughly a quarter of the slide.

**Side image**: On the far right edge of the slide, partially cropped, place an illustrated graphic of a rocket launching upward from a Kubernetes cluster node diagram. Style: flat vector art, cyan and amber on navy, futuristic. The rocket represents fast delivery; the cluster nodes at its base represent the infrastructure being built. Size: approximately 22% slide width, full slide height, right-aligned, clipped at the slide edge.

**Slide title**: `The Goal`

**Column 1 heading**: `What We Needed to Build`
Column 1 body text (bulleted, 15 pt):
- A Python CLI (`kube-galaxy`) that provisions real Kubernetes clusters via kubeadm
- YAML-manifest-driven component system covering 30+ K8s components per version
- Multi-architecture support: amd64, arm64, riscv64, ppc64le, s390x
- GitHub Actions CI that matrix-tests Kubernetes 1.33 → 1.36 in parallel
- Spread test integration pulling tests from upstream component repositories
- Automatic failure capture (debug logs, GitHub Issues) for operator visibility

**Column 2 heading**: `The Challenge`
Column 2 body text (bulleted, 15 pt):
- Broad scope: cluster lifecycle, component plugin system, arch detection, testing harness, CI/CD
- Speed: needed a working, well-tested codebase fast
- Correctness: real Kubernetes infra — bugs have hard failures, not soft ones

**Column 3 heading**: `Copilot's Role`
Column 3 body text: render as a single amber-background call-out box (full column width, rounded corners 8 px) containing the quote in 15 pt Inter Italic warm white:
> "Rather than writing boilerplate and scaffolding by hand, we guided Copilot to produce complete, tested, production-quality code through carefully crafted instructions, custom agents, and parallel model use."

---

## SLIDE 3 — Category 1: Custom Agents Workflow

**Layout**: Title at top; left 55% is descriptive text content; right 45% is a dark code panel.

**Background**: Solid deep space navy `#0D1B2A`. Place a large faint robot/AI head icon (geometric, circuit-board style) in electric cyan at 5% opacity, centred behind the right panel area.

**Side image**: Above the right code panel, place a small flat-vector illustration of a robot hand pressing a "Generate" key on a keyboard, rendered in cyan and amber on a dark navy surface. Size roughly 18% slide width × 10% slide height.

**Slide title**: `🤖  Category 1: Custom Agents Workflow`

**Left column heading**: `End-to-End Hands-Off Workflow with a Custom Python Expert Agent`

Left column content (16 pt body text):
- **What we built**: A dedicated `.github/agents/python.md` agent named **"Python Expert"** running on **GPT-4.1**

Then a sub-section with amber label `Agent capabilities defined in the skill file:` followed by a bulleted list:
- Python 3.12+ with strict type hints and Pydantic models
- Typer CLI framework, async patterns, decorator-based component registration
- tox/uv development workflow (`tox -e format,lint,unit`)
- Lifecycle hook patterns (download → install → configure → bootstrap → verify)
- Error handling using project-specific exception types (`ShellError`, `ClusterError`)

Then a numbered list under amber label `How it worked in practice:`:
1. Developer writes a plain-English prompt: *"Add a sonobuoy component with download and verify hooks"*
2. Agent autonomously generates a complete `ComponentBase` subclass with all hooks, type hints, docstrings, and tests
3. Agent self-validates using `tox -e type,lint,test` before committing
4. Zero boilerplate written by hand — entire `src/kube_galaxy/pkg/components/` module generated this way

**Right column**: Create a dark code panel (`#1A2A3A` background, 8 px rounded corners, subtle 1 px cyan border) containing the following directory tree rendered in Fira Code 14 pt amber:
```
.github/
└── agents/
    └── python.md   ← Custom agent definition
```
Below the code block within the same panel, in 13 pt warm white italic:
"6 component classes produced — containerd, kubeadm, kubelet, CNI plugins, pause, sonobuoy — with consistent patterns and zero human-written scaffolding."

---

## SLIDE 4 — Category 1 (continued): What the Agent Produced

**Layout**: Title at top; a wide "prompt box" spanning full width just below the title; below that, two columns: left shows a list of what the agent produced, right shows a three-row metrics table.

**Background**: Solid deep space navy `#0D1B2A`. Place a faint stylised Python snake logo in electric cyan at 5% opacity watermark, lower-left quadrant, large (roughly 30% slide height).

**Side image**: Upper-right corner, a flat-vector illustration of a conveyor belt where a plain text document enters from the left, passes through a glowing AI processor chip in the middle, and a finished stack of neatly labelled Python files exits on the right. Style: isometric flat vector, cyan/amber/navy. Width: approximately 25% slide width.

**Slide title**: `From Prompt → Production Code in One Step`

**Prompt box**: A full-width rounded rectangle (8 px corners) in `#1A2A3A` with a 2 px amber left border accent. Inside, in 14 pt Fira Code amber:
> "Create a new Kubernetes component plugin for containerd. It needs download, install, configure, and bootstrap lifecycle hooks. Use the binary-archive install method, support multiarch, and follow the existing ComponentBase pattern."

**Left column heading**: `Agent produced (src/kube_galaxy/pkg/components/containerd.py)`
Left column bulleted list (15 pt warm white):
- Complete `@register_component("containerd")` class
- Multiarch binary download with `K8S_ARCH` environment variable
- systemd service configuration
- `bootstrap_hook()` with kubeadm containerd config generation
- Matching unit tests in `tests/unit/`
- Type hints on every method, docstrings describing each hook

**Right column**: Render a styled table with a cyan header row and alternating `#1A2A3A` / `#0D1B2A` body rows (all text warm white, 14 pt, Fira Code for file names):

| Artifact | Lines | Human-written |
|---|---|---|
| `containerd.py` | ~120 | **0** |
| `kubeadm.py` | ~150 | **0** |
| `kubelet.py` | ~110 | **0** |
| `__init__.py` registry | ~50 | **0** |
| Unit tests (all components) | ~200 | **0** |

Make the **0** values in the "Human-written" column amber and bold to make the zero-human-effort point visually striking.

---

## SLIDE 5 — Category 2: Optimizing Instruction Files → Skills

**Layout**: Title at top; a wide evolution timeline table spanning full width below it; then two content sections side by side below the table.

**Background**: Solid deep space navy `#0D1B2A`. In the lower-right corner, place a faint stylised document/scroll icon with a brain overlay (representing knowledge transfer) in electric cyan at 6% opacity, roughly 25% slide height.

**Side image**: Left edge of slide, vertically centred, a flat-vector illustration of a plain README page transforming (with a glowing arrow) into a rich structured skill document with highlighted sections. Style: flat vector, cyan/amber/navy. Width: approximately 16% slide width; crop at left edge.

**Slide title**: `📄  Category 2: Optimizing Instruction Files → Skills`

**Sub-heading** (24 pt Inter SemiBold warm white): `From README to Structured Copilot Skills`

**What we built line** (16 pt, italic warm white): "A comprehensive `.github/copilot-instructions.md` that Copilot treats as a persistent skill document."

**Evolution table** — render as a styled 5-row progression table with a cyan header row. Use a left-to-right arrow indicator (→) between the Stage column and the What Existed column to reinforce the progression idea. Alternating row backgrounds `#1A2A3A` / `#0D1B2A`, all text 14 pt warm white:

| Stage | What Existed | What Copilot Could Do |
|---|---|---|
| Start | Basic README | Generic Python suggestions |
| v1 | Copilot instructions with architecture overview | Understands manifest format |
| v2 | Added `Essential Workflows & Patterns` section | Generates correct CLI commands |
| v3 | Added `Critical Design Patterns` + code examples | Produces code matching project conventions |
| **Final** | Full 200-line skill document with YAML/Python samples | **End-to-end feature generation** |

Bold the Final row and render it with an amber background to show it as the goal state.

**Below the table, two columns:**

Left column heading: `Key Skill Sections Added`
Bulleted list (15 pt):
- **Manifest Anatomy** with annotated YAML — Copilot learned the exact schema
- **Component Installation Pattern** — 5-step lifecycle Copilot follows when adding components
- **Module Organization** — Maps file paths to responsibilities, preventing wrong-file edits
- **Error Handling & Cleanup** — Ensures generated code uses `ShellError`/`ClusterError` correctly
- **Quick Start Commands** — Natural-language prompts Copilot understands as project shortcuts

Right column: A single large amber call-out box (rounded 8 px corners) with a bold metric inside:
- Large text (36 pt Inter ExtraBold amber): `< 2`
- Below it (16 pt warm white): `review iterations to merge`
- Below it (14 pt warm white italic): `Down from ~5 with a plain README — a 60% reduction in review cycles`

---

## SLIDE 6 — Category 2 (continued): Skill Design Principles

**Layout**: Title at top; four equal-sized call-out card boxes arranged in a 2 × 2 grid filling the lower three-quarters of the slide.

**Background**: Solid deep space navy `#0D1B2A`. Faint diagonal blueprint grid lines in electric cyan at 4% opacity across the full slide, suggesting technical documentation.

**Side image**: Top-right corner, a flat-vector illustration of a stylised instruction manual being read by a robot, with glowing lightbulb above the robot's head. Style: flat vector, cyan/amber/navy. Width: approximately 18% slide width.

**Slide title**: `How We Turned Documentation into a Copilot Skill`

**Four cards** — each card: `#1A2A3A` background, 10 px rounded corners, 2 px solid top border in the colour specified per card, drop shadow 0 2 px 8 px rgba(0,200,255,0.15). Each card has an emoji icon (32 pt), a bold heading (18 pt Inter SemiBold warm white), and a body paragraph (14 pt warm white):

**Card 1** (top-left, top border cyan):
Icon: 🎯
Heading: `Principle 1: Show, Don't Just Tell`
Body: Instead of writing "use the manifest loader", the instructions include a concrete YAML block with every field annotated inline. Copilot uses these annotations as schema hints.

**Card 2** (top-right, top border amber):
Icon: 🔗
Heading: `Principle 2: Map Concepts to Files`
Body: Every architectural concept links to its Python module path. When asked to add architecture detection, Copilot immediately opens `pkg/arch/detector.py` rather than creating a new file.

**Card 3** (bottom-left, top border amber):
Icon: ✅
Heading: `Principle 3: Encode Quality Gates`
Body: The instructions include the exact tox commands for type checking, linting, and testing. Copilot runs these as part of every generation task, making CI green from the first push.

**Card 4** (bottom-right, top border cyan):
Icon: ⚡
Heading: `Principle 4: Quick-Start Prompts as Shortcuts`
Body: The `## Quick Start Commands` section defines reusable natural-language macros. A single prompt like `"Add comprehensive error handling and issue creation to the workflow"` generates an entire feature end-to-end.

---

## SLIDE 7 — Category 3: Working with Multiple Models in Parallel

**Layout**: Title at top; a large visual workflow diagram in the upper-centre area (built from slide shapes); a four-bullet summary list below the diagram.

**Background**: Solid deep space navy `#0D1B2A`. In the upper-right background, place a faint stylised illustration of two parallel circuit pathways converging into one, rendered in electric cyan at 7% opacity, suggesting parallelism and convergence.

**Side image**: Right edge of slide, vertically centred, a flat-vector illustration of two AI chat bubbles side-by-side (one labelled GPT-4.1, one labelled Claude) with arrows pointing down to a single merged pull-request symbol. Style: flat vector, cyan/amber/navy. Width: approximately 20% slide width, cropped at the right edge.

**Slide title**: `🔀  Category 3: Working with Multiple Models in Parallel`

**Workflow diagram** — build using slide shapes (not imported images):
- Two equal-width rounded rectangles side by side, with a 12 px gap between them. Left box background `#1A2A3A`, 2 px cyan border. Right box background `#1A2A3A`, 2 px amber border.
- Left box label (top, 16 pt Inter SemiBold cyan): `GPT-4.1 · Python Expert Agent`
  Content (14 pt warm white bulleted, no bullet symbols, use • character):
  • Component plugin classes
  • Type-safe Python generation
  • tox/uv workflow execution
  • Pydantic model definitions
  • Unit test generation
- Right box label (top, 16 pt Inter SemiBold amber): `Claude / Sonnet · General Agent`
  Content (14 pt warm white bulleted):
  • Architecture design decisions
  • YAML manifest authoring
  • GitHub Actions workflows
  • Documentation & README
  • Failure analysis & debugging
- Below both boxes, draw two diagonal lines (1 px, cyan) converging from the bottom-centre of each box down to a single merge point.
- At the merge point, place a rounded rectangle (amber background, navy text, 16 pt Inter SemiBold): `Pull Request · CI validates both`

**Four-bullet summary** (below diagram, 15 pt warm white, standard bullets):
- While GPT-4.1 generated `containerd.py` and its tests, Claude authored the corresponding `baseline-k8s-1.35.yaml` manifest entry and updated the README
- Both outputs were opened as separate Copilot conversations simultaneously
- Final PR combined both outputs — merged in one step with no conflicts
- Time saving vs. sequential: estimated **40–60% faster** for features spanning code + config + docs

---

## SLIDE 8 — The Achieved Results

**Layout**: Title at top; a seven-row metrics table on the left half; a bulleted feature checklist on the right half; a three-stat highlight bar spanning full width at the bottom.

**Background**: Solid deep space navy `#0D1B2A`. Place a faint star-field scatter pattern (50–60 small white dots at varying opacities 3–10%) across the entire slide background to evoke the "galaxy" theme.

**Side image**: Top-right corner, a flat-vector illustration of a trophy or rocket on a podium labelled "Production Ready", rendered in gold/amber with cyan highlights. Size: approximately 18% slide width × 20% slide height.

**Slide title**: `What Was Built in Record Time`

**Left table** — heading row in electric cyan, alternating body rows in `#1A2A3A` / `#0D1B2A`, all 14 pt warm white. Metric values in the right column should be bold amber:

| Metric | Value |
|---|---|
| Python source files | **28** |
| Total lines of Python | **~4,000** |
| Cluster manifests (K8s versions) | **5** (1.33–1.36 + smoke test) |
| Components per manifest | **15+** |
| GitHub Actions workflows | **3** (lint, test, baseline clusters) |
| Supported CPU architectures | **6** (amd64, arm64, riscv64, ppc64le, s390x, arm) |
| Component lifecycle hooks | **9** (download → post_delete) |

**Right column heading**: `Architecture Features Delivered`
Bulleted list using green ✅ emoji prefix, 14 pt warm white:
- ✅ Real kubeadm cluster provisioning (no Minikube shortcuts)
- ✅ Plugin-based component registry with `@register_component` decorator
- ✅ Dynamic manifest discovery — CI matrix auto-expands as manifests are added
- ✅ Spread test integration for component-level functional testing
- ✅ Automatic failure issue creation with full debug state capture
- ✅ `upterm` interactive debugging session on PR failures
- ✅ Architecture detection with 3-variable env injection (SYSTEM_ARCH, K8S_ARCH, IMAGE_ARCH)

**Bottom highlight bar** — a full-width 80 px tall strip in `#1A2A3A` with a 3 px top border in amber. Inside, three stats arranged horizontally and equally spaced, each with a large amber number above and a warm-white label below:

- `~2 days` · `Full CLI: zero to functional`
- `0` · `Hand-written boilerplate lines in pkg/components/`
- `>80%` · `First CI pass rate (vs. ~50% industry average)`

---

## SLIDE 9 — Repository Links

**Layout**: Title at top; seven link cards arranged in a grid (3 top row, 2 middle row, 2 bottom row) filling the slide body.

**Background**: Solid deep space navy `#0D1B2A`. Place a faint illustration of branching git commit graph lines (horizontal with nodes) in electric cyan at 5% opacity running across the middle of the slide.

**Side image**: Left edge of slide, vertically centred, a flat-vector GitHub Octocat logo reimagined with a space helmet and stars around it, rendered in electric cyan and amber line art. Width: approximately 14% slide width, cropped at left edge.

**Slide title**: `🔗  Repository & Key Files`

**Seven link cards** — each card: `#1A2A3A` background, 8 px rounded corners, 1 px cyan border on left edge (4 px wide), drop shadow. Inside each card: an emoji icon (20 pt), a bold label (14 pt Inter SemiBold warm white), and the URL on the line below (13 pt Inter Regular electric cyan, underlined, clickable hyperlink). Generate the seven cards with the following content:

1. 🏠 `Main Repository` → `https://github.com/canonical/kube-galaxy-test`
2. 🤖 `Custom Agent Definition` → `https://github.com/canonical/kube-galaxy-test/blob/main/.github/agents/python.md`
3. 📄 `Copilot Instructions / Skills File` → `https://github.com/canonical/kube-galaxy-test/blob/main/.github/copilot-instructions.md`
4. 🏛️ `Architecture Documentation` → `https://github.com/canonical/kube-galaxy-test/blob/main/.github/ARCHITECTURE.md`
5. 🧩 `Component Plugin System` → `https://github.com/canonical/kube-galaxy-test/tree/main/src/kube_galaxy/pkg/components`
6. ⚙️ `GitHub Actions CI Workflow (matrix)` → `https://github.com/canonical/kube-galaxy-test/blob/main/.github/workflows/test-baseline-clusters.yml`
7. 📦 `Cluster Manifests (K8s 1.33–1.36)` → `https://github.com/canonical/kube-galaxy-test/tree/main/manifests`

---

## SLIDE 10 — Key Findings & Learnings

**Layout**: Title at top; three equal-width vertical columns below, each a distinct card with a coloured top accent bar.

**Background**: Solid deep space navy `#0D1B2A`. Subtle horizontal scan-line texture (very faint, 1 px lines at 2% opacity every 4 px) across the full slide, suggesting a system readout / terminal output aesthetic.

**Side image**: Top-right, a flat-vector illustration of a magnifying glass with a gear inside it, rendered in electric cyan on navy, representing "findings and review". Width: approximately 15% slide width.

**Slide title**: `Key Findings & Learnings`

**Column 1** — `#1A2A3A` background, 8 px rounded corners, 4 px top bar in green (`#00C87A`):
Heading (18 pt Inter SemiBold, green `#00C87A`): `✅ What Worked Exceptionally Well`
Body (14 pt warm white, bulleted):
- **Rich instruction files pay compound interest** — every hour invested in `.github/copilot-instructions.md` saved 3–4 hours of review on generated code
- **Custom agents enforce style** — the Python Expert agent produced consistently typed, documented code from day one
- **Parallel models for orthogonal concerns** — GPT-4.1 for Python precision, Claude for system design and documentation, never blocking each other
- **Encoding quality gates in instructions** — Copilot runs `tox -e type,lint,test` autonomously; CI was green on first push for most features
- **Natural-language shortcuts** — the Quick Start Commands section let non-expert contributors generate correct features without knowing the full codebase

**Column 2** — `#1A2A3A` background, 8 px rounded corners, 4 px top bar in amber `#FFB700`:
Heading (18 pt Inter SemiBold amber): `😮 What Surprised Us`
Body (14 pt warm white, bulleted):
- Copilot maintained **consistent architectural patterns** across 28 files without drift — the instruction file acted as a living style guide
- The agent correctly chose between `ShellError` and `ClusterError` exception types based only on the instruction file description — zero explicit teaching needed
- Multi-model parallel sessions had **no integration conflicts** — models independently produced compatible outputs because both read the same instruction file

**Column 3** — `#1A2A3A` background, 8 px rounded corners, 4 px top bar in electric cyan `#00C8FF`:
Heading (18 pt Inter SemiBold cyan): `🔁 What We'd Do Differently`
Body (14 pt warm white, bulleted):
- **Version the instruction file** — as the project grew, earlier agents used outdated patterns; semantic versioning of `copilot-instructions.md` would have prevented this
- **Add model-specific skill sections** — GPT-4.1 and Claude have different strengths; separating Python-specific vs. systems-design guidance into agent-specific files would improve output quality further
- **Create a validation agent** — a dedicated "code reviewer" agent that checks generated PRs against the instruction file before merge would close the loop fully

---

## SLIDE 11 — Conclusion

**Layout**: Title at top; a large centred quote block spanning 80% of the slide width in the upper body; three numbered take-away cards in a horizontal row below; a final impact statement at the very bottom.

**Background image**: Generate a second space nebula image, different from Slide 1. This one should show a bright star formation in the shape of a network graph / cluster topology, glowing in electric cyan and warm amber against deep navy black. More "dawn" than "void" — the mood should feel like breakthrough and emergence. Apply a 40% dark overlay so text reads clearly. Fill the entire 16:9 canvas.

**Side image**: None on this slide — let the background breathe.

**Slide title**: `Copilot as a Force Multiplier for Infrastructure Engineering`

**Large quote block** — a `#0D1B2A` at 80% opacity rounded rectangle (12 px corners, 3 px cyan left border, 3 px amber right border) spanning 80% slide width, centred. Inside:
- A large open-quote character " in electric cyan (72 pt) positioned top-left of the box
- Quote text in 19 pt Inter Italic warm white:
  "The biggest insight was that GitHub Copilot isn't just an autocomplete tool — when you invest in its instruction files and custom agents, it becomes a disciplined collaborator that enforces your architecture consistently across every file it touches."
- Attribution below in 14 pt Inter Regular warm white italic: `— Adam Dyess, Canonical`

**Three take-away cards** — horizontal row, equal width, each `#1A2A3A` at 90% opacity background, 8 px rounded corners, amber numbered badge top-left:

Card 1 badge `1`, heading (16 pt Inter SemiBold cyan): `Structured Knowledge Transfer`
Body (13 pt warm white): Writing `.github/copilot-instructions.md` as a *skill document* (not a README) meant Copilot understood the *why* behind every design decision, not just the *what*.

Card 2 badge `2`, heading (16 pt Inter SemiBold cyan): `Right Model, Right Task`
Body (13 pt warm white): Assigning GPT-4.1 to type-safe Python generation and Claude to system design/documentation respected each model's strengths, cutting review cycles in half.

Card 3 badge `3`, heading (16 pt Inter SemiBold cyan): `Closed-Loop Automation`
Body (13 pt warm white): Custom agent + tox quality gates + GitHub Actions CI created a fully automated feedback loop: Copilot writes code → agent runs tests → CI validates → merge with confidence.

**Final impact statement** (bottom of slide, full width, centred, 15 pt Inter SemiBold amber):
`A production-quality Kubernetes testing platform built in days, not weeks — Copilot wrote the code; the human designed the architecture.`

---

*End of Gemini instructions. The completed deck should be 11 slides.*
*Submission for the GitHub Copilot Competition — deadline 06 March 2026 23:59 UTC*
*Repository: https://github.com/canonical/kube-galaxy-test*
