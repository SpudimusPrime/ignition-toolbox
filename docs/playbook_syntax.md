# Playbook Syntax Reference

Complete reference for writing YAML playbooks. Playbooks automate Ignition Gateway operations, Perspective UI testing, and Designer desktop workflows.

---

## File Structure

```yaml
name: "Playbook Name"
version: "1.0"
description: "What this playbook does"
domain: perspective        # gateway | browser | perspective | designer

parameters:
  - name: gateway_url
    type: string
    required: true
    description: "Gateway base URL"

steps:
  - id: step_id
    name: "Human-readable step name"
    type: step.type
    parameters:
      key: value
    timeout: 60            # seconds, step-level override
    retry_count: 2
    retry_delay: 5
    on_failure: abort      # abort | continue

metadata:
  author: "Your Name"
  category: "gateway"
  tags: ["module", "upgrade"]
```

---

## Parameters

Parameters are declared at the top of the file and injected into steps at runtime via `{{ parameter.name }}` references.

### Parameter Types

| Type | Description |
|------|-------------|
| `string` | Text |
| `integer` | Whole number |
| `float` | Decimal number |
| `boolean` | `true` / `false` |
| `file` | Filesystem path |
| `credential` | Vault credential reference |
| `list` | Sequence of values |
| `dict` | Key/value map |
| `selector` | CSS selector string |

```yaml
parameters:
  - name: gateway_url
    type: string
    required: true
    description: "e.g. http://192.168.1.10:8088"

  - name: timeout_secs
    type: integer
    required: false
    default: 30
    description: "How long to wait"
```

---

## Template References

Use `{{ ... }}` anywhere in a parameter value to inject runtime data.

```yaml
# Playbook parameter
value: "{{ parameter.gateway_url }}"

# Credential vault — whole object, username, or password
value: "{{ credential.my_cred }}"
value: "{{ credential.my_cred.username }}"
value: "{{ credential.my_cred.password }}"

# Variable set earlier in the same playbook
value: "{{ variable.module_name }}"

# Output from a previous step (see utility.python)
value: "{{ step.detect_module.MODULE_VERSION }}"

# Mix references and literals in one string
url: "http://{{ parameter.host }}:{{ parameter.port }}/data/perspective/client/{{ parameter.project }}"
```

---

## Step Options

These fields apply to every step type.

```yaml
- id: upload                  # Unique ID within the playbook (required)
  name: "Upload Module"       # Display name shown in UI (optional)
  type: gateway.upload_module
  parameters:
    file: "{{ parameter.module_file }}"
  timeout: 300        # Max seconds for this step (default: varies by type)
  retry_count: 3      # Retry on failure up to N times
  retry_delay: 10     # Seconds between retries
  on_failure: abort   # abort (default) | continue
  skip_if: "{{ variable.already_uploaded }}"  # skip when expression is truthy
```

### Conditional Execution (`skip_if`)

Skip a step when a runtime expression is truthy. Missing variables are treated as falsy so the step always runs when unset — the same playbook works standalone or chained.

```yaml
# Skip if variable is truthy
skip_if: "{{ variable.session_logged_in }}"

# Skip if variable equals a value (case-sensitive)
skip_if: "{{ variable.navigation }} = materials"

# Skip if variable does not equal a value
skip_if: "{{ variable.navigation }} != administration"
```

**Pattern — track shared state with `utility.set_variable`:**

```yaml
# At the end of elev8_login.yaml:
- id: mark_logged_in
  type: utility.set_variable
  parameters:
    name: "session_logged_in"
    value: "true"

# After navigating to a view:
- id: set_nav
  type: utility.set_variable
  parameters:
    name: "navigation"
    value: "materials"   # value is case-sensitive — keep it consistent
```

Variables set inside nested `playbook.run` calls are visible to all other playbooks in the same execution chain.

---

## Gateway Steps

Gateway steps call the Ignition REST API directly — no browser required.

