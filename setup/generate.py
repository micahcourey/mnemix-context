#!/usr/bin/env python3
"""
Mnemix Context - Template Generator
===================================
Reads toolkit.config.yaml and renders all template files into the .ai/ directory.
After generation, run `.ai/setup-links.sh` to create platform symlinks.

Usage:
    python3 setup/generate.py                        # Uses toolkit.config.yaml
    python3 setup/generate.py --config my.yaml       # Uses custom config
    python3 setup/generate.py --dry-run              # Preview without writing
    python3 setup/generate.py --validate             # Validate config only
    python3 setup/generate.py --target copilot,cursor # Only these platforms
    python3 setup/generate.py --target all            # All platforms regardless of config
    python3 setup/generate.py --upgrade              # Upgrade from new toolkit templates
    python3 setup/generate.py --upgrade --dry-run    # Preview upgrade without writing
    python3 setup/generate.py --upgrade --non-interactive  # Auto-accept safe changes
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# All supported platform keys
ALL_PLATFORMS = {"agents_md", "skills", "context_files", "copilot", "opencode", "codex", "cursor", "claude", "cline", "windsurf"}

# Universal platform keys (open standards)
UNIVERSAL_PLATFORMS = {"agents_md", "skills", "context_files"}

# Platform-specific adapter keys
ADAPTER_PLATFORMS = {"cursor", "claude", "cline", "windsurf"}

REQUIRED_FIELDS = [
    "project.name",
    "project.description",
    "tech_stack.frontend.framework",
    "tech_stack.backend.framework",
]

# Adapter file → platform mapping and output path (inside .ai/)
ADAPTER_OUTPUT_MAP = {
    "CLAUDE.md.tmpl": ("claude", ".ai/CLAUDE.md"),
    "cursor-rules.mdc.tmpl": ("cursor", ".ai/cursor-rules.mdc"),
    "clinerules.md.tmpl": ("cline", ".ai/clinerules"),
    "windsurfrules.md.tmpl": ("windsurf", ".ai/windsurfrules"),
}

# File categories for upgrade manifest
# Determines how each generated file is treated during --upgrade
FILE_CATEGORIES = {
    "script": "Auto-regenerate (no user content)",
    "update-meta": "Auto-regenerate (toolkit-internal docs)",
    "template-output": "Diff review if user modified",
    "context-stub": "Never touch (populated by bootstrap/user)",
}




# ---------------------------------------------------------------------------
# Config loader & validator
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Version & hashing utilities
# ---------------------------------------------------------------------------

def get_toolkit_version(root: Path) -> Dict[str, Any]:
    """Read toolkit version from VERSION file and git commit hash."""
    version_file = root / "VERSION"
    version = version_file.read_text().strip() if version_file.exists() else "0.0.0"

    commit = None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=root,
        )
        if result.returncode == 0:
            commit = result.stdout.strip()
    except FileNotFoundError:
        pass

    return {"version": version, "commit": commit}


def compute_file_hash(filepath: Path) -> str:
    """SHA-256 hash of a file's contents (first 16 hex chars)."""
    return "sha256:" + hashlib.sha256(filepath.read_bytes()).hexdigest()[:16]


def compute_content_hash(content: str) -> str:
    """SHA-256 hash of string content (first 16 hex chars)."""
    return "sha256:" + hashlib.sha256(content.encode()).hexdigest()[:16]


def classify_output_file(output_rel: str) -> str:
    """Classify a generated file into an upgrade category."""
    # Context stubs — never auto-updated
    if output_rel.startswith(".ai/context/"):
        return "context-stub"

    # Scripts — always safe to regenerate
    if output_rel.endswith(".py") or output_rel.endswith(".sh"):
        return "script"

    # Update agent and its README — toolkit-internal
    if output_rel.startswith(".ai/update/"):
        return "update-meta"

    # Everything else (AGENTS.md, instructions, agents, skills, adapters)
    return "template-output"


def compute_config_hash(config_path: Path) -> str:
    """Hash the config file for drift detection."""
    if config_path.exists():
        return compute_file_hash(config_path)
    return "sha256:0000000000000000"


def write_manifest(
    manifest_entries: Dict[str, Dict],
    toolkit_version: Dict[str, Any],
    config_hash: str,
    output_root: Path,
    dry_run: bool = False,
) -> None:
    """Write the toolkit manifest for upgrade tracking."""
    manifest = {
        "toolkit_version": toolkit_version["version"],
        "toolkit_commit": toolkit_version["commit"],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config_hash": config_hash,
        "files": manifest_entries,
    }

    manifest_path = output_root / ".ai" / "update" / ".toolkit-manifest.json"

    if dry_run:
        print(f"  📋 .ai/update/.toolkit-manifest.json (manifest)")
        return

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print(f"  📋 .ai/update/.toolkit-manifest.json (manifest — {len(manifest_entries)} files tracked)")


# ---------------------------------------------------------------------------
# Config loader & validator
# ---------------------------------------------------------------------------

def load_config(config_path: str) -> Dict[str, Any]:
    """Load and parse the YAML config file."""
    path = Path(config_path)
    if not path.exists():
        print(f"❌ Config file not found: {config_path}")
        print("   Run: cp setup/examples/angular-node-aws.yaml toolkit.config.yaml")
        sys.exit(1)

    with open(path, "r") as f:
        config = yaml.safe_load(f)

    if not config:
        print(f"❌ Config file is empty: {config_path}")
        sys.exit(1)

    return config


def get_nested(data: Dict, path: str, default: Any = "") -> Any:
    """Get a nested value from a dict using dot notation."""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current if current is not None else default


def validate_config(config: Dict[str, Any]) -> list:
    """Validate required fields are populated. Returns list of errors."""
    errors = []
    for field in REQUIRED_FIELDS:
        value = get_nested(config, field)
        if not value or (isinstance(value, str) and not value.strip()):
            errors.append(f"Missing required field: {field}")
    return errors


def get_enabled_platforms(config: Dict[str, Any], target_override: Optional[str] = None) -> Set[str]:
    """Determine which platforms to generate for."""
    if target_override == "all":
        return ALL_PLATFORMS.copy()

    if target_override:
        # Parse comma-separated target list
        requested = {t.strip() for t in target_override.split(",")}

        # Validate platform names
        invalid = requested - ALL_PLATFORMS
        if invalid:
            print(f"⚠️  Unknown platforms: {', '.join(invalid)}")
            print(f"   Valid platforms: {', '.join(sorted(ALL_PLATFORMS))}")

        # Always include universal platforms when any platform-specific one is requested
        enabled = requested & ALL_PLATFORMS
        if enabled & (ALL_PLATFORMS - UNIVERSAL_PLATFORMS):
            enabled |= UNIVERSAL_PLATFORMS
        return enabled

    # Use config values
    platforms_config = config.get("platforms", {})
    enabled = set()
    for platform in ALL_PLATFORMS:
        if platforms_config.get(platform, platform in UNIVERSAL_PLATFORMS):
            enabled.add(platform)

    return enabled


