#!/bin/bash
echo "=== Ralph Wiggum - Interactive Mode ==="

claude -p "
You are a coding agent. Read prd.json and progress.txt.
Choose ONE task with passes: false and:
1. Explain what you will do BEFORE doing it
2. Implement the feature
3. Show the tests you will run
4. Wait for confirmation before committing
"

echo ""
echo "Do you want to proceed with the commit? (y/n)"
read answer

if [ "$answer" = "y" ]; then
  git add .
  git commit -m "feat: implementation by Ralph"
  echo "Commit done!"
fi
