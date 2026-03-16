import sys
from pathlib import Path
import tempfile
import unittest

# Allow importing from parent setup/ directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from generate import (
    _process_includes,
    _resolve_include_path,
    build_context,
    resolve_output_path,
    should_process_template,
)


class TestTemplateIncludes(unittest.TestCase):
    def test_resolve_include_path_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            templates_dir = Path(temp_dir)
            with self.assertRaises(ValueError):
                _resolve_include_path("../outside.md", templates_dir)

    def test_process_includes_file_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            templates_dir = Path(temp_dir)
            with self.assertRaises(ValueError):
                _process_includes("{{#include shared/personas/missing.md.tmpl}}", templates_dir)

    def test_process_includes_multiple_includes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            templates_dir = Path(temp_dir)
            shared_dir = templates_dir / "shared" / "personas"
            shared_dir.mkdir(parents=True)
            (shared_dir / "one.md.tmpl").write_text("ONE")
            (shared_dir / "two.md.tmpl").write_text("TWO")

            rendered = _process_includes(
                "A {{#include shared/personas/one.md.tmpl}} B {{#include shared/personas/two.md.tmpl}} C",
                templates_dir,
            )

            self.assertEqual(rendered, "A ONE B TWO C")

    def test_process_includes_nested_include(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            templates_dir = Path(temp_dir)
            shared_dir = templates_dir / "shared" / "personas"
            shared_dir.mkdir(parents=True)
            (shared_dir / "inner.md.tmpl").write_text("INNER")
            (shared_dir / "outer.md.tmpl").write_text("OUTER {{#include shared/personas/inner.md.tmpl}}")

            rendered = _process_includes(
                "{{#include shared/personas/outer.md.tmpl}}",
                templates_dir,
            )

            self.assertEqual(rendered, "OUTER INNER")

    def test_process_includes_expansion_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            templates_dir = Path(temp_dir)
            shared_dir = templates_dir / "shared" / "personas"
            shared_dir.mkdir(parents=True)
            (shared_dir / "loop.md.tmpl").write_text("{{#include shared/personas/loop.md.tmpl}}")

            with self.assertRaises(ValueError) as context:
                _process_includes("{{#include shared/personas/loop.md.tmpl}}", templates_dir, max_depth=3)

            self.assertIn("expansion limit exceeded", str(context.exception))

    # ── {{#include-commented}} ────────────────────────────────────────────

    def test_include_commented_prefixes_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            templates_dir = Path(temp_dir)
            shared_dir = templates_dir / "shared" / "personas"
            shared_dir.mkdir(parents=True)
            (shared_dir / "role.md.tmpl").write_text("line one\nline two\n\nline four")

            rendered = _process_includes(
                "{{#include-commented shared/personas/role.md.tmpl}}",
                templates_dir,
            )

            self.assertEqual(rendered, "# line one\n# line two\n#\n# line four")

    def test_include_commented_empty_lines_become_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            templates_dir = Path(temp_dir)
            shared_dir = templates_dir / "shared" / "personas"
            shared_dir.mkdir(parents=True)
            (shared_dir / "role.md.tmpl").write_text("A\n\nB")

            rendered = _process_includes(
                "start\n{{#include-commented shared/personas/role.md.tmpl}}\nend",
                templates_dir,
            )

            self.assertEqual(rendered, "start\n# A\n#\n# B\nend")

    def test_include_commented_nested_includes_still_expand_in_second_pass(self) -> None:
        """Verify nested {{#include}} inside commented content still gets expanded.

        The commented pass reads raw text and prefixes with '# ', but the second
        pass (regular {{#include}}) will still match and expand {{#include}}
        directives that appear in the commented output. The expanded content stays
        within the comment-prefixed line, so the result remains valid as comments.
        This is acceptable because shared persona templates do not use nested includes.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            templates_dir = Path(temp_dir)
            shared_dir = templates_dir / "shared" / "personas"
            shared_dir.mkdir(parents=True)
            # File contains a nested {{#include}} directive
            (shared_dir / "outer.md.tmpl").write_text(
                "Top\n{{#include shared/personas/inner.md.tmpl}}\nBottom"
            )
            (shared_dir / "inner.md.tmpl").write_text("INNER CONTENT")

            rendered = _process_includes(
                "{{#include-commented shared/personas/outer.md.tmpl}}",
                templates_dir,
            )

            # The nested include IS expanded by the second pass, but remains in
            # a comment-prefixed line — the '# ' prefix survives replacement
            self.assertEqual(rendered, "# Top\n# INNER CONTENT\n# Bottom")


class TestOpenCodeTemplateProcessing(unittest.TestCase):
    """Tests for OpenCode-specific should_process_template and resolve_output_path logic."""

    def _base_config(self, agents_overrides: dict = None) -> dict:
        """Return a minimal config with all agents enabled by default."""
        agents = {
            "engineer": True,
            "reviewer": True,
            "documentation": True,
            "architect": True,
        }
        if agents_overrides:
            agents.update(agents_overrides)
        return {"features": {"agents": agents, "skills": {}}}

    # ── should_process_template ───────────────────────────────────────────

    def test_opencode_agent_processed_when_platform_enabled(self) -> None:
        config = self._base_config()
        result = should_process_template(
            "opencode/agents/engineer.md",
            {"opencode"},
            config,
        )
        self.assertTrue(result)

    def test_opencode_agent_skipped_when_platform_disabled(self) -> None:
        config = self._base_config()
        result = should_process_template(
            "opencode/agents/engineer.md",
            {"copilot"},
            config,
        )
        self.assertFalse(result)

    def test_opencode_config_file_processed_when_platform_enabled(self) -> None:
        config = self._base_config()
        result = should_process_template(
            "opencode/opencode.json",
            {"opencode"},
            config,
        )
        self.assertTrue(result)

    # ── resolve_output_path ───────────────────────────────────────────────

    def test_resolve_output_path_opencode_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = resolve_output_path("opencode/agents/engineer.md", root)
            self.assertEqual(result, root / ".ai" / "opencode" / "agents" / "engineer.md")

    def test_resolve_output_path_opencode_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = resolve_output_path("opencode/opencode.json", root)
            self.assertEqual(result, root / ".ai" / "opencode" / "opencode.json")


class TestCodexTemplateProcessing(unittest.TestCase):
    """Tests for Codex-specific should_process_template and resolve_output_path logic."""

    def _base_config(self, agents_overrides: dict = None) -> dict:
        """Return a minimal config with all agents enabled by default."""
        agents = {
            "engineer": True,
            "reviewer": True,
            "documentation": True,
            "architect": True,
        }
        if agents_overrides:
            agents.update(agents_overrides)
        return {"features": {"agents": agents, "skills": {}}}

    # ── should_process_template ───────────────────────────────────────────

    def test_codex_agent_processed_when_platform_enabled(self) -> None:
        config = self._base_config()
        result = should_process_template(
            "codex/agents/engineer.toml",
            {"codex"},
            config,
        )
        self.assertTrue(result)

    def test_codex_agent_skipped_when_platform_disabled(self) -> None:
        config = self._base_config()
        result = should_process_template(
            "codex/agents/engineer.toml",
            {"copilot"},
            config,
        )
        self.assertFalse(result)

    def test_codex_config_file_processed_when_platform_enabled(self) -> None:
        config = self._base_config()
        result = should_process_template(
            "codex/config.toml",
            {"codex"},
            config,
        )
        self.assertTrue(result)

    def test_codex_architect_agent_respects_toggle(self) -> None:
        config = self._base_config(agents_overrides={"architect": False})
        result = should_process_template(
            "codex/agents/architect.toml",
            {"codex"},
            config,
        )
        self.assertFalse(result)

    # ── resolve_output_path ───────────────────────────────────────────────

    def test_resolve_output_path_codex_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = resolve_output_path("codex/agents/engineer.toml", root)
            self.assertEqual(result, root / ".ai" / "codex" / "agents" / "engineer.toml")

    def test_resolve_output_path_codex_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = resolve_output_path("codex/config.toml", root)
            self.assertEqual(result, root / ".ai" / "codex" / "config.toml")


class TestMnemixTemplateProcessing(unittest.TestCase):
    """Tests for Mnemix should_process_template and build_context logic."""

    def _base_config(self, mnemix: bool = True) -> dict:
        """Return a config with mnemix integration toggle."""
        return {
            "features": {
                "agents": {},
                "skills": {},
                "integrations": {"mnemix": mnemix},
            },
            "mnemix": {
                "session_strategy": "branch",
                "store_path": ".mnemix",
                "binary": "mnemix",
                "scope": "repo:test-project",
            },
        }

    # ── should_process_template: mnemix-memory skill ─────────────────────

    def test_mnemix_memory_skill_processed_when_enabled(self) -> None:
        config = self._base_config(mnemix=True)
        result = should_process_template(
            "universal/skills/mnemix-memory/SKILL.md",
            {"skills"},
            config,
        )
        self.assertTrue(result)

    def test_mnemix_memory_skill_skipped_when_disabled(self) -> None:
        config = self._base_config(mnemix=False)
        result = should_process_template(
            "universal/skills/mnemix-memory/SKILL.md",
            {"skills"},
            config,
        )
        self.assertFalse(result)

    def test_mnemix_memory_skill_skipped_when_skills_platform_disabled(self) -> None:
        config = self._base_config(mnemix=True)
        result = should_process_template(
            "universal/skills/mnemix-memory/SKILL.md",
            {"copilot"},  # skills not in enabled platforms
            config,
        )
        self.assertFalse(result)

    # ── should_process_template: mnemix/ directory ──────────────────────

    def test_mnemix_readme_processed_when_enabled(self) -> None:
        config = self._base_config(mnemix=True)
        result = should_process_template(
            "universal/mnemix/README.md",
            {"copilot"},
            config,
        )
        self.assertTrue(result)

    def test_mnemix_readme_skipped_when_disabled(self) -> None:
        config = self._base_config(mnemix=False)
        result = should_process_template(
            "universal/mnemix/README.md",
            {"copilot"},
            config,
        )
        self.assertFalse(result)

    def test_mnemix_directory_nonexistent_runtime_not_required(self) -> None:
        config = self._base_config(mnemix=True)
        result = should_process_template(
            "universal/mnemix/README.md",
            {"copilot"},
            config,
        )
        self.assertTrue(result)

    def test_mnemix_adapter_processed_when_enabled(self) -> None:
        config = self._base_config(mnemix=True)
        result = should_process_template(
            "universal/mnemix/adapters/coding_agent_adapter.py",
            {"copilot"},
            config,
        )
        self.assertTrue(result)

    def test_mnemix_policy_processed_when_enabled(self) -> None:
        config = self._base_config(mnemix=True)
        result = should_process_template(
            "universal/mnemix/MEMORY_POLICY.md",
            {"copilot"},
            config,
        )
        self.assertTrue(result)


class TestBuildContext(unittest.TestCase):
    def test_build_context_includes_task_tracking_fields(self) -> None:
        config = {
            "project": {
                "name": "example",
                "description": "Example project",
                "task_tracking_system": "Linear",
                "task_tracking_notes": "Bugs are triaged in Linear and mirrored to Slack.",
            },
            "tech_stack": {
                "frontend": {"framework": "React"},
                "backend": {"framework": "Fastify"},
            },
        }

        context = build_context(config)

        self.assertEqual(context["project.task_tracking_system"], "Linear")
        self.assertEqual(
            context["project.task_tracking_notes"],
            "Bugs are triaged in Linear and mirrored to Slack.",
        )


class TestEvalsTemplateProcessing(unittest.TestCase):
    """Tests for evals should_process_template gating logic."""

    def _base_config(self, evals_enabled: bool = True, skills_to_eval: list = None) -> dict:
        """Return a config with evals feature toggle."""
        evals_config = {"enabled": evals_enabled}
        if skills_to_eval is not None:
            evals_config["skills_to_eval"] = skills_to_eval
        return {
            "features": {
                "agents": {},
                "skills": {},
                "integrations": {},
                "evals": evals_config,
            },
        }

    # ── Evals enabled/disabled ────────────────────────────────────────────

    def test_evals_runner_processed_when_enabled(self) -> None:
        config = self._base_config(evals_enabled=True)
        result = should_process_template(
            "universal/evals/run_eval.py",
            {"copilot"},
            config,
        )
        self.assertTrue(result)

    def test_evals_skipped_when_disabled(self) -> None:
        config = self._base_config(evals_enabled=False)
        result = should_process_template(
            "universal/evals/run_eval.py",
            {"copilot"},
            config,
        )
        self.assertFalse(result)

    def test_evals_grader_processed_when_enabled(self) -> None:
        config = self._base_config(evals_enabled=True)
        result = should_process_template(
            "universal/evals/grade_eval.py",
            {"copilot"},
            config,
        )
        self.assertTrue(result)

    def test_evals_readme_processed_when_enabled(self) -> None:
        config = self._base_config(evals_enabled=True)
        result = should_process_template(
            "universal/evals/README.md",
            {"copilot"},
            config,
        )
        self.assertTrue(result)

    def test_evals_gitignore_processed_when_enabled(self) -> None:
        config = self._base_config(evals_enabled=True)
        result = should_process_template(
            "universal/evals/.gitignore",
            {"copilot"},
            config,
        )
        self.assertTrue(result)

    # ── Per-skill filtering ───────────────────────────────────────────────

    def test_evals_skill_processed_when_in_skills_list(self) -> None:
        config = self._base_config(evals_enabled=True, skills_to_eval=["mnemix-memory"])
        result = should_process_template(
            "universal/evals/mnemix-memory/eval_metadata.json",
            {"copilot"},
            config,
        )
        self.assertTrue(result)

    def test_evals_skill_skipped_when_not_in_skills_list(self) -> None:
        config = self._base_config(evals_enabled=True, skills_to_eval=["mnemix-memory"])
        result = should_process_template(
            "universal/evals/api-endpoint/eval_metadata.json",
            {"copilot"},
            config,
        )
        self.assertFalse(result)

    def test_evals_skill_processed_when_no_skills_list(self) -> None:
        """When skills_to_eval is empty, all skills pass."""
        config = self._base_config(evals_enabled=True, skills_to_eval=[])
        result = should_process_template(
            "universal/evals/api-endpoint/eval_metadata.json",
            {"copilot"},
            config,
        )
        self.assertTrue(result)

    def test_evals_shared_files_always_pass_regardless_of_skills_list(self) -> None:
        """Runner, grader, README, .gitignore always pass when evals enabled."""
        config = self._base_config(evals_enabled=True, skills_to_eval=["mnemix-memory"])
        for path in [
            "universal/evals/run_eval.py",
            "universal/evals/grade_eval.py",
            "universal/evals/README.md",
            "universal/evals/.gitignore",
        ]:
            result = should_process_template(path, {"copilot"}, config)
            self.assertTrue(result, f"Expected {path} to pass")

    def test_evals_no_config_defaults_to_disabled(self) -> None:
        """When features.evals is missing entirely, evals are disabled."""
        config = {"features": {"agents": {}, "skills": {}, "integrations": {}}}
        result = should_process_template(
            "universal/evals/run_eval.py",
            {"copilot"},
            config,
        )
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