# ---------------------------------------------------------------------------
# Template context builder
# ---------------------------------------------------------------------------

def build_context(config: Dict[str, Any]) -> Dict[str, str]:
    """
    Flatten config into a dict of {{PLACEHOLDER}} -> value mappings.
    Uses double-brace syntax: {{project.name}}, {{tech_stack.frontend.framework}}
    """
    context = {}

    # --- Project ---
    context["project.name"] = get_nested(config, "project.name")
    context["project.full_name"] = get_nested(config, "project.full_name", context["project.name"])
    context["project.description"] = get_nested(config, "project.description")
    context["project.org_name"] = get_nested(config, "project.org_name")
    context["project.repo_url"] = get_nested(config, "project.repo_url")
    context["project.jira_key"] = get_nested(config, "project.jira_key")

    # --- Tech Stack ---
    context["tech.frontend.framework"] = get_nested(config, "tech_stack.frontend.framework")
    context["tech.frontend.language"] = get_nested(config, "tech_stack.frontend.language")
    context["tech.frontend.ui_library"] = get_nested(config, "tech_stack.frontend.ui_library")
    context["tech.frontend.state_mgmt"] = get_nested(config, "tech_stack.frontend.state_management")
    context["tech.frontend.testing"] = get_nested(config, "tech_stack.frontend.testing")
    context["tech.frontend.component_prefix"] = get_nested(config, "tech_stack.frontend.component_prefix")
    context["tech.backend.framework"] = get_nested(config, "tech_stack.backend.framework")
    context["tech.backend.language"] = get_nested(config, "tech_stack.backend.language")
    context["tech.backend.runtime"] = get_nested(config, "tech_stack.backend.runtime")
    context["tech.backend.testing"] = get_nested(config, "tech_stack.backend.testing")
    context["tech.backend.api_style"] = get_nested(config, "tech_stack.backend.api_style", "REST")
    context["tech.cloud.provider"] = get_nested(config, "tech_stack.cloud.provider")
    context["tech.cloud.compute"] = get_nested(config, "tech_stack.cloud.compute")
    context["tech.auth.provider"] = get_nested(config, "tech_stack.auth.provider")
    context["tech.auth.strategy"] = get_nested(config, "tech_stack.auth.strategy")
    context["tech.auth.token_type"] = get_nested(config, "tech_stack.auth.token_type")
    context["tech.cicd.platform"] = get_nested(config, "tech_stack.cicd.platform")
    context["tech.cicd.secondary"] = get_nested(config, "tech_stack.cicd.secondary")

    # Cloud services as comma-separated
    cloud_services = get_nested(config, "tech_stack.cloud.key_services", [])
    context["tech.cloud.services"] = ", ".join(cloud_services) if cloud_services else ""

    # Databases as formatted list
    databases = get_nested(config, "tech_stack.databases", [])
    db_names = []
    primary_type = ""
    for db in databases:
        if isinstance(db, dict):
            db_names.append(db.get("name", ""))
            if not primary_type:
                primary_type = db.get("name", "")
        elif isinstance(db, str):
            db_names.append(db)
            if not primary_type:
                primary_type = db
    context["tech.databases"] = ", ".join(db_names)
    context["tech.databases.list"] = "\n".join(f"- {d}" for d in db_names)

    # Testing-specific variables
    context["tech.testing.e2e_framework"] = get_nested(config, "tech_stack.testing.e2e_framework",
                                                        get_nested(config, "tech_stack.frontend.e2e_framework", ""))

    # --- tech_stack.* aliases (templates may use either tech.* or tech_stack.*) ---
    context["tech_stack.frontend.framework"] = context["tech.frontend.framework"]
    context["tech_stack.backend.framework"] = context["tech.backend.framework"]
    context["tech_stack.backend.language"] = context["tech.backend.language"]
    context["tech_stack.backend.runtime"] = context["tech.backend.runtime"]
    context["tech_stack.auth.provider"] = context["tech.auth.provider"]
    context["tech_stack.testing.e2e_framework"] = context["tech.testing.e2e_framework"]
    context["tech_stack.databases.primary_type"] = primary_type

    # --- Tech Stack Table (for instructions files) ---
    fe = config.get("tech_stack", {}).get("frontend", {})
    be = config.get("tech_stack", {}).get("backend", {})
    cl = config.get("tech_stack", {}).get("cloud", {})
    au = config.get("tech_stack", {}).get("auth", {})
    ci = config.get("tech_stack", {}).get("cicd", {})

    fe_techs = ", ".join(filter(None, [
        fe.get("framework"), fe.get("language"),
        fe.get("state_management"), fe.get("ui_library")
    ]))
    be_techs = ", ".join(filter(None, [
        be.get("runtime"), be.get("framework"),
        be.get("language")
    ]))
    db_techs = ", ".join(db_names)
    cl_techs = ", ".join(filter(None, [
        cl.get("provider"), cl.get("compute")
    ]))
    if cloud_services:
        cl_techs += f" ({', '.join(cloud_services)})"
    au_techs = ", ".join(filter(None, [
        au.get("provider"), au.get("strategy")
    ]))
    test_techs = ", ".join(filter(None, [
        fe.get("testing"), f"{be.get('testing', '')} (backend)"
    ]))
    ci_techs = ", ".join(filter(None, [
        ci.get("platform"), ci.get("secondary")
    ]))

    context["tech.stack_table"] = f"""| Layer | Technologies |
|-------|--------------|
| **Frontend** | {fe_techs} |
| **Backend** | {be_techs} |
| **Databases** | {db_techs} |
| **Cloud** | {cl_techs} |
| **Auth** | {au_techs} |
| **Testing** | {test_techs} |
| **CI/CD** | {ci_techs} |"""

    # --- Patterns ---
    context["patterns.auth.description"] = get_nested(config, "patterns.auth_middleware.description")
    context["patterns.auth.backend_chain"] = get_nested(config, "patterns.auth_middleware.backend_chain", "").strip()
    context["patterns.auth.frontend_check"] = get_nested(config, "patterns.auth_middleware.frontend_check", "").strip()
    context["patterns.auth.authenticate"] = get_nested(config, "patterns.auth_middleware.middleware_names.authenticate")
    context["patterns.auth.authorize"] = get_nested(config, "patterns.auth_middleware.middleware_names.authorize")
    context["patterns.auth.audit"] = get_nested(config, "patterns.auth_middleware.middleware_names.audit")

    # Derive auth enabled flag from whether auth_middleware config exists
    auth_mw_config = get_nested(config, "patterns.auth_middleware", {})
    auth_enabled = str(bool(auth_mw_config and isinstance(auth_mw_config, dict))).lower()
    context["patterns.auth.enabled"] = auth_enabled

    # --- patterns.auth_middleware.* aliases (templates may use either prefix) ---
    context["patterns.auth_middleware.enabled"] = auth_enabled
    context["patterns.auth_middleware.backend_chain"] = context["patterns.auth.backend_chain"]
    context["patterns.auth_middleware.frontend_check"] = context["patterns.auth.frontend_check"]
    context["patterns.auth_middleware.type"] = get_nested(config, "patterns.auth_middleware.type",
                                                          context["patterns.auth.description"])
    context["patterns.error_format"] = get_nested(config, "patterns.error_format", "").strip()
    context["patterns.isolation.enabled"] = str(get_nested(config, "patterns.data_isolation.enabled", False)).lower()
    context["patterns.isolation.strategy"] = get_nested(config, "patterns.data_isolation.strategy")
    context["patterns.isolation.field"] = get_nested(config, "patterns.data_isolation.isolation_field")
    context["patterns.isolation.description"] = get_nested(config, "patterns.data_isolation.description")
    context["patterns.db.table_naming"] = get_nested(config, "patterns.database_conventions.table_naming")
    context["patterns.db.migration_tool"] = get_nested(config, "patterns.database_conventions.migration_tool")
    context["patterns.db.soft_delete"] = str(get_nested(config, "patterns.database_conventions.soft_delete", False)).lower()
    context["patterns.db.soft_delete_col"] = get_nested(config, "patterns.database_conventions.soft_delete_column")

    audit_cols = get_nested(config, "patterns.database_conventions.audit_columns", [])
    context["patterns.db.audit_columns"] = ", ".join(audit_cols) if audit_cols else ""

    # --- Domain ---
    context["domain.industry"] = get_nested(config, "domain.industry")

    sensitive = get_nested(config, "domain.sensitive_data_types", [])
    context["domain.sensitive_data"] = ", ".join(sensitive) if sensitive else "N/A"

    compliance = get_nested(config, "domain.compliance_frameworks", [])
    context["domain.compliance"] = ", ".join(compliance) if compliance else "N/A"

    entities = get_nested(config, "domain.key_entities", [])
    context["domain.entities"] = ", ".join(entities) if entities else ""

    models = get_nested(config, "domain.business_models", [])
    context["domain.models"] = ", ".join(models) if models else ""
    context["domain.model_variations"] = context["domain.models"]  # alias

    roles = get_nested(config, "domain.user_roles", [])
    context["domain.roles"] = ", ".join(roles) if roles else ""

    role_desc = get_nested(config, "domain.role_descriptions", {})
    if role_desc:
        role_table = "| Role | Description |\n|------|-------------|\n"
        for role, desc in role_desc.items():
            role_table += f"| **{role}** | {desc} |\n"
        context["domain.roles_table"] = role_table
    else:
        context["domain.roles_table"] = "*(Define roles in toolkit.config.yaml → domain.role_descriptions)*"

    # --- Conventions ---
    context["conventions.branch_pattern"] = get_nested(config, "conventions.branch_pattern")
    context["conventions.commit_format"] = get_nested(config, "conventions.commit_format", "conventional")
    context["conventions.default_branch"] = get_nested(config, "conventions.default_branch", "main")
    context["conventions.coverage_target"] = str(get_nested(config, "conventions.test_coverage_target", 80))
    context["conventions.max_fn_lines"] = str(get_nested(config, "conventions.max_function_lines", 30))

    naming = get_nested(config, "conventions.naming", {})
    context["conventions.naming.services"] = naming.get("services", "") if isinstance(naming, dict) else ""
    context["conventions.naming.components"] = naming.get("components", "") if isinstance(naming, dict) else ""

    # --- Mnemix ---
    mnemix = config.get("mnemix", config.get("temporal", {}))
    features = config.get("features", {})
    integrations = features.get("integrations", {})
    mnemix_enabled = str(
        integrations.get("mnemix", integrations.get("temporal_plane", False))
    ).lower()
    context["mnemix.enabled"] = mnemix_enabled
    context["mnemix.store_path"] = mnemix.get("store_path", ".mnemix")
    context["mnemix.session_strategy"] = mnemix.get("session_strategy", "branch")
    context["mnemix.binary"] = mnemix.get("binary", "mnemix")
    context["mnemix.scope"] = mnemix.get("scope", f"repo:{context['project.name']}")

    # Backward-compatible aliases for older templates.
    context["temporal.enabled"] = context["mnemix.enabled"]
    context["temporal.store_path"] = context["mnemix.store_path"]
    context["temporal.session_strategy"] = context["mnemix.session_strategy"]

    return context


