#!/bin/bash

# Local .bashrc for this repository
# This file contains project-specific bash configurations

# Add LM Studio to PATH for this project
# Commenting 1.25.26 because I don't have it installed
# export PATH="$PATH:/c/Users/tmf77/.lmstudio/bin"
# alias lms='/c/Users/tmf77/.lmstudio/bin/lms.exe'

# Add Ollama to PATH for this project
export PATH="$PATH:/c/Users/jonyl/AppData/Local/Programs/Ollama"
alias ollama='/c/Users/jonyl/AppData/Local/Programs/Ollama/ollama.exe'

# Add R to your Path for this project 
export PATH="$PATH:/c/Program\ Files/R/R-4.5.2/bin"
alias Rscript='/c/Program\ Files/R/R-4.5.2/bin/Rscript.exe'
# Add R libraries to your path for this project 
export R_LIBS_USER="/c/Users/jonyl/AppData/Local/R/win-library/4.5"

# Add Python to your Path for this project 
export PATH="$PATH:/c/Users/jonyl/AppData/Local/Python/pythoncore-3.14-64:/c/Users/jonyl/AppData/Local/Python/pythoncore-3.14-64/Scripts"
alias python='/c/Users/jonyl/AppData/Local/Python/pythoncore-3.14-64/python.exe'

# Add uvicorn to your Path for this project - if using Python for APIs (here's mine)
# Commenting 1.25.26 because I don't have it installed
# export PATH="$PATH:/c/Users/jonyl/AppData/Roaming/Python/Python314/Scripts"

echo "✅ Local .bashrc loaded."