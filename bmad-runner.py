#!/usr/bin/env python3
"""
BMAD Story Automation Runner - Interactive CLI with Rich UI
Cross-platform (Windows/Linux/Mac)

Usage:
    python bmad-runner.py                    # Default 5 iterations
    python bmad-runner.py --iterations 3    # Custom iterations
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
CLAUDE_PROMPT = '''EXECUTE ALL STEPS IN ORDER - DO NOT STOP EARLY.

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

STEP 11: Git add -A and commit with message: "feat: complete STORY_ID"
         Write progress

IMPORTANT: Complete ALL 11 steps. Do not stop after creating the story.
'''


class BMadRunner:
    def __init__(self, max_iterations: int = 5, demo_mode: bool = False):
        self.console = Console()
        self.max_iterations = max_iterations
        self.demo_mode = demo_mode
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

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, self._signal_handler)

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

    def _ensure_dirs(self):
        """Ensure .claude directory exists"""
        Path(".claude").mkdir(exist_ok=True)
        # Remove old stop file
        Path(STOP_FILE).unlink(missing_ok=True)

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
        """Monitor progress file and update display"""
        last_step = 0
        step_start_time = time.time()

        while not self.stop_event.is_set():
            progress = self._read_progress()

            if progress:
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

            live.update(self._build_display())
            time.sleep(0.5)

    def _run_claude(self) -> int:
        """Run Claude with the prompt"""
        try:
            self.claude_process = subprocess.Popen(
                ["claude", "--dangerously-skip-permissions", "-p", CLAUDE_PROMPT],
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
        # Simulated story IDs for demo
        demo_stories = [
            "1-1-initialize-monorepo", "1-2-configure-typescript",
            "2-1-database-connection", "2-2-table-discovery"
        ]

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

    def _reset_iteration(self):
        """Reset state for new iteration"""
        self.step_status = {step["key"]: "pending" for step in STEPS}
        self.step_times = {}
        self.last_message = ""
        self.story_id = "..."
        # Clear progress file
        Path(PROGRESS_FILE).unlink(missing_ok=True)

    def run(self):
        """Main run loop"""
        self._ensure_dirs()
        self.start_time = datetime.now()

        # Show startup banner
        mode_text = "[yellow]DEMO MODE[/yellow] (simulated)" if self.demo_mode else "[green]PRODUCTION MODE[/green]"
        self.console.print()
        self.console.print(Panel(
            f"[bold cyan]BMAD Story Automation[/bold cyan]\n\n"
            f"[white]Mode:[/white] {mode_text}\n"
            f"[white]Max Iterations:[/white] [bold]{self.max_iterations}[/bold]\n"
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

            # Save tracking info
            tracking = {
                "iteration": iteration,
                "max_iterations": self.max_iterations,
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
            if exit_code == 0:
                self.console.print(f"[green]✓ Iteration {iteration} completed successfully[/green]")
            else:
                self.console.print(f"[yellow]⚠ Iteration {iteration} completed with exit code {exit_code}[/yellow]")

            # Check stop condition again
            if Path(STOP_FILE).exists():
                self.console.print("[yellow]Stop file detected. Exiting...[/yellow]")
                Path(STOP_FILE).unlink(missing_ok=True)
                break

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
  python bmad-runner.py                    # Run with default 5 iterations
  python bmad-runner.py --iterations 3    # Run with 3 iterations
  python bmad-runner.py -i 10             # Run with 10 iterations
  python bmad-runner.py --demo            # Demo mode (simulated, no Claude)
  python bmad-runner.py --demo -i 2       # Demo with 2 iterations

To stop the automation:
  - Press Ctrl+C
  - Or create file: .claude/bmad-stop
        """
    )
    parser.add_argument(
        "-i", "--iterations",
        type=int,
        default=5,
        help="Maximum number of iterations (default: 5)"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode (simulated progress, no Claude)"
    )

    args = parser.parse_args()

    runner = BMadRunner(max_iterations=args.iterations, demo_mode=args.demo)
    runner.run()


if __name__ == "__main__":
    main()