### `gateway.login`
Authenticates with the Gateway. Required before most other gateway steps.
```yaml
- id: login
  type: gateway.login
  parameters:
    credential: "{{ credential.gateway_admin }}"
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `credential` | credential | yes | Vault credential containing username + password |

---

### `gateway.logout`
Ends the authenticated session.
```yaml
- id: logout
  type: gateway.logout
```

---

### `gateway.ping`
Checks that the Gateway is reachable.
```yaml
- id: ping
  type: gateway.ping
```

---

### `gateway.get_info`
Retrieves Gateway system information (version, edition, license state).
```yaml
- id: info
  type: gateway.get_info
```

---

### `gateway.get_health`
Returns Gateway health status. Useful as a post-restart verification step.
```yaml
- id: health_check
  type: gateway.get_health
  retry_count: 3
  retry_delay: 10
```

---

### `gateway.list_modules`
Returns the list of installed modules.
```yaml
- id: modules
  type: gateway.list_modules
```

---

### `gateway.upload_module`
Uploads a `.modl` file to the Gateway.
```yaml
- id: upload
  type: gateway.upload_module
  parameters:
    file: "{{ parameter.module_file }}"
  timeout: 300
  retry_count: 2
  retry_delay: 15
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | file | yes | Path to the `.modl` file |

---

### `gateway.wait_for_module_installation`
Polls until a module reaches the installed+running state.
```yaml
- id: wait_install
  type: gateway.wait_for_module_installation
  parameters:
    module_name: "Perspective"
    timeout: 300
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `module_name` | string | yes | Module display name |
| `timeout` | integer | no | Max wait in seconds (default: 300) |

---

### `gateway.restart`
Restarts the Gateway process.
```yaml
- id: restart
  type: gateway.restart
  parameters:
    wait_for_ready: true
  timeout: 600
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `wait_for_ready` | boolean | no | Block until Gateway is back (default: true) |

---

### `gateway.wait_for_ready`
Waits for Gateway to finish starting up without triggering a restart.
```yaml
- id: wait
  type: gateway.wait_for_ready
  parameters:
    timeout: 300
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `timeout` | integer | no | Max wait in seconds (default: 300) |

---

### `gateway.list_projects`
Lists all projects on the Gateway.
```yaml
- id: projects
  type: gateway.list_projects
```

---

### `gateway.get_project`
Gets details for a specific project.
```yaml
- id: project_info
  type: gateway.get_project
  parameters:
    project_name: "{{ parameter.project }}"
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_name` | string | yes | Project name |

---

## Browser Steps

Browser steps drive Chromium via Playwright. Used for Perspective UI testing and any web-based workflows.

> **Perspective inputs:** Add `fill_mode: type` to `browser.fill` steps when targeting Perspective TextField components. This types character-by-character to properly trigger React's synthetic event system; without it the field reverts when focus moves away.

### `browser.navigate`
Navigates the browser to a URL.
```yaml
- id: navigate
  type: browser.navigate
  parameters:
    url: "http://{{ parameter.host }}:8088/data/perspective/client/{{ parameter.project }}"
    wait_until: networkidle
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | yes | Target URL |
| `wait_until` | string | no | `load` \| `domcontentloaded` \| `networkidle` (default: `load`) |

---

### `browser.click`
Clicks an element.
```yaml
- id: submit
  type: browser.click
  parameters:
    selector: "#submitBtn"
    force: false
    timeout: 10000
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `selector` | selector | yes | CSS selector |
| `timeout` | integer | no | Max wait in ms (default: 30000) |
| `force` | boolean | no | Click even if behind another element |

---

### `browser.fill`
Types a value into an input field.
```yaml
- id: fill_name
  type: browser.fill
  parameters:
    selector: "#NameInput"
    value: "{{ parameter.material_name }}"
    fill_mode: type      # required for Perspective TextFields
    timeout: 10000
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `selector` | selector | yes | CSS selector |
| `value` | string | yes | Text to enter |
| `fill_mode` | string | no | `fill` (default) or `type`. Use `type` for Perspective inputs. |
| `timeout` | integer | no | Max wait in ms (default: 30000) |

---

