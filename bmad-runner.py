#!/usr/bin/env python3
"""
BMAD Story Automation Runner - Interactive CLI with Rich UI
Cross-platform (Windows/Linux/Mac)

Usage:
    python bmad-runner.py                    # Default 5 iterations
    python bmad-runner.py --iterations 3    # Custom iterations
    python bmad-runner.py --story 5-2       # Process specific story
    python bmad-runner.py --demo            # Demo mode (simulated, no Claude)
    python bmad-runner.py --help            # Show help
"""

import subprocess
import json
import time
import sys
import os
import signal
import argparse
import random
from pathlib import Path
from datetime import datetime
from threading import Thread, Event

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
    from rich.style import Style
    from rich import box
except ImportError:
    print("Missing dependencies. Please run:")
    print("  pip install rich")
    sys.exit(1)

# Constants
PROGRESS_FILE = ".claude/bmad-progress.json"
STOP_FILE = ".claude/bmad-stop"
TRACKING_FILE = ".claude/bmad-automation.tracking.json"

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

STEPS = [
    {"id": 1, "name": "Read workflow status", "key": "read_status"},
    {"id": 2, "name": "Create story", "key": "create_story"},
    {"id": 3, "name": "Develop story", "key": "develop_story"},
    {"id": 4, "name": "Run tests", "key": "run_tests"},
    {"id": 5, "name": "Code review", "key": "code_review"},
    {"id": 6, "name": "Fix issues", "key": "fix_issues"},
    {"id": 7, "name": "Run tests until pass", "key": "run_tests_final"},
    {"id": 8, "name": "Update story status", "key": "update_story"},
    {"id": 9, "name": "Update sprint-status.yaml", "key": "update_sprint"},
    {"id": 10, "name": "Update bmm-workflow-status.yaml", "key": "update_bmm"},
    {"id": 11, "name": "Git commit", "key": "git_commit"},
]

# The prompt that instructs Claude to write progress
# Based on working PowerShell script - simple and direct
CLAUDE_PROMPT_AUTO = '''EXECUTE ALL STEPS IN ORDER - DO NOT STOP EARLY.

After completing EACH step, write progress to .claude/bmad-progress.json:
{"story_id": "X", "current_step": N, "status": "done", "message": "what you did"}

STEP 1: Read _bmad-output/implementation-artifacts/sprint-status.yaml
        Find first story with status "backlog" → save as STORY_ID
        Write progress with story_id

STEP 2: Call /bmad:bmm:workflows:create-story with STORY_ID to create the story file
        Write progress

STEP 3: Call /bmad:bmm:workflows:dev-story with STORY_ID to implement the code
        Write progress

STEP 4: Run tests (pnpm test or npm test or the appropriate test command)
        Write progress

STEP 5: Call /bmad:bmm:workflows:code-review to review the code
        Write progress

STEP 6: Fix any issues found in code review
        Write progress

STEP 7: Run tests again until ALL PASS
        Write progress

STEP 8: Update story file: set status to "done", mark all tasks [x], fill Dev Agent Record
        Write progress

STEP 9: Update _bmad-output/implementation-artifacts/sprint-status.yaml: mark STORY_ID as "done"
        Write progress

STEP 10: Update _bmad-output/planning-artifacts/bmm-workflow-status.yaml with completion info
         Write progress

STEP 11: Git add -A and commit with message: "feat(story): complete SHORT_ID"
         (SHORT_ID is like "5-9" - the first two parts of STORY_ID)
         Write progress

IMPORTANT: Complete ALL 11 steps. Do not stop after creating the story.
'''

# Prompt for manual story selection
CLAUDE_PROMPT_MANUAL = '''EXECUTE ALL STEPS IN ORDER - DO NOT STOP EARLY.

After completing EACH step, write progress to .claude/bmad-progress.json:
{{"story_id": "{story_id}", "current_step": N, "status": "done", "message": "what you did"}}

STORY_ID = {story_id}

STEP 1: Confirm story {story_id} exists in _bmad-output/implementation-artifacts/sprint-status.yaml
        Write progress with story_id

STEP 2: Call /bmad:bmm:workflows:create-story with {story_id} to create the story file
        Write progress

STEP 3: Call /bmad:bmm:workflows:dev-story with {story_id} to implement the code
        Write progress

STEP 4: Run tests (pnpm test or npm test or the appropriate test command)
        Write progress

STEP 5: Call /bmad:bmm:workflows:code-review to review the code
        Write progress

STEP 6: Fix any issues found in code review
        Write progress

STEP 7: Run tests again until ALL PASS
        Write progress

STEP 8: Update story file: set status to "done", mark all tasks [x], fill Dev Agent Record
        Write progress

STEP 9: Update _bmad-output/implementation-artifacts/sprint-status.yaml: mark {story_id} as "done"
        Write progress

STEP 10: Update _bmad-output/planning-artifacts/bmm-workflow-status.yaml with completion info
         Write progress

STEP 11: Git add -A and commit with message: "feat(story): complete {story_id}"
         Write progress

IMPORTANT: Complete ALL 11 steps. Do not stop after creating the story.
'''


