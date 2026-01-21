# BMAD Story Automation

Automated workflow script for BMAD Story with Rich UI. Combines **Runner** (create & develop stories) and **Verifier** (validate stories).

## Prerequisites

- **Python 3.8+**
- **Claude CLI** (for production mode)

## Getting Started

### 1. Clone Repository

```bash
git clone https://github.com/mannnrachman/bmad-story-automation.git
cd bmad-story-automation
```

> **Note:** You can also place this script directly in your project folder for easier access.

### 2. Install Dependencies

```bash
pip install rich pyyaml
```

### 3. Run

```bash
# Interactive menu (recommended)
python bmad.py

# Or use direct commands
python bmad.py status           # View sprint status
python bmad.py run 5-2          # Run specific story
python bmad.py verify 5-2       # Verify specific story
```

> **Note for Linux/macOS:** use `python3` instead of `python`

---

## Scripts Overview

| Script             | Function                                             |
| ------------------ | ---------------------------------------------------- |
| `bmad.py`          | Unified CLI - main entry point with interactive menu |
| `bmad-runner.py`   | Runs create-story + dev-story workflow               |
| `bmad-verifier.py` | Validates whether story is completed correctly       |

---

## bmad.py - Unified CLI (Recommended)

Main entry point with interactive menu and direct commands.

### Interactive Menu

```bash
python bmad.py
```

```
╔═══════════════════════════════════════════════════════════════════╗
║ 🚀 BMAD Automation Suite                                          ║
║                                                                   ║
║ Runner + Verifier unified CLI                                     ║
║                                                                   ║
║ 📁 Project: <your-project-path>                                   ║
║ 📄 Sprint file: ✓ Found                                           ║
╚═══════════════════════════════════════════════════════════════════╝

╭─────┬──────────────────────────────────────────╮
│ [0] │ 📁 Change Project Directory              │
│ [1] │ 📊 Check Sprint Status                   │
│ [2] │ ▶️  Runner (Create & Develop stories)    │
│ [3] │ ✅ Verifier (Validate stories)           │
│ [4] │ ❓ Help                                  │
│ [5] │ 🚪 Exit                                  │
╰─────┴──────────────────────────────────────────╯
```

### Direct CLI Commands

```bash
# Sprint Status
python bmad.py status                 # View sprint status with epic breakdown

# Runner Commands
python bmad.py run 5-2                # Run only story 5-2
python bmad.py run 5-2 -c 3           # Run 5-2, then continue to 5-3, 5-4 (3 stories total)
python bmad.py run -e 5               # Run ALL stories from epic 5
python bmad.py run -c 5               # Auto-pick 5 stories from backlog
python bmad.py run --demo             # Demo mode (simulated, no Claude)

# Verifier Commands
python bmad.py verify 5-2             # Quick verify story 5-2
python bmad.py verify 5-2 -d          # Deep verify with Claude AI
python bmad.py verify 5-2 -i          # Quick verify + interactive action menu
python bmad.py verify 5-2 -d -i       # Deep verify + interactive (recommended for debugging)
```

### Runner Submenu Options

When selecting `[2] Runner` from the menu:

| Option | Description                                                        |
| ------ | ------------------------------------------------------------------ |
| `[1]`  | Run specific story (enter story ID like `5-2`)                     |
| `[2]`  | Run from story + continue N more (e.g., start at 5-2, run 3 total) |
| `[3]`  | Run all stories from epic (e.g., all stories in epic 5)            |
| `[4]`  | Run next backlog stories (auto-pick, specify count)                |
| `[5]`  | Demo mode (simulated, no Claude)                                   |

### Verifier Submenu Options

When selecting `[3] Verifier` from the menu:

| Option | Description                                  |
| ------ | -------------------------------------------- |
| `[1]`  | Quick validate story (fast file checks only) |
| `[2]`  | Deep validate story (with Claude AI)         |
| `[3]`  | Quick + Interactive (with action menu)       |
| `[4]`  | Deep + Interactive (full check + actions)    |
| `[5]`  | Validate all stories in an epic              |

---

## Running Multiple Stories

### Common Scenarios

**Run a single story:**

```bash
python bmad.py run 5-2                # Only runs story 5-2
```

**Run from story 5-10, continue for 35 stories total (5-10 to 5-44):**

```bash
python bmad.py run 5-10 -c 35
```

**Run all stories in epic 5:**

```bash
python bmad.py run -e 5
```

**Auto-pick 10 stories from backlog:**

```bash
python bmad.py run -c 10
```

### How `-c` (count) Works

| Command          | What it does                               |
| ---------------- | ------------------------------------------ |
| `run 5-2`        | Runs only 5-2 (single story)               |
| `run 5-2 -c 1`   | Same as above, runs only 5-2               |
| `run 5-2 -c 3`   | Runs 5-2 → 5-3 → 5-4 (3 stories)           |
| `run 5-10 -c 35` | Runs 5-10 → 5-11 → ... → 5-44 (35 stories) |
| `run -c 5`       | Auto-picks 5 stories from backlog          |