### `browser.keyboard`
Sends a key or key combination to the page (acts on the currently focused element).
```yaml
- id: confirm
  type: browser.keyboard
  parameters:
    key: "Enter"

- id: select_all
  type: browser.keyboard
  parameters:
    key: "Control+A"
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key` | string | yes | Key name or combo: `Enter`, `Tab`, `Escape`, `Control+A`, etc. |

---

### `browser.screenshot`
Saves a screenshot to the data/screenshots directory.
```yaml
- id: capture
  type: browser.screenshot
  parameters:
    name: "post_submit"
    full_page: true
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | no | Filename (without extension) |
| `full_page` | boolean | no | Capture full scrollable page (default: false) |

---

### `browser.wait`
Waits for an element to appear in the DOM.
```yaml
- id: wait_modal
  type: browser.wait
  parameters:
    selector: "#confirmDialog"
    timeout: 15000
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `selector` | selector | yes | CSS selector to wait for |
| `timeout` | integer | no | Max wait in ms (default: 30000) |

**Tip:** Use `on_failure: continue` with a short timeout to create an optional wait:
```yaml
- id: optional_banner
  type: browser.wait
  parameters:
    selector: ".warning-banner"
    timeout: 2000
  on_failure: continue
```

---

### `browser.verify`
Asserts that an element does or does not exist.
```yaml
- id: check_logged_in
  type: browser.verify
  parameters:
    selector: ".user-profile"
    exists: true

- id: check_no_errors
  type: browser.verify
  parameters:
    selector: ".error-message"
    exists: false
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `selector` | selector | yes | CSS selector |
| `exists` | boolean | no | `true` = must exist, `false` = must not exist (default: true) |
| `timeout` | integer | no | Max wait in ms |

---

### `browser.verify_text`
Asserts the text content of an element.
```yaml
- id: check_title
  type: browser.verify_text
  parameters:
    selector: "h1.page-title"
    text: "Administration"
    match: contains
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `selector` | selector | yes | CSS selector |
| `text` | string | yes | Expected text |
| `match` | string | no | `exact` \| `contains` \| `regex` (default: `exact`) |
| `timeout` | integer | no | Max wait in ms |

---

### `browser.verify_attribute`
Asserts an HTML attribute value.
```yaml
- id: check_disabled
  type: browser.verify_attribute
  parameters:
    selector: "#submitBtn"
    attribute: "disabled"
    value: "true"
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `selector` | selector | yes | CSS selector |
| `attribute` | string | yes | Attribute name |
| `value` | string | yes | Expected attribute value |
| `timeout` | integer | no | Max wait in ms |

---

### `browser.verify_state`
Asserts the interactive state of an element.
```yaml
- id: check_button_enabled
  type: browser.verify_state
  parameters:
    selector: "#submitBtn"
    state: enabled
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `selector` | selector | yes | CSS selector |
| `state` | string | yes | `visible` \| `hidden` \| `enabled` \| `disabled` |
| `timeout` | integer | no | Max wait in ms |

---

### `browser.get_text`
Extracts text from an element and optionally stores it as a variable.
```yaml
- id: read_status
  type: browser.get_text
  parameters:
    selector: "#statusLabel"
    variable_name: "current_status"

# Later steps can reference: {{ variable.current_status }}
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `selector` | selector | yes | CSS selector |
| `variable_name` | string | no | Variable to store the result in |
| `timeout` | integer | no | Max wait in ms |

---

### `browser.file_upload`
Sets a file on a file input element.
```yaml
- id: upload_csv
  type: browser.file_upload
  parameters:
    selector: "input[type='file']"
    file_path: "{{ parameter.csv_file }}"
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `selector` | selector | yes | CSS selector for `<input type="file">` |
| `file_path` | file | yes | Absolute path to the file |
| `timeout` | integer | no | Max wait in ms |

---

## Designer Steps

Designer steps automate the Ignition Designer desktop application using OS-level automation.