class BMadRunner:
    def __init__(self, max_iterations: int = 5, demo_mode: bool = False, story_id: str = None):
        self.console = Console()
        # Support both single story and story + continue modes
        self.max_iterations = max_iterations
        self.demo_mode = demo_mode
        self.start_story_id = story_id  # Starting story (can continue from here)
        self.current_story_id = story_id  # Current story being processed
        self.current_iteration = 0
        self.current_step = 0
        self.story_id = "..."
        self.step_status = {step["key"]: "pending" for step in STEPS}
        self.step_times = {}
        self.start_time = None
        self.iteration_start_time = None
        self.stop_event = Event()
        self.last_message = ""
        self.claude_process = None

        # Watchdog settings
        self.last_progress_time = None
        self.watchdog_timeout = 300  # 5 minutes without progress = hung
        self.step_timeout = 600  # 10 minutes max per step
        self.max_step_retries = 2  # Max retry attempts for incomplete steps

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, self._signal_handler)

    def _get_next_story_id(self, current_id: str) -> str:
        """Calculate the next story ID (e.g., 5-10 -> 5-11)"""
        if not current_id:
            return None
        parts = current_id.split("-")
        if len(parts) >= 2:
            try:
                epic = parts[0]
                story_num = int(parts[1])
                return f"{epic}-{story_num + 1}"
            except ValueError:
                return None
        return None

    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        self.console.print("\n[yellow]Received stop signal. Cleaning up...[/yellow]")
        self.stop_event.set()
        if self.claude_process:
            self.claude_process.terminate()
        self._cleanup()
        sys.exit(0)

    def _cleanup(self):
        """Cleanup temporary files"""
        for f in [PROGRESS_FILE, TRACKING_FILE, STOP_FILE]:
            try:
                Path(f).unlink(missing_ok=True)
            except:
                pass

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

    def _ensure_dirs(self):
        """Ensure .claude directory exists and .gitignore is configured"""
        Path(".claude").mkdir(exist_ok=True)
        # Remove old stop file
        Path(STOP_FILE).unlink(missing_ok=True)
        # Ensure temp files are in .gitignore
        self._ensure_gitignore()

    def _read_progress(self) -> dict:
        """Read progress from JSON file"""
        try:
            if Path(PROGRESS_FILE).exists():
                with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return {}

    def _get_status_icon(self, status: str) -> str:
        """Get icon for status"""
        icons = {
            "pending": "[dim]⬚[/dim]",
            "running": "[yellow]⏳[/yellow]",
            "done": "[green]✓[/green]",
            "error": "[red]✗[/red]",
        }
        return icons.get(status, "⬚")

    def _get_status_style(self, status: str) -> str:
        """Get style for status"""
        styles = {
            "pending": "dim",
            "running": "yellow bold",
            "done": "green",
            "error": "red",
        }
        return styles.get(status, "")

    def _build_header(self) -> Panel:
        """Build header panel"""
        elapsed = ""
        if self.start_time:
            delta = datetime.now() - self.start_time
            elapsed = f"{int(delta.total_seconds() // 60):02d}:{int(delta.total_seconds() % 60):02d}"

        header_text = Text()
        header_text.append("🚀 BMAD Story Automation\n", style="bold cyan")
        header_text.append(f"Story: ", style="dim")
        header_text.append(f"{self.story_id}", style="bold white")
        header_text.append(f"  │  ", style="dim")
        header_text.append(f"Iteration: ", style="dim")
        header_text.append(f"{self.current_iteration}/{self.max_iterations}", style="bold white")
        header_text.append(f"  │  ", style="dim")
        header_text.append(f"Elapsed: ", style="dim")
        header_text.append(f"{elapsed}", style="bold white")

        return Panel(header_text, box=box.ROUNDED, border_style="cyan")

    def _build_steps_table(self) -> Table:
        """Build steps progress table"""
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        table.add_column("Icon", width=3)
        table.add_column("Step", width=30)
        table.add_column("Status", width=15)
        table.add_column("Time", width=10, justify="right")

        for step in STEPS:
            status = self.step_status.get(step["key"], "pending")
            icon = self._get_status_icon(status)
            style = self._get_status_style(status)

            # Get time for this step
            step_time = self.step_times.get(step["key"], "")
            if step_time:
                step_time = f"{step_time:.1f}s"

            # Status text
            status_text = {
                "pending": "[dim]Pending[/dim]",
                "running": "[yellow]Running...[/yellow]",
                "done": "[green]Done[/green]",
                "error": "[red]Error[/red]",
            }.get(status, "")

            table.add_row(
                icon,
                f"[{style}]Step {step['id']}: {step['name']}[/{style}]",
                status_text,
                f"[dim]{step_time}[/dim]"
            )

        return table

    def _build_progress_bar(self) -> Panel:
        """Build overall progress bar"""
        completed = sum(1 for s in self.step_status.values() if s == "done")
        total = len(STEPS)
        percentage = (completed / total) * 100

        # Build progress bar manually
        bar_width = 40
        filled = int(bar_width * completed / total)
        bar = "█" * filled + "░" * (bar_width - filled)

        progress_text = Text()
        progress_text.append(f"Progress: ", style="dim")
        progress_text.append(f"[cyan]{bar}[/cyan]")
        progress_text.append(f"  {percentage:.0f}%  ", style="bold")
        progress_text.append(f"[{completed}/{total} steps]", style="dim")

        return Panel(progress_text, box=box.SIMPLE)

    def _build_message_panel(self) -> Panel:
        """Build message/status panel"""
        if self.last_message:
            return Panel(
                f"[dim]{self.last_message}[/dim]",
                title="[dim]Status[/dim]",
                box=box.ROUNDED,
                border_style="dim"
            )
        return Panel("[dim]Waiting for Claude...[/dim]", box=box.SIMPLE)

    def _build_footer(self) -> Text:
        """Build footer with controls"""
        footer = Text()
        footer.append("Controls: ", style="dim")
        footer.append("Ctrl+C", style="yellow")
        footer.append(" to stop  │  ", style="dim")
        footer.append("touch .claude/bmad-stop", style="yellow")
        footer.append(" to stop gracefully", style="dim")
        return footer

    def _build_display(self) -> Panel:
        """Build the full display"""
        layout = Table.grid(padding=0)
        layout.add_column()

        layout.add_row(self._build_header())
        layout.add_row("")
        layout.add_row(self._build_steps_table())
        layout.add_row("")
        layout.add_row(self._build_progress_bar())
        layout.add_row(self._build_message_panel())
        layout.add_row("")
        layout.add_row(self._build_footer())

        return Panel(
            layout,
            title="[bold white]BMAD Automation[/bold white]",
            box=box.DOUBLE,
            border_style="blue"
        )

    def _monitor_progress(self, live: Live):
        """Monitor progress file and update display with watchdog"""
        last_step = 0
        step_start_time = time.time()
        self.last_progress_time = time.time()

        while not self.stop_event.is_set():
            progress = self._read_progress()

            if progress:
                # Update last progress time (watchdog)
                self.last_progress_time = time.time()

                # Update story ID
                if "story_id" in progress:
                    self.story_id = progress["story_id"]

                # Update current step
                current = progress.get("current_step", 0)
                status = progress.get("status", "running")
                message = progress.get("message", "")

                if current != last_step:
                    # Previous step is done
                    if last_step > 0:
                        prev_key = STEPS[last_step - 1]["key"]
                        self.step_status[prev_key] = "done"
                        self.step_times[prev_key] = time.time() - step_start_time

                    # Current step is running
                    if current > 0 and current <= len(STEPS):
                        curr_key = STEPS[current - 1]["key"]
                        self.step_status[curr_key] = "running" if status != "done" else "done"
                        step_start_time = time.time()

                    last_step = current

                # Update message
                if message:
                    self.last_message = message

                # Mark current step as done if status is done
                if status == "done" and current > 0 and current <= len(STEPS):
                    curr_key = STEPS[current - 1]["key"]
                    if self.step_status[curr_key] != "done":
                        self.step_status[curr_key] = "done"
                        self.step_times[curr_key] = time.time() - step_start_time

            # === WATCHDOG CHECK ===
            time_since_progress = time.time() - self.last_progress_time
            if time_since_progress > self.watchdog_timeout:
                self.last_message = f"[red]⚠ WATCHDOG: No progress for {int(time_since_progress)}s - possible hang![/red]"
                # Kill hung Claude process
                if self.claude_process and self.claude_process.poll() is None:
                    self.console.print(f"\n[red]WATCHDOG: Terminating hung Claude process after {int(time_since_progress)}s[/red]")
                    self.claude_process.terminate()
                    try:
                        self.claude_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.claude_process.kill()
                    self.stop_event.set()
                    break

            live.update(self._build_display())
            time.sleep(0.5)

    def _run_claude(self) -> int:
        """Run Claude with the prompt"""
        try:
            # Use current story or auto prompt
            if self.current_story_id:
                prompt = CLAUDE_PROMPT_MANUAL.format(story_id=self.current_story_id)
            else:
                prompt = CLAUDE_PROMPT_AUTO

            self.claude_process = subprocess.Popen(
                ["claude", "--dangerously-skip-permissions", "-p", prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Read output but don't display (Rich UI handles display)
            while True:
                line = self.claude_process.stdout.readline()
                if not line and self.claude_process.poll() is not None:
                    break
                # Could parse output here for additional progress detection

            return self.claude_process.returncode or 0
        except FileNotFoundError:
            self.console.print("[red]Error: 'claude' command not found. Is Claude CLI installed?[/red]")
            return 1
        except Exception as e:
            self.console.print(f"[red]Error running Claude: {e}[/red]")
            return 1

    def _run_demo(self) -> int:
        """Run demo mode - simulate progress without Claude"""
        # Use current story or pick random for demo
        if self.current_story_id:
            story_id = self.current_story_id
        else:
            demo_stories = [
                "1-1-initialize-monorepo", "1-2-configure-typescript",
                "2-1-database-connection", "2-2-table-discovery"
            ]
            story_id = random.choice(demo_stories)

        # Demo messages for each step (11 steps now)
        demo_messages = [
            "Reading sprint-status.yaml...",
            "Creating story file...",
            "Developing story implementation...",
            "Running tests...",
            "Performing code review...",
            "Fixing issues found...",
            "Running tests until all pass...",
            "Updating story status to done...",
            "Updating sprint-status.yaml...",
            "Updating bmm-workflow-status.yaml...",
            "Committing changes to git..."
        ]

        # Pick a random story for this iteration
        if not self.current_story_id:
            story_id = random.choice(demo_stories)

        # Simulate each step with random delays
        for step_num in range(1, len(STEPS) + 1):
            if self.stop_event.is_set():
                return 1

            # Write progress to file (simulating what Claude would do)
            progress = {
                "story_id": story_id,
                "current_step": step_num,
                "step_name": STEPS[step_num - 1]["name"],
                "status": "running",
                "message": demo_messages[step_num - 1],
                "timestamp": datetime.now().isoformat()
            }

            with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump(progress, f, indent=2)

            # Random delay to simulate work
            delay = random.uniform(1.0, 3.0)

            # Longer delays for certain steps
            if step_num == 3:  # Develop story
                delay = random.uniform(4.0, 8.0)
            elif step_num in [4, 7]:  # Run tests
                delay = random.uniform(2.0, 4.0)
            elif step_num == 5:  # Code review
                delay = random.uniform(3.0, 5.0)

            time.sleep(delay)

            # Mark step as done
            progress["status"] = "done"
            progress["message"] = f"Step {step_num} completed"
            with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump(progress, f, indent=2)

            time.sleep(0.3)  # Brief pause before next step

        return 0

    def _call_verifier(self, story_id: str, deep: bool = False) -> dict:
        """Call bmad-verifier.py and parse JSON output"""
        verifier_script = Path(__file__).parent / "bmad-verifier.py"
        cmd = [sys.executable, str(verifier_script), story_id, "--json"]
        if deep:
            cmd.append("--deep")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180 if deep else 30
            )
            if result.stdout:
                return json.loads(result.stdout.strip())
        except subprocess.TimeoutExpired:
            return {"error": "Verifier timeout", "passed": False}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON from verifier", "passed": False}
        except Exception as e:
            return {"error": str(e), "passed": False}

        return {"error": "No output from verifier", "passed": False}

    def _run_fix_story(self, story_id: str) -> int:
        """Run Claude to fix story tracking files (code is done, just update status)"""
        # Story files are named like "5-9-migration-summary-report.md", not just "5-9.md"
        prompt = f'''Fix the tracking files for story {story_id}. The code is already implemented, but tracking files need updating.

1. Find the story file in _bmad-output/implementation-artifacts/ that starts with "{story_id}-" (e.g., {story_id}-*.md)
2. Update the story file:
   - Set Status: done
   - Mark ALL tasks as completed: - [x]
   - Fill the Dev Agent Record section if empty
3. Update _bmad-output/implementation-artifacts/sprint-status.yaml:
   - Find the entry that starts with "{story_id}-" and set it to: done
4. Git commit with message: "fix(story): update {story_id} tracking"

Only update tracking - do NOT modify any source code.
'''

        try:
            self.console.print(f"[yellow]Running fix for {story_id}...[/yellow]")
            process = subprocess.run(
                ["claude", "--dangerously-skip-permissions", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=180
            )
            return process.returncode or 0
        except Exception as e:
            self.console.print(f"[red]Error running fix: {e}[/red]")
            return 1

    def _run_dev_story(self, story_id: str) -> int:
        """Run Claude to develop/implement a story"""
        prompt = f'''Implement story {story_id}.

1. Read the story file at _bmad-output/implementation-artifacts/{story_id}.md
2. Implement ALL tasks described in the story
3. Write tests for the implementation
4. Run tests until they pass
5. Update story file: set Status: done, mark all tasks [x]
6. Update sprint-status.yaml: set {story_id}: done
7. Git commit with message: "feat(story): complete {story_id}"
'''

        try:
            self.console.print(f"[yellow]Running dev for {story_id}...[/yellow]")
            process = subprocess.run(
                ["claude", "--dangerously-skip-permissions", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=600  # 10 min for dev
            )
            return process.returncode or 0
        except Exception as e:
            self.console.print(f"[red]Error running dev: {e}[/red]")
            return 1

    def _verify_and_fix_loop(self, story_id: str, max_retries: int = 3) -> bool:
        """Verify story completion using verifier and fix/retry if needed."""
        for attempt in range(max_retries):
            self.console.print()
            self.console.print(Panel(
                f"[bold]🔍 Verification Attempt {attempt + 1}/{max_retries}[/bold]\n\n"
                f"Story: [cyan]{story_id}[/cyan]",
                box=box.ROUNDED,
                border_style="yellow"
            ))

            # Step 1: Quick verify using verifier
            self.console.print("[dim]Running quick verification...[/dim]")
            quick_result = self._call_verifier(story_id, deep=False)

            if quick_result.get("error"):
                self.console.print(f"[yellow]Verifier error: {quick_result['error']}[/yellow]")
                continue

            if quick_result.get("passed"):
                self.console.print("[green]✓ Quick verification PASSED![/green]")
                return True

            # Show what failed
            self.console.print("[yellow]Quick verification found issues:[/yellow]")
            checks = quick_result.get("checks", {})
            for name, passed in checks.items():
                icon = "[green]✓[/green]" if passed else "[red]✗[/red]"
                self.console.print(f"  {icon} {name}")

            # If file doesn't exist, cannot continue
            if not checks.get("file_exists"):
                self.console.print("[red]Story file doesn't exist - cannot verify[/red]")
                return False

            # Step 2: Deep verify to check if code is actually implemented
            self.console.print()
            self.console.print("[dim]Running deep verification with Claude...[/dim]")
            deep_result = self._call_verifier(story_id, deep=True)

            if deep_result.get("error"):
                self.console.print(f"[yellow]Deep verify error: {deep_result['error']}[/yellow]")
                # Try fix anyway
                self.console.print("[dim]Attempting fix despite error...[/dim]")
                self._run_fix_story(story_id)
                continue

            if deep_result.get("code_implemented"):
                # Code is implemented! Just need to fix tracking files
                self.console.print("[green]✓ Code is implemented![/green]")
                if deep_result.get("deep_summary"):
                    self.console.print(f"[dim]{deep_result['deep_summary']}[/dim]")
                self.console.print()
                self.console.print("[yellow]Fixing tracking files...[/yellow]")

                fix_result = self._run_fix_story(story_id)
                if fix_result == 0:
                    # Verify again
                    final_check = self._call_verifier(story_id, deep=False)
                    if final_check.get("passed"):
                        self.console.print("[green]✓ Fix successful![/green]")
                        return True
                    else:
                        self.console.print("[yellow]Fix completed but verification still failing[/yellow]")
            else:
                # Code is NOT implemented - need to re-run dev
                self.console.print("[red]✗ Code is NOT implemented![/red]")
                if deep_result.get("deep_summary"):
                    self.console.print(f"[dim]{deep_result['deep_summary']}[/dim]")
                self.console.print()
                self.console.print("[yellow]Re-running development...[/yellow]")

                dev_result = self._run_dev_story(story_id)
                if dev_result != 0:
                    self.console.print(f"[yellow]Dev returned exit code {dev_result}[/yellow]")

            # Check for stop signal
            if Path(STOP_FILE).exists() or self.stop_event.is_set():
                self.console.print("[yellow]Stop requested during verification[/yellow]")
                return False

        self.console.print(f"[red]✗ Failed to verify after {max_retries} attempts[/red]")
        return False

    def _reset_iteration(self):
        """Reset state for new iteration"""
        self.step_status = {step["key"]: "pending" for step in STEPS}
        self.step_times = {}
        self.last_message = ""
        self.story_id = "..."
        # Clear progress file
        Path(PROGRESS_FILE).unlink(missing_ok=True)

    def _verify_all_steps_completed(self) -> tuple:
        """Check if all 11 steps are marked as Done.
        Returns: (all_done: bool, completed_count: int, missing_steps: list)
        """
        completed = []
        missing = []
        for step in STEPS:
            if self.step_status.get(step["key"]) == "done":
                completed.append(step)
            else:
                missing.append(step)
        return len(missing) == 0, len(completed), missing

    def _get_retry_prompt_for_steps(self, missing_steps: list, story_id: str) -> str:
        """Generate a focused prompt to retry only the missing steps."""
        step_instructions = []
        for step in missing_steps:
            step_id = step["id"]

            if step_id == 1:
                step_instructions.append(f"STEP {step_id}: Read _bmad-output/implementation-artifacts/sprint-status.yaml and confirm story {story_id}")
            elif step_id == 2:
                step_instructions.append(f"STEP {step_id}: Call /bmad:bmm:workflows:create-story with {story_id} to create the story file")
            elif step_id == 3:
                step_instructions.append(f"STEP {step_id}: Call /bmad:bmm:workflows:dev-story with {story_id} to implement the code")
            elif step_id == 4:
                step_instructions.append(f"STEP {step_id}: Run tests (pnpm test or npm test)")
            elif step_id == 5:
                step_instructions.append(f"STEP {step_id}: Call /bmad:bmm:workflows:code-review to review the code")
            elif step_id == 6:
                step_instructions.append(f"STEP {step_id}: Fix any issues found in code review")
            elif step_id == 7:
                step_instructions.append(f"STEP {step_id}: Run tests again until ALL PASS")
            elif step_id == 8:
                step_instructions.append(f"STEP {step_id}: Update story file: set status to 'done', mark all tasks [x], fill Dev Agent Record")
            elif step_id == 9:
                step_instructions.append(f"STEP {step_id}: Update _bmad-output/implementation-artifacts/sprint-status.yaml: mark {story_id} as 'done'")
            elif step_id == 10:
                step_instructions.append(f"STEP {step_id}: Update _bmad-output/planning-artifacts/bmm-workflow-status.yaml with completion info")
            elif step_id == 11:
                short_id = "-".join(story_id.split("-")[:2]) if story_id and story_id != "..." else "X-X"
                step_instructions.append(f"STEP {step_id}: Git add -A and commit with message: \"feat(story): complete {short_id}\"")

        prompt = f'''CONTINUE INCOMPLETE STORY: {story_id}

The previous execution stopped early. Complete ONLY these remaining steps:

After completing EACH step, write progress to .claude/bmad-progress.json:
{{"story_id": "{story_id}", "current_step": N, "status": "done", "message": "what you did"}}

{chr(10).join(step_instructions)}

IMPORTANT: Complete ALL listed steps. Do not stop early. Do not ask questions - make reasonable decisions.
'''
        return prompt

    def _run_claude_retry(self, prompt: str) -> int:
        """Run Claude with a retry prompt for missing steps."""
        try:
            self.claude_process = subprocess.Popen(
                ["claude", "--dangerously-skip-permissions", "-p", prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            while True:
                line = self.claude_process.stdout.readline()
                if not line and self.claude_process.poll() is not None:
                    break

            return self.claude_process.returncode or 0
        except Exception as e:
            self.console.print(f"[red]Error running Claude retry: {e}[/red]")
            return 1

    def _retry_missing_steps(self, missing_steps: list, story_id: str, max_retries: int = None) -> bool:
        """Retry only the missing steps with focused prompts."""
        if max_retries is None:
            max_retries = self.max_step_retries

        for attempt in range(max_retries):
            self.console.print(f"\n[yellow]🔄 Retry attempt {attempt + 1}/{max_retries} for {len(missing_steps)} missing steps...[/yellow]")

            # Show which steps are missing
            for step in missing_steps:
                self.console.print(f"  [dim]• Step {step['id']}: {step['name']}[/dim]")

            # Generate focused retry prompt
            retry_prompt = self._get_retry_prompt_for_steps(missing_steps, story_id)

            # Clear progress file for retry monitoring
            Path(PROGRESS_FILE).unlink(missing_ok=True)

            # Run retry with monitoring
            with Live(self._build_display(), console=self.console, refresh_per_second=2) as live:
                monitor_thread = Thread(target=self._monitor_progress, args=(live,), daemon=True)
                monitor_thread.start()

                exit_code = self._run_claude_retry(retry_prompt)

                self.stop_event.set()
                monitor_thread.join(timeout=1)
                self.stop_event.clear()

            # Check if steps are now complete
            all_done, completed_count, still_missing = self._verify_all_steps_completed()

            if all_done:
                self.console.print(f"[green]✓ All {len(STEPS)} steps now complete![/green]")
                return True

            if len(still_missing) < len(missing_steps):
                self.console.print(f"[yellow]Progress: {len(missing_steps) - len(still_missing)} steps completed, {len(still_missing)} still missing[/yellow]")
                missing_steps = still_missing
            else:
                self.console.print(f"[yellow]No progress on retry attempt {attempt + 1}[/yellow]")

            # Check stop signal
            if Path(STOP_FILE).exists() or self.stop_event.is_set():
                return False

        return False

    def run(self):
        """Main run loop"""
        self._ensure_dirs()
        self.start_time = datetime.now()

        # Show startup banner
        mode_text = "[yellow]DEMO MODE[/yellow] (simulated)" if self.demo_mode else "[green]PRODUCTION MODE[/green]"
        story_text = f"[bold cyan]{self.start_story_id}[/bold cyan] (+ continue)" if self.start_story_id else "[dim]Auto (next backlog)[/dim]"
        iter_text = str(self.max_iterations)

        self.console.print()
        self.console.print(Panel(
            f"[bold cyan]BMAD Story Automation[/bold cyan]\n\n"
            f"[white]Mode:[/white] {mode_text}\n"
            f"[white]Start Story:[/white] {story_text}\n"
            f"[white]Total Stories:[/white] [bold]{iter_text}[/bold]\n"
            f"[white]Started:[/white] [bold]{self.start_time.strftime('%Y-%m-%d %H:%M:%S')}[/bold]\n\n"
            "[dim]Press Ctrl+C to stop at any time[/dim]",
            box=box.DOUBLE,
            border_style="cyan"
        ))
        self.console.print()
        time.sleep(2)

        for iteration in range(1, self.max_iterations + 1):
            # Check stop condition
            if Path(STOP_FILE).exists() or self.stop_event.is_set():
                self.console.print("[yellow]Stop requested. Exiting...[/yellow]")
                break

            self.current_iteration = iteration
            self._reset_iteration()
            self.iteration_start_time = datetime.now()

            # Show current story being processed
            if self.current_story_id:
                self.console.print(f"\n[bold cyan]▶ Processing story: {self.current_story_id}[/bold cyan]")

            # Save tracking info
            tracking = {
                "iteration": iteration,
                "max_iterations": self.max_iterations,
                "current_story": self.current_story_id,
                "started_at": self.iteration_start_time.isoformat(),
                "status": "running"
            }
            with open(TRACKING_FILE, "w", encoding="utf-8") as f:
                json.dump(tracking, f, indent=2)

            # Run with live display
            with Live(self._build_display(), console=self.console, refresh_per_second=2) as live:
                # Start monitor thread
                monitor_thread = Thread(target=self._monitor_progress, args=(live,), daemon=True)
                monitor_thread.start()

                # Run Claude or Demo
                if self.demo_mode:
                    exit_code = self._run_demo()
                else:
                    exit_code = self._run_claude()

                # Stop monitor
                self.stop_event.set()
                monitor_thread.join(timeout=1)
                self.stop_event.clear()

            # Update tracking
            tracking["completed_at"] = datetime.now().isoformat()
            tracking["exit_code"] = exit_code
            tracking["status"] = "completed"
            with open(TRACKING_FILE, "w", encoding="utf-8") as f:
                json.dump(tracking, f, indent=2)

            # Show iteration result
            self.console.print()

            # === STEP COMPLETION VERIFICATION ===
            all_done, completed_count, missing_steps = self._verify_all_steps_completed()

            if exit_code == 0 and all_done:
                self.console.print(f"[green]✓ Iteration {iteration} completed successfully ({completed_count}/{len(STEPS)} steps)[/green]")
            elif exit_code == 0 and not all_done:
                self.console.print(f"[yellow]⚠ Iteration {iteration} INCOMPLETE: {completed_count}/{len(STEPS)} steps done[/yellow]")

                # Attempt to retry missing steps
                if not self.demo_mode and self.story_id and self.story_id != "...":
                    retry_success = self._retry_missing_steps(missing_steps, self.story_id)
                    if retry_success:
                        self.console.print(f"[green]✓ Missing steps completed via retry![/green]")
                    else:
                        self.console.print(f"[red]✗ Could not complete all steps after retries[/red]")
            else:
                self.console.print(f"[yellow]⚠ Iteration {iteration} completed with exit code {exit_code}[/yellow]")

            # === VERIFICATION LOOP ===
            # After Claude finishes, verify the story was actually completed
            completed_story_id = self.story_id
            if completed_story_id and completed_story_id != "...":
                self.console.print()
                self.console.print(Panel(
                    f"[bold cyan]📋 Post-Execution Verification[/bold cyan]\n\n"
                    f"Verifying story [bold]{completed_story_id}[/bold] was completed correctly...",
                    box=box.ROUNDED,
                    border_style="cyan"
                ))

                if self.demo_mode:
                    # In demo mode, skip real verification
                    self.console.print("[dim]Demo mode: skipping actual verification[/dim]")
                    verified = True
                else:
                    # Real verification loop
                    verified = self._verify_and_fix_loop(completed_story_id)

                if verified:
                    self.console.print()
                    self.console.print(f"[green]✓ Story {completed_story_id} verified as DONE![/green]")
                else:
                    self.console.print()
                    self.console.print(f"[red]✗ Story {completed_story_id} could not be verified[/red]")
                    self.console.print("[dim]Check manually or run verifier: python bmad-verifier.py {completed_story_id} -d -i[/dim]")

            # Check stop condition again
            if Path(STOP_FILE).exists():
                self.console.print("[yellow]Stop file detected. Exiting...[/yellow]")
                Path(STOP_FILE).unlink(missing_ok=True)
                break

            # Increment story ID for next iteration (if in continue mode)
            if self.current_story_id and iteration < self.max_iterations:
                next_story = self._get_next_story_id(self.current_story_id)
                if next_story:
                    self.current_story_id = next_story
                    self.console.print(f"[dim]Next story: {next_story}[/dim]")

            # Delay before next iteration
            if iteration < self.max_iterations:
                self.console.print("[dim]Waiting 5 seconds before next iteration...[/dim]")
                for _ in range(5):
                    if Path(STOP_FILE).exists() or self.stop_event.is_set():
                        break
                    time.sleep(1)

        # Cleanup and show summary
        self._cleanup()

        elapsed = datetime.now() - self.start_time
        self.console.print()
        self.console.print(Panel(
            f"[bold green]Automation Complete![/bold green]\n\n"
            f"[white]Iterations:[/white] [bold]{self.current_iteration}[/bold]\n"
            f"[white]Total Time:[/white] [bold]{int(elapsed.total_seconds() // 60):02d}:{int(elapsed.total_seconds() % 60):02d}[/bold]\n"
            f"[white]Finished:[/white] [bold]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold]",
            box=box.DOUBLE,
            border_style="green"
        ))
        self.console.print()


def main():
    parser = argparse.ArgumentParser(
        description="BMAD Story Automation Runner with Interactive UI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bmad-runner.py                    # Run with default 5 iterations (auto pick stories)
  python bmad-runner.py --iterations 3    # Run with 3 iterations
  python bmad-runner.py --story 5-2       # Process specific story only
  python bmad-runner.py -s 5-2            # Short form for --story
  python bmad-runner.py --demo            # Demo mode (simulated, no Claude)
  python bmad-runner.py --demo -s 5-2     # Demo with specific story

To stop the automation:
  - Press Ctrl+C
  - Or create file: .claude/bmad-stop
        """
    )
    parser.add_argument(
        "-i", "--iterations",
        type=int,
        default=5,
        help="Maximum number of iterations (default: 5, ignored if --story is set)"
    )
    parser.add_argument(
        "-s", "--story",
        type=str,
        default=None,
        help="Specific story ID to process (e.g. '5-2' or '5-2-my-story-name')"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode (simulated progress, no Claude)"
    )
    parser.add_argument(
        "--watchdog-timeout",
        type=int,
        default=300,
        help="Seconds without progress before killing hung process (default: 300 = 5 min)"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Max retry attempts for incomplete steps (default: 2)"
    )

    args = parser.parse_args()

    runner = BMadRunner(max_iterations=args.iterations, demo_mode=args.demo, story_id=args.story)
    runner.watchdog_timeout = args.watchdog_timeout
    runner.max_step_retries = args.max_retries
    runner.run()


if __name__ == "__main__":
    main()
