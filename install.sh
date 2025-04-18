#!/bin/bash

# SysMonitor Deployment Script
# ---------------------------------

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

echo -e "${BOLD}Starting SysMonitor deployment...${RESET}\n"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed.${RESET}"
    echo "Please install Python 3 and try again."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d " " -f 2)
echo -e "${YELLOW}Detected Python version: ${PYTHON_VERSION}${RESET}"

if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}Error: requirements.txt not found!${RESET}"
    echo "Make sure you're running this script from the project root directory."
    exit 1
fi

echo -e "\n${BOLD}Step 1: Creating virtual environment...${RESET}"
if [ -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment already exists.${RESET}"
    read -p "Do you want to recreate it? (y/n): " recreate_venv
    if [[ $recreate_venv == "y" ]]; then
        echo "Removing existing virtual environment..."
        rm -rf venv
        python3 -m venv venv
        if [ $? -ne 0 ]; then
            echo -e "${RED}Failed to create virtual environment!${RESET}"
            exit 1
        fi
    fi
else
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to create virtual environment!${RESET}"
        exit 1
    fi
fi

echo -e "\n${BOLD}Step 2: Activating virtual environment...${RESET}"
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to activate virtual environment!${RESET}"
    exit 1
fi
echo -e "${GREEN}Virtual environment activated successfully.${RESET}"

echo -e "\n${BOLD}Step 3: Installing dependencies...${RESET}"
pip install --upgrade pip
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to install dependencies!${RESET}"
    exit 1
fi

echo -e "\n${GREEN}${BOLD}Deployment completed successfully!${RESET}"
echo -e "To start the application, run: ${YELLOW}source venv/bin/activate && python sysmonitor.py${RESET}"

echo -e "\n${BOLD}Creating startup script...${RESET}"
cat > start.sh << 'EOF'
#!/bin/bash
source venv/bin/activate
python sysmonitor.py
EOF

chmod +x start.sh
echo -e "${GREEN}Created startup script: start.sh${RESET}"

echo -e "\nYou can now run the application with: ${YELLOW}./start.sh${RESET}" 