# Changelog

All notable changes to Mnemix Context will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-03-15

### Added
- Tool-neutral setup workflow in `setup/SETUP.md` and generated `.ai/SETUP.md`.
- Native `setup` agents for Copilot, OpenCode, and Codex generated from a shared setup playbook.
- Clear setup migration guidance for incorporating existing assistant instructions and skills into generated `.ai/` output.
- Expanded Mnemix memory guidance covering recall rules, checkpoints, durable memory kinds, and adapter-oriented integration.

### Changed
- Copilot instructions now advertise the `setup` agent alongside the existing role agents.
- Mnemix setup and skill documentation now recommend the official `coding_agent_adapter.py` integration model for richer agent memory behavior.

## [0.1.0] - 2026-03-15

### Added
- Initial 0.1.0 release changelog for Mnemix Context.
- New single-repo project context template: `Project_Structure.md`.
- Mnemix branding for the cross-session memory layer.