### Via Interactive Menu

1. Run `python bmad.py`
2. Select `[2] Runner`
3. Select `[2] Run from story + continue N more`
4. Enter starting story: `5-10`
5. Enter total count: `35`

This will run stories 5-10, 5-11, 5-12, ... up to 5-44 (35 total).

---

## Workflow

```
┌─────────────────┐
│  Sprint Status  │ ← View stories (backlog/in-progress/done)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│     Runner      │ ← Create story + Develop code + Run tests + Commit
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Verifier     │ ← Validate story completion (quick or deep)
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
  PASS      FAIL
    │         │
    │    ┌────┴────┐
    │    │         │
    │    ▼         ▼
    │  Code?    No Code?
    │    │         │
    │    ▼         ▼
    │   Fix      Re-dev
    │  (tracking) (implement)
    │    │         │
    │    └────┬────┘
    │         │
    │         ▼
    │    ┌────────┐
    │    │ Retry  │ (max 3x)
    │    └────────┘
    │
    ▼
┌─────────────────┐
│  Next Story     │
└─────────────────┘
```

---

## Validation Checks

### Quick Check (default)

Fast validation without Claude AI:

- ✓ Story file exists
- ✓ Status: done in story file
- ✓ All tasks marked [x]
- ✓ Git commit exists (format: `feat(story): complete X-Y`)
- ✓ Sprint-status.yaml: done

### Deep Check (`-d` flag)

Uses Claude AI to verify:

- ✓ Code files actually exist
- ✓ Test files exist
- ✓ Implementation matches requirements

### Interactive Mode (`-i` flag)

Shows action menu after validation:

```
╭─ Select Action ───────────────────────────────────────────────╮
│ [1] 🔍 Deep Check First    - Verify code before fixing       │
│ [2] 🔧 Fix Story           - Update tracking files only      │
│ [3] 📝 Create Story        - Generate story from epic        │
│ [4] 💻 Dev Story           - Implement the story             │
│ [5] 🚪 Exit                                                  │
╰───────────────────────────────────────────────────────────────╯
```

---

## Runner Steps (11 Steps)

| Step | Description                                    |
| ---- | ---------------------------------------------- |
| 1    | Read workflow status (find next backlog story) |
| 2    | Create story file                              |
| 3    | Develop/implement story                        |
| 4    | Run tests                                      |
| 5    | Code review                                    |
| 6    | Fix issues                                     |
| 7    | Run tests until pass                           |
| 8    | Update story status to done                    |
| 9    | Update sprint-status.yaml                      |
| 10   | Update bmm-workflow-status.yaml                |
| 11   | Git commit                                     |

---

## Stopping the Script

```bash
# Option 1: Keyboard interrupt
Ctrl+C

# Option 2: Create stop file (graceful stop)
touch .claude/bmad-stop          # Linux/macOS
New-Item .claude/bmad-stop       # Windows PowerShell
```

---

## Tips

- Use `--demo` to test UI without Claude
- Use `-d -i` in verifier for debugging failed stories
- Deep check takes longer but verifies actual code exists
- Sprint status shows next story to work on with epic breakdown
- The runner auto-verifies after each story and retries up to 3x if failed

---

## Direct Script Usage (Advanced)

### bmad-runner.py

```bash
python bmad-runner.py                    # Default 5 iterations (auto-pick)
python bmad-runner.py -i 3               # 3 iterations
python bmad-runner.py -s 5-2             # Specific story only
python bmad-runner.py -s 5-2 -i 3        # Start at 5-2, run 3 stories
python bmad-runner.py --demo             # Demo mode
```

| Option         | Short | Description                       |
| -------------- | ----- | --------------------------------- |
| `--story`      | `-s`  | Specific story ID (e.g., `5-2`)   |
| `--iterations` | `-i`  | Number of iterations (default: 5) |
| `--demo`       | -     | Simulation mode without Claude    |

### bmad-verifier.py

```bash
python bmad-verifier.py 5-2              # Quick verify
python bmad-verifier.py 5-2 --deep       # Deep verify with Claude
python bmad-verifier.py 5-2 -i           # Interactive mode
python bmad-verifier.py 5-2 -d -i        # Deep + interactive
python bmad-verifier.py 5-2 --json       # JSON output (for scripts)
```

| Option          | Short | Description                        |
| --------------- | ----- | ---------------------------------- |
| `--deep`        | `-d`  | Deep validation with Claude AI     |
| `--interactive` | `-i`  | Show action menu after validation  |
| `--json`        | -     | Output JSON (for programmatic use) |

---

## Requirements

- Python 3.8+
- Rich library (`pip install rich`)
- PyYAML (`pip install pyyaml`)
- Claude CLI (for production mode)

---

## Contributing

We welcome contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.
