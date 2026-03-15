"""Tests for the --upgrade mechanism in generate.py."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from generate import (
    classify_output_file,
    compute_content_hash,
    compute_file_hash,
    load_manifest,
    upgrade,
    _collect_current_template_outputs,
    _show_diff,
)

# The module path used for patching depends on how the test is run.
# When run via `python3 -m unittest setup.tests.test_upgrade`, the module
# is loaded as `setup.generate`. When run directly, it's `generate`.
# We detect which one is active.
import generate as _gen_module
_PATCH_MODULE = _gen_module.__name__

import tempfile


class TestLoadManifest(unittest.TestCase):
    def test_returns_none_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = load_manifest(Path(tmp) / "nonexistent.json")
            self.assertIsNone(result)

    def test_loads_valid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = {"toolkit_version": "0.9.0", "files": {}}
            p = Path(tmp) / "manifest.json"
            p.write_text(json.dumps(manifest))
            result = load_manifest(p)
            self.assertEqual(result["toolkit_version"], "0.9.0")


class TestShowDiff(unittest.TestCase):
    def test_identical_content_produces_empty_diff(self) -> None:
        diff = _show_diff("hello\n", "hello\n", "test.md")
        self.assertEqual(diff, "")

    def test_different_content_produces_diff(self) -> None:
        diff = _show_diff("line1\n", "line2\n", "test.md")
        self.assertIn("-line1", diff)
        self.assertIn("+line2", diff)


class TestUpgradeNoManifest(unittest.TestCase):
    def test_exits_when_no_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / ".toolkit-manifest.json"
            with self.assertRaises(SystemExit):
                upgrade(
                    manifest_path=manifest_path,
                    templates_dir=Path(tmp),
                    output_root=Path(tmp),
                    config={},
                    context={},
                    enabled_platforms=set(),
                    toolkit_version={"version": "1.0.0", "commit": "abc"},
                    config_hash="sha256:test",
                )


class TestUpgradeSkipUnchanged(unittest.TestCase):
    """When template hash hasn't changed, the file should be skipped."""

    def test_unchanged_template_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Create a template
            templates_dir = tmp_path / "templates"
            tmpl_dir = templates_dir / "universal"
            tmpl_dir.mkdir(parents=True)
            tmpl_file = tmpl_dir / "AGENTS.md.tmpl"
            tmpl_file.write_text("# Agents\n")
            tmpl_hash = compute_file_hash(tmpl_file)

            # Create existing output
            output_dir = tmp_path / "output" / ".ai"
            output_dir.mkdir(parents=True)
            output_file = output_dir / "AGENTS.md"
            output_file.write_text("# Agents\n")
            output_hash = compute_content_hash("# Agents\n")

            # Create manifest
            manifest = {
                "toolkit_version": "0.8.0",
                "toolkit_commit": "old",
                "generated_at": "2026-01-01T00:00:00Z",
                "config_hash": "sha256:test",
                "files": {
                    ".ai/AGENTS.md": {
                        "source": "universal/AGENTS.md.tmpl",
                        "template_hash": tmpl_hash,
                        "output_hash": output_hash,
                        "category": "template-output",
                    }
                },
            }
            manifest_path = tmp_path / "output" / ".ai" / "update"
            manifest_path.mkdir(parents=True)
            manifest_file = manifest_path / ".toolkit-manifest.json"
            manifest_file.write_text(json.dumps(manifest))

            # Mock _collect to return the same template hash as manifest
            current_outputs = {
                ".ai/AGENTS.md": {
                    "source": "universal/AGENTS.md.tmpl",
                    "template_hash": tmpl_hash,
                    "rendered_content": "# Agents\n",
                    "category": "template-output",
                },
            }

            with patch(
                f"{_PATCH_MODULE}._collect_current_template_outputs",
                return_value=current_outputs,
            ):
                upgrade(
                    manifest_path=manifest_file,
                    templates_dir=templates_dir,
                    output_root=tmp_path / "output",
                    config={},
                    context={},
                    enabled_platforms={"agents_md"},
                    toolkit_version={"version": "0.9.0", "commit": "new"},
                    config_hash="sha256:test",
                    dry_run=True,
                )

            # Output file should not be modified
            self.assertEqual(output_file.read_text(), "# Agents\n")


class TestUpgradeAutoRegenerate(unittest.TestCase):
    """When template changed but user didn't modify output, auto-regenerate."""

    def test_auto_regenerates_unmodified_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Create template with NEW content
            templates_dir = tmp_path / "templates"
            tmpl_dir = templates_dir / "universal"
            tmpl_dir.mkdir(parents=True)
            tmpl_file = tmpl_dir / "AGENTS.md.tmpl"
            tmpl_file.write_text("# Agents v2\nNew content\n")
            new_tmpl_hash = compute_file_hash(tmpl_file)

            # Create existing output with OLD content
            output_dir = tmp_path / "output" / ".ai"
            output_dir.mkdir(parents=True)
            output_file = output_dir / "AGENTS.md"
            old_content = "# Agents v1\nOld content\n"
            output_file.write_text(old_content)
            output_hash = compute_content_hash(old_content)

            # Manifest with OLD template hash
            manifest = {
                "toolkit_version": "0.8.0",
                "toolkit_commit": "old",
                "generated_at": "2026-01-01T00:00:00Z",
                "config_hash": "sha256:test",
                "files": {
                    ".ai/AGENTS.md": {
                        "source": "universal/AGENTS.md.tmpl",
                        "template_hash": "sha256:oldoldhash12345",
                        "output_hash": output_hash,
                        "category": "template-output",
                    }
                },
            }
            manifest_path = tmp_path / "output" / ".ai" / "update"
            manifest_path.mkdir(parents=True)
            manifest_file = manifest_path / ".toolkit-manifest.json"
            manifest_file.write_text(json.dumps(manifest))

            # Mock: template changed, new rendered content
            current_outputs = {
                ".ai/AGENTS.md": {
                    "source": "universal/AGENTS.md.tmpl",
                    "template_hash": new_tmpl_hash,
                    "rendered_content": "# Agents v2\nNew content\n",
                    "category": "template-output",
                },
            }

            with patch(
                f"{_PATCH_MODULE}._collect_current_template_outputs",
                return_value=current_outputs,
            ):
                upgrade(
                    manifest_path=manifest_file,
                    templates_dir=templates_dir,
                    output_root=tmp_path / "output",
                    config={},
                    context={},
                    enabled_platforms={"agents_md"},
                    toolkit_version={"version": "0.9.0", "commit": "new"},
                    config_hash="sha256:test",
                )

            # Output should be updated to new content
            self.assertEqual(output_file.read_text(), "# Agents v2\nNew content\n")

            # Manifest should be updated
            new_manifest = json.loads(manifest_file.read_text())
            self.assertEqual(new_manifest["toolkit_version"], "0.9.0")
            self.assertIn(".ai/AGENTS.md", new_manifest["files"])
            self.assertEqual(
                new_manifest["files"][".ai/AGENTS.md"]["output_hash"],
                compute_content_hash("# Agents v2\nNew content\n"),
            )


