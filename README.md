# BMAD Story Automation

Automated workflow script for BMAD Story with Rich UI. This script helps automate story workflow iterations with an interactive and informative CLI interface.

## Prerequisites

- **Python 3.8+**
- **Claude CLI** (for production mode)

## Getting Started

### 1. Clone Repository

```bash
git clone https://github.com/mannnrachman/bmad-story-automation.git
cd bmad-story-automation
```

### 2. Install Dependencies

```bash
# Windows
pip install -r requirements.txt

# Linux/macOS
pip3 install -r requirements.txt
```

### 3. Run Script

```bash
# Demo mode (testing UI without Claude CLI)
python bmad-runner.py --demo -i 1

# Production mode (requires Claude CLI)
python bmad-runner.py -i 5
```

**Note for Windows users:** use `python` instead of `python3`

---

## Options

| Option         | Short | Default | Description                      |
| -------------- | ----- | ------- | -------------------------------- |
| `--iterations` | `-i`  | 5       | Number of iterations             |
| `--demo`       | -     | false   | Simulation mode (without Claude) |
| `--help`       | `-h`  | -       | Show help                        |

## Stopping the Script

To stop the script while running:

```bash
# Press Ctrl+C in terminal, or:

touch .claude/bmad-stop          # Linux/macOS
New-Item .claude/bmad-stop       # Windows
```

## Demo

Example output from the script with Rich UI:

```
╔══════════════════════════════════════════════════════════════════╗
║                       BMAD Automation                            ║
╠══════════════════════════════════════════════════════════════════╣
║  Story: STORY-2.1.1  │  Iteration: 1/5  │  Elapsed: 02:15        ║
║                                                                  ║
║   ✓  Step 1: Read workflow status             Done        0.5s   ║
║   ✓  Step 2: Create story file                Done        2.3s   ║
║   ⏳ Step 3: Implement code                   Running...         ║
║   ⬚  Step 4: Run tests                        Pending            ║
║   ⬚  Step 5: Code review                      Pending            ║
║                                                                  ║
║   Progress: ████████░░░░░░░░░░░░░░░░░░░░░░░░░  22%  [2/9 steps]  ║
╚══════════════════════════════════════════════════════════════════╝
```

## Contributing

We welcome contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.