### `designer.launch`
Launches Designer from a `.jnlp` or `.exe` launcher file.
```yaml
- id: launch
  type: designer.launch
  parameters:
    launcher_file: "C:/Users/me/Downloads/designer.jnlp"
  timeout: 120
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `launcher_file` | file | yes | Path to launcher file |

---

### `designer.launch_shortcut`
Launches Designer via a Windows shortcut with auto-login.
```yaml
- id: launch
  type: designer.launch_shortcut
  parameters:
    designer_shortcut: "Ignition Designer"
    project_name: "MyProject"
    gateway_credential: "{{ credential.gateway_admin }}"
  timeout: 120
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `designer_shortcut` | string | yes | Shortcut name or path |
| `project_name` | string | yes | Project to open |
| `gateway_credential` | credential | no | Vault credential for login |
| `username` | string | no | Username (if not using credential) |
| `password` | string | no | Password (if not using credential) |
| `timeout` | integer | no | Max wait in seconds |

---

### `designer.login`
Logs in to an already-running Designer.
```yaml
- id: login
  type: designer.login
  parameters:
    username: "{{ credential.designer_admin.username }}"
    password: "{{ credential.designer_admin.password }}"
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `username` | string | yes | |
| `password` | string | yes | |
| `timeout` | integer | no | Max wait in seconds (default: 30) |

---

### `designer.open_project`
Opens a project inside the Designer.
```yaml
- id: open
  type: designer.open_project
  parameters:
    project_name: "{{ parameter.project }}"
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_name` | string | no | Leave empty to open the first available project |
| `timeout` | integer | no | Max wait in seconds (default: 30) |

---

### `designer.screenshot`
Captures a screenshot of the Designer window.
```yaml
- id: capture
  type: designer.screenshot
  parameters:
    name: "designer_open"
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | no | Filename (without extension) |

---

### `designer.wait`
Waits for the Designer window to appear.
```yaml
- id: wait
  type: designer.wait
  parameters:
    timeout: 60
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `timeout` | integer | no | Max wait in seconds (default: 30) |

---

### `designer.close`
Closes the Designer application.
```yaml
- id: close
  type: designer.close
```

---

## Perspective Steps

Perspective steps extend browser automation with Perspective-specific component awareness.

### `perspective.discover_page`
Scans a Perspective page and returns an inventory of interactive components.
```yaml
- id: discover
  type: perspective.discover_page
  parameters:
    selector: "#main-content"
    types: ["Button", "TextField", "Dropdown"]
    exclude_selectors: [".header", ".footer"]
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `selector` | selector | no | Root element to search within (default: `body`) |
| `types` | list | no | Perspective component types to include |
| `exclude_selectors` | list | no | Selectors to exclude |

Output stored in step results as `inventory` (list of components with selectors, labels, paths).

---

### `perspective.extract_component_metadata`
Enriches a component list from `discover_page` with reliability scores and labels.
```yaml
- id: enrich
  type: perspective.extract_component_metadata
  parameters:
    components: "{{ step.discover.inventory }}"
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `components` | list | yes | Component list from `discover_page` |

---

### `perspective.execute_test_manifest`
Runs a list of click/fill actions against Perspective components in sequence,
capturing screenshots and reporting pass/fail per item.

> **Build this in Form mode.** The `manifest` parameter has a structured editor
> (Add Test Item button) that renders one form per item. Do not hand-write the
> manifest in YAML — use the Form editor or the YAML editor only after the Form
> editor has generated the structure correctly.

```yaml
- id: run_form_tests
  type: perspective.execute_test_manifest
  parameters:
    manifest:
      - component_id: name_field
        selector: "#NameInput"
        action: fill
        value: "Test Material"
        fill_mode: type
        expected: Name field accepts input
      - component_id: submit_btn
        selector: "#addEditMaterial button >> text=/Submit/i"
        action: click
        expected: Form submits without error
    capture_screenshots: true
    on_failure: continue
    return_to_baseline: false
