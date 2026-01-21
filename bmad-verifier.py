#!/usr/bin/env python3
"""
BMAD Story Verifier - Deep validation using Claude AI
Cross-platform (Windows/Linux/Mac)

Parallel to bmad-runner.py:
- Runner:   Uses Claude to CREATE stories
- Verifier: Uses Claude to VALIDATE stories were done correctly

Usage:
    python bmad-verifier.py 5-1          # Quick validate story 5-1
    python bmad-verifier.py 5-1 --deep   # Deep validate with Claude AI
    python bmad-verifier.py 5-1 --fix    # Validate then offer to fix
    python bmad-verifier.py --help       # Show help
"""

import subprocess
import re
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.text import Text
    from rich import box
    import yaml
except ImportError:
    print("Missing dependencies. Please run:")
    print("  pip install rich pyyaml")
    sys.exit(1)

# Constants
SPRINT_STATUS_FILE = "_bmad-output/implementation-artifacts/sprint-status.yaml"
STORY_FOLDER = "_bmad-output/implementation-artifacts"
PROGRESS_FILE = ".claude/bmad-verifier-progress.json"

# Files that should be in .gitignore (temp files that shouldn't be committed)
GITIGNORE_ENTRIES = [
    "# BMAD Automation (auto-added)",
    "__pycache__/",
    "*.py[cod]",
    ".claude/bmad-progress.json",
    ".claude/bmad-automation.tracking.json",
    ".claude/bmad-verifier-progress.json",
    ".claude/bmad-stop",
]

# Quick validation steps (no Claude)
QUICK_STEPS = [
    {"id": 1, "name": "Story file exists", "key": "file_exists"},
    {"id": 2, "name": "Status = done in file", "key": "status_done"},
    {"id": 3, "name": "All tasks marked [x]", "key": "tasks_done"},
    {"id": 4, "name": "Git commit exists", "key": "git_commit"},
    {"id": 5, "name": "Sprint-status = done", "key": "sprint_done"},
]


