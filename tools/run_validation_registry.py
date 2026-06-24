#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

def main():
    print("Running Validation Registry...")
    
    # Run the tests using pytest and get JSON output
    # Note: We run it with pytest -q and we also capture output. 
    # To get a structured registry, we could use pytest --json-report but let's just run pytest
    
    # Let's run unittest
    print("Running unittest suite...")
    unittest_res = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        capture_output=True, text=True
    )
    
    # Let's run pytest
    print("Running pytest suite...")
    pytest_res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        capture_output=True, text=True
    )
    
    print("Running stress tests...")
    stress_res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/stress_tests/", "-q"],
        capture_output=True, text=True
    )
    
    all_passed = (
        unittest_res.returncode == 0 and 
        pytest_res.returncode == 0 and 
        stress_res.returncode == 0
    )
    
    registry = {
        "status": "PASS" if all_passed else "FAIL",
        "suites": {
            "unittest": {
                "exit_code": unittest_res.returncode,
            },
            "pytest": {
                "exit_code": pytest_res.returncode,
            },
            "stress": {
                "exit_code": stress_res.returncode,
            }
        }
    }
    
    evidence_dir = Path("evidence")
    evidence_dir.mkdir(exist_ok=True)
    registry_file = evidence_dir / "VALIDATION_REGISTRY.json"
    
    with open(registry_file, "w") as f:
        json.dump(registry, f, indent=2)
        
    print(f"\nValidation Registry updated: {registry_file}")
    print(f"Overall Status: {registry['status']}")
    
    if not all_passed:
        print("\n--- Unittest Output ---")
        print(unittest_res.stderr)
        print("\n--- Pytest Output ---")
        print(pytest_res.stdout)
        print("\n--- Stress Test Output ---")
        print(stress_res.stdout)
        sys.exit(1)

if __name__ == "__main__":
    main()
