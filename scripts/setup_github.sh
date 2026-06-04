#!/usr/bin/env bash
# Initializes a local git repo and pushes to a new private GitHub repository.
# Requirements: git, GitHub CLI (gh) installed and authenticated.
set -euo pipefail

REPO_NAME="stock-ai-whatsapp-alert"

echo "→ Initializing git..."
git init
git checkout -b main

echo "→ Creating .gitignore-safe initial commit..."
git add .
git commit -m "init: stock-ai-whatsapp-alert MVP

- Data provider layer (yfinance + Sectors.app placeholder)
- Technical indicator engine (pandas-ta)
- Rule-based signal engine with risk controls
- Meta WhatsApp Cloud API + Twilio fallback
- FastAPI TradingView webhook
- Daily watchlist scanner CLI
- Streamlit monitoring dashboard
- Backtest module (vectorbt + pandas fallback)
- GitHub Actions CI"

echo "→ Creating private GitHub repository and pushing..."
gh repo create "$REPO_NAME" --private --source=. --remote=origin --push

echo ""
echo "✅ Done! Repository: https://github.com/$(gh api user --jq .login)/$REPO_NAME"