# ---------------------------------------------------------------------------
# Template renderer
# ---------------------------------------------------------------------------

def _resolve_include_path(include_ref: str, templates_dir: Path) -> Path:
    """Resolve include path safely under templates_dir."""
    include_path = (templates_dir / include_ref.strip()).resolve()
    templates_root = templates_dir.resolve()

    try:
        include_path.relative_to(templates_root)
    except ValueError as exc:
        raise ValueError(f"Include path escapes templates directory: {include_ref}") from exc

    if not include_path.exists() or not include_path.is_file():
        raise ValueError(f"Include file not found: {include_ref}")

    return include_path


def _process_includes(
    template_content: str,
    templates_dir: Optional[Path],
    max_depth: int = 20,
) -> str:
    """Process include directives like {{#include shared/personas/engineer.md.tmpl}}.

    Also handles {{#include-commented path}} which prefixes every included line
    with '# ' so the content is valid as TOML/YAML/shell comments.
    """
    if templates_dir is None:
        return template_content

    result = template_content

    # First pass: process {{#include-commented path}} — prefix each line with "# "
    # NOTE: This reads raw content and comment-prefixes it, but does NOT prevent
    # the second pass from expanding any {{#include}} directives that appear in
    # the commented output. Those nested includes will still be expanded, but
    # remain within comment-prefixed lines so the output stays valid as comments.
    # This is acceptable because shared persona templates do not use nested includes.
    commented_pattern = re.compile(r"\{\{#include-commented\s+([^}]+)\}\}")
    for _ in range(max_depth):
        match = commented_pattern.search(result)
        if not match:
            break
        include_ref = match.group(1).strip()
        include_path = _resolve_include_path(include_ref, templates_dir)
        raw = include_path.read_text()
        commented = "\n".join(
            ("# " + line) if line.strip() else "#"
            for line in raw.splitlines()
        )
        result = result.replace(match.group(0), commented, 1)

    # Second pass: process regular {{#include path}}
    include_pattern = re.compile(r"\{\{#include\s+([^}]+)\}\}")
    for _ in range(max_depth):
        match = include_pattern.search(result)
        if not match:
            return result

        include_ref = match.group(1).strip()
        include_path = _resolve_include_path(include_ref, templates_dir)
        include_content = include_path.read_text()

        result = result.replace(match.group(0), include_content, 1)

    raise ValueError(f"Template include expansion limit exceeded (max {max_depth} iterations)")


