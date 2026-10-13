# aap-plugins

Custom credential plugins for **Red Hat Ansible Automation Platform (AAP)** and **AWX**.

Structured to mirror [`ansible/awx-plugins`](https://github.com/ansible/awx-plugins) — uses a `src/` layout with implicit namespace packages so multiple plugins can coexist and new ones can be added easily.

## Table of Contents

- [Plugins](#plugins)
- [Architecture](#architecture)
- [Adding a New Plugin](#adding-a-new-plugin)
- [Installation](#installation)
  - [Determining the Right Environment](#determining-the-right-environment)
  - [RHEL — Containerized AAP (installer-managed, Podman)](#rhel--containerized-aap-installer-managed-podman)
  - [OpenShift — AAP Operator (OCP)](#openshift--aap-operator-ocp)
- [Development](#development)
- [License](#license)

## Plugins

| Entry Point | Module | Description |
|---|---|---|
| [`conjur_oidc`](docs/conjur_oidc.md) | `aap_plugins.credentials.conjur_oidc` | CyberArk Conjur Secrets Lookup via AAP workload identity (OIDC/JWT) |

## Architecture

```
src/
└── aap_plugins/                    # namespace package (no __init__.py)
    └── credentials/                # namespace package (no __init__.py)
        ├── _types.py               # shared TypedDict definitions
        ├── conjur_oidc.py          # Conjur authn-jwt plugin
        └── <future_plugin>.py      # add new plugins here
```

Plugins register via the `awx_plugins.credentials` [entry-point group](https://packaging.python.org/en/latest/specifications/entry-points/) — the same group AWX scans at startup:

```toml
[project.entry-points."awx_plugins.credentials"]
conjur_oidc = "aap_plugins.credentials.conjur_oidc:conjur_oidc_plugin"
```

## Adding a New Plugin

1. Create `src/aap_plugins/credentials/<name>.py`
2. Define a `CredentialPlugin` instance (import from `awx_plugins.credentials.plugin`)
3. Register the entry point in `pyproject.toml`
4. Add any new dependencies to `[project.dependencies]`

Each plugin module should export a single `CredentialPlugin` named tuple with:
- **`name`** — display name shown in AAP UI
- **`inputs`** — field and metadata schema (`PluginInputs`)
- **`backend`** — callable that receives all field + metadata values and returns the secret
- **`plugin_description`** *(optional)* — longer description

## Installation

Credential plugins must be installed into the **same Python environment used by the AWX/AAP task process** on every controller node. The correct approach differs between RHEL-based and OpenShift deployments.

### Determining the Right Environment

On a running controller node, confirm which Python and `awx-manage` are in use:

```bash
# Find the active awx-manage interpreter
head -1 $(which awx-manage)

# Verify the site-packages path where plugins will be discovered
awx-manage shell -c "import awx_plugins; print(awx_plugins.__file__)"
```

The `pip` invocation in each section below targets that same interpreter.

---

### RHEL — Containerized AAP (installer-managed, Podman)

Containerized AAP on RHEL is deployed by the AAP setup bundle and runs as Podman containers under the `awx` system user. The task container (`automation-controller-task`) is what loads credential plugins.

#### Runtime injection (all controller nodes)

Run the following on **each** controller node. The setup bundle installer can automate this via a post-install playbook if needed.

```bash
# 1. Identify the running task container (runs as the awx user)
TASK_CTR=$(sudo -u awx podman ps --filter name=automation-controller-task --format '{{.Names}}' | head -1)

# 2. Install the plugin into the container's site-packages
sudo -u awx podman exec "$TASK_CTR" pip install git+https://github.com/zjleblanc/aap-plugins.git

# 3. Register the new credential type
sudo -u awx podman exec "$TASK_CTR" awx-manage setup_managed_credential_types

# 4. Restart the task container to reload entry points
sudo -u awx podman restart "$TASK_CTR"
```

> **Note:** Runtime injection does not survive a container image update or re-run of the AAP installer. For a durable solution, bake the package into a custom task image (see below).

#### Baking into a custom task image

Create a `Containerfile` that layers on top of the official image:

```dockerfile
FROM registry.redhat.io/ansible-automation-platform-25/controller-rhel9:latest

USER root
RUN pip install git+https://github.com/zjleblanc/aap-plugins.git
USER 1000
```

Build and push to your internal registry, then set `automation_controller_image` in your AAP installer inventory to the new image and re-run the setup script to roll it out:

```bash
cd /path/to/aap-setup-bundle
./setup.sh -e automation_controller_image=registry.example.com/aap/controller-custom:latest
```

Once the containers are back up, register the credential type:

```bash
sudo -u awx podman exec "$TASK_CTR" awx-manage setup_managed_credential_types
```

---

### OpenShift — AAP Operator (OCP)

On OpenShift, the controller pods are managed by the AAP Operator. The recommended approach is a **custom init container** or a **custom task image** via the `AutomationController` CR.

#### Custom task image (recommended)

1. Build and push the image (same `Containerfile` as above) to a registry accessible from OCP.

2. Patch the `AutomationController` CR to reference it:

```yaml
apiVersion: automationcontroller.ansible.com/v1beta1
kind: AutomationController
metadata:
  name: automation-controller
  namespace: aap
spec:
  image: registry.example.com/aap/controller-custom:latest
  image_pull_policy: Always
```

Apply the patch:

```bash
oc patch automationcontroller automation-controller -n aap \
  --type merge \
  --patch-file patch.yaml
```

The operator will roll the controller pods automatically. Once they are `Running`, register the credential type from any controller pod:

```bash
oc exec -n aap deployment/automation-controller-task -- \
  awx-manage setup_managed_credential_types
```

#### Runtime injection via `oc exec` (dev/testing only)

```bash
# Install into the running task pod (lost on pod restart)
oc exec -n aap deployment/automation-controller-task -- \
  pip install git+https://github.com/zjleblanc/aap-plugins.git

# Register the credential type
oc exec -n aap deployment/automation-controller-task -- \
  awx-manage setup_managed_credential_types

# Restart the deployment to reload entry points
oc rollout restart -n aap deployment/automation-controller-task
oc rollout status  -n aap deployment/automation-controller-task
```

## Development

```bash
git clone https://github.com/zjleblanc/aap-plugins.git
cd aap-plugins
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## License

Apache License 2.0
