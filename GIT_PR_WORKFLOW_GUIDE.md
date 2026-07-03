# Git Pull Request Workflow Guide

This guide explains how to properly add features to a project using Pull Requests (PRs) instead of pushing directly to main. This is the standard professional workflow for team collaboration.

---

## 📋 Overview

Instead of pushing directly to `main`, you:
1. Create a feature branch
2. Make your changes on that branch
3. Push the branch to remote
4. Open a Pull Request
5. Review and merge

---

## 🚀 Step-by-Step Workflow

### Step 1: Make Sure You're on Main and Up-to-Date

```bash
git checkout main
git pull origin main
```

### Step 2: Create a Feature Branch

Name your branch descriptively (e.g., `feature/add-security-scanning`, `fix/login-bug`, `docs/update-readme`):

```bash
git checkout -b feature/your-feature-name
```

### Step 3: Make Your Changes

- Add new files
- Edit existing files
- Do whatever work is needed

### Step 4: Stage and Commit Your Changes

```bash
# Stage all changes
git add -A

# Or stage specific files
git add path/to/file.py

# Commit with a descriptive message
git commit -m "feat: Add security scanning workflow

Add Gitea CI/CD workflow for automated security scanning:
- Bandit security linter for Python code analysis
- Safety check for known vulnerabilities in dependencies
- Secret scanning to detect hardcoded credentials

Runs on push and pull requests to main/master branches."
```

### Step 5: Push Your Branch to Remote

```bash
git push -u origin feature/your-feature-name
```

You'll see output like:
```
remote: Create a new pull request for 'feature/your-feature-name':
remote:   https://gitea.personalsoftware.space/username/repo/pulls/new/feature/your-feature-name
```

### Step 6: Create the Pull Request on Gitea

1. Go to your repository on Gitea
2. Click **"Pull Requests"** in the top navigation
3. Click the green **"New Pull Request"** button
4. Select your feature branch as "pull from"
5. Select `main` as "merge into"
6. Add a title and description
7. Click **"Create Pull Request"**

### Step 7: Merge the Pull Request

1. Review the changes in the PR
2. Click **"Create merge commit"**
3. Optionally check "Delete Branch" to clean up

### Step 8: Sync Your Local Repository

After merging, update your local main branch:

```bash
git checkout main
git pull origin main
```

Optionally delete your local feature branch:

```bash
git branch -d feature/your-feature-name
```

---

## 📝 Commit Message Conventions

Use conventional commit prefixes:

| Prefix | Use Case |
|--------|----------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation changes |
| `chore:` | Maintenance tasks |
| `refactor:` | Code refactoring |
| `test:` | Adding tests |
| `style:` | Code style changes |

**Examples:**
```
feat: Add user authentication
fix: Resolve login timeout issue
docs: Update API documentation
chore: Add security scanning workflow
```

---

## 🔒 Adding Security Scanning Workflow

To add the security scanning workflow to any Python project:

### 1. Create the workflow directory and file:

```bash
mkdir -p .gitea/workflows
```

### 2. Create `.gitea/workflows/security-scan.yml`:

```yaml
name: Security Scan

on:
  push:
    branches:
      - main
      - master
  pull_request:
    branches:
      - main
      - master

jobs:
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install safety bandit

      - name: Run Bandit security linter
        run: |
          bandit -r . -x ./test,./venv,./.venv -f json -o bandit-report.json || true
          bandit -r . -x ./test,./venv,./.venv

      - name: Check for known vulnerabilities
        run: |
          if [ -f requirements.txt ]; then
            safety check -r requirements.txt --full-report || true
          fi

      - name: Scan for secrets
        run: |
          echo "Scanning for potential secrets..."
          grep -rn --include="*.py" -E "(api_key|secret|password|token)\s*=\s*['\"][^'\"]+['\"]" . || echo "No hardcoded secrets found in Python files"

  dependency-audit:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install pip-audit
        run: pip install pip-audit

      - name: Run pip-audit
        run: |
          if [ -f requirements.txt ]; then
            pip-audit -r requirements.txt || true
          fi
```

### 3. Add via Pull Request:

```bash
# Create feature branch
git checkout -b feature/add-security-scanning

# Stage the workflow file
git add .gitea/workflows/security-scan.yml

# Commit
git commit -m "feat: Add security scanning workflow

Add Gitea CI/CD workflow for automated security scanning:
- Bandit security linter for Python code analysis
- Safety check for known vulnerabilities in dependencies
- Secret scanning to detect hardcoded credentials
- pip-audit for dependency vulnerability auditing

Runs on push and pull requests to main/master branches."

# Push branch
git push -u origin feature/add-security-scanning

# Then go to Gitea and create the PR
```

---

## 📁 Recommended .gitignore for Python Projects

```gitignore
# Environment and secrets
.env
*.json
!package.json
!package-lock.json

# Logs
*.log
nohup.out

# Python
__pycache__/
*.py[cod]
*$py.class
venv/
.venv/

# Test files
test/
test_*.py
test_*.html

# Documentation (internal notes)
*.md
!README.md

# Backup files
*.backup
*_backup.py

# Temporary files
temp_*

# System files
.DS_Store
Thumbs.db
```

---

## ✅ Quick Reference Commands

```bash
# Start new feature
git checkout main
git pull origin main
git checkout -b feature/my-feature

# Save work
git add -A
git commit -m "feat: Description of changes"

# Push for PR
git push -u origin feature/my-feature

# After PR is merged
git checkout main
git pull origin main
git branch -d feature/my-feature
```

---

## 🔗 References

- [Gitea Documentation](https://docs.gitea.com/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Git Branching](https://git-scm.com/book/en/v2/Git-Branching-Basic-Branching-and-Merging)