class TestUpgradeConflictNonInteractive(unittest.TestCase):
    """When template changed AND user modified output, non-interactive keeps user's version."""

    def test_conflict_keeps_user_version_non_interactive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Template with new content
            templates_dir = tmp_path / "templates"
            tmpl_dir = templates_dir / "universal"
            tmpl_dir.mkdir(parents=True)
            tmpl_file = tmpl_dir / "AGENTS.md.tmpl"
            tmpl_file.write_text("# Agents v2\nNew template content\n")
            new_tmpl_hash = compute_file_hash(tmpl_file)

            # User-modified output
            output_dir = tmp_path / "output" / ".ai"
            output_dir.mkdir(parents=True)
            output_file = output_dir / "AGENTS.md"
            user_content = "# Agents v1\nUser's custom changes\n"
            output_file.write_text(user_content)

            # Manifest with original output hash (different from current file)
            original_content = "# Agents v1\nOriginal generated content\n"
            manifest = {
                "toolkit_version": "0.8.0",
                "toolkit_commit": "old",
                "generated_at": "2026-01-01T00:00:00Z",
                "config_hash": "sha256:test",
                "files": {
                    ".ai/AGENTS.md": {
                        "source": "universal/AGENTS.md.tmpl",
                        "template_hash": "sha256:oldoldhash12345",
                        "output_hash": compute_content_hash(original_content),
                        "category": "template-output",
                    }
                },
            }
            manifest_path = tmp_path / "output" / ".ai" / "update"
            manifest_path.mkdir(parents=True)
            manifest_file = manifest_path / ".toolkit-manifest.json"
            manifest_file.write_text(json.dumps(manifest))

            current_outputs = {
                ".ai/AGENTS.md": {
                    "source": "universal/AGENTS.md.tmpl",
                    "template_hash": new_tmpl_hash,
                    "rendered_content": "# Agents v2\nNew template content\n",
                    "category": "template-output",
                },
            }

            with patch(
                f"{_PATCH_MODULE}._collect_current_template_outputs",
                return_value=current_outputs,
            ):
                upgrade(
                    manifest_path=manifest_file,
                    templates_dir=templates_dir,
                    output_root=tmp_path / "output",
                    config={},
                    context={},
                    enabled_platforms={"agents_md"},
                    toolkit_version={"version": "0.9.0", "commit": "new"},
                    config_hash="sha256:test",
                    non_interactive=True,
                )

            # User's content should be preserved
            self.assertEqual(output_file.read_text(), user_content)


class TestUpgradeScriptAutoRegenerate(unittest.TestCase):
    """Scripts (category=script) are auto-regenerated even if user modified them."""

    def test_script_auto_regenerated_despite_user_modification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Create a script template
            templates_dir = tmp_path / "templates"
            scripts_dir = tmp_path / "setup" / "scripts"
            scripts_dir.mkdir(parents=True)
            script_file = scripts_dir / "parse-csv.py"
            script_file.write_text("#!/usr/bin/env python3\n# v2\n")

            # User-modified script on disk
            output_dir = tmp_path / "output" / ".ai" / "update" / "scripts"
            output_dir.mkdir(parents=True)
            output_file = output_dir / "parse-csv.py"
            output_file.write_text("#!/usr/bin/env python3\n# user-modified\n")

            # Manifest with old hash
            manifest = {
                "toolkit_version": "0.8.0",
                "toolkit_commit": "old",
                "generated_at": "2026-01-01T00:00:00Z",
                "config_hash": "sha256:test",
                "files": {
                    ".ai/update/scripts/parse-csv.py": {
                        "source": "setup/scripts/parse-csv.py",
                        "template_hash": "sha256:oldscripthash11",
                        "output_hash": compute_content_hash("#!/usr/bin/env python3\n# v1\n"),
                        "category": "script",
                    }
                },
            }
            manifest_path = tmp_path / "output" / ".ai" / "update"
            manifest_file = manifest_path / ".toolkit-manifest.json"
            manifest_file.write_text(json.dumps(manifest))

            # Patch _collect_current_template_outputs to return our script
            current_outputs = {
                ".ai/update/scripts/parse-csv.py": {
                    "source": "setup/scripts/parse-csv.py",
                    "template_hash": compute_file_hash(script_file),
                    "rendered_content": script_file.read_text(),
                    "category": "script",
                },
            }

            with patch(
                f"{_PATCH_MODULE}._collect_current_template_outputs",
                return_value=current_outputs,
            ):
                upgrade(
                    manifest_path=manifest_file,
                    templates_dir=templates_dir,
                    output_root=tmp_path / "output",
                    config={},
                    context={},
                    enabled_platforms=set(),
                    toolkit_version={"version": "0.9.0", "commit": "new"},
                    config_hash="sha256:test",
                )

            # Script should be overwritten with new version
            self.assertEqual(output_file.read_text(), "#!/usr/bin/env python3\n# v2\n")


