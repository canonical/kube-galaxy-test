# Plan: Component Spread Test Integration via Isolated Directory Structure

This document describes the approach kube-galaxy uses to execute
component-specific spread tests without depending on each component repo's
top-level `spread.yaml`.  Components provide tests at `spread/kube-galaxy/`
which kube-galaxy orchestrates through its own `spread.yaml`.

**Context**: Components (like containerd, kubelet, etc.) maintain their own
spread tests for their CI. kube-galaxy needs to run component tests against an
existing Kubernetes cluster without interfering with or depending on each
component's spread configuration.

**Key Design Principle**: Isolation through directory structure - each
component's tests live in
`/opt/kube-galaxy/tests/<component>/spread/kube-galaxy/` and are
orchestrated by kube-galaxy's primary `spread.yaml` at
`/opt/kube-galaxy/tests/spread.yaml`.

**Design Decisions Incorporated**:
- Sequential test execution respecting component dependency order
- Continue on failure to collect all test results
- Fresh namespace per component (cleaned after each component completes)
- Tests run via separate `kube-galaxy test` command (not during setup)

---

## Source Modes

Components have two source modes controlled by the `test.repo.base-url` field.
Each component now has a separate `test:` section that specifies how to locate
and execute its spread tests, independently of the `installation:` section.

### Remote source (`test.repo.base-url: https://...`)

Tests are cloned from the component repository during setup:

```yaml
- name: containerd
  installation:
    method: binary-archive
    repo:
      base-url: https://github.com/containerd/containerd
    source-format: "{{ repo.base-url }}/releases/download/v{{ release }}/containerd-{{ release }}-linux-{{ arch }}.tar.gz"
  test:
    method: spread
    repo:
      base-url: https://github.com/containerd/containerd
    source-format: "{{ repo.base-url }}/spread/kube-galaxy"
```

During `kube-galaxy setup`, `download_tasks_from_config()` clones the repo and
places the tests under `tests_root/<name>/spread/kube-galaxy/`.

### Local source (`test.repo.base-url: local://`)

Tests live in the kube-galaxy-test repository itself at
`components/<name>/spread/kube-galaxy/task.yaml`.

```yaml
- name: sonobuoy
  installation:
    method: none
  test:
    method: spread
    repo:
      base-url: local://components/sonobuoy/
      subdir: spread/kube-galaxy/task.yaml
    source-format: "{{ repo.base-url }}/{{ repo.subdir }}"
```

**Local source rules**:
- `{{ repo.base-url }}` in `test.source-format` resolves to a `file://` URI of cwd
- `download_tasks_from_config()` copies the resolved path to `tests_root/<name>/`
- `task_path_for_component()` returns `tests_root/<name>/spread/kube-galaxy/` (same as remote)

---

## `source-format` Placeholders

The `installation.source-format` and `test.source-format` fields support the
following placeholders:

| Placeholder           | Resolves to                                                |
|-----------------------|------------------------------------------------------------|
| `{{ name }}`          | Component name from the manifest                          |
| `{{ arch }}`          | Kubernetes arch name (`amd64`, `arm64`, `riscv64`, ...)   |
| `{{ release }}`       | Component release tag from the manifest                   |
| `{{ ref }}`           | Git ref override, or empty string                         |
| `{{ repo.base-url }}` | Repository base URL; `local://path` expands to a `file://` URI rooted at cwd; `gh-artifact://name/path` routes to GitHub Artifacts API |
| `{{ repo.subdir }}`   | Optional subdirectory within the repo (empty if unset); `{{ name }}` within the `subdir` YAML field is also expanded |
| `{{ repo.ref }}`      | Git ref from the `repo` block (empty if unset)            |

**Implementation note**: Source-format templates are rendered using **Mustache**
(via the `chevron` library).  Chevron performs nested dict lookups using dot
notation, so `{{ repo.base-url }}` naturally resolves the `base-url` key inside
the `repo` context — no preprocessing required.  The `repo.subdir` value is
itself pre-rendered with `{{ name }}` in scope, so you can write
`subdir: "components/{{ name }}"` and the component name will be substituted.

