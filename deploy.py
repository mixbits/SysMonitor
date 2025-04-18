#!/usr/bin/env python3
"""
SysMonitorDeployment Script
---------------------------------
This script automates the setup of a Python virtual environment
and installation of dependencies for the SysMonitor application.
"""

import os
import sys
import subprocess
import platform
import shutil
from pathlib import Path

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def print_colored(text, color):
    """Print colored text to the terminal."""
    print(f"{color}{text}{Colors.END}")

def print_step(step_number, description):
    """Print a deployment step."""
    print_colored(f"\nStep {step_number}: {description}", Colors.BOLD)

def check_python_version():
    """Check if the Python version is compatible."""
    print_colored(f"Detected Python: {platform.python_version()}", Colors.YELLOW)
    major, minor = sys.version_info.major, sys.version_info.minor
    if major < 3 or (major == 3 and minor < 6):
        print_colored("Error: Python 3.6 or higher is required.", Colors.RED)
        sys.exit(1)

def run_command(command, error_message=None):
    """Run a shell command and handle errors."""
    try:
        subprocess.run(command, check=True, shell=True)
        return True
    except subprocess.CalledProcessError:
        if error_message:
            print_colored(f"Error: {error_message}", Colors.RED)
        return False

def create_virtual_environment():
    """Create a Python virtual environment."""
    print_step(1, "Creating virtual environment")
    
    venv_path = Path("venv")
    if venv_path.exists():
        print_colored("Virtual environment already exists.", Colors.YELLOW)
        user_input = input("Do you want to recreate it? (y/n): ").lower()
        if user_input == 'y':
            print("Removing existing virtual environment...")
            shutil.rmtree(venv_path)
            if not run_command(
                "python3 -m venv venv",
                "Failed to create virtual environment."
            ):
                sys.exit(1)
        else:
            print("Using existing virtual environment.")
    else:
        if not run_command(
            "python3 -m venv venv",
            "Failed to create virtual environment."
        ):
            sys.exit(1)

def install_dependencies():
    """Install dependencies from requirements.txt."""
    print_step(2, "Installing dependencies")
    
    if not Path("requirements.txt").exists():
        print_colored("Error: requirements.txt not found!", Colors.RED)
        print("Make sure you're running this script from the project root directory.")
        sys.exit(1)
    
    if platform.system() == "Windows":
        activate_cmd = ".\\venv\\Scripts\\activate"
        activate_and_install = f"{activate_cmd} && pip install --upgrade pip && pip install -r requirements.txt"
        success = run_command(activate_and_install, "Failed to install dependencies.")
    else:
        activate_cmd = "source venv/bin/activate"
        activate_and_install = f"{activate_cmd} && pip install --upgrade pip && pip install -r requirements.txt"
        success = run_command(activate_and_install, "Failed to install dependencies.")
    
    if not success:
        sys.exit(1)
    
    print_colored("Dependencies installed successfully.", Colors.GREEN)

def create_startup_script():
    """Create a script to easily start the application."""
    print_step(3, "Creating startup script")
    
    if platform.system() == "Windows":
        with open("start.bat", "w") as f:
            f.write("@echo off\n")
            f.write("call venv\\Scripts\\activate\n")
            f.write("python sysmonitor.py\n")
        print_colored("Created startup script: start.bat", Colors.GREEN)
        print_colored("You can now run the application with: start.bat", Colors.YELLOW)
    else:
        with open("start.sh", "w") as f:
            f.write("#!/bin/bash\n")
            f.write("source venv/bin/activate\n")
            f.write("python sysmonitor.py\n")
        os.chmod("start.sh", 0o755)
        print_colored("Created startup script: start.sh", Colors.GREEN)
        print_colored("You can now run the application with: ./start.sh", Colors.YELLOW)

def main():
    """Main deployment function."""
    print_colored("Starting SysMonitor deployment...", Colors.BOLD)
    
    check_python_version()
    
    create_virtual_environment()
    
    install_dependencies()
    
    create_startup_script()
    
    print_colored("\nDeployment completed successfully!", Colors.GREEN + Colors.BOLD)

if __name__ == "__main__":
    main() 