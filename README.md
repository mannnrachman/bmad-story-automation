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
pip install -r requirements.txt
```

### 3. Run

```bash
# Interactive menu (recommended)
python bmad.py

# Or directly:
python bmad.py status           # View sprint status
python bmad.py run 5-2          # Run story 5-2
python bmad.py verify 5-2       # Verify story 5-2
```

> **Note for Linux/macOS:** use `python3` instead of `python`

---

## Scripts

| Script             | Function                                             |
| ------------------ | ---------------------------------------------------- |
| `bmad.py`          | Unified CLI - main entry point with interactive menu |
| `bmad-runner.py`   | Runs create-story + dev-story workflow               |
| `bmad-verifier.py` | Validates whether story is completed correctly       |

---

## bmad.py - Unified CLI

Main entry point with interactive menu.

```bash
python bmad.py              # Interactive menu
python bmad.py status       # Sprint status
python bmad.py run 5-2      # Run specific story
python bmad.py verify 5-2   # Verify specific story
```

### Interactive Menu

```
╔═══════════════════════════════════════════════════════════════════╗
║ 🚀 BMAD Story Automation                                          ║
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

---

## bmad-runner.py - Story Runner

Runs create-story + dev-story workflow automatically.

### Usage

```bash
# Specific story (recommended)
python bmad-runner.py -s 5-2

# Multiple iterations (auto-pick from backlog)
python bmad-runner.py -i 5

# Demo mode (testing UI without Claude)
python bmad-runner.py --demo -s 5-2
```

### Options

| Option         | Short | Default | Description                                        |
| -------------- | ----- | ------- | -------------------------------------------------- |
| `--story`      | `-s`  | -       | Specific story ID (e.g., `5-2`)                    |
| `--iterations` | `-i`  | 5       | Number of iterations (ignored if `--story` is set) |
| `--demo`       | -     | false   | Simulation mode without Claude                     |
| `--help`       | `-h`  | -       | Show help                                          |

### Verification Loop

After each story completes, runner automatically:

1. **Quick verify** - check tracking files
2. If failed → **Deep verify** with Claude
3. If code exists → **Fix** tracking files
4. If code doesn't exist → **Re-dev** story
5. Retry max 3x per story

### Screenshot

```
╔════════════════════════════ BMAD Automation ═════════════════════════════╗
║ ╭──────────────────────────────────────────────────────────────────────╮ ║
║ │ 🚀 BMAD Story Automation                                             │ ║
║ │ Story: 5-2  │  Iteration: 1/1  │  Elapsed: 02:15                     │ ║
║ ╰──────────────────────────────────────────────────────────────────────╯ ║
║                                                                          ║
║   ✓     Step 1: Read workflow status     Done            0.5s           ║
║   ✓     Step 2: Create story file        Done            2.3s           ║
║   ⏳    Step 3: Implement code           Running...                     ║
║   ⬚     Step 4: Run tests                Pending                        ║
║   ⬚     Step 5: Code review              Pending                        ║
║                                                                          ║
║   Progress: ████████░░░░░░░░░░░░░░░░░░░░░░░░░  22%  [2/9 steps]         ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## bmad-verifier.py - Story Verifier

Validates whether story is completed correctly.

### Usage

```bash
# Quick verify (file checks only)
python bmad-verifier.py 5-2

# Deep verify (with Claude AI)
python bmad-verifier.py 5-2 --deep

# Interactive mode (with action menu)
python bmad-verifier.py 5-2 -i

# Deep + Interactive (recommended for debugging)
python bmad-verifier.py 5-2 -d -i

# JSON output (for programmatic use)
python bmad-verifier.py 5-2 --json
```

### Options

| Option          | Short | Default | Description                                |
| --------------- | ----- | ------- | ------------------------------------------ |
| `story`         | -     | -       | Story ID (e.g., `5-2` or `5-2-story-name`) |
| `--deep`        | `-d`  | false   | Deep validation with Claude AI             |
| `--interactive` | `-i`  | false   | Show action menu after validation          |
| `--json`        | -     | false   | Output JSON (for runner subprocess)        |
| `--help`        | `-h`  | -       | Show help                                  |

### Validation Checks

**Quick Check:**

- ✓ Story file exists
- ✓ Status: done
- ✓ All tasks marked [x]
- ✓ Git commit exists
- ✓ Sprint status: done

**Deep Check (with Claude):**

- ✓ Code files exist
- ✓ Test files exist
- ✓ Implementation matches requirements
- ✓ Tests pass

### Interactive Actions

When using `-i`:

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

## Stopping the Script

```bash
# Press Ctrl+C in terminal, or:

touch .claude/bmad-stop          # Linux/macOS
New-Item .claude/bmad-stop       # Windows PowerShell
```

---

## Workflow

```
┌─────────────────┐
│  Sprint Status  │ ← View stories that need to be worked on
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│     Runner      │ ← Create story + Develop code + Commit
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Verifier     │ ← Validate story completion
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

## Tips

- Use `--demo` to test UI without Claude
- Use `-d -i` in verifier for debugging failed stories
- Deep check takes longer but is more accurate
- Create `.claude/bmad-stop` file to stop runner gracefully
- Sprint status shows the next story that needs to be worked on

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