class TestUpgradeNewTemplate(unittest.TestCase):
    """New templates not in manifest are offered for addition."""

    def test_new_template_added_non_interactive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Create a template for a new skill
            templates_dir = tmp_path / "templates"
            skill_dir = templates_dir / "universal" / "skills" / "new-skill"
            skill_dir.mkdir(parents=True)
            skill_tmpl = skill_dir / "SKILL.md.tmpl"
            skill_tmpl.write_text("# New Skill\n")

            # Empty manifest (no files tracked)
            output_root = tmp_path / "output"
            manifest_dir = output_root / ".ai" / "update"
            manifest_dir.mkdir(parents=True)
            manifest = {
                "toolkit_version": "0.8.0",
                "toolkit_commit": "old",
                "generated_at": "2026-01-01T00:00:00Z",
                "config_hash": "sha256:test",
                "files": {},
            }
            manifest_file = manifest_dir / ".toolkit-manifest.json"
            manifest_file.write_text(json.dumps(manifest))

            # Mock _collect_current_template_outputs to return the new skill
            current_outputs = {
                ".ai/skills/new-skill/SKILL.md": {
                    "source": "universal/skills/new-skill/SKILL.md.tmpl",
                    "template_hash": compute_file_hash(skill_tmpl),
                    "rendered_content": "# New Skill\n",
                    "category": "template-output",
                },
            }

            with patch(
                f"{_PATCH_MODULE}._collect_current_template_outputs",
                return_value=current_outputs,
            ):
                upgrade(
                    manifest_path=manifest_file,
                    templates_dir=templates_dir,
                    output_root=output_root,
                    config={},
                    context={},
                    enabled_platforms={"skills"},
                    toolkit_version={"version": "0.9.0", "commit": "new"},
                    config_hash="sha256:test",
                    non_interactive=True,
                )

            # New skill file should exist
            new_file = output_root / ".ai" / "skills" / "new-skill" / "SKILL.md"
            self.assertTrue(new_file.exists())
            self.assertEqual(new_file.read_text(), "# New Skill\n")

            # Manifest should include the new file
            updated_manifest = json.loads(manifest_file.read_text())
            self.assertIn(".ai/skills/new-skill/SKILL.md", updated_manifest["files"])


class TestUpgradeContextStubNeverTouched(unittest.TestCase):
    """Context-stub files are never modified during upgrade."""

    def test_context_stub_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            templates_dir = tmp_path / "templates"
            templates_dir.mkdir()

            # Context file on disk
            output_root = tmp_path / "output"
            ctx_dir = output_root / ".ai" / "context"
            ctx_dir.mkdir(parents=True)
            ctx_file = ctx_dir / "schema.yaml"
            ctx_file.write_text("# user-populated schema\n")

            # Manifest marks it as context-stub
            manifest_dir = output_root / ".ai" / "update"
            manifest_dir.mkdir(parents=True)
            manifest = {
                "toolkit_version": "0.8.0",
                "toolkit_commit": "old",
                "generated_at": "2026-01-01T00:00:00Z",
                "config_hash": "sha256:test",
                "files": {
                    ".ai/context/schema.yaml": {
                        "source": "universal/context/schema.yaml.tmpl",
                        "template_hash": "sha256:any",
                        "output_hash": "sha256:any",
                        "category": "context-stub",
                    }
                },
            }
            manifest_file = manifest_dir / ".toolkit-manifest.json"
            manifest_file.write_text(json.dumps(manifest))

            with patch(
                f"{_PATCH_MODULE}._collect_current_template_outputs",
                return_value={},
            ):
                upgrade(
                    manifest_path=manifest_file,
                    templates_dir=templates_dir,
                    output_root=output_root,
                    config={},
                    context={},
                    enabled_platforms=set(),
                    toolkit_version={"version": "0.9.0", "commit": "new"},
                    config_hash="sha256:test",
                    dry_run=True,
                )

            # Context file should be unchanged
            self.assertEqual(ctx_file.read_text(), "# user-populated schema\n")