class BMadVerifier:
    def __init__(self, story_filter: str = None, deep_mode: bool = False, interactive: bool = False):
        self.console = Console()
        self.story_filter = story_filter
        self.deep_mode = deep_mode
        self.interactive = interactive  # Show action menu after verify
        self.sprint_data = {}
        self.results = []

    def _ensure_gitignore(self):
        """Ensure .gitignore has entries for temp files (auto-add if missing)"""
        gitignore_path = Path(".gitignore")

        # Read existing content
        existing_content = ""
        if gitignore_path.exists():
            existing_content = gitignore_path.read_text(encoding="utf-8")

        # Check which entries are missing
        missing_entries = []
        for entry in GITIGNORE_ENTRIES:
            if entry not in existing_content:
                missing_entries.append(entry)

        # Add missing entries
        if missing_entries:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                if existing_content and not existing_content.endswith("\n"):
                    f.write("\n")
                f.write("\n".join(missing_entries) + "\n")
            self.console.print(f"[dim]Added {len(missing_entries)} entries to .gitignore[/dim]")

    def _load_sprint_status(self) -> dict:
        """Load sprint-status.yaml"""
        try:
            with open(SPRINT_STATUS_FILE, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data.get("development_status", {})
        except Exception as e:
            self.console.print(f"[red]Error loading sprint-status.yaml: {e}[/red]")
            return {}

    def _is_story_id(self, key: str) -> bool:
        """Check if a key is a story ID"""
        if key.startswith("epic-"):
            return False
        if key.endswith("-retrospective"):
            return False
        return bool(re.match(r"^\d+-\d+", key))

    def _matches_filter(self, key: str) -> bool:
        """Check if story matches the filter"""
        if not self.story_filter:
            return True
        if "-" in self.story_filter:
            return key.startswith(self.story_filter + "-")
        else:
            return key.startswith(self.story_filter + "-")

    def _parse_tasks_from_story(self, content: str) -> list:
        """Parse task list from story file content"""
        tasks = []
        # Match lines like "- [ ] Task 1: Description" or "- [x] Task 1: Description"
        pattern = r"^-\s*\[([ x])\]\s*(Task\s*\d+[^:\n]*:?[^\n]*)"
        matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
        for checked, task_text in matches:
            # Only get main tasks, not subtasks (subtasks are indented)
            tasks.append({
                "text": task_text.strip(),
                "checked": checked.lower() == "x"
            })
        return tasks

    def _quick_validate(self, story_id: str, sprint_status: str) -> dict:
        """Quick validation without Claude"""
        story_file = Path(STORY_FOLDER) / f"{story_id}.md"
        result = {
            "id": story_id,
            "sprint_status": sprint_status,
            "steps": {},
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "tasks": [],
            "deep_results": None,
        }

        # Step 1: File exists
        file_exists = story_file.exists()
        result["steps"]["file_exists"] = {
            "passed": file_exists,
            "message": "File found" if file_exists else "File not found"
        }

        if not file_exists:
            for step in QUICK_STEPS[1:]:
                result["steps"][step["key"]] = {"passed": None, "message": "Skipped"}
                result["skipped"] += 1
            result["failed"] = 1
            return result

        content = story_file.read_text(encoding="utf-8")

        # Step 2: Status = done
        status_match = re.search(r"^Status:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
        file_status = status_match.group(1).strip().lower() if status_match else "unknown"
        result["steps"]["status_done"] = {
            "passed": file_status == "done",
            "message": f"Status: {file_status}"
        }

        # Step 3: Tasks marked
        unchecked = len(re.findall(r"^-\s*\[\s*\]", content, re.MULTILINE))
        checked = len(re.findall(r"^-\s*\[x\]", content, re.MULTILINE | re.IGNORECASE))
        total = unchecked + checked
        result["steps"]["tasks_done"] = {
            "passed": unchecked == 0 and total > 0,
            "message": f"{checked}/{total} tasks"
        }
        result["tasks"] = self._parse_tasks_from_story(content)

        # Step 4: Git commit (search for standardized commit format)
        try:
            short_id = "-".join(story_id.split("-")[:2])
            # Search for standardized format: "feat(story): complete 5-9" or "fix(story): update 5-9"
            git_result = subprocess.run(
                f'git log --oneline | grep -E "(feat|fix)\\(story\\):.*{short_id}"',
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            has_commit = bool(git_result.stdout.strip())
            result["steps"]["git_commit"] = {
                "passed": has_commit,
                "message": "Commit found" if has_commit else "No commit"
            }
        except Exception:
            result["steps"]["git_commit"] = {"passed": None, "message": "Git error"}
            result["skipped"] += 1

        # Step 5: Sprint status
        result["steps"]["sprint_done"] = {
            "passed": sprint_status == "done",
            "message": f"Sprint: {sprint_status}"
        }

        # Count results
        for step_result in result["steps"].values():
            if step_result["passed"] is True:
                result["passed"] += 1
            elif step_result["passed"] is False:
                result["failed"] += 1

        return result

    def _deep_validate_with_claude(self, story_id: str, result: dict) -> dict:
        """Deep validation using Claude to check if task code exists"""
        story_file = Path(STORY_FOLDER) / f"{story_id}.md"

        if not story_file.exists():
            return result

        # Build prompt for Claude
        prompt = f'''You are validating if story tasks were implemented. Check the ACTUAL codebase.

STORY FILE: {story_file}

Read the story file and for EACH main task (Task 1, Task 2, etc.):
1. Read what files/code should be created
2. Check if those files ACTUALLY exist in the codebase
3. Check if the code implements what the task describes

Output JSON format ONLY (no markdown, no explanation):
{{
  "tasks": [
    {{
      "task_id": "Task 1",
      "description": "short description",
      "expected_files": ["file1.ts", "file2.ts"],
      "files_found": ["file1.ts"],
      "files_missing": ["file2.ts"],
      "implemented": true/false,
      "evidence": "brief evidence why"
    }}
  ],
  "overall_implemented": true/false,
  "summary": "one line summary"
}}

IMPORTANT:
- Only output valid JSON
- Check REAL files in the codebase
- Be thorough but concise
'''

        try:
            # Show loading spinner
            with Live(
                Panel(
                    Text.assemble(
                        ("🤖 ", "cyan"),
                        ("Claude is analyzing ", "white"),
                        (story_id, "bold cyan"),
                        (" tasks...\n\n", "white"),
                        ("Reading story file → ", "dim"),
                        ("Checking codebase → ", "dim"),
                        ("Validating implementation", "dim"),
                    ),
                    title="[yellow]Deep Validation[/yellow]",
                    box=box.ROUNDED,
                    border_style="yellow"
                ),
                console=self.console,
                refresh_per_second=4
            ):
                # Call Claude CLI
                process = subprocess.run(
                    ["claude", "-p", prompt],
                    capture_output=True,
                    text=True,
                    timeout=120
                )

            output = process.stdout.strip()

            # Try to parse JSON from output
            json_match = re.search(r'\{[\s\S]*\}', output)
            if json_match:
                deep_result = json.loads(json_match.group())
                result["deep_results"] = deep_result

                if deep_result.get("overall_implemented"):
                    result["deep_passed"] = True
                else:
                    result["deep_passed"] = False
            else:
                result["deep_results"] = {"error": "Could not parse Claude response", "raw": output[:500]}
                result["deep_passed"] = None

        except subprocess.TimeoutExpired:
            result["deep_results"] = {"error": "Claude timeout (>120s)"}
            result["deep_passed"] = None
        except json.JSONDecodeError as e:
            result["deep_results"] = {"error": f"JSON parse error: {e}", "raw": output[:500] if 'output' in dir() else ""}
            result["deep_passed"] = None
        except FileNotFoundError:
            result["deep_results"] = {"error": "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-cli"}
            result["deep_passed"] = None
        except Exception as e:
            result["deep_results"] = {"error": str(e)}
            result["deep_passed"] = None

        return result

    def verify(self):
        """Run verification"""
        self.sprint_data = self._load_sprint_status()

        if not self.sprint_data:
            self.console.print("[red]No development_status found[/red]")
            return

        for key, sprint_status in self.sprint_data.items():
            if not self._is_story_id(key):
                continue
            if not self._matches_filter(key):
                continue
            if sprint_status == "backlog" and not self.story_filter:
                continue

            # Quick validation first
            result = self._quick_validate(key, sprint_status)

            # Deep validation with Claude if requested
            if self.deep_mode:
                result = self._deep_validate_with_claude(key, result)

            self.results.append(result)

    def _build_quick_table(self, result: dict) -> Table:
        """Build quick validation table"""
        table = Table(
            title=f"[bold]{result['id']}[/bold]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
            title_justify="left"
        )

        table.add_column("Step", width=5, justify="center")
        table.add_column("Check", width=25)
        table.add_column("Result", width=8, justify="center")
        table.add_column("Details", width=25)

        for step in QUICK_STEPS:
            step_result = result["steps"].get(step["key"], {})
            passed = step_result.get("passed")
            message = step_result.get("message", "")

            if passed is True:
                icon = "[green]✓ PASS[/green]"
            elif passed is False:
                icon = "[red]✗ FAIL[/red]"
            else:
                icon = "[dim]○ SKIP[/dim]"

            table.add_row(str(step["id"]), step["name"], icon, f"[dim]{message}[/dim]")

        return table

    def _build_deep_table(self, result: dict) -> Table:
        """Build deep validation table for tasks"""
        table = Table(
            title="[bold cyan]🤖 Claude Deep Validation[/bold cyan]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )

        table.add_column("Task", width=10)
        table.add_column("Description", width=30)
        table.add_column("Implemented?", width=12, justify="center")
        table.add_column("Evidence", width=35)

        deep = result.get("deep_results", {})

        if "error" in deep:
            table.add_row("[red]Error[/red]", deep["error"], "", "")
            return table

        tasks = deep.get("tasks", [])
        for task in tasks:
            impl = task.get("implemented", False)
            icon = "[green]✓ YES[/green]" if impl else "[red]✗ NO[/red]"
            table.add_row(
                task.get("task_id", "?"),
                task.get("description", "")[:30],
                icon,
                task.get("evidence", "")[:35]
            )

        return table

    def _build_summary(self, result: dict) -> Panel:
        """Build summary panel"""
        lines = []

        # Quick validation summary
        quick_status = "[green]✓ PASS[/green]" if result["failed"] == 0 else "[red]✗ FAIL[/red]"
        lines.append(f"Quick Check: {quick_status} ({result['passed']}/{len(QUICK_STEPS)})")

        # Deep validation summary
        if self.deep_mode and result.get("deep_results"):
            deep = result["deep_results"]
            if "error" not in deep:
                deep_status = "[green]✓ IMPLEMENTED[/green]" if deep.get("overall_implemented") else "[red]✗ NOT IMPLEMENTED[/red]"
                lines.append(f"Deep Check:  {deep_status}")
                if deep.get("summary"):
                    lines.append(f"[dim]{deep['summary']}[/dim]")

        return Panel("\n".join(lines), title="Summary", box=box.ROUNDED, border_style="blue")

    def _build_recommendations(self, result: dict) -> Panel:
        """Build recommendations panel based on validation results"""
        recommendations = []
        story_id = result["id"]
        steps = result["steps"]

        # Check each failure and recommend action
        if not steps.get("status_done", {}).get("passed"):
            recommendations.append(f"[yellow]→[/yellow] Update story file: set [bold]Status: done[/bold]")

        if not steps.get("tasks_done", {}).get("passed"):
            recommendations.append(f"[yellow]→[/yellow] Mark all tasks as completed: [bold]- [x][/bold]")

        if not steps.get("git_commit", {}).get("passed"):
            short_id = "-".join(story_id.split("-")[:2])
            recommendations.append(f"[yellow]→[/yellow] Create git commit: [bold]git commit -m \"feat(story): complete {short_id}\"[/bold]")

        if not steps.get("sprint_done", {}).get("passed"):
            recommendations.append(f"[yellow]→[/yellow] Update sprint-status.yaml: set [bold]{story_id}: done[/bold]")

        # Deep validation specific
        if self.deep_mode and result.get("deep_results"):
            deep = result["deep_results"]
            if "error" not in deep:
                if deep.get("overall_implemented"):
                    if recommendations:
                        recommendations.insert(0, "[green]✓ Code is implemented! Just need to update tracking files:[/green]\n")
                else:
                    # Find which tasks are not implemented
                    missing_tasks = [t["task_id"] for t in deep.get("tasks", []) if not t.get("implemented")]
                    if missing_tasks:
                        recommendations.append(f"[red]→[/red] Implement missing tasks: [bold]{', '.join(missing_tasks)}[/bold]")

        if not recommendations:
            return Panel(
                "[green]✓ All checks passed! No action needed.[/green]",
                title="✅ Next Steps",
                box=box.ROUNDED,
                border_style="green"
            )

        # Add auto-fix hint if code is done but files need update
        if self.deep_mode and result.get("deep_passed") and result["failed"] > 0:
            recommendations.append("")
            recommendations.append("[dim]Hint: You can manually update the story file and sprint-status.yaml,[/dim]")
            recommendations.append("[dim]      or create a script to auto-fix these tracking files.[/dim]")

        return Panel(
            "\n".join(recommendations),
            title="📋 Next Steps",
            box=box.ROUNDED,
            border_style="yellow"
        )

    def _determine_available_actions(self, result: dict) -> list:
        """Determine what actions are available based on validation results"""
        actions = []
        steps = result["steps"]
        story_id = result["id"]

        file_exists = steps.get("file_exists", {}).get("passed", False)
        all_passed = result["failed"] == 0
        code_implemented = result.get("deep_passed", None)  # None = not checked, True/False = checked

        # Scenario 1: All checks passed - no action needed
        if all_passed:
            return []

        # Scenario 2: File doesn't exist - offer to create story
        if not file_exists:
            actions.append({
                "key": "1",
                "label": "[1] Create Story",
                "action": "create",
                "description": f"Create story file for {story_id}",
                "command": f"/bmad:bmm:workflows:create-story {story_id}"
            })

        # Scenario 3: Code is verified implemented (deep check passed) - offer fix
        elif code_implemented is True and result["failed"] > 0:
            actions.append({
                "key": "1",
                "label": "[1] Fix Story",
                "action": "fix",
                "description": "Update story file status, mark tasks [x], update sprint-status",
                "command": f"Update {story_id}: set Status: done, mark all tasks [x], update sprint-status.yaml"
            })

        # Scenario 4: File exists but we haven't verified code (no deep check yet)
        elif file_exists and code_implemented is None:
            # Recommend deep check first before fixing
            actions.append({
                "key": "1",
                "label": "[1] Deep Check First",
                "action": "deep_check",
                "description": "Verify code is actually implemented before fixing",
                "command": f"Run deep validation for {story_id}"
            })
            actions.append({
                "key": "2",
                "label": "[2] Run Dev",
                "action": "dev",
                "description": f"Develop/implement story {story_id} (if not done)",
                "command": f"/bmad:bmm:workflows:dev-story {story_id}"
            })
            actions.append({
                "key": "3",
                "label": "[3] Fix Story (skip check)",
                "action": "fix",
                "description": "Update tracking files (ONLY if you're sure code is done)",
                "command": f"Update {story_id} tracking files"
            })

        # Scenario 5: Deep check failed - code not implemented, offer to develop
        elif file_exists and code_implemented is False:
            actions.append({
                "key": "1",
                "label": "[1] Run Dev",
                "action": "dev",
                "description": f"Develop/implement story {story_id}",
                "command": f"/bmad:bmm:workflows:dev-story {story_id}"
            })

        # Always add exit option
        actions.append({
            "key": str(len(actions) + 1),
            "label": f"[{len(actions) + 1}] Exit",
            "action": "exit",
            "description": "Exit without action",
            "command": None
        })

        return actions

    def _show_action_menu(self, result: dict) -> str:
        """Show interactive action menu and get user choice"""
        actions = self._determine_available_actions(result)

        if not actions:
            return None

        # Build menu table
        table = Table(
            title="[bold yellow]🎯 Available Actions[/bold yellow]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )
        table.add_column("Option", width=15)
        table.add_column("Description", width=50)

        for action in actions:
            if action["action"] == "exit":
                table.add_row(
                    f"[dim]{action['label']}[/dim]",
                    f"[dim]{action['description']}[/dim]"
                )
            else:
                table.add_row(
                    action['label'],
                    action['description']
                )

        self.console.print()
        self.console.print(table)
        self.console.print()

        # Get user input
        try:
            choice = input("Select action (number): ").strip()
        except (KeyboardInterrupt, EOFError):
            return "exit"

        # Find selected action
        for action in actions:
            if choice == action["key"] or choice == action["key"].strip("[]"):
                return action

        return None

    def _execute_action(self, action: dict, result: dict):
        """Execute the selected action using Claude"""
        if not action or action["action"] == "exit":
            self.console.print("[dim]No action taken.[/dim]")
            return

        story_id = result["id"]
        action_type = action["action"]

        # Build the appropriate prompt based on action
        if action_type == "create":
            prompt = f'''Create story file for {story_id}.

Call /bmad:bmm:workflows:create-story with story ID: {story_id}

After creating, confirm the file was created successfully.
'''
        elif action_type == "dev":
            prompt = f'''Develop/implement story {story_id}.

Call /bmad:bmm:workflows:dev-story with story ID: {story_id}

Complete all implementation tasks in the story.
'''
        elif action_type == "fix":
            prompt = f'''Fix the tracking files for story {story_id}. The code is already implemented, but tracking files need updating.

1. Read the story file at _bmad-output/implementation-artifacts/{story_id}.md
2. Update the story file:
   - Set Status: done
   - Mark ALL tasks as completed: - [x]
   - Fill the Dev Agent Record section if empty
3. Update _bmad-output/implementation-artifacts/sprint-status.yaml:
   - Set {story_id}: done
4. Git commit with message: "fix(story): update {story_id} tracking"

Only update tracking - do NOT modify any source code.
'''
        elif action_type == "deep_check":
            # Run deep validation and then show action menu with new results
            self.console.print()
            self.console.print(Panel(
                f"[bold]Running deep validation for [cyan]{story_id}[/cyan]...[/bold]\n\n"
                f"[dim]Claude will check if code is actually implemented.[/dim]",
                title="[yellow]🔍 Deep Check[/yellow]",
                box=box.ROUNDED,
                border_style="yellow"
            ))

            # Re-run validation with deep mode
            new_result = self._quick_validate(story_id, result["sprint_status"])
            new_result = self._deep_validate_with_claude(story_id, new_result)

            # Show deep validation results
            self.console.print()
            self.console.print(self._build_deep_table(new_result))
            self.console.print()
            self.console.print(self._build_summary(new_result))
            self.console.print()
            self.console.print(self._build_recommendations(new_result))

            # Show action menu again with deep results
            new_action = self._show_action_menu(new_result)
            if new_action and new_action != "exit":
                self._execute_action(new_action, new_result)
            return
        else:
            self.console.print(f"[red]Unknown action: {action_type}[/red]")
            return

        # Show what will be executed
        self.console.print()
        self.console.print(Panel(
            f"[bold]Action:[/bold] {action['label']}\n"
            f"[bold]Story:[/bold] {story_id}\n\n"
            f"[dim]Claude will execute:[/dim]\n{action['description']}",
            title="[yellow]⚡ Confirm Execution[/yellow]",
            box=box.ROUNDED,
            border_style="yellow"
        ))

        try:
            confirm = input("\nProceed? (y/n): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            self.console.print("\n[dim]Cancelled.[/dim]")
            return

        if confirm not in ['y', 'yes']:
            self.console.print("[dim]Cancelled.[/dim]")
            return

        # Execute with Claude
        self.console.print()
        with Live(
            Panel(
                Text.assemble(
                    ("🤖 ", "cyan"),
                    ("Claude is executing ", "white"),
                    (action['label'], "bold yellow"),
                    (" for ", "white"),
                    (story_id, "bold cyan"),
                    ("...", "white"),
                ),
                title="[yellow]Executing[/yellow]",
                box=box.ROUNDED,
                border_style="yellow"
            ),
            console=self.console,
            refresh_per_second=4
        ):
            try:
                process = subprocess.run(
                    ["claude", "--dangerously-skip-permissions", "-p", prompt],
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 min timeout
                )
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                self.console.print("[red]Timeout: Claude took too long (>5 min)[/red]")
                return
            except FileNotFoundError:
                self.console.print("[red]Error: Claude CLI not found[/red]")
                return

        # Show result
        if exit_code == 0:
            self.console.print(Panel(
                f"[green]✓ Action completed successfully![/green]\n\n"
                f"[dim]You can run the verifier again to confirm:[/dim]\n"
                f"[white]python bmad-verifier.py {story_id}[/white]",
                title="[green]✅ Done[/green]",
                box=box.ROUNDED,
                border_style="green"
            ))
        else:
            self.console.print(Panel(
                f"[yellow]⚠ Action completed with warnings (exit code: {exit_code})[/yellow]\n\n"
                f"[dim]Check the output above for details.[/dim]",
                title="[yellow]⚠ Warning[/yellow]",
                box=box.ROUNDED,
                border_style="yellow"
            ))

    def run(self):
        """Main run method"""
        # Ensure temp files are in .gitignore
        self._ensure_gitignore()

        self.console.print()

        mode_parts = []
        if self.deep_mode:
            mode_parts.append("[yellow]DEEP[/yellow]")
        else:
            mode_parts.append("[cyan]QUICK[/cyan]")
        if self.interactive:
            mode_parts.append("[magenta]+INTERACTIVE[/magenta]")
        mode = " ".join(mode_parts)

        filter_text = self.story_filter if self.story_filter else "all non-backlog"

        self.console.print(Panel(
            f"[bold cyan]BMAD Story Verifier[/bold cyan]\n\n"
            f"[white]Mode:[/white] {mode}\n"
            f"[white]Validating:[/white] [bold]{filter_text}[/bold]",
            box=box.DOUBLE,
            border_style="cyan"
        ))
        self.console.print()

        # Run verification
        self.verify()

        if not self.results:
            self.console.print("[yellow]No stories found matching filter[/yellow]")
            return

        # Show results
        for result in self.results:
            # Quick validation table
            self.console.print(self._build_quick_table(result))

            # Deep validation table if available
            if self.deep_mode and result.get("deep_results"):
                self.console.print()
                self.console.print(self._build_deep_table(result))

            # Summary
            self.console.print()
            self.console.print(self._build_summary(result))

            # Recommendations
            self.console.print()
            self.console.print(self._build_recommendations(result))
            self.console.print()

            # Interactive action menu (only for single story in interactive mode)
            if self.interactive and len(self.results) == 1:
                action = self._show_action_menu(result)
                if action and action != "exit":
                    self._execute_action(action, result)


def main():
    parser = argparse.ArgumentParser(
        description="BMAD Story Verifier - Validate stories with optional Claude AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  Quick (default): Check file, status, tasks, git, sprint
  Deep (--deep):   Use Claude AI to verify actual code implementation
  Interactive (-i): Show action menu to fix/create/develop after validation

Examples:
  python bmad-verifier.py 2-1              # Quick validate story 2-1
  python bmad-verifier.py 2-1 --deep       # Deep validate with Claude
  python bmad-verifier.py 2-1 -i           # Quick + interactive actions
  python bmad-verifier.py 2-1 --deep -i    # Deep + interactive actions
  python bmad-verifier.py 2 --deep         # Deep validate all epic 2
        """
    )
    parser.add_argument(
        "story",
        nargs="?",
        default=None,
        help="Story ID to validate (e.g. '2-1' or '2' for epic)"
    )
    parser.add_argument(
        "-d", "--deep",
        action="store_true",
        help="Use Claude AI for deep code validation"
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Show interactive action menu after validation (fix/create/dev)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (for programmatic use)"
    )

    args = parser.parse_args()

    if args.deep and not args.story:
        print("Error: --deep mode requires a specific story ID")
        print("Usage: python bmad-verifier.py 2-1 --deep")
        sys.exit(1)

    if args.interactive and not args.story:
        print("Error: --interactive mode requires a specific story ID")
        print("Usage: python bmad-verifier.py 2-1 -i")
        sys.exit(1)

    if args.json and not args.story:
        print("Error: --json mode requires a specific story ID")
        print("Usage: python bmad-verifier.py 2-1 --json")
        sys.exit(1)

    verifier = BMadVerifier(story_filter=args.story, deep_mode=args.deep, interactive=args.interactive)

    if args.json:
        # JSON output mode for programmatic use
        verifier.verify()
        if verifier.results:
            result = verifier.results[0]
            output = {
                "story_id": result["id"],
                "passed": result["failed"] == 0,
                "checks": {
                    "file_exists": result["steps"].get("file_exists", {}).get("passed", False),
                    "status_done": result["steps"].get("status_done", {}).get("passed", False),
                    "tasks_done": result["steps"].get("tasks_done", {}).get("passed", False),
                    "git_commit": result["steps"].get("git_commit", {}).get("passed", False),
                    "sprint_done": result["steps"].get("sprint_done", {}).get("passed", False),
                },
                "deep_check": None,
                "code_implemented": None,
            }
            if result.get("deep_results"):
                deep = result["deep_results"]
                if "error" not in deep:
                    output["deep_check"] = True
                    output["code_implemented"] = deep.get("overall_implemented", False)
                    output["deep_summary"] = deep.get("summary", "")
                else:
                    output["deep_check"] = False
                    output["deep_error"] = deep.get("error", "")
            print(json.dumps(output))
        else:
            print(json.dumps({"error": "No results", "story_id": args.story}))
    else:
        verifier.run()


if __name__ == "__main__":
    main()
