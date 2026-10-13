# aap-plugins

Custom credential plugins for **Red Hat Ansible Automation Platform (AAP)** and **AWX**.

Structured to mirror [`ansible/awx-plugins`](https://github.com/ansible/awx-plugins) — uses a `src/` layout with implicit namespace packages so multiple plugins can coexist and new ones can be added easily.

## Plugins

| Entry Point | Module | Description |
|---|---|---|
| `conjur_oidc` | `aap_plugins.credentials.conjur_oidc` | CyberArk Conjur Secrets Lookup via AAP workload identity (OIDC/JWT) |

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

---

## CyberArk Conjur Secrets Lookup (OIDC)

Uses AAP's **workload identity token** — a platform-issued JWT automatically injected into each job run — to authenticate against Conjur's `authn-jwt` authenticator. No static API keys or external IdP client credentials required.

### How It Works

```
┌─────────────┐    ① JWT (auto)    ┌──────────────────┐
│  AAP Job Run │──────────────────▶│  conjur_oidc      │
│              │                   │  plugin            │
└─────────────┘                   └────────┬──────────┘
                                           │
                              ② POST /authn-jwt/{svc}/{acct}/authenticate
                                           │  body: jwt=<workload_identity_token>
                                           ▼
                                  ┌──────────────────┐
                                  │  Conjur Server    │
                                  │  (authn-jwt)      │
                                  └────────┬──────────┘
                                           │
                              ③ GET /secrets/{acct}/variable/{path}
                                           │  header: Token token="..."
                                           ▼
                                  ┌──────────────────┐
                                  │  Secret Value     │
                                  └──────────────────┘
```

### Prerequisites

#### AAP Side
- AAP 2.5+ with OIDC provider / workload identity enabled
- The AAP gateway must expose a JWKS endpoint that Conjur can reach

#### Conjur Side

1. **Enable `authn-jwt` authenticator** in Conjur policy:
   ```yaml
   - !policy
     id: conjur/authn-jwt/aap
     body:
       - !webservice

       - !variable provider-uri
       - !variable token-app-property
       - !variable issuer
       - !variable jwks-uri

       - !group authenticatable
       - !permit
         role: !group authenticatable
         privilege: [ read, authenticate ]
         resource: !webservice
   ```

2. **Set the authenticator variables:**
   ```bash
   conjur variable set -i conjur/authn-jwt/aap/provider-uri \
     -v "https://aap-gateway.example.com/o"
   conjur variable set -i conjur/authn-jwt/aap/jwks-uri \
     -v "https://aap-gateway.example.com/o/jwks"
   conjur variable set -i conjur/authn-jwt/aap/issuer \
     -v "https://aap-gateway.example.com/o"
   conjur variable set -i conjur/authn-jwt/aap/token-app-property \
     -v "sub"
   ```

3. **Create a host identity** matching AAP JWT claims:
   ```yaml
   - !host
     id: aap/automation-jobs
     annotations:
       authn-jwt/aap/sub: "<expected-sub-claim>"

   - !grant
     role: !group conjur/authn-jwt/aap/authenticatable
     member: !host aap/automation-jobs
   ```

4. **Grant the host access** to secrets:
   ```yaml
   - !permit
     role: !host aap/automation-jobs
     privilege: [ read, execute ]
     resource: !variable data/vault/db/prod/password
   ```

### Plugin Fields

#### Credential Fields (configured once)

| Field | Required | Description |
|-------|----------|-------------|
| Conjur URL | ✅ | Base URL of the Conjur instance |
| Conjur Account | ✅ | Organization account name |
| JWT Authenticator Service ID | ✅ | `authn-jwt` service ID in Conjur (e.g. `aap`) |
| JWT Host ID | | Conjur host to authenticate as (auto-mapped from claims if blank) |
| CA Certificate | | PEM CA cert for Conjur TLS |
| Workload Identity Token | | *Auto-populated by AAP — do not set manually* |

#### Metadata Fields (configured per linked credential)

| Field | Required | Description |
|-------|----------|-------------|
| Secret Identifier | ✅ | Variable path in Conjur (e.g. `data/vault/db/prod/password`) |
| Secret Version | | Specific version (blank = latest) |

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