---

## Test Directory Structure

After `kube-galaxy setup` all component test tasks must live under:

```
/opt/kube-galaxy/tests/
  spread.yaml            <- generated orchestration manifest
  <component>/
    spread/
      kube-galaxy/
        task.yaml        <- component spread task
```

For remote sources this is populated by `download_tasks_from_config()`.
For local sources (`base-url: local://`) this is populated by `download_tasks_from_config()`
which copies `cwd/components/<name>/` → `tests_root/<name>/`.

---

## Environment Variables Available to `task.yaml`

When spread executes a component's `task.yaml`, the following shell environment
variables are available in the `execute` block in addition to the standard
spread-level variables:

| Variable            | Value                                     |
|---------------------|-------------------------------------------|
| `COMPONENT_NAME`    | Component name from the manifest          |
| `COMPONENT_VERSION` | Component release tag from the manifest   |
| `KUBECONFIG`        | Path to the kubeconfig file               |
| `SYSTEM_ARCH`       | Raw `uname -m` architecture string        |
| `K8S_ARCH`          | Kubernetes arch format (`amd64`, `arm64`) |
| `IMAGE_ARCH`        | Container image arch tag format           |
| `TEST_TIMEOUT_M`    | Test timeout in minutes                   |
| `TEST_TIMEOUT_S`    | Test timeout in seconds                   |

Example `task.yaml` using `COMPONENT_VERSION` and `K8S_ARCH`:

```yaml
summary: My component conformance tests
execute: |
    wget https://example.com/releases/v${COMPONENT_VERSION}/tool-linux-${K8S_ARCH}.tar.gz
    tar xf tool-linux-${K8S_ARCH}.tar.gz
    ./tool --kubeconfig=$KUBECONFIG run --wait=$TEST_TIMEOUT_M
```

`COMPONENT_NAME` and `COMPONENT_VERSION` are injected per-suite by
`_generate_orchestration_spread_yaml()` in
[pkg/testing/spread.py](src/kube_galaxy/pkg/testing/spread.py).

---

## Steps (Implementation Reference)

1. **Directory structure constants** in
   [pkg/literals.py](src/kube_galaxy/pkg/literals.py) - `tests_root()`,
   `tests_spread_yaml()`

2. **Component repo checkout** in
   [pkg/testing/spread.py](src/kube_galaxy/pkg/testing/spread.py) -
   `_checkout_component_repo()` uses GitPython to clone and checkout
   `component.release` tag/ref into `tests_root/<name>/`

3. **Orchestration spread.yaml generation** in
   [pkg/testing/spread.py](src/kube_galaxy/pkg/testing/spread.py) -
   `_generate_orchestration_spread_yaml()` reads each component's `task.yaml`
   from `tests_root/<name>/spread/kube-galaxy/` and builds a spread manifest

4. **Local source handling** in
   [pkg/components/_base.py](src/kube_galaxy/pkg/components/_base.py) -
   `download_tasks_from_config()` checks `config.test.repo.base_url.startswith("local://")`
   to determine whether to copy a local path or clone a remote repo

5. **Validator path resolution** in
   [pkg/manifest/validator.py](src/kube_galaxy/pkg/manifest/validator.py) -
   `task_path_for_component()` always returns `tests_root/<name>/spread/kube-galaxy/`
   regardless of local or remote source

6. **Local test suite copy** — `download_tasks_from_config()` in
   [pkg/components/_base.py](src/kube_galaxy/pkg/components/_base.py)
   for the reference implementation

   - Use `{{ variable }}` Mustache syntax (rendered by `chevron`) for `source-format` values