```

**Each manifest item:**

| Field | Required | Description |
|-------|----------|-------------|
| `component_id` | yes | Unique label used in results and screenshot names |
| `selector` | yes | CSS selector for the target element |
| `action` | yes | `click` or `fill` |
| `value` | fill only | Text to enter |
| `fill_mode` | fill only | `type` (default, required for Perspective TextFields) or `fill` |
| `expected` | no | Human-readable description of expected outcome (logged only) |

**Step parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `manifest` | list | yes | List of test items (see above) |
| `capture_screenshots` | boolean | no | Screenshot after each item (default: true) |
| `on_failure` | string | no | `continue` (default) \| `abort` |
| `return_to_baseline` | boolean | no | Navigate back after each item (default: true) |
| `baseline_url` | string | no | URL to return to between items |

---

### `perspective.verify_navigation`
Asserts that the browser navigated to an expected URL or page title.
```yaml
- id: check_nav
  type: perspective.verify_navigation
  parameters:
    expected_url_pattern: "/administration"
    expected_title_pattern: "Admin"
    timeout: 5000
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `expected_url_pattern` | string | no | Substring to find in current URL |
| `expected_title_pattern` | string | no | Substring to find in page title |
| `timeout` | integer | no | Max wait in ms (default: 5000) |

---

### `perspective.verify_dock_opened`
Asserts that a Perspective dock panel became visible.
```yaml
- id: check_dock
  type: perspective.verify_dock_opened
  parameters:
    dock_selector: ".ia-dock-panel"
    timeout: 3000
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `dock_selector` | selector | yes | CSS selector for the dock element |
| `timeout` | integer | no | Max wait in ms (default: 3000) |

---

### `perspective.verify_with_ai`
Uses AI vision to verify a UI state from a screenshot.
```yaml
- id: ai_check
  type: perspective.verify_with_ai
  parameters:
    prompt: "Verify the login form is visible with username and password fields"
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prompt` | string | yes | Description of what to verify |

Requires an AI API key configured in `.env` (`ANTHROPIC_API_KEY`).

---

## Utility Steps

### `utility.sleep`
Pauses execution for a fixed duration.
```yaml
- id: pause
  type: utility.sleep
  parameters:
    seconds: 3
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `seconds` | float | yes | Duration to sleep |

---

### `utility.log`
Writes a message to the execution log (visible in the UI).
```yaml
- id: log_status
  type: utility.log
  parameters:
    message: "Module {{ parameter.module_name }} upload complete"
    level: info
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | yes | Message text (supports templates) |
| `level` | string | no | `debug` \| `info` \| `warning` \| `error` (default: `info`) |

---

### `utility.set_variable`
Stores a value for use in later steps via `{{ variable.name }}`.
```yaml
- id: store_url
  type: utility.set_variable
  parameters:
    name: "target_url"
    value: "http://{{ parameter.host }}:8088"

# Later: {{ variable.target_url }}
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | yes | Variable name |
| `value` | string | yes | Value (supports templates) |

---

### `utility.python`
Executes an inline Python script. Output lines matching `KEY=value` are captured as step outputs and accessible via `{{ step.step_id.KEY }}`.
```yaml
- id: detect
  type: utility.python
  parameters:
    script: |
      import zipfile, os
      modl = "{{ parameter.module_file }}"
      with zipfile.ZipFile(modl) as z:
          with z.open("module.xml") as f:
              content = f.read().decode()
      import re
      name = re.search(r'<name>(.*?)</name>', content).group(1)
      print(f"MODULE_NAME={name}")

# Later steps: {{ step.detect.MODULE_NAME }}
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `script` | string | yes | Python code. Print `KEY=value` lines to expose outputs. |

---

## Playbook Steps

### `playbook.run`
Executes another playbook as a single nested step. The target playbook must be marked **Verified** in the UI.
```yaml
- id: login
  name: "Execute App Login"
  type: playbook.run
  parameters:
    playbook: "elev8_login.yaml"
  timeout: 60

# With parameter passing:
- id: install_module
  type: playbook.run
  parameters:
    playbook: "gateway/module_install.yaml"
    gateway_url: "{{ parameter.gateway_url }}"
    module_file: "{{ parameter.module_file }}"
  timeout: 300
