# Plan: Component Spread Test Integration via Isolated Directory Structure

This plan establishes a structured approach for kube-galaxy to execute
component-specific spread tests without depending on each component repo's
top-level spread.yaml. Instead, components provide tests at
`/spread/kube-galaxy/` which kube-galaxy orchestrates through its own
spread.yaml.

**Context**: Components (like containerd, kubelet, etc.) maintain their own
spread tests for their CI. kube-galaxy needs to run component tests against an
existing Kubernetes cluster without interfering with or depending on each
component's spread configuration.

**Key Design Principle**: Isolation through directory structure — each
component's tests live in
`/opt/kube-galaxy/tests/<component>/origin/spread/kube-galaxy/` and are
orchestrated by kube-galaxy's primary spread.yaml at
`/opt/kube-galaxy/tests/spread.yaml`.

**Design Decisions Incorporated**:
- Sequential test execution respecting component dependency order
- Continue on failure to collect all test results
- Fresh namespace per component (cleaned after each component completes)
- Tests run via separate `kube-galaxy test` command (not during setup)

---

## Steps

1. **Define directory structure conventions** in
   [pkg/literals.py](src/kube_galaxy/pkg/literals.py)
   - Add `SPREAD_TEST_ROOT = "/opt/kube-galaxy/tests"` constant
   - Add `SPREAD_MANIFEST_PATH = "/opt/kube-galaxy/tests/spread.yaml"`
   - Add component test path helper: `get_component_test_dir(name: str) -> Path`
   - Structure: `/opt/kube-galaxy/tests/<component>/origin/spread/kube-galaxy/`

2. **Implement component repo checkout** in
   [pkg/testing/spread.py](src/kube_galaxy/pkg/testing/spread.py)
   - Add `_checkout_component_repo(component: ComponentConfig, dest_path: Path)
     -> None` function
   - Use GitPython (already in dependencies) to clone `component.repo`
   - Checkout specific `component.release` tag/ref
   - Validate `/spread/kube-galaxy/` directory exists in repo (error if missing)
   - Clone to `/opt/kube-galaxy/tests/<component.name>/origin/`

3. **Create spread.yaml template file**
   - Create `src/kube_galaxy/pkg/testing/spread.yaml.tmpl` as template
   - Use Python string template format (e.g., `${variable}` placeholders)
   - Template fields: `project`, `path`, `kubeconfig`, `namespace`, `system_arch`,
     `k8s_arch`, `image_arch`, `component_suites`
   - No need for Jinja2 - use Python's `string.Template` for substitution

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
