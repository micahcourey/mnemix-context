# Changelog

All notable changes to Mnemix Context will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-03-16

### Added
- Tool-neutral update entrypoint in `.ai/update/UPDATE.md` for non-Copilot update flows.

### Changed
- README onboarding and bootstrap guidance were refined to better separate bootstrap, fallback setup, and completion steps.
- Progressive disclosure and Mnemix positioning in the README were simplified and clarified.
- Manual setup was demoted to a fallback/advanced path and condensed.
- Bootstrap completion guidance now explicitly covers PR creation and optional cleanup of the temporary `mnemix-context` workspace.
- Update workflow guidance now supports other tools and no longer assumes a specific team role should run updates.
- Generated `setup` agents were removed so post-bootstrap maintenance centers on the update workflow instead.

## [0.2.0] - 2026-03-15

### Added
- Tool-neutral setup workflow in `setup/SETUP.md` for non-Copilot bootstrap flows.
- Clear setup migration guidance for incorporating existing assistant instructions and skills into generated `.ai/` output.
- Expanded Mnemix memory guidance covering recall rules, checkpoints, durable memory kinds, and adapter-oriented integration.

### Changed
- Mnemix setup and skill documentation now recommend the official `coding_agent_adapter.py` integration model for richer agent memory behavior.

## [0.1.0] - 2026-03-15

### Added
- Initial 0.1.0 release changelog for Mnemix Context.
- New single-repo project context template: `Project_Structure.md`.
- Mnemix branding for the cross-session memory layer.