def render_template(
    template_content: str,
    context: Dict[str, str],
    templates_dir: Optional[Path] = None,
) -> str:
    """Replace all {{placeholder}} tokens with values from context."""
    result = _process_includes(template_content, templates_dir)

    # Replace all {{key}} placeholders
    def replacer(match):
        key = match.group(1).strip()
        return context.get(key, match.group(0))  # Keep original if no match

    result = re.sub(r"\{\{([^}#/]+)\}\}", replacer, result)

    # Process conditional blocks: {{#if key}}...{{/if}}
    # Handle nesting by processing innermost blocks first and repeating
    def process_if(match):
        key = match.group(1).strip()
        content = match.group(2)
        value = context.get(key, "")
        if value and value not in ("", "false", "False", "N/A", "0"):
            return content
        return ""

    # Repeat until no more {{#if}} blocks (handles nested conditionals)
    if_pattern = re.compile(
        r"\{\{#if\s+([^}]+)\}\}((?:(?!\{\{#if\s)(?!\{\{/if\}\}).)*?)\{\{/if\}\}",
        re.DOTALL,
    )
    while if_pattern.search(result):
        result = if_pattern.sub(process_if, result)

    # Process {{#unless key}}...{{/unless}} (same nesting-aware approach)
    def process_unless(match):
        key = match.group(1).strip()
        content = match.group(2)
        value = context.get(key, "")
        if not value or value in ("", "false", "False", "N/A", "0"):
            return content
        return ""

    unless_pattern = re.compile(
        r"\{\{#unless\s+([^}]+)\}\}((?:(?!\{\{#unless\s)(?!\{\{/unless\}\}).)*?)\{\{/unless\}\}",
        re.DOTALL,
    )
    while unless_pattern.search(result):
        result = unless_pattern.sub(process_unless, result)

    return result


# ---------------------------------------------------------------------------
# Platform-aware file processing
# ---------------------------------------------------------------------------

def resolve_output_path(template_rel_path: str, output_root: Path) -> Path:
    """
    Map a template's relative path to its output location inside .ai/.

    All generated files are written to the .ai/ directory. After generation,
    run .ai/setup-links.sh to create symlinks where each platform expects them.

    Template directory structure → Output location:
      universal/AGENTS.md          → <root>/.ai/AGENTS.md
      universal/context/*          → <root>/.ai/context/*
      universal/update/*           → <root>/.ai/update/*
      universal/skills/*           → <root>/.ai/skills/*
      copilot/copilot-instructions → <root>/.ai/copilot-instructions.md
      copilot/agents/*             → <root>/.ai/agents/*
      opencode/agents/*.md         → <root>/.ai/opencode/agents/*.md
      opencode/opencode.json       → <root>/.ai/opencode/opencode.json
      codex/config.toml            → <root>/.ai/codex/config.toml
      codex/agents/*.toml          → <root>/.ai/codex/agents/*.toml
      adapters/*                   → handled separately by ADAPTER_OUTPUT_MAP
    """
    ai_dir = output_root / ".ai"

    if template_rel_path.startswith("universal/"):
        inner = template_rel_path[len("universal/"):]
        return ai_dir / inner

    elif template_rel_path.startswith("copilot/"):
        inner = template_rel_path[len("copilot/"):]
        return ai_dir / inner

    elif template_rel_path.startswith("opencode/"):
        inner = template_rel_path[len("opencode/"):]
        return ai_dir / "opencode" / inner

    elif template_rel_path.startswith("codex/"):
        inner = template_rel_path[len("codex/"):]
        return ai_dir / "codex" / inner

    else:
        # Fallback
        return ai_dir / template_rel_path


def should_process_template(
    template_rel_path: str,
    enabled_platforms: Set[str],
    config: Dict[str, Any],
) -> bool:
    """Check if a template should be processed based on platform and feature toggles."""
    features = config.get("features", {})
    agents_config = features.get("agents", {})
    skills_config = features.get("skills", {})

    # Universal templates
    if template_rel_path.startswith("universal/"):
        inner = template_rel_path[len("universal/"):]

        # AGENTS.md
        if inner == "AGENTS.md":
            return "agents_md" in enabled_platforms

        # Instruction modules (L2)
        if inner.startswith("instructions/"):
            return "agents_md" in enabled_platforms

        # Context files (L3 — markdown overviews + JSONL/YAML data)
        if inner.startswith("context/"):
            return "context_files" in enabled_platforms

        # Skills — check both platform toggle and individual skill toggle
        if inner.startswith("skills/"):
            if "skills" not in enabled_platforms:
                return False
            parts = inner.split("/")
            if len(parts) >= 2:
                skill_key = parts[1].replace("-", "_")
                # mnemix-memory skill is gated by the mnemix integration toggle
                if skill_key == "mnemix_memory":
                    integrations = features.get("integrations", {})
                    return integrations.get("mnemix", integrations.get("temporal_plane", False))
                if not skills_config.get(skill_key, True):
                    return False
            return True

        # Mnemix templates — gated by integration toggle
        if inner.startswith("mnemix/") or inner.startswith("temporal/"):
            integrations = features.get("integrations", {})
            return integrations.get("mnemix", integrations.get("temporal_plane", False))

        # Evals — gated by features.evals.enabled + per-skill filtering
        if inner.startswith("evals/"):
            evals_config = features.get("evals", {})
            if not evals_config.get("enabled", False):
                return False
            parts = inner.split("/")
            if len(parts) >= 2:
                skill_dir = parts[1]
                skills_to_eval = evals_config.get("skills_to_eval", [])
                # Shared files (runner, grader, README, .gitignore) always pass
                if skill_dir in ("run_eval.py", "grade_eval.py", "README.md", ".gitignore"):
                    return True
                # Skill-specific dirs gated by skills_to_eval list
                if skills_to_eval and skill_dir not in skills_to_eval:
                    return False
            return True

        return True

    # Copilot templates
    if template_rel_path.startswith("copilot/"):
        if "copilot" not in enabled_platforms:
            return False
        inner = template_rel_path[len("copilot/"):]

        # Check agent feature toggles
        if inner.startswith("agents/"):
            agent_name = inner.replace("agents/", "").replace(".agent.md", "")
            agent_key = agent_name.replace("-", "_")
            if not agents_config.get(agent_key, True):
                return False

        return True

    # OpenCode templates
    if template_rel_path.startswith("opencode/"):
        if "opencode" not in enabled_platforms:
            return False
        inner = template_rel_path[len("opencode/"):]

        # Check agent feature toggles (same toggles control both platforms)
        if inner.startswith("agents/"):
            agent_name = inner.replace("agents/", "").replace(".md", "")
            agent_key = agent_name.replace("-", "_")
            if not agents_config.get(agent_key, True):
                return False

        return True

    # Codex templates
    if template_rel_path.startswith("codex/"):
        if "codex" not in enabled_platforms:
            return False
        inner = template_rel_path[len("codex/"):]

        # Check agent feature toggles (same toggles control all platforms)
        if inner.startswith("agents/"):
            agent_name = inner.replace("agents/", "").replace(".toml", "")
            agent_key = agent_name.replace("-", "_")
            if not agents_config.get(agent_key, True):
                return False

        return True

    # Adapters are handled separately in process_adapters()
    return False


