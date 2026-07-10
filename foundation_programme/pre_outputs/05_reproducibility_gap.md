# SMC Codex Desk — Reproducibility Gap Report (WP-0042 pre-output #5)
# Generated: 2026-07-10 against frozen baseline 554e499

## 1. Python project metadata (pyproject.toml)
[project]
name = "smc-codex-desk"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "pandas>=2.2",
  "numpy>=1.26",
  "matplotlib>=3.8",
  "mplfinance>=0.12",
  "pillow>=10.0",
  "pydantic>=2.6",
  "fastapi>=0.110",
  "plotly>=5.20",
  "opencv-python>=4.10",
  "requests>=2.31",
]

[tool.setuptools.packages.find]
include = ["smc_desk*"]

## 2. requirements files
-rw-r--r--@ 1 tobimobolade  staff  132 Mar 10 15:56 requirements.txt
--- requirements.txt ---
pandas>=2.2
numpy>=1.26
matplotlib>=3.8
mplfinance>=0.12
pillow>=10.0
pydantic>=2.6
fastapi>=0.110
plotly>=5.20
opencv-python>=4.10

## 3. Dependency lock (pip / poetry / uv)
MISSING: poetry.lock
MISSING: Pipfile.lock
MISSING: requirements.lock
MISSING: uv.lock
MISSING: pyproject.lock

## 4. CI configuration
MISSING: .github/workflows
MISSING: .gitlab-ci.yml
MISSING: .circleci/config.yml
MISSING: Jenkinsfile

## 5. Console entry points
(no entry_points in pyproject.toml)

## 6. .gitignore + large generated dirs
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environment
.venv/
venv/
ENV/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Data (large files)
/data/

# Stress test outputs
reports/

# Backtest outputs (artifacts)
backtests/

# Case library (artifacts)
case_library/


## 7. Python version constraint
4:requires-python = ">=3.12"
14:  "opencv-python>=4.10",

## 8. Test counts (just before baseline)
Per VALIDATION_REGISTRY.json, latest_validation id=WP-0022 (date 2026-06-27)

## 9. Last full-pytest baseline
WP-0041 final report claims: 740 passed, 1 skipped
(see governance/WORK_PACKAGES/WP-0041-PROFESSIONAL-AI-SMC-ANNOTATION-PLANNER/final_report.md)
