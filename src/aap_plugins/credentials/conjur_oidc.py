"""AAP credential plugin — CyberArk Conjur Secrets Lookup (OIDC).

Authenticates to Conjur via its ``authn-jwt`` authenticator using the
workload identity JWT that AAP automatically issues for each job run.
No static API keys or external IdP client credentials are required —
AAP itself acts as the trusted OIDC provider.

Prerequisites — Conjur side:
  1. Enable the ``authn-jwt`` authenticator and configure it to trust
     AAP's OIDC issuer (the AAP gateway JWKS endpoint).
  2. Create a Conjur host identity whose annotations match the JWT
     claims AAP issues (e.g. ``sub``, ``iss``, ``organization_id``).
  3. Grant the host ``read``/``execute`` on the required variables.

Flow:
  1. AAP injects a short-lived workload identity JWT into the plugin
     (``workload_identity_token`` — populated automatically).
  2. The plugin POSTs the JWT to Conjur's
     ``/authn-jwt/{service_id}/{account}/authenticate`` endpoint
     and receives a Conjur access token.
  3. The access token retrieves the requested secret from
     ``/secrets/{account}/variable/{path}``.

References:
  - Conjur authn-jwt docs:
    https://docs.conjur.org/Latest/en/Content/Integrations/authn-jwt.htm
  - AWX credential plugin interface:
    https://github.com/ansible/awx-plugins
"""

from __future__ import annotations

import base64
import logging
from urllib.parse import quote, urljoin

import requests

from awx_plugins.credentials.plugin import (
    CertFiles,
    CredentialPlugin,
    raise_for_status,
)

from . import _types

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Input schema
# ---------------------------------------------------------------------------

conjur_oidc_inputs: _types.PluginInputs = {
    'fields': [
        {
            'id': 'conjur_url',
            'label': 'Conjur URL',
            'type': 'string',
            'format': 'url',
            'help_text': (
                'Base URL of the Conjur instance '
                '(e.g. https://conjur.example.com).'
            ),
        },
        {
            'id': 'account',
            'label': 'Conjur Account',
            'type': 'string',
            'help_text': 'The Conjur organization account name.',
        },
        {
            'id': 'service_id',
            'label': 'JWT Authenticator Service ID',
            'type': 'string',
            'help_text': (
                'The authn-jwt service identifier configured in Conjur '
                '(e.g. "aap", "aap-prod"). Must match the authenticator '
                'enabled in Conjur policy.'
            ),
        },
        {
            'id': 'jwt_host_id',
            'label': 'JWT Host ID',
            'type': 'string',
            'help_text': (
                'The Conjur host identity to authenticate as '
                '(e.g. "host/aap/automation-jobs"). If left blank, '
                'Conjur will map the JWT claims to a host identity '
                'using the configured token-app-property.'
            ),
        },
        {
            'id': 'cacert',
            'label': 'CA Certificate',
            'type': 'string',
            'multiline': True,
            'help_text': (
                'PEM-encoded CA certificate for verifying the Conjur '
                'server TLS certificate. Leave blank to use system CAs.'
            ),
        },
        {
            'id': 'workload_identity_token',
            'label': 'Workload Identity Token',
            'type': 'string',
            'secret': True,
            'internal': True,
            'help_text': (
                'JWT token for workload identity authentication. '
                'Automatically populated by the AAP platform.'
            ),
        },
    ],
    'metadata': [
        {
            'id': 'secret_path',
            'label': 'Secret Identifier',
            'type': 'string',
            'help_text': (
                'Variable path in Conjur to retrieve '
                '(e.g. "data/vault/db/prod/password").'
            ),
        },
        {
            'id': 'secret_version',
            'label': 'Secret Version',
            'type': 'string',
            'help_text': (
                'Specific secret version to retrieve. '
                'Leave blank for the latest version.'
            ),
        },
    ],
    'required': [
        'conjur_url',
        'account',
        'service_id',
    ],
}


# ---------------------------------------------------------------------------
# Conjur authn-jwt helpers
# ---------------------------------------------------------------------------

