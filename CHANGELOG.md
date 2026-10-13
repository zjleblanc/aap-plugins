# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 2026-10-12 — Initial release with Conjur OIDC support

### Added
- Initial project structure mirroring `ansible/awx-plugins` conventions.
- CyberArk Conjur Secrets Lookup (OIDC) credential plugin using AAP workload identity (`authn-jwt`).
- Shared `_types.py` for plugin input and metadata schema definitions.
- Automatic entry point registration for AWX plugin discovery.

### Changed
- Refactored documentation structure: moved plugin-specific details to `docs/` folder with snake-case naming and updated top-level `README.md` to link to them.
- Added a Table of Contents to the top-level `README.md`.
