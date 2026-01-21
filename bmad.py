#!/usr/bin/env python3
"""
BMAD Automation Suite - Unified CLI Entry Point
Cross-platform (Windows/Linux/Mac)

Combines Runner and Verifier with an interactive menu.

Usage:
    python bmad.py          # Interactive menu
    python bmad.py status   # Quick sprint status
    python bmad.py run 5-2  # Direct run story
    python bmad.py verify 5-2  # Direct verify story
"""

import subprocess
import sys
import re
import os
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box
    import yaml
except ImportError:
    print("Missing dependencies. Please run:")
    print("  pip install rich pyyaml")
    sys.exit(1)

# Constants
SPRINT_STATUS_FILE = "_bmad-output/implementation-artifacts/sprint-status.yaml"
SCRIPTS_DIR = Path(__file__).parent


class BMadSuite:
    def __init__(self):
        self.console = Console()

    def _load_sprint_status(self) -> dict:
        """Load sprint-status.yaml"""
        try:
            with open(SPRINT_STATUS_FILE, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data.get("development_status", {})
        except FileNotFoundError:
            self.console.print(f"[red]File not found: {SPRINT_STATUS_FILE}[/red]")
            return {}
        except Exception as e:
            self.console.print(f"[red]Error loading sprint-status.yaml: {e}[/red]")
            return {}

    def _is_story_id(self, key: str) -> bool:
        """Check if a key is a story ID (not epic or retrospective)"""
        if key.startswith("epic-"):
            return False
        if key.endswith("-retrospective"):
            return False
        return bool(re.match(r"^\d+-\d+", key))

    def show_banner(self):
        """Show welcome banner with project location"""
        cwd = Path.cwd()
        sprint_file = cwd / SPRINT_STATUS_FILE
        sprint_exists = sprint_file.exists()

        self.console.print()
        self.console.print(Panel(
            Text.assemble(
                ("🚀 ", "cyan"),
                ("BMAD Automation Suite\n\n", "bold cyan"),
                ("Runner + Verifier unified CLI\n\n", "white"),
                ("📁 ", "blue"),
                ("Project: ", "white"),
                (str(cwd), "cyan"),
                ("\n", ""),
                ("📄 ", "blue"),
                ("Sprint file: ", "white"),
                ("✓ Found" if sprint_exists else "✗ Not found", "green" if sprint_exists else "red"),
            ),
            box=box.DOUBLE,
            border_style="cyan"
        ))

    def change_directory(self) -> bool:
        """Change to a different project directory. Returns True if changed."""
        self.console.print()
        self.console.print("[bold]📁 Change Project Directory[/bold]")
        self.console.print()
        self.console.print(f"[dim]Current: {Path.cwd()}[/dim]")
        self.console.print()

        try:
            new_dir = input("Enter new project path (or Enter to cancel): ").strip()
            if not new_dir:
                return False

            new_path = Path(new_dir).expanduser().resolve()
            if new_path.exists() and new_path.is_dir():
                os.chdir(new_path)
                self.console.print(f"[green]✓ Changed to: {new_path}[/green]")

                # Check if sprint file exists in new location
                sprint_file = new_path / SPRINT_STATUS_FILE
                if sprint_file.exists():
                    self.console.print("[green]✓ Sprint file found![/green]")
                else:
                    self.console.print("[yellow]⚠ Sprint file not found in this directory[/yellow]")
                return True
            else:
                self.console.print(f"[red]✗ Invalid path: {new_path}[/red]")
                return False
        except (KeyboardInterrupt, EOFError):
            return False

    def show_sprint_status(self):
        """Display detailed sprint status"""
        sprint_data = self._load_sprint_status()

        if not sprint_data:
            self.console.print("[yellow]⚠ No sprint data found. Use [0] to change directory.[/yellow]")
            return

        # Count by status and group stories by epic
        counts = {"backlog": 0, "in-progress": 0, "done": 0}
        stories = {"backlog": [], "in-progress": [], "done": []}
        epics = {}  # epic_num -> {backlog: [], done: [], in-progress: []}

        for key, status in sprint_data.items():
            if not self._is_story_id(key):
                continue
            status_lower = status.lower() if status else "backlog"
            if status_lower in counts:
                counts[status_lower] += 1
                stories[status_lower].append(key)

                # Group by epic
                epic_num = key.split("-")[0]
                if epic_num not in epics:
                    epics[epic_num] = {"backlog": [], "in-progress": [], "done": []}
                epics[epic_num][status_lower].append(key)

        total_stories = counts["backlog"] + counts["in-progress"] + counts["done"]
        progress_pct = (counts["done"] / total_stories * 100) if total_stories > 0 else 0

        # Header with progress
        self.console.print()
        self.console.print(Panel(
            f"[bold cyan]📊 Sprint Status[/bold cyan]\n\n"
            f"[white]Total Stories:[/white] [bold]{total_stories}[/bold]\n"
            f"[white]Progress:[/white] [bold green]{counts['done']}[/bold green] / {total_stories} ([bold]{progress_pct:.0f}%[/bold])",
            box=box.ROUNDED,
            border_style="cyan"
        ))

        # Summary counts table
        self.console.print()
        summary_table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        summary_table.add_column("Status", width=15)
        summary_table.add_column("Count", width=8, justify="center")
        summary_table.add_column("Progress Bar", width=30)

        # Visual progress bars
        bar_width = 20
        for status_name, color, icon in [
            ("done", "green", "✅"),
            ("in-progress", "blue", "🔄"),
            ("backlog", "yellow", "⬜")
        ]:
            count = counts[status_name]
            bar_fill = int((count / total_stories * bar_width)) if total_stories > 0 else 0
            bar = f"[{color}]{'█' * bar_fill}[/{color}][dim]{'░' * (bar_width - bar_fill)}[/dim]"
            summary_table.add_row(
                f"[{color}]{icon} {status_name.title()}[/{color}]",
                f"[{color}]{count}[/{color}]",
                bar
            )

        self.console.print(summary_table)

        # Epic breakdown table
        self.console.print()
        self.console.print("[bold]📋 Epic Breakdown[/bold]")
        epic_table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
        epic_table.add_column("Epic", width=8)
        epic_table.add_column("Done", width=6, justify="center")
        epic_table.add_column("In Progress", width=12, justify="center")
        epic_table.add_column("Backlog", width=8, justify="center")
        epic_table.add_column("Status", width=15)

        for epic_num in sorted(epics.keys(), key=lambda x: int(x)):
            epic_data = epics[epic_num]
            done = len(epic_data["done"])
            inprog = len(epic_data["in-progress"])
            backlog = len(epic_data["backlog"])
            total = done + inprog + backlog

            if done == total:
                status = "[green]✓ Complete[/green]"
            elif inprog > 0:
                status = "[blue]● Active[/blue]"
            elif done > 0:
                status = "[yellow]◐ Partial[/yellow]"
            else:
                status = "[dim]○ Not started[/dim]"

            epic_table.add_row(
                f"[bold]Epic {epic_num}[/bold]",
                f"[green]{done}[/green]" if done > 0 else "[dim]0[/dim]",
                f"[blue]{inprog}[/blue]" if inprog > 0 else "[dim]0[/dim]",
                f"[yellow]{backlog}[/yellow]" if backlog > 0 else "[dim]0[/dim]",
                status
            )

        self.console.print(epic_table)

        # In Progress details (if any)
        if stories["in-progress"]:
            self.console.print()
            self.console.print("[bold blue]🔄 Currently In Progress[/bold blue]")
            for story in stories["in-progress"]:
                self.console.print(f"  [blue]→[/blue] {story}")

        # Next backlog stories
        self.console.print()
        self.console.print("[bold yellow]⬜ Next Up (Backlog)[/bold yellow]")
        for story in stories["backlog"][:5]:
            self.console.print(f"  [yellow]→[/yellow] {story}")
        if len(stories["backlog"]) > 5:
            self.console.print(f"  [dim]... and {len(stories['backlog']) - 5} more[/dim]")

        # Recently completed
        if stories["done"]:
            self.console.print()
            self.console.print("[bold green]✅ Recently Completed[/bold green]")
            for story in stories["done"][-5:]:
                self.console.print(f"  [green]✓[/green] {story}")
            if len(stories["done"]) > 5:
                self.console.print(f"  [dim]... and {len(stories['done']) - 5} more[/dim]")

        # Quick action hint
        self.console.print()
        if stories["backlog"]:
            next_story = stories["backlog"][0]
            self.console.print(Panel(
                f"[bold]💡 Quick Action[/bold]\n\n"
                f"Next story: [bold cyan]{next_story}[/bold cyan]\n\n"
                f"[dim]Run:[/dim] python bmad.py run {next_story.split('-')[0]}-{next_story.split('-')[1]}",
                box=box.ROUNDED,
                border_style="green"
            ))

        self.console.print()

    def show_main_menu(self) -> str:
        """Show main menu and get choice"""
        table = Table(box=box.ROUNDED, show_header=False, padding=(0, 2))
        table.add_column("Option", width=5)
        table.add_column("Description", width=40)

        table.add_row("[dim][0][/dim]", "[dim]📁 Change Project Directory[/dim]")
        table.add_row("[cyan][1][/cyan]", "📊 Check Sprint Status")
        table.add_row("[cyan][2][/cyan]", "▶️  Runner (Create & Develop stories)")
        table.add_row("[cyan][3][/cyan]", "✅ Verifier (Validate stories)")
        table.add_row("[cyan][4][/cyan]", "❓ Help")
        table.add_row("[dim][5][/dim]", "[dim]🚪 Exit[/dim]")

        self.console.print()
        self.console.print(table)
        self.console.print()

        try:
            choice = input("Select option: ").strip()
        except (KeyboardInterrupt, EOFError):
            return "5"

        return choice

    def show_runner_menu(self) -> tuple:
        """Show runner submenu"""
        self.console.print()
        self.console.print(Panel(
            "[bold]▶️ BMAD Runner[/bold]\n\n"
            "Create and develop stories automatically",
            box=box.ROUNDED,
            border_style="green"
        ))

        # Show next backlog story for reference
        sprint_data = self._load_sprint_status()
        next_backlog = None
        for key, status in sprint_data.items():
            if self._is_story_id(key) and status == "backlog":
                next_backlog = key
                break

        if next_backlog:
            self.console.print(f"[dim]Next backlog story: [cyan]{next_backlog}[/cyan][/dim]")

        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        table.add_column("Option", width=5)
        table.add_column("Description", width=50)

        table.add_row("[green][1][/green]", "Run specific story (enter story ID)")
        table.add_row("[green][2][/green]", "Run from story + continue N more (e.g. 5-2 then 5-3, 5-4...)")
        table.add_row("[green][3][/green]", "Run all stories from epic (e.g. all 5-x stories)")
        table.add_row("[green][4][/green]", "Run next backlog stories (auto-pick, specify count)")
        table.add_row("[green][5][/green]", "Demo mode (simulated, no Claude)")
        table.add_row("[dim][6][/dim]", "[dim]← Back to main menu[/dim]")

        self.console.print(table)
        self.console.print()

        try:
            choice = input("Select option: ").strip()
        except (KeyboardInterrupt, EOFError):
            return ("back", None, None)

        if choice == "1":
            # Single story
            try:
                story_id = input("Enter story ID (e.g. 5-2): ").strip()
            except (KeyboardInterrupt, EOFError):
                return ("back", None, None)
            if story_id:
                return ("story", story_id, 1)
            return ("back", None, None)

        elif choice == "2":
            # Story + continue N more
            try:
                story_id = input("Start from story ID (e.g. 5-2): ").strip()
                if not story_id:
                    return ("back", None, None)
                count = input("How many stories total? [1]: ").strip()
                count = int(count) if count.isdigit() else 1
            except (KeyboardInterrupt, EOFError):
                return ("back", None, None)
            return ("story_continue", story_id, count)

        elif choice == "3":
            # Run all stories from epic
            try:
                epic = input("Enter epic number (e.g. 5): ").strip()
                if not epic:
                    return ("back", None, None)
            except (KeyboardInterrupt, EOFError):
                return ("back", None, None)
            # Count stories in this epic from sprint data
            epic_stories = [k for k in sprint_data.keys() if self._is_story_id(k) and k.startswith(f"{epic}-")]
            if not epic_stories:
                self.console.print(f"[yellow]No stories found for epic {epic}[/yellow]")
                return ("back", None, None)
            self.console.print(f"[dim]Found {len(epic_stories)} stories in epic {epic}[/dim]")
            return ("epic", epic, len(epic_stories))

        elif choice == "4":
            # Auto from backlog
            try:
                count = input("How many stories to process? [1]: ").strip()
                count = int(count) if count.isdigit() else 1
            except (KeyboardInterrupt, EOFError):
                return ("back", None, None)
            return ("auto", None, count)

        elif choice == "5":
            # Demo mode
            try:
                story_id = input("Story ID for demo (or Enter for random): ").strip()
            except (KeyboardInterrupt, EOFError):
                return ("back", None, None)
            return ("demo", story_id if story_id else None, 1)

        return ("back", None, None)

    def show_verifier_menu(self) -> tuple:
        """Show verifier submenu"""
        self.console.print()
        self.console.print(Panel(
            "[bold]✅ BMAD Verifier[/bold]\n\n"
            "Validate story implementation",
            box=box.ROUNDED,
            border_style="yellow"
        ))

        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        table.add_column("Option", width=5)
        table.add_column("Description", width=45)

        table.add_row("[yellow][1][/yellow]", "Quick validate story (fast check)")
        table.add_row("[yellow][2][/yellow]", "Deep validate story (with Claude)")
        table.add_row("[yellow][3][/yellow]", "Quick + Interactive (with actions)")
        table.add_row("[yellow][4][/yellow]", "Deep + Interactive (full check + actions)")
        table.add_row("[yellow][5][/yellow]", "Validate all epic (e.g. epic 5)")
        table.add_row("[dim][6][/dim]", "[dim]← Back to main menu[/dim]")

        self.console.print(table)
        self.console.print()

        try:
            choice = input("Select option: ").strip()
        except (KeyboardInterrupt, EOFError):
            return ("back", None, None)

        if choice in ["1", "2", "3", "4"]:
            try:
                story_id = input("Enter story ID (e.g. 5-2): ").strip()
            except (KeyboardInterrupt, EOFError):
                return ("back", None, None)

            if not story_id:
                return ("back", None, None)

            if choice == "1":
                return ("quick", story_id, False)
            elif choice == "2":
                return ("deep", story_id, False)
            elif choice == "3":
                return ("quick", story_id, True)
            elif choice == "4":
                return ("deep", story_id, True)

        elif choice == "5":
            try:
                epic = input("Enter epic number (e.g. 5): ").strip()
            except (KeyboardInterrupt, EOFError):
                return ("back", None, None)
            if epic:
                return ("epic", epic, False)

        return ("back", None, None)

    def run_runner(self, mode: str, story_id: str, count: int):
        """Execute the runner script"""
        script = SCRIPTS_DIR / "bmad-runner.py"

        if mode == "story":
            # Single specific story
            cmd = [sys.executable, str(script), "-s", story_id]
        elif mode == "story_continue":
            # Start from story, continue for count iterations
            cmd = [sys.executable, str(script), "-s", story_id, "-i", str(count)]
        elif mode == "epic":
            # Run all stories from epic - start from X-1 and run count iterations
            first_story = f"{story_id}-1"
            cmd = [sys.executable, str(script), "-s", first_story, "-i", str(count)]
        elif mode == "auto":
            # Auto pick from backlog, run count iterations
            cmd = [sys.executable, str(script), "-i", str(count)]
        elif mode == "demo":
            cmd = [sys.executable, str(script), "--demo"]
            if story_id:
                cmd.extend(["-s", story_id])
        else:
            return

        self.console.print()
        self.console.print(f"[cyan]Executing:[/cyan] {' '.join(cmd)}")
        self.console.print()

        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Interrupted[/yellow]")

    def run_verifier(self, mode: str, story_id: str, interactive: bool):
        """Execute the verifier script"""
        script = SCRIPTS_DIR / "bmad-verifier.py"

        cmd = [sys.executable, str(script), story_id]

        if mode == "deep":
            cmd.append("--deep")
        if interactive:
            cmd.append("-i")

        self.console.print()
        self.console.print(f"[cyan]Executing:[/cyan] {' '.join(cmd)}")
        self.console.print()

        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Interrupted[/yellow]")

    def show_help(self):
        """Display help information"""
        self.console.print()

        # Overview
        self.console.print(Panel(
            "[bold cyan]BMAD Automation Suite[/bold cyan]\n\n"
            "Unified CLI untuk menjalankan otomasi BMAD workflow.\n"
            "Menggabungkan Runner (create & develop) dan Verifier (validate).",
            box=box.ROUNDED,
            border_style="cyan"
        ))

        # Quick Commands Table
        self.console.print()
        self.console.print("[bold]📋 Quick Commands (CLI)[/bold]")
        cmd_table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        cmd_table.add_column("Command", width=35)
        cmd_table.add_column("Description", width=40)

        cmd_table.add_row("python bmad.py", "Interactive menu")
        cmd_table.add_row("python bmad.py status", "Lihat sprint status")
        cmd_table.add_row("python bmad.py run 5-2", "Jalankan story 5-2")
        cmd_table.add_row("python bmad.py run 5-2 -c 3", "Jalankan 5-2, 5-3, 5-4 (3 stories)")
        cmd_table.add_row("python bmad.py run -e 5", "Jalankan semua story di epic 5")
        cmd_table.add_row("python bmad.py run -c 5", "Auto-pick 5 story dari backlog")
        cmd_table.add_row("python bmad.py verify 5-2", "Quick verify story 5-2")
        cmd_table.add_row("python bmad.py verify 5-2 -d", "Deep verify dengan Claude")
        cmd_table.add_row("python bmad.py verify 5-2 -d -i", "Deep verify + interactive fix")

        self.console.print(cmd_table)

        # Workflow explanation
        self.console.print()
        self.console.print("[bold]🔄 Workflow BMAD[/bold]")
        flow_table = Table(box=box.SIMPLE, show_header=False)
        flow_table.add_column("Step", width=5)
        flow_table.add_column("Description", width=60)

        flow_table.add_row("[cyan]1[/cyan]", "[bold]Runner[/bold] - Create story dari backlog, develop code, commit")
        flow_table.add_row("[cyan]2[/cyan]", "[bold]Verifier[/bold] - Validasi apakah story selesai dengan benar")
        flow_table.add_row("[cyan]3[/cyan]", "[bold]Fix/Dev[/bold] - Jika ada masalah, jalankan fix atau dev lagi")

        self.console.print(flow_table)

        # Tips
        self.console.print()
        self.console.print(Panel(
            "[bold]💡 Tips:[/bold]\n\n"
            "• Gunakan [cyan]--demo[/cyan] untuk test tanpa Claude (simulasi)\n"
            "• Gunakan [cyan]-i[/cyan] (interactive) di verifier untuk action langsung\n"
            "• Deep check ([cyan]-d[/cyan]) memverifikasi code benar-benar ada\n"
            "• Ctrl+C untuk stop kapan saja\n"
            "• Buat file [cyan].claude/bmad-stop[/cyan] untuk stop runner",
            box=box.ROUNDED,
            border_style="yellow"
        ))

        self.console.print()

    def run_interactive(self):
        """Main interactive loop"""
        self.show_banner()

        while True:
            choice = self.show_main_menu()

            if choice == "0":
                changed = self.change_directory()
                if changed:
                    self.show_banner()  # Refresh banner with new location
                else:
                    input("[dim]Press Enter to continue...[/dim]")

            elif choice == "1":
                self.show_sprint_status()
                input("[dim]Press Enter to continue...[/dim]")

            elif choice == "2":
                mode, story_id, count = self.show_runner_menu()
                if mode != "back":
                    self.run_runner(mode, story_id, count)
                    input("\n[dim]Press Enter to continue...[/dim]")

            elif choice == "3":
                mode, story_id, interactive = self.show_verifier_menu()
                if mode != "back" and story_id:
                    self.run_verifier(mode, story_id, interactive)
                    input("\n[dim]Press Enter to continue...[/dim]")

            elif choice == "4":
                self.show_help()
                input("[dim]Press Enter to continue...[/dim]")

            elif choice == "5" or choice.lower() in ["q", "quit", "exit"]:
                self.console.print("\n[dim]Goodbye! 👋[/dim]\n")
                break

            else:
                self.console.print("[red]Invalid option. Try again.[/red]")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="BMAD Automation Suite - Unified CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  (no args)         Interactive menu
  status            Show sprint status
  run STORY         Run specific story
  run STORY -c N    Run from story, continue N stories total
  run -e EPIC       Run all stories from epic (e.g. -e 5)
  run -c N          Auto-pick from backlog, run N stories
  verify STORY      Quick verify story
  verify STORY -d   Deep verify with Claude

Examples:
  python bmad.py                    # Interactive menu
  python bmad.py status             # Sprint status
  python bmad.py run 5-2            # Run only story 5-2
  python bmad.py run 5-2 -c 3       # Run 5-2, 5-3, 5-4 (3 stories)
  python bmad.py run -e 5           # Run ALL stories from epic 5
  python bmad.py run -c 5           # Auto-pick 5 stories from backlog
  python bmad.py verify 5-2         # Quick verify 5-2
  python bmad.py verify 5-2 -d      # Deep verify 5-2
  python bmad.py verify 5-2 -d -i   # Deep verify + interactive fix
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Status command
    subparsers.add_parser("status", help="Show sprint status")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run story automation")
    run_parser.add_argument("story", nargs="?", help="Story ID to start from (e.g. 5-2)")
    run_parser.add_argument("-c", "--count", type=int, default=1, help="Number of stories to process (default: 1)")
    run_parser.add_argument("-e", "--epic", type=str, help="Run all stories from epic (e.g. 5)")
    run_parser.add_argument("--demo", action="store_true", help="Demo mode (simulated)")

    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify story")
    verify_parser.add_argument("story", help="Story ID to verify")
    verify_parser.add_argument("-d", "--deep", action="store_true", help="Deep validation with Claude")
    verify_parser.add_argument("-i", "--interactive", action="store_true", help="Interactive mode (fix/create/dev)")

    args = parser.parse_args()

    suite = BMadSuite()

    if args.command == "status":
        suite.show_banner()
        suite.show_sprint_status()

    elif args.command == "run":
        if args.demo:
            suite.run_runner("demo", args.story, 1)
        elif args.epic:
            # Run all stories from epic - need to count them first
            sprint_data = suite._load_sprint_status()
            epic_stories = [k for k in sprint_data.keys() if suite._is_story_id(k) and k.startswith(f"{args.epic}-")]
            if epic_stories:
                suite.run_runner("epic", args.epic, len(epic_stories))
            else:
                print(f"No stories found for epic {args.epic}")
        elif args.story:
            # Start from specific story
            if args.count > 1:
                suite.run_runner("story_continue", args.story, args.count)
            else:
                suite.run_runner("story", args.story, 1)
        elif args.count > 1:
            # Auto-pick from backlog with count > 1
            suite.run_runner("auto", None, args.count)
        else:
            # No args for run, show runner menu
            suite.show_banner()
            mode, story_id, count = suite.show_runner_menu()
            if mode != "back":
                suite.run_runner(mode, story_id, count)

    elif args.command == "verify":
        mode = "deep" if args.deep else "quick"
        suite.run_verifier(mode, args.story, args.interactive)

    else:
        # No command - interactive mode
        suite.run_interactive()


if __name__ == "__main__":
    main()