def _conjur_authn_jwt(
    conjur_url: str,
    account: str,
    service_id: str,
    jwt: str,
    host_id: str | None,
    cacert: str | None,
) -> str:
    """Authenticate to Conjur via ``authn-jwt`` using a workload identity JWT.

    ``POST /authn-jwt/{service_id}/{account}/authenticate``
    Body: ``jwt={token}[&id={host_id}]``
    """
    account_enc = quote(account, safe='')
    service_enc = quote(service_id, safe='')

    auth_url = urljoin(
        conjur_url.rstrip('/') + '/',
        '/'.join([
            'authn-jwt', service_enc, account_enc, 'authenticate',
        ]),
    )

    payload = f'jwt={jwt}'
    if host_id:
        payload += f'&id={quote(host_id, safe="")}'

    with CertFiles(cacert) as cert:
        verify = cert if cert else True
        resp = requests.post(
            auth_url,
            data=payload,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            verify=verify,
            timeout=30,
            allow_redirects=False,
        )
    raise_for_status(resp)
    return resp.content.decode('utf-8')


def _conjur_retrieve_secret(
    conjur_url: str,
    account: str,
    access_token: str,
    secret_path: str,
    secret_version: str | None,
    cacert: str | None,
) -> str:
    """Retrieve a secret from Conjur's secrets API."""
    account_enc = quote(account, safe='')
    path_enc = quote(secret_path, safe='')

    secret_url = urljoin(
        conjur_url.rstrip('/') + '/',
        '/'.join(['secrets', account_enc, 'variable', path_enc]),
    )
    if secret_version:
        secret_url += f'?version={quote(secret_version, safe="")}'

    token_b64 = base64.b64encode(
        access_token.encode('utf-8'),
    ).decode('utf-8')

    with CertFiles(cacert) as cert:
        verify = cert if cert else True
        resp = requests.get(
            secret_url,
            headers={'Authorization': f'Token token="{token_b64}"'},
            verify=verify,
            timeout=30,
            allow_redirects=False,
        )
    raise_for_status(resp)
    return resp.text


# ---------------------------------------------------------------------------
# Backend callable
# ---------------------------------------------------------------------------

def conjur_oidc_backend(**kwargs) -> str:
    """Look up a secret in Conjur using AAP workload identity (authn-jwt).

    Called by AWX with all values from ``fields`` and ``metadata``
    merged into ``kwargs``.
    """
    conjur_url: str = kwargs['conjur_url']
    account: str = kwargs['account']
    service_id: str = kwargs['service_id']
    jwt_host_id: str | None = kwargs.get('jwt_host_id')
    cacert: str | None = kwargs.get('cacert')
    secret_path: str = kwargs['secret_path']
    secret_version: str | None = kwargs.get('secret_version')

    workload_identity_token: str | None = kwargs.get(
        'workload_identity_token',
    )
    if not workload_identity_token:
        raise ValueError(
            'No workload identity token was provided. '
            'Ensure the AAP platform is configured as an OIDC provider '
            'and that workload identity is enabled for this credential type.',
        )

    logger.debug(
        'conjur-oidc: authenticating to account=%s service_id=%s',
        account,
        service_id,
    )

    access_token = _conjur_authn_jwt(
        conjur_url,
        account,
        service_id,
        workload_identity_token,
        jwt_host_id,
        cacert,
    )

    return _conjur_retrieve_secret(
        conjur_url,
        account,
        access_token,
        secret_path,
        secret_version,
        cacert,
    )


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

conjur_oidc_plugin = CredentialPlugin(
    name='CyberArk Conjur Secrets Lookup (OIDC)',
    inputs=conjur_oidc_inputs,
    backend=conjur_oidc_backend,
    plugin_description=(
        'Retrieve secrets from CyberArk Conjur using AAP workload identity '
        '(authn-jwt). AAP issues a short-lived JWT for each job run, which '
        'Conjur validates against the platform OIDC provider — no static '
        'API keys or client secrets required.'
    ),
)