class TestUpgradeDryRun(unittest.TestCase):
    """Dry-run should not write any files."""

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Template with new content
            templates_dir = tmp_path / "templates"
            tmpl_dir = templates_dir / "universal"
            tmpl_dir.mkdir(parents=True)
            tmpl_file = tmpl_dir / "AGENTS.md.tmpl"
            tmpl_file.write_text("# New content\n")
            new_tmpl_hash = compute_file_hash(tmpl_file)

            # Existing output
            output_root = tmp_path / "output"
            output_dir = output_root / ".ai"
            output_dir.mkdir(parents=True)
            output_file = output_dir / "AGENTS.md"
            old_content = "# Old content\n"
            output_file.write_text(old_content)

            # Manifest with old template hash
            manifest_dir = output_root / ".ai" / "update"
            manifest_dir.mkdir(parents=True)
            manifest = {
                "toolkit_version": "0.8.0",
                "toolkit_commit": "old",
                "generated_at": "2026-01-01T00:00:00Z",
                "config_hash": "sha256:test",
                "files": {
                    ".ai/AGENTS.md": {
                        "source": "universal/AGENTS.md.tmpl",
                        "template_hash": "sha256:oldoldhash12345",
                        "output_hash": compute_content_hash(old_content),
                        "category": "template-output",
                    }
                },
            }
            manifest_file = manifest_dir / ".toolkit-manifest.json"
            manifest_file.write_text(json.dumps(manifest))

            # Store original manifest content
            original_manifest = manifest_file.read_text()

            current_outputs = {
                ".ai/AGENTS.md": {
                    "source": "universal/AGENTS.md.tmpl",
                    "template_hash": new_tmpl_hash,
                    "rendered_content": "# New content\n",
                    "category": "template-output",
                },
            }

            with patch(
                f"{_PATCH_MODULE}._collect_current_template_outputs",
                return_value=current_outputs,
            ):
                upgrade(
                    manifest_path=manifest_file,
                    templates_dir=templates_dir,
                    output_root=output_root,
                    config={},
                    context={},
                    enabled_platforms={"agents_md"},
                    toolkit_version={"version": "0.9.0", "commit": "new"},
                    config_hash="sha256:test",
                    dry_run=True,
                )

            # File should be unchanged
            self.assertEqual(output_file.read_text(), old_content)
            # Manifest should be unchanged
            self.assertEqual(manifest_file.read_text(), original_manifest)


class TestClassifyOutputFile(unittest.TestCase):
    def test_context_stub(self) -> None:
        self.assertEqual(classify_output_file(".ai/context/schema.yaml"), "context-stub")

    def test_script_py(self) -> None:
        self.assertEqual(classify_output_file(".ai/update/scripts/parse-csv.py"), "script")

    def test_script_sh(self) -> None:
        self.assertEqual(classify_output_file(".ai/setup-links.sh"), "script")

    def test_update_meta(self) -> None:
        self.assertEqual(classify_output_file(".ai/update/README.md"), "update-meta")

    def test_template_output(self) -> None:
        self.assertEqual(classify_output_file(".ai/AGENTS.md"), "template-output")
        self.assertEqual(classify_output_file(".ai/agents/engineer.agent.md"), "template-output")
        self.assertEqual(classify_output_file(".ai/skills/security-scan/SKILL.md"), "template-output")


