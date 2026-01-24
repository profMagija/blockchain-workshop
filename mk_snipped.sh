#!/bin/bash

mkdir -p snipped
cp -r .vscode README.md pyproject.toml snipped
uv pip freeze > snipped/requirements.txt
python snip.py bcws snipped/bcws