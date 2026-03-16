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

Also inspect any existing AI-assistant inputs already present in the repository, including:

- `AGENTS.md`
- `CLAUDE.md`
- Copilot instructions files
- Cursor/Cline/Windsurf rules files
- existing skill directories or `SKILL.md` files
- any other agent or assistant instruction files

Treat these as migration inputs, not noise.

### 1a. Review provided references thoroughly

If the user placed files in `reference/` or another setup input folder, read them thoroughly before generating output.

Make sure all relevant guidance is captured, especially:

- architecture and integration details
- auth and access-control rules
- domain terminology
- API and schema information
- operational or workflow constraints
- existing agent instructions and skills

### 1b. Detect existing agent instructions and skills

If you find pre-existing agent instruction files or skills during the scan:

1. summarize what was found
2. ask the user whether they want those materials incorporated into the generated `.ai/` output
3. if they say yes, merge the relevant guidance into the generated instructions, agents, or skills

If the user provided pre-existing `AGENTS.md`, `CLAUDE.md`, Copilot instructions, or skill files in `reference/`, ask whether they should be treated as authoritative inputs for the generated `.ai/` output.

### 2. Ask only for missing facts

If anything is unclear, ask targeted questions about:

- project description and organization name
- task tracking system and any workflow notes
- branch naming and commit style
- coverage target
- key domain entities and roles
- sensitive data handled
- optional compliance requirements
- data isolation strategy

Also ask, when applicable:

- whether discovered pre-existing agent instructions should be incorporated into `.ai/`
- whether discovered pre-existing skills should be migrated or merged into `.ai/skills/`

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
- platform-specific native/adapter files for the enabled tools

### 7. Final handoff

Summarize:

- what was auto-detected
- what was provided manually
- which platforms were enabled
- any sections of `toolkit.config.yaml` that still need refinement
- any context files that still need project-specific content

Then guide the user through completion:

- recommend creating a PR for the generated `.ai/` output
- recommend committing `.ai/` and the platform symlinks together
- offer to clean up the temporary `mnemix-context` workspace clone if it is no longer needed

Do not treat generation as the end of the workflow. Close by asking whether the user wants help with PR prep and workspace cleanup.