def process_templates(
    templates_dir: Path,
    output_root: Path,
    context: Dict[str, str],
    config: Dict[str, Any],
    enabled_platforms: Set[str],
    manifest_entries: Dict[str, Dict],
    dry_run: bool = False,
) -> tuple:
    """Walk the templates directory and render templates to platform-appropriate locations."""
    if not templates_dir.exists():
        print(f"❌ Templates directory not found: {templates_dir}")
        sys.exit(1)

    files_written = 0
    files_skipped = 0

    # Process universal/, copilot/, opencode/, and codex/ directories
    for subdir in ["universal", "copilot", "opencode", "codex"]:
        subdir_path = templates_dir / subdir
        if not subdir_path.exists():
            continue

        for template_path in sorted(subdir_path.rglob("*")):
            if template_path.is_dir():
                continue
            if "__pycache__" in template_path.parts or template_path.suffix == ".pyc":
                files_skipped += 1
                continue

            # Get relative path from templates dir (e.g., "universal/context/System_Architecture.md.tmpl")
            rel_path = template_path.relative_to(templates_dir)
            rel_str = str(rel_path)

            # Strip .tmpl extension for output
            # Handles: .md.tmpl → .md, .jsonl.tmpl → .jsonl, .yaml.tmpl → .yaml
            output_rel = rel_str
            if output_rel.endswith(".tmpl"):
                output_rel = output_rel[:-5]

            # Check if this template should be processed
            if not should_process_template(output_rel, enabled_platforms, config):
                files_skipped += 1
                continue

            # Read and render template
            with open(template_path, "r") as f:
                content = f.read()
            rendered = render_template(content, context, templates_dir)

            # Resolve output path
            output_path = resolve_output_path(output_rel, output_root)

            # Display path relative to output root
            display_path = str(output_path.relative_to(output_root))

            if dry_run:
                print(f"  📄 {display_path}")
            else:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w") as f:
                    f.write(rendered)
                print(f"  ✅ {display_path}")

            # Track in manifest for upgrade support
            manifest_entries[display_path] = {
                "source": str(rel_path),
                "template_hash": compute_file_hash(template_path),
                "output_hash": compute_content_hash(rendered),
                "category": classify_output_file(display_path),
            }

            files_written += 1

    return files_written, files_skipped


def process_adapters(
    templates_dir: Path,
    output_root: Path,
    context: Dict[str, str],
    enabled_platforms: Set[str],
    manifest_entries: Dict[str, Dict],
    dry_run: bool = False,
) -> tuple:
    """Process adapter templates (CLAUDE.md, .cursor/rules, .clinerules, .windsurfrules)."""
    adapters_dir = templates_dir / "adapters"
    if not adapters_dir.exists():
        return 0, 0

    files_written = 0
    files_skipped = 0

    for template_file, (platform, output_rel) in ADAPTER_OUTPUT_MAP.items():
        template_path = adapters_dir / template_file
        if not template_path.exists():
            files_skipped += 1
            continue

        if platform not in enabled_platforms:
            files_skipped += 1
            continue

        # Read and render
        with open(template_path, "r") as f:
            content = f.read()
        rendered = render_template(content, context, templates_dir)

        # Write output
        output_path = output_root / output_rel

        if dry_run:
            print(f"  📄 {output_rel}")
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                f.write(rendered)
            print(f"  ✅ {output_rel}")

        # Track in manifest for upgrade support
        manifest_entries[output_rel] = {
            "source": f"adapters/{template_file}",
            "template_hash": compute_file_hash(template_path),
            "output_hash": compute_content_hash(rendered),
            "category": "template-output",
        }

        files_written += 1

    return files_written, files_skipped


# ---------------------------------------------------------------------------
# Upgrade mechanism
# ---------------------------------------------------------------------------

