#!/usr/bin/env python3
"""
Test runner for Omnix application
Runs all test suites including OpenAI API compatibility tests
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path

# Add the project root and src to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'src'))

def run_tests(test_type="all", verbose=True, coverage=False):
    """
    Run the test suite
    
    Args:
        test_type (str): Type of tests to run ('all', 'unit', 'integration', 'openai')
        verbose (bool): Whether to run tests in verbose mode
        coverage (bool): Whether to run with coverage reporting
    """
    
    # Test directories and files
    test_files = {
        "unit": [
            "tests/test_unit_backend.py",
            "tests/test_huggingface_url.py",
            "tests/test_search.py"
        ],
        "openai": [
            "tests/test_openai_api.py",
            "tests/test_openai_compatibility.py"
        ],
        "integration": [
            "tests/test_openai_integration.py"
        ],
        "api": [
            "src/tests/api"
        ],
        "healthcheck": [
            "src/tests/api/healthcheck"
        ],
        "e2e": [
            "src/tests/e2e"
        ],
    }
    
    # Determine which tests to run
    if test_type == "all":
        test_targets = test_files["unit"] + test_files["openai"] + test_files["integration"]
    elif test_type in test_files:
        test_targets = test_files[test_type]
    else:
        print(f"Unknown test type: {test_type}")
        return False
    
    # Build pytest command
    cmd = ["python", "-m", "pytest"]
    
    if verbose:
        cmd.append("-v")
    
    if coverage:
        cmd.extend(["--cov=app", "--cov=openai_api", "--cov-report=html", "--cov-report=term"])
    
    # Add test files
    cmd.extend(test_targets)
    
    print(f"Running tests: {test_type}")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 60)
    
    # Run the tests
    try:
        result = subprocess.run(cmd, cwd=project_root, check=False)
        return result.returncode == 0
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
        return False
    except Exception as e:
        print(f"Error running tests: {e}")
        return False

def check_dependencies():
    """Check if required test dependencies are installed"""
    required_packages = [
        "pytest",
        "pytest-cov",
        "requests",
        "fastapi",
        "uvicorn"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("Missing required packages:")
        for package in missing_packages:
            print(f"  - {package}")
        print("\nInstall missing packages with:")
        print(f"  pip install {' '.join(missing_packages)}")
        return False
    
    return True

def main():
    """Main test runner"""
    parser = argparse.ArgumentParser(description="Run Omnix test suite")
    parser.add_argument(
        "--type", 
        choices=["all", "unit", "openai", "integration", "api", "healthcheck", "e2e"],
        default="all",
        help="Type of tests to run (default: all)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Run tests with verbose output"
    )
    parser.add_argument(
        "--no-verbose",
        action="store_true",
        help="Run tests without verbose output"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Generate coverage report"
    )
    parser.add_argument(
        "--check-deps",
        action="store_true",
        help="Check if required dependencies are installed"
    )
    
    args = parser.parse_args()
    
    # Check dependencies if requested
    if args.check_deps:
        if not check_dependencies():
            sys.exit(1)
        print("All required dependencies are installed!")
        return
    
    # Check dependencies
    if not check_dependencies():
        print("Please install missing dependencies before running tests.")
        sys.exit(1)
    
    # Run tests
    success = run_tests(
        test_type=args.type,
        verbose=not args.no_verbose,
        coverage=args.coverage
    )
    
    if success:
        print("\n" + "=" * 60)
        print("All tests passed!")
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("Some tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()