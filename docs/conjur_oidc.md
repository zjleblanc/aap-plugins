# CyberArk Conjur Secrets Lookup (OIDC)

Uses AAP's **workload identity token** — a platform-issued JWT automatically injected into each job run — to authenticate against Conjur's `authn-jwt` authenticator. No static API keys or external IdP client credentials required.

## How It Works

```mermaid
sequenceDiagram
    participant Job as AAP Job Run
    participant Plugin as conjur_oidc plugin
    participant Conjur as Conjur Server (authn-jwt)

    Job->>Plugin: ① JWT (workload_identity_token, auto-injected)
    Plugin->>Conjur: ② POST /authn-jwt/{svc}/{acct}/authenticate<br/>body: jwt=&lt;workload_identity_token&gt;
    Conjur-->>Plugin: Conjur access token
    Plugin->>Conjur: ③ GET /secrets/{acct}/variable/{path}<br/>header: Token token="..."
    Conjur-->>Plugin: Secret value
    Plugin-->>Job: Secret value
```

## Prerequisites

### AAP Side
- AAP 2.5+ with OIDC provider / workload identity enabled
- The AAP gateway must expose a JWKS endpoint that Conjur can reach

### Conjur Side

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

## Plugin Fields

### Credential Fields (configured once)

| Field | Required | Description |
|-------|----------|-------------|
| Conjur URL | ✅ | Base URL of the Conjur instance |
| Conjur Account | ✅ | Organization account name |
| JWT Authenticator Service ID | ✅ | `authn-jwt` service ID in Conjur (e.g. `aap`) |
| JWT Host ID | | Conjur host to authenticate as (auto-mapped from claims if blank) |
| CA Certificate | | PEM CA cert for Conjur TLS |
| Workload Identity Token | | *Auto-populated by AAP — do not set manually* |

### Metadata Fields (configured per linked credential)

| Field | Required | Description |
|-------|----------|-------------|
| Secret Identifier | ✅ | Variable path in Conjur (e.g. `data/vault/db/prod/password`) |
| Secret Version | | Specific version (blank = latest) |