def load_manifest(manifest_path: Path) -> Optional[Dict[str, Any]]:
    """Load the toolkit manifest. Returns None if not found."""
    if not manifest_path.exists():
        return None
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _show_diff(old_content: str, new_content: str, filepath: str) -> str:
    """Generate a unified diff string between old and new content."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{filepath}", tofile=f"b/{filepath}")
    return "".join(diff)


def _prompt_conflict(filepath: str, diff_text: str, non_interactive: bool) -> str:
    """Prompt user for conflict resolution. Returns 'accept', 'keep', or 'diff'."""
    if non_interactive:
        return "keep"  # Non-interactive skips conflicts

    print(f"\n  ⚠️  {filepath}")
    print(f"      Template changed upstream AND you modified the output.")
    print(f"      Options: [a]ccept new | [k]eep mine | [d]iff")

    while True:
        try:
            choice = input(f"      Choice [a/k/d]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "keep"
        if choice in ("a", "accept", "accept-new"):
            return "accept"
        if choice in ("k", "keep", "keep-mine"):
            return "keep"
        if choice in ("d", "diff", "show-diff"):
            print()
            if diff_text:
                print(diff_text)
            else:
                print("      (no textual differences)")
            print()
            # After showing diff, re-prompt for accept/keep
            continue
        print(f"      Invalid choice. Use a/k/d.")


def _prompt_add_new(filepath: str, non_interactive: bool) -> bool:
    """Ask whether to add a new template file."""
    if non_interactive:
        return True  # Non-interactive adds new files

    try:
        choice = input(f"  + {filepath} — new template. Add it? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return choice in ("", "y", "yes")


def _prompt_remove(filepath: str, non_interactive: bool) -> bool:
    """Ask whether to remove a deprecated template file."""
    if non_interactive:
        return False  # Non-interactive never deletes

    try:
        choice = input(f"  - {filepath} — template removed upstream. Delete it? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return choice in ("y", "yes")


def _collect_current_template_outputs(
    templates_dir: Path,
    output_root: Path,
    context: Dict[str, str],
    config: Dict[str, Any],
    enabled_platforms: Set[str],
    scripts_dir: Path,
) -> Dict[str, Dict]:
    """Build a dict of what generate.py would produce now (without writing).

    Returns {display_path: {source, template_hash, rendered_content, category}}.
    Used to detect new templates not in the manifest.
    """
    results: Dict[str, Dict] = {}

    # Walk template subdirs
    for subdir in ["universal", "copilot", "opencode", "codex"]:
        subdir_path = templates_dir / subdir
        if not subdir_path.exists():
            continue
        for template_path in sorted(subdir_path.rglob("*")):
            if template_path.is_dir():
                continue
            if "__pycache__" in template_path.parts or template_path.suffix == ".pyc":
                continue
            rel_path = template_path.relative_to(templates_dir)
            rel_str = str(rel_path)
            output_rel = rel_str[:-5] if rel_str.endswith(".tmpl") else rel_str
            if not should_process_template(output_rel, enabled_platforms, config):
                continue
            output_path = resolve_output_path(output_rel, output_root)
            display_path = str(output_path.relative_to(output_root))
            content = template_path.read_text()
            rendered = render_template(content, context, templates_dir)
            results[display_path] = {
                "source": str(rel_path),
                "template_hash": compute_file_hash(template_path),
                "rendered_content": rendered,
                "category": classify_output_file(display_path),
            }

    # Adapters
    adapters_dir = templates_dir / "adapters"
    if adapters_dir.exists():
        for template_file, (platform, output_rel) in ADAPTER_OUTPUT_MAP.items():
            template_path = adapters_dir / template_file
            if not template_path.exists() or platform not in enabled_platforms:
                continue
            content = template_path.read_text()
            rendered = render_template(content, context, templates_dir)
            results[output_rel] = {
                "source": f"adapters/{template_file}",
                "template_hash": compute_file_hash(template_path),
                "rendered_content": rendered,
                "category": "template-output",
            }

    # Scripts
    if scripts_dir.is_dir():
        for script in sorted(scripts_dir.glob("*.py")):
            display_path = f".ai/update/scripts/{script.name}"
            results[display_path] = {
                "source": f"setup/scripts/{script.name}",
                "template_hash": compute_file_hash(script),
                "rendered_content": script.read_text(),
                "category": "script",
            }

    # setup-links.sh
    setup_links = scripts_dir.parent / "setup-links.sh"
    if setup_links.is_file():
        results[".ai/setup-links.sh"] = {
            "source": "setup/setup-links.sh",
            "template_hash": compute_file_hash(setup_links),
            "rendered_content": setup_links.read_text(),
            "category": "script",
        }

    return results


def _process_manifest_files(
    manifest_files: Dict[str, Dict],
    current_outputs: Dict[str, Dict],
    output_root: Path,
    dry_run: bool,
    non_interactive: bool,
) -> tuple:
    """Process files already tracked in the manifest.

    Returns (auto_updated, conflicts, conflict_skipped, removed_available,
             unchanged, new_manifest_entries).
    """
    auto_updated: List[str] = []
    conflicts: List[str] = []
    conflict_skipped: List[str] = []
    removed_available: List[str] = []
    unchanged: List[str] = []
    new_manifest_entries: Dict[str, Dict] = {}

    for output_rel, file_info in sorted(manifest_files.items()):
        category = file_info.get("category", "template-output")

        # Context stubs are never touched
        if category == "context-stub":
            unchanged.append(output_rel)
            new_manifest_entries[output_rel] = file_info
            continue

        output_path = output_root / output_rel

        # Check if template source still exists
        if output_rel not in current_outputs:
            removed_available.append(output_rel)
            continue

        current_info = current_outputs[output_rel]
        old_template_hash = file_info.get("template_hash", "")
        new_template_hash = current_info["template_hash"]

        # Step 1: Did the template change?
        if old_template_hash == new_template_hash:
            unchanged.append(output_rel)
            new_manifest_entries[output_rel] = file_info
            continue

        # Template changed. Step 2: Did the user modify the output?
        old_output_hash = file_info.get("output_hash", "")
        try:
            current_output_hash = compute_file_hash(output_path)
        except (FileNotFoundError, OSError):
            current_output_hash = None

        user_modified = current_output_hash != old_output_hash
        new_rendered = current_info["rendered_content"]

        if not user_modified or category in ("script", "update-meta"):
            # Safe to auto-regenerate
            if not dry_run:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(new_rendered)
                if output_rel.endswith(".sh"):
                    output_path.chmod(output_path.stat().st_mode | 0o111)
            auto_updated.append(output_rel)
            new_manifest_entries[output_rel] = {
                "source": current_info["source"],
                "template_hash": new_template_hash,
                "output_hash": compute_content_hash(new_rendered),
                "category": current_info["category"],
            }
        else:
            # Conflict: template changed AND user modified output
            try:
                old_content = output_path.read_text()
            except (FileNotFoundError, OSError):
                old_content = ""
            diff_text = _show_diff(old_content, new_rendered, output_rel)

            if dry_run:
                conflicts.append(output_rel)
                new_manifest_entries[output_rel] = file_info
            else:
                resolution = _prompt_conflict(output_rel, diff_text, non_interactive)
                if resolution == "accept":
                    output_path.write_text(new_rendered)
                    auto_updated.append(output_rel)
                    new_manifest_entries[output_rel] = {
                        "source": current_info["source"],
                        "template_hash": new_template_hash,
                        "output_hash": compute_content_hash(new_rendered),
                        "category": current_info["category"],
                    }
                else:
                    conflict_skipped.append(output_rel)
                    updated_entry = dict(file_info)
                    updated_entry["template_hash"] = new_template_hash
                    if current_output_hash:
                        updated_entry["output_hash"] = current_output_hash
                    new_manifest_entries[output_rel] = updated_entry

    return (auto_updated, conflicts, conflict_skipped, removed_available,
            unchanged, new_manifest_entries)


def _process_new_templates(
    current_outputs: Dict[str, Dict],
    manifest_files: Dict[str, Dict],
    output_root: Path,
    dry_run: bool,
    non_interactive: bool,
    new_manifest_entries: Dict[str, Dict],
) -> tuple:
    """Detect and optionally add templates not yet in the manifest.

    Returns (new_added, new_available).
    """
    new_added: List[str] = []
    new_available: List[str] = []

    for output_rel, info in sorted(current_outputs.items()):
        if output_rel in manifest_files:
            continue
        new_rendered = info["rendered_content"]
        output_path = output_root / output_rel

        if dry_run:
            new_available.append(output_rel)
        else:
            if _prompt_add_new(output_rel, non_interactive):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(new_rendered)
                if output_rel.endswith(".sh"):
                    output_path.chmod(output_path.stat().st_mode | 0o111)
                new_added.append(output_rel)
                new_manifest_entries[output_rel] = {
                    "source": info["source"],
                    "template_hash": info["template_hash"],
                    "output_hash": compute_content_hash(new_rendered),
                    "category": info["category"],
                }
            else:
                new_available.append(output_rel)

    return new_added, new_available


def _process_removed_templates(
    removed_available: List[str],
    output_root: Path,
    dry_run: bool,
    non_interactive: bool,
) -> tuple:
    """Handle templates removed upstream.

    Returns (still_available, removed_deleted).
    """
    still_available: List[str] = []
    removed_deleted: List[str] = []

    for output_rel in removed_available:
        output_path = output_root / output_rel
        if not output_path.exists():
            continue  # Already gone from disk

        if dry_run:
            still_available.append(output_rel)
        else:
            if _prompt_remove(output_rel, non_interactive):
                output_path.unlink()
                removed_deleted.append(output_rel)
            else:
                still_available.append(output_rel)

    return still_available, removed_deleted


def _print_upgrade_summary(
    auto_updated: List[str],
    conflicts: List[str],
    conflict_skipped: List[str],
    new_added: List[str],
    new_available: List[str],
    removed_deleted: List[str],
    removed_available: List[str],
    unchanged: List[str],
    dry_run: bool,
    new_version: str,
) -> None:
    """Print the upgrade summary report."""
    print()
    if auto_updated:
        print("━━━ AUTO-UPDATED ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for f in auto_updated:
            action = "would regenerate" if dry_run else "regenerated"
            print(f"  ✅ {f} — {action}")
        print()

    if conflicts:
        print("━━━ CONFLICTS (user modified + template changed) ━━")
        for f in conflicts:
            print(f"  ⚠️  {f} — needs resolution (run without --dry-run)")
        print()

    if conflict_skipped:
        print("━━━ CONFLICTS KEPT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for f in conflict_skipped:
            print(f"  ⏭️  {f} — kept your version")
        print()

    if new_available or new_added:
        print("━━━ NEW ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for f in new_added:
            print(f"  ✅ {f} — added")
        for f in new_available:
            action = "available to add" if dry_run else "skipped"
            print(f"  + {f} — {action}")
        print()

    if removed_available or removed_deleted:
        print("━━━ REMOVED UPSTREAM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for f in removed_deleted:
            print(f"  🗑️  {f} — deleted")
        for f in removed_available:
            action = "deprecated (run without --dry-run to remove)" if dry_run else "kept"
            print(f"  ⚠️  {f} — {action}")
        print()

    if unchanged:
        print(f"━━━ UNCHANGED ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  ⏭️  {len(unchanged)} files unchanged")
        print()

    # Final counts
    n_updated = len(auto_updated)
    n_conflicts = len(conflicts) + len(conflict_skipped)
    n_new = len(new_added) + len(new_available)
    n_removed = len(removed_deleted) + len(removed_available)
    n_unchanged = len(unchanged)

    verb = "would be " if dry_run else ""
    print(f"{'📋' if dry_run else '✅'} Done! {n_updated} files {verb}updated, "
          f"{n_conflicts} conflict{'s' if n_conflicts != 1 else ''}, "
          f"{n_new} new, {n_removed} deprecated, {n_unchanged} unchanged")

    if not dry_run and n_updated > 0:
        print()
        print("Next steps:")
        print(f'  git add .ai/ && git commit -m "chore: upgrade AI toolkit to v{new_version}"')


def upgrade(
    manifest_path: Path,
    templates_dir: Path,
    output_root: Path,
    config: Dict[str, Any],
    context: Dict[str, str],
    enabled_platforms: Set[str],
    toolkit_version: Dict[str, Any],
    config_hash: str,
    dry_run: bool = False,
    non_interactive: bool = False,
) -> None:
    """Three-way merge upgrade: compare manifest hashes to detect changes."""
    manifest = load_manifest(manifest_path)
    if manifest is None:
        print("❌ No manifest found at", manifest_path)
        print("   Run generate.py without --upgrade first to create a manifest.")
        sys.exit(1)

    old_version = manifest.get("toolkit_version", "unknown")
    new_version = toolkit_version["version"]
    print(f"📌 Toolkit: {old_version} → {new_version}")
    print()

    scripts_dir = Path(__file__).resolve().parent / "scripts"

    current_outputs = _collect_current_template_outputs(
        templates_dir, output_root, context, config, enabled_platforms, scripts_dir,
    )

    manifest_files = manifest.get("files", {})

    # Phase 1: Process existing manifest files
    (auto_updated, conflicts, conflict_skipped, removed_available,
     unchanged, new_manifest_entries) = _process_manifest_files(
        manifest_files, current_outputs, output_root, dry_run, non_interactive,
    )

    # Phase 2: Detect new templates
    new_added, new_available = _process_new_templates(
        current_outputs, manifest_files, output_root, dry_run, non_interactive,
        new_manifest_entries,
    )

    # Phase 3: Handle removed templates
    removed_available, removed_deleted = _process_removed_templates(
        removed_available, output_root, dry_run, non_interactive,
    )

    # Print summary
    _print_upgrade_summary(
        auto_updated, conflicts, conflict_skipped, new_added, new_available,
        removed_deleted, removed_available, unchanged, dry_run, new_version,
    )

    # Update manifest
    if not dry_run:
        write_manifest(new_manifest_entries, toolkit_version, config_hash, output_root)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Mnemix Context - Generate project-specific AI resources from templates"
    )
    parser.add_argument(
        "--config", "-c",
        default="toolkit.config.yaml",
        help="Path to config file (default: toolkit.config.yaml)",
    )
    parser.add_argument(
        "--templates", "-t",
        default="templates",
        help="Path to templates directory (default: templates/)",
    )
    parser.add_argument(
        "--output", "-o",
        default=".",
        help="Project root directory to generate into (default: current directory)",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Override platform selection. Comma-separated: copilot,opencode,codex,cursor,claude,cline,windsurf,agents_md,skills,context_files. Use 'all' for everything.",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview files without writing",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate config and exit",
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Upgrade existing .ai/ files from new toolkit templates (three-way merge)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Auto-accept safe changes, skip conflicts (for CI use with --upgrade)",
    )
    args = parser.parse_args()

    # Resolve paths relative to script location (project root)
    root = Path(__file__).resolve().parent.parent
    config_path = root / args.config
    templates_dir = root / args.templates
    output_root = Path(args.output).resolve() if args.output != "." else root

    print("=" * 60)
    print("  Mnemix Context - Template Generator")
    print("=" * 60)
    print()

    # Load config
    print(f"📋 Loading config: {config_path}")
    config = load_config(str(config_path))

    # Validate
    errors = validate_config(config)
    if errors:
        print()
        print("⚠️  Config validation warnings:")
        for err in errors:
            print(f"   - {err}")
        print()

    if args.validate:
        if errors:
            print("❌ Validation failed")
            sys.exit(1)
        else:
            print("✅ Config is valid")
            sys.exit(0)

    # Determine platforms
    enabled_platforms = get_enabled_platforms(config, args.target)

    # Categorize for display
    NATIVE_PLATFORMS = {"copilot", "opencode", "codex"}
    ADAPTER_DISPLAY_PLATFORMS = {"cursor", "claude", "cline", "windsurf"}

    universal = sorted(enabled_platforms & UNIVERSAL_PLATFORMS)
    native = sorted(enabled_platforms & NATIVE_PLATFORMS)
    adapters = sorted(enabled_platforms & ADAPTER_DISPLAY_PLATFORMS)

    print(f"🎯 Platforms:")
    if universal:
        print(f"   Universal: {', '.join(universal)}")
    if native:
        print(f"   Native:    {', '.join(native)}")
    if adapters:
        print(f"   Adapters:  {', '.join(adapters)}")
    print()

    # Read toolkit version
    version_info = get_toolkit_version(root)
    print(f"📌 Toolkit version: {version_info['version']}")
    if version_info["commit"]:
        print(f"   Commit: {version_info['commit']}")
    print()

    # Build context
    print("🔧 Building template context...")
    context = build_context(config)
    print(f"   {len(context)} variables loaded")
    print()

    # Config hash for manifest
    config_hash = compute_config_hash(config_path)

    # --- Upgrade mode ---
    if args.upgrade:
        manifest_path = output_root / ".ai" / "update" / ".toolkit-manifest.json"
        mode = "UPGRADE DRY RUN" if args.dry_run else "UPGRADING"
        print(f"🔄 {mode} — comparing templates against manifest")
        print()
        upgrade(
            manifest_path=manifest_path,
            templates_dir=templates_dir,
            output_root=output_root,
            config=config,
            context=context,
            enabled_platforms=enabled_platforms,
            toolkit_version=version_info,
            config_hash=config_hash,
            dry_run=args.dry_run,
            non_interactive=args.non_interactive,
        )
        return

    # Track manifest entries for upgrade support
    manifest_entries: Dict[str, Dict] = {}

    # Render
    mode = "DRY RUN" if args.dry_run else "GENERATING"
    print(f"📝 {mode} files → {output_root}")
    print()

    # Process main templates (universal + copilot)
    written, skipped = process_templates(
        templates_dir, output_root, context, config, enabled_platforms,
        manifest_entries, args.dry_run,
    )

    # Process adapter templates
    adapter_written, adapter_skipped = process_adapters(
        templates_dir, output_root, context, enabled_platforms,
        manifest_entries, args.dry_run,
    )

    total_written = written + adapter_written
    total_skipped = skipped + adapter_skipped

    # Copy helper scripts to .ai/update/scripts/ for the update agent
    scripts_src = Path(__file__).parent / "scripts"
    if scripts_src.is_dir() and not args.dry_run:
        scripts_dst = output_root / ".ai" / "update" / "scripts"
        scripts_dst.mkdir(parents=True, exist_ok=True)
        copied = 0
        for script in sorted(scripts_src.glob("*.py")):
            dst = scripts_dst / script.name
            shutil.copy2(script, dst)
            copied += 1
            manifest_entries[f".ai/update/scripts/{script.name}"] = {
                "source": f"setup/scripts/{script.name}",
                "template_hash": compute_file_hash(script),
                "output_hash": compute_file_hash(dst),
                "category": "script",
            }
        if copied:
            print(f"  📦 Copied {copied} helper scripts → .ai/update/scripts/")
            total_written += copied

    # Copy setup-links.sh into .ai/ so users can create symlinks after copying
    setup_links_src = Path(__file__).parent / "setup-links.sh"
    if setup_links_src.is_file() and not args.dry_run:
        setup_links_dst = output_root / ".ai" / "setup-links.sh"
        shutil.copy2(setup_links_src, setup_links_dst)
        setup_links_dst.chmod(setup_links_dst.stat().st_mode | 0o111)  # make executable
        print(f"  📦 Copied setup-links.sh → .ai/setup-links.sh")
        total_written += 1
        manifest_entries[".ai/setup-links.sh"] = {
            "source": "setup/setup-links.sh",
            "template_hash": compute_file_hash(setup_links_src),
            "output_hash": compute_file_hash(setup_links_dst),
            "category": "script",
        }

    # Write toolkit manifest for upgrade tracking
    write_manifest(manifest_entries, version_info, config_hash, output_root, args.dry_run)
    total_written += 1

    print()
    summary = f"{total_written} files {'would be ' if args.dry_run else ''}generated, {total_skipped} skipped"
    print(f"{'📋' if args.dry_run else '✅'} Done! {summary}")

    if not args.dry_run:
        print()
        print("Generated output → .ai/")
        if "agents_md" in enabled_platforms:
            print("  📄 .ai/AGENTS.md                — L1 router (always loaded)")
            print("  📂 .ai/instructions/            — L2 instruction modules (on demand)")
        if "context_files" in enabled_platforms:
            print("  📂 .ai/context/                 — L3 project knowledge (on demand)")
            print("     ├── *.md                     — prose overviews")
            print("     ├── *.jsonl                  — structured lookup data")
            print("     └── *.yaml                   — hierarchical data")

        print("  📂 .ai/update/                  — context update agent + metadata")
        if "skills" in enabled_platforms:
            print("  📂 .ai/skills/                  — auto-activating skills")
        if "copilot" in enabled_platforms:
            print("  📄 .ai/copilot-instructions.md")
            print("  📂 .ai/agents/                  — Copilot agent personas")
        if "opencode" in enabled_platforms:
            print("  📄 .ai/opencode/opencode.json   — OpenCode project config")
            print("  📂 .ai/opencode/agents/         — OpenCode agent personas")
        if "codex" in enabled_platforms:
            print("  📄 .ai/codex/config.toml        — Codex project config")
            print("  📂 .ai/codex/agents/            — Codex agent role configs")
        if "claude" in enabled_platforms:
            print("  📄 .ai/CLAUDE.md                — pointer to AGENTS.md")
        if "cursor" in enabled_platforms:
            print("  📄 .ai/cursor-rules.mdc         — Cursor rules")
        if "cline" in enabled_platforms:
            print("  📄 .ai/clinerules               — pointer to AGENTS.md")
        if "windsurf" in enabled_platforms:
            print("  📄 .ai/windsurfrules            — pointer to AGENTS.md")

        print()
        print("Next steps:")
        print("  1. Drop project docs (DB extracts, API specs, glossaries) into mnemix-context/reference/")
        print("  2. Run the Bootstrap Agent to auto-populate context files")
        print("  3. Review generated files in .ai/")
        print("  4. Copy .ai/ to your workspace root")
        print("  5. Run: bash .ai/setup-links.sh")
        print("  6. Commit .ai/ directory and symlinks to your project")
        print()
        print("💡 Tip: Use the Bootstrap Agent in VS Code Copilot Chat to")
        print("   auto-populate context files from your codebase.")


if __name__ == "__main__":
    main()