```
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `playbook` | string | yes | Relative path from playbooks directory |
| *(any)* | any | no | Additional keys are passed as parameters to the child playbook |

**Constraints:**
- Target must be marked Verified
- Maximum nesting depth: 3 levels
- Circular references are prevented

---

## FAT Reporting Steps

### `fat.generate_report`
Generates a Factory Acceptance Test report from execution results.
```yaml
- id: report
  type: fat.generate_report
  parameters:
    title: "Elev8 FAT Report"
    include_screenshots: true
```

---

### `fat.export_report`
Exports a previously generated report to a file.
```yaml
- id: export
  type: fat.export_report
  parameters:
    format: pdf
    output_path: "{{ parameter.output_dir }}/report.pdf"
```

---

## Selectors

CSS selectors work as in standard web automation. Common patterns for Perspective:

```yaml
# By ID (set in Perspective component properties)
selector: "#ComponentId"

# By ID — target the actual input inside a Perspective wrapper
selector: "#NameInput input"

# By text content
selector: "text='Submit'"
selector: "text=/submit/i"          # case-insensitive regex

# By button text inside a container
selector: "#myDialog button >> text=/Submit/i"

# By placeholder
selector: "input[placeholder*='username' i]"

# By name attribute (standard login forms)
selector: "input[name='j_username']"

# Multiple fallback selectors (comma-separated — first match wins)
selector: "input[name='j_username'], input[name='username'], input[type='text']"
```

---

## Complete Example

```yaml
name: "Add Material"
version: "1.0"
description: "Adds a new material record via the Perspective admin UI"
domain: perspective

parameters:
  - name: material_name
    type: string
    required: false
    default: "New Material"
  - name: material_description
    type: string
    required: false
    default: "Description"
  - name: material_uom
    type: string
    required: false
    default: "EA"

steps:
  - id: login
    name: "App Login"
    type: playbook.run
    parameters:
      playbook: "elev8_login.yaml"
    timeout: 60

  - id: navigate
    name: "Navigate to Administration"
    type: browser.navigate
    parameters:
      url: "http://192.168.1.10:8088/data/perspective/client/myapp/administration"
      wait_until: networkidle

  - id: click_materials
    type: browser.click
    parameters:
      selector: "#materialNav"

  - id: wait_page
    type: browser.wait
    parameters:
      selector: "text='Administration Menu'"

  - id: click_add
    type: browser.click
    parameters:
      selector: "#addBtn"

  - id: wait_modal
    type: browser.wait
    parameters:
      selector: "#addEditMaterial"

  - id: fill_name
    type: browser.fill
    parameters:
      selector: "#NameInput"
      value: "{{ parameter.material_name }}"
      fill_mode: type

  - id: fill_desc
    type: browser.fill
    parameters:
      selector: "#DescriptionInput"
      value: "{{ parameter.material_description }}"
      fill_mode: type

  - id: fill_uom
    type: browser.fill
    parameters:
      selector: "#UomInput"
      value: "{{ parameter.material_uom }}"
      fill_mode: type

  - id: submit
    type: browser.click
    parameters:
      selector: "#addEditMaterial button >> text=/Submit/i"

  - id: screenshot
    type: browser.screenshot
    parameters:
      name: "material_added"

metadata:
  author: "mdawson"
  category: "perspective"
  tags: ["materials", "admin"]
```

---

## Tips

- **Credentials** — store secrets in the vault (Credentials page) and reference them with `{{ credential.name.username }}` / `.password`. Never hardcode passwords in YAML.
- **Perspective inputs** — always use `fill_mode: type` for Perspective TextFields. The default `fill` mode bypasses React's event system and values will revert.
- **Optional waits** — use `on_failure: continue` with a short `timeout` to wait for elements that may or may not appear (e.g., banners, modals).
- **Debugging** — add `browser.screenshot` steps before and after any step that might fail to capture state.
- **Step outputs** — `utility.python` captures any `KEY=value` printed line as `{{ step.id.KEY }}`, useful for dynamic values like detected version numbers or file paths.
- **Composability** — break complex workflows into verified sub-playbooks and compose them with `playbook.run`. Keep each sub-playbook focused on one logical operation.