4. **Generate kube-galaxy orchestration spread.yaml** in
   [pkg/testing/spread.py](src/kube_galaxy/pkg/testing/spread.py)
   - Add `_generate_orchestration_spread_yaml(manifest: Manifest, components:
     list[ComponentConfig]) -> Path` function
   - Load template from `spread.yaml.tmpl`
   - Populate template with runtime values using `string.Template.substitute()`
   - Write populated spread.yaml to `/opt/kube-galaxy/tests/spread.yaml`
   - Template defines: `project: kube-galaxy-component-tests`, `backend: adhoc`,
     global `prepare:`/`restore:` sections, and `suites:` entries for each component

5. **Implement namespace lifecycle management** in
   [pkg/testing/spread.py](src/kube_galaxy/pkg/testing/spread.py)
   - Add `_create_test_namespace(component_name: str) -> str` function
   - Generate namespace: `kube-galaxy-test-{component_name}` (normalized)
   - Create via kubectl with labels: `app.kubernetes.io/managed-by=kube-galaxy`,
     `component={name}`
   - Return namespace name for injection into environment
   - Add `_cleanup_test_namespace(namespace: str) -> None` function
   - Delete namespace and wait for termination (with timeout)

6. **Update component test execution** in
   [pkg/testing/spread.py](src/kube_galaxy/pkg/testing/spread.py)
   - Replace placeholder in `_run_component_tests()` (lines 93-106)
   - For each component with `test: true`:
     - Checkout component repo to appropriate path
     - Create fresh test namespace
     - Set environment variables: `KUBECONFIG`, `KUBE_GALAXY_NAMESPACE`,
       `SYSTEM_ARCH`, `K8S_ARCH`, `IMAGE_ARCH`, `COMPONENT_NAME`,
       `COMPONENT_VERSION`
     - Execute spread via orchestration spread.yaml (specify suite path)
     - Capture stdout/stderr to component-specific log file
     - Cleanup namespace (even on failure)
     - Continue to next component (don't fail-fast)
   - Sequential execution preserving component dependency order from manifest

7. **Add test framework command execution wrapper** in
   [pkg/testing/spread.py](src/kube_galaxy/pkg/testing/spread.py)
   - Add `_execute_spread_for_component(component: ComponentConfig, namespace:
     str, spread_yaml: Path) -> bool` function
   - Build spread command: `spread -v -debug <backend>:<suite-path>`
   - Pass environment variables for cluster context and namespace
   - Stream output to console and capture to file
   - Return True on success, False on failure (don't raise exception)
   - Log component test results (passed/failed) with timestamps

8. **Implement test result aggregation** in
   [pkg/testing/spread.py](src/kube_galaxy/pkg/testing/spread.py)
   - Update `collect_test_results()` function (currently stub)
   - Parse test framework output logs from each component directory
   - Generate summary: components tested, passed, failed, skipped
   - Create JUnit XML report at `logs/component-tests.xml`
   - Output summary table to console showing per-component results

9. **Add validation for component test readiness** in
   [pkg/manifest/validator.py](src/kube_galaxy/pkg/manifest/validator.py)
   - Add `validate_component_spread_structure(component: ComponentConfig) ->
     list[str]` function
   - For components with `test: true`, check:
     - Repo URL is valid and accessible
     - Release tag/ref exists in repo
     - `/spread/kube-galaxy/` directory exists at that ref
     - At least one task.yaml exists under that directory
   - Return list of validation errors (empty if valid)
   - Call during `get_components_with_spread()` to warn early

10. **Reference spread.yaml.tmpl template structure**
    - Template file location: `src/kube_galaxy/pkg/testing/spread.yaml.tmpl`
    - Template structure using Python `string.Template` format:
      ```yaml
      project: kube-galaxy-component-tests
      path: ${test_root_path}
      backends:
        adhoc:
          type: adhoc
          allocate: echo "Using existing cluster"
      environment:
        KUBECONFIG: ${kubeconfig_path}
        KUBE_GALAXY_NAMESPACE: ${namespace}
        SYSTEM_ARCH: ${system_arch}
        K8S_ARCH: ${k8s_arch}
        IMAGE_ARCH: ${image_arch}
      prepare: |
        kubectl cluster-info
        kubectl get nodes
      restore: |
        kubectl delete namespace $${KUBE_GALAXY_NAMESPACE} --ignore-not-found
      suites:
      ${component_suites}
      ```
    - Note: `$${KUBE_GALAXY_NAMESPACE}` uses double `$$` to escape the literal `$`
      for shell expansion (not template substitution)

11. **Document component test requirements** in
    [docs/spread-based-component-tests.md](docs/spread-based-component-tests.md)
    - Document required directory structure: `/spread/kube-galaxy/` in component
      repos
    - Specify available environment variables components can use
    - Document namespace naming convention and lifecycle
    - Provide task.yaml template showing kubectl usage with
      `$KUBE_GALAXY_NAMESPACE`
    - Show example component test structure
    - Document how components mark themselves as spread-ready (`test:
      true`)

12. **Add error handling and cleanup guarantees** in
    [pkg/testing/spread.py](src/kube_galaxy/pkg/testing/spread.py)
    - Wrap each component test in try/finally block
    - Ensure namespace cleanup in finally block (always executes)
    - On failure, preserve test framework logs in `logs/<component>/` before
      cleanup
    - Log all errors but continue testing remaining components

13. **Enable component tests for initial components** in manifest files
    - Start with well-tested components:
      [manifests/smoktest.yaml](manifests/smoktest.yaml)
    - Set `test: true` for 1-2 pilot components (e.g., containerd,
      kubelet)
    - For each enabled component, ensure their repos have `/spread/kube-galaxy/`
      with tasks
    - Gradually enable more components as tests are added to their repos

---

## Verification

After implementation:
1. **Validate Unit tests**:
   - Use `tox -e format,lint,unit` to verify Python code is correct
   - Verify template file loads and substitutes correctly

2. **Local smoke test**: Run `kube-galaxy test` with smoktest.yaml (1-2 components enabled)
   - Verify checkout to `/opt/kube-galaxy/tests/<component>/origin/`
   - Verify orchestration spread.yaml generated from template at `/opt/kube-galaxy/tests/spread.yaml`
   - Verify namespace creation/cleanup per component
   - Verify environment variables passed to test execution
   - Check logs directory contains per-component logs

3. **Validation test**: Run `kube-galaxy validate` with test-enabled components
   - Should validate component repos have `/spread/kube-galaxy/` structure
   - Should warn if `test: true` but no tests found

---

## Decisions

- **Directory structure**: Using `/opt/kube-galaxy/tests/<component>/origin/`
  provides clear isolation and allows future expansion (e.g., generated test
  data in sibling directories)
- **Orchestration approach**: kube-galaxy generates its own spread.yaml rather
  than modifying component repos' spread configuration — maintains strict
  separation of concerns
- **Namespace strategy**: Fresh namespace per component chosen over shared
  namespace to prevent cross-test pollution and enable parallel execution in
  future
- **Execution model**: Sequential with continue-on-failure balances safety and
  comprehensive test coverage; preserves option to parallelize in future
- **Component opt-in**: `test: true` flag allows gradual rollout as
  components add tests to their repos -- This might change

---

## Additional Considerations

### Architecture Variables
Components receive these environment variables during test execution:
- `SYSTEM_ARCH`: Raw system architecture from uname
- `K8S_ARCH`: Kubernetes binary format (amd64, arm64, etc.)
- `IMAGE_ARCH`: Container image tag format
- `COMPONENT_NAME`: Name of the component being tested
- `COMPONENT_VERSION`: Release/version from manifest

### Test Isolation
Each component test:
- Gets its own temporary namespace
- Cannot affect other component tests
- Runs in sequence respecting dependencies
- Has independent pass/fail status

### Future Enhancements
- Parallel component test execution (when dependencies allow)
- Test result caching to skip unchanged components
- Integration with GitHub Actions for automated component validation
- Support for component test timeouts
- Automatic issue creation for test failures with component context