class TestUpgradeConflictAccept(unittest.TestCase):
    """When the user selects 'accept' on a conflict, the new content replaces theirs."""

    def test_conflict_accept_overwrites_user_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            templates_dir = tmp_path / "templates"
            tmpl_dir = templates_dir / "universal"
            tmpl_dir.mkdir(parents=True)
            tmpl_file = tmpl_dir / "AGENTS.md.tmpl"
            tmpl_file.write_text("# Agents v2\nNew template content\n")
            new_tmpl_hash = compute_file_hash(tmpl_file)

            output_root = tmp_path / "output"
            output_dir = output_root / ".ai"
            output_dir.mkdir(parents=True)
            output_file = output_dir / "AGENTS.md"
            user_content = "# Agents v1\nUser's custom changes\n"
            output_file.write_text(user_content)

            original_content = "# Agents v1\nOriginal generated content\n"
            manifest_dir = output_root / ".ai" / "update"
            manifest_dir.mkdir(parents=True)
            manifest = {
                "toolkit_version": "0.8.0",
                "toolkit_commit": "old",
                "generated_at": "2026-01-01T00:00:00Z",
                "config_hash": "sha256:test",
                "files": {
                    ".ai/AGENTS.md": {
                        "source": "universal/AGENTS.md.tmpl",
                        "template_hash": "sha256:oldoldhash12345",
                        "output_hash": compute_content_hash(original_content),
                        "category": "template-output",
                    }
                },
            }
            manifest_file = manifest_dir / ".toolkit-manifest.json"
            manifest_file.write_text(json.dumps(manifest))

            current_outputs = {
                ".ai/AGENTS.md": {
                    "source": "universal/AGENTS.md.tmpl",
                    "template_hash": new_tmpl_hash,
                    "rendered_content": "# Agents v2\nNew template content\n",
                    "category": "template-output",
                },
            }

            with patch(
                f"{_PATCH_MODULE}._collect_current_template_outputs",
                return_value=current_outputs,
            ), patch(
                f"{_PATCH_MODULE}._prompt_conflict",
                return_value="accept",
            ):
                upgrade(
                    manifest_path=manifest_file,
                    templates_dir=templates_dir,
                    output_root=output_root,
                    config={},
                    context={},
                    enabled_platforms={"agents_md"},
                    toolkit_version={"version": "0.9.0", "commit": "new"},
                    config_hash="sha256:test",
                )

            # Output should be overwritten with new content
            self.assertEqual(output_file.read_text(), "# Agents v2\nNew template content\n")
            updated_manifest = json.loads(manifest_file.read_text())
            self.assertEqual(
                updated_manifest["files"][".ai/AGENTS.md"]["output_hash"],
                compute_content_hash("# Agents v2\nNew template content\n"),
            )


class TestUpgradeRemovalAccepted(unittest.TestCase):
    """When user accepts removal of a deprecated template, the file is deleted."""

    def test_removal_accepted_deletes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            templates_dir = tmp_path / "templates"
            templates_dir.mkdir()

            output_root = tmp_path / "output"
            output_dir = output_root / ".ai"
            output_dir.mkdir(parents=True)
            deprecated_file = output_dir / "old-agent.agent.md"
            deprecated_file.write_text("# Deprecated agent\n")

            manifest_dir = output_root / ".ai" / "update"
            manifest_dir.mkdir(parents=True)
            manifest = {
                "toolkit_version": "0.8.0",
                "toolkit_commit": "old",
                "generated_at": "2026-01-01T00:00:00Z",
                "config_hash": "sha256:test",
                "files": {
                    ".ai/old-agent.agent.md": {
                        "source": "universal/old-agent.agent.md.tmpl",
                        "template_hash": "sha256:oldhash123",
                        "output_hash": compute_content_hash("# Deprecated agent\n"),
                        "category": "template-output",
                    }
                },
            }
            manifest_file = manifest_dir / ".toolkit-manifest.json"
            manifest_file.write_text(json.dumps(manifest))

            # current_outputs has no entry for this file (template removed upstream)
            with patch(
                f"{_PATCH_MODULE}._collect_current_template_outputs",
                return_value={},
            ), patch(
                f"{_PATCH_MODULE}._prompt_remove",
                return_value=True,
            ):
                upgrade(
                    manifest_path=manifest_file,
                    templates_dir=templates_dir,
                    output_root=output_root,
                    config={},
                    context={},
                    enabled_platforms=set(),
                    toolkit_version={"version": "0.9.0", "commit": "new"},
                    config_hash="sha256:test",
                )

            # File should be deleted
            self.assertFalse(deprecated_file.exists())


class TestLoadManifestCorrupted(unittest.TestCase):
    """Corrupted manifest JSON should raise an error."""

    def test_corrupted_manifest_raises_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "manifest.json"
            p.write_text("{invalid json!!!")
            with self.assertRaises(json.JSONDecodeError):
                load_manifest(p)


if __name__ == "__main__":
    unittest.main()
