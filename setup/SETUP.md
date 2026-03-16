# Mnemix Context Setup Workflow

Use this file with any coding assistant when you want help configuring **Mnemix Context** for a repository and you are not using the GitHub Copilot bootstrap agent.

## Goal

Set up Mnemix Context for the current repository by:

1. Discovering the stack and project structure
2. Interviewing for anything not detectable from code
3. Updating `toolkit.config.yaml`
4. Running the generator
5. Verifying the progressive-disclosure output in `.ai/`

## Workflow

### 1. Discover the codebase

Inspect the repository to infer:

- project name
- frontend and backend frameworks
- runtime/language versions
- database and cloud usage
- auth patterns
- testing frameworks
- branch/test conventions
- important entry points and scripts

### 2. Ask only for missing facts

If anything is unclear, ask targeted questions about:

- project description and organization name
- branch naming and commit style
- coverage target
- key domain entities and roles
- sensitive data handled
- optional compliance requirements
- data isolation strategy

### 3. Configure platforms

Ask which outputs should be enabled:

- universal: `AGENTS.md`, skills, context files
- native: Copilot, OpenCode, Codex
- adapters: Cursor, Claude Code, Cline, Windsurf

### 4. Update the config

Edit `toolkit.config.yaml` with the discovered and confirmed values.

### 5. Generate toolkit output

Run:

```bash
python3 setup/generate.py --config toolkit.config.yaml
```

### 6. Verify the result

Check that generation produced:

- `.ai/AGENTS.md`
- `.ai/instructions/`
- `.ai/context/`
- `.ai/skills/`
- `.ai/SETUP.md`
- platform-specific native/adapter files for the enabled tools

### 7. Final handoff

Summarize:

- what was auto-detected
- what was provided manually
- which platforms were enabled
- any sections of `toolkit.config.yaml` that still need refinement
- any context files that still need project-specific content
