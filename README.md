# aap-plugins

Custom credential plugins for **Red Hat Ansible Automation Platform (AAP)** and **AWX**.

Structured to mirror [`ansible/awx-plugins`](https://github.com/ansible/awx-plugins) — uses a `src/` layout with implicit namespace packages so multiple plugins can coexist and new ones can be added easily.

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

Install the plugin into the **same Python environment as AWX/AAP** on all nodes:

```bash
pip install git+https://github.com/zjleblanc/aap-plugins.git
```

Then register and restart:

```bash
awx-manage setup_managed_credential_types
# restart AWX services
```

For containerized deployments, include the package in a custom execution environment or the AWX task container image.

## Development

```bash
git clone https://github.com/zjleblanc/aap-plugins.git
cd aap-plugins
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## License

Apache License 2.0
