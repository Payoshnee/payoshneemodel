# 🧠 AutoReviewBot

**AutoReviewBot** is an end-to-end GitHub PR review automation system powered by a Large Language Model (LLM). It automatically analyzes Java code changes in pull requests, flags violations based on a predefined set of 10 coding standards, and posts inline or summary review comments with code fix suggestions.

---

## 🚀 Features

- ✅ Automatically triggers on every pull request (PR) to the repository  
- 🧪 Analyzes changed `.java` files only — not the entire repo  
- 🧠 Uses **GPT-4** to enforce 10 firm-specific Java review rules  
- 💬 Posts **inline review comments** with explanation and code fix  
- 🧾 Posts a **summary comment** on the PR  
- 🟥 Fails the PR if **critical violations** are found  
- 🔐 Works with **GitHub Actions** + **Personal Access Token (PAT)**  
- 📦 Fully containerized (optional) and extensible  

---

## 🧠 Rules Enforced by AutoReviewBot

1. Adhere to Java Naming Conventions  
2. Use Lambdas and Streams (Java 8+)  
3. Handle Nulls Gracefully (Optional, annotations)  
4. Avoid Exposing Mutable Internal State  
5. Manage Exceptions Correctly  
6. Select Appropriate Data Structures  
7. Default to Private Access  
8. Program to Interfaces, Not Implementations  
9. Don't Overuse Interfaces  
10. Override `hashCode()` When Overriding `equals()`  

---

## 🏗️ Architecture Overview

```plaintext
┌─────────────────────────────────────────────────────────────────────┐
│                        GitHub (Pull Request)                        │
│  PR Created/Updated  ─────────────────────────►  Webhook/Action     │
└─────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
                              ┌──────────────────────────┐
                              │  GitHub Actions Workflow │
                              └──────────────────────────┘
                                            │
                                            ▼
                              ┌──────────────────────────┐
                              │ review_bot.py (Python)   │
                              └──────────────────────────┘
                                            │
                        ┌────────────┬──────────────┬─────────────┐
                        ▼            ▼              ▼             ▼
              Git CLI (diff)    OpenAI GPT-4     GitHub API   PR Metadata
                 │                  │              │             │
                 ▼                  ▼              ▼             ▼
       Extract changed       Analyze diffs      Post comments   Update PR status
        Java files             for violations     and summary     (pass/fail)
```
---

## 🧠 LLM Integration

Model: GPT-4 (via OpenAI Python SDK)

Prompt Style: System prompt describing all 10 rules + custom prompt per diff

Output Format: Strict JSON with fields:

line

rule

explanation

suggestion

severity (info / warning / error)

code_fix (recommended snippet)

## 🛠️ Setup Instructions

✅ 1. Generate a GitHub Personal Access Token (PAT)
Go to GitHub Token Settings

Click "Generate new token (classic)"

Select scopes:

repo

write:discussion

read:org

Copy and save the token securely

✅ 2. Add GitHub Secrets
In your repository:

Navigate to: Settings → Secrets → Actions

Add the following secrets:

Name	Description
OPENAI_API_KEY	Your OpenAI GPT-4 API key
BOT_TOKEN	Your GitHub PAT (from above step)

✅ 3. Configure GitHub Workflow

Create .github/workflows/review.yml:

```plaintext yaml
name: AutoReviewBot

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout full history
        uses: actions/checkout@v3
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: 3.11

      - name: Install dependencies
        run: pip install openai requests

      - name: Run AutoReviewBot
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.BOT_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          GITHUB_SHA: ${{ github.sha }}
          GITHUB_REF: ${{ github.ref }}
        run: python review_bot.py
```
✅ 4. Create Pull Requests to Trigger the Bot
AutoReviewBot will:

Detect changed Java files

Ask GPT-4 to review diffs

Post inline + summary comments

Update PR status with pass/fail

---
## 📦 Project Structure

```plaintext
.
├── review_bot.py             # Main logic: fetch PR, diff, LLM, GitHub API
├── .github/
│   └── workflows/
│       └── review.yml        # GitHub Actions workflow trigger
├── README.md                 # Documentation

```
---

## Example Comment Output (Inline)
```
// Rule: Handle Nulls Gracefully
// name.toUpperCase() may throw NullPointerException.

if (name != null) System.out.println(name.toUpperCase());
```
