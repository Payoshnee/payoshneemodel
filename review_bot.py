import os
import subprocess
import json
import requests
import openai

# Set up OpenAI
client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPOSITORY"]
GITHUB_SHA = os.environ["GITHUB_SHA"]
PR_NUMBER = os.environ["GITHUB_REF"].split("/")[-1]

def get_changed_java_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        stdout=subprocess.PIPE,
        check=True
    )
    files = result.stdout.decode().splitlines()
    return [f for f in files if f.endswith(".java")]

def get_diff(file_path):
    result = subprocess.run(
        ["git", "diff", "origin/main", "--", file_path],
        stdout=subprocess.PIPE,
        check=True
    )
    return result.stdout.decode()

def call_llm(diff_text):
    prompt = """You are a senior Java reviewer. Given Java source code diffs, analyze them based on these 10 rules:

1. Adhere to Java naming conventions (e.g., PascalCase for class names).
2. Use lambdas/streams instead of basic for-loops when processing collections.
3. Handle nulls gracefully using Optional or @Nullable annotations.
4. Avoid exposing mutable internal state directly.
5. Catch exceptions from specific to general, use checked exceptions where appropriate.
6. Choose correct data structures (Map, List, Set) for the use case.
7. Default to private access unless external access is required.
8. Program to interfaces, not implementations.
9. Avoid unnecessary interfaces with no multiple implementations.
10. If equals() is overridden, hashCode() must be overridden too.

Return a JSON list. For each violation include:
- line: line number
- rule: rule name
- explanation: why it’s a violation
- suggestion: how to fix it
- severity: error/warning/info
- code_fix: suggested replacement code (if possible)
"""

    user_input = f"Review the following Java diff:\n\n{diff_text}"

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input}
        ],
        temperature=0.2
    )
    return json.loads(response.choices[0].message.content)
    

def post_comment(file_path, line, message):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls/{PR_NUMBER}/comments"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "body": message,
        "commit_id": GITHUB_SHA,
        "path": file_path,
        "line": line,
        "side": "RIGHT"
    }
    response = requests.post(url, headers=headers, json=payload)
    print(f"Posted comment on {file_path}:{line}")

def post_status(state, description):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/statuses/{GITHUB_SHA}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "state": state,
        "description": description,
        "context": "AutoReviewBot"
    }
    requests.post(url, headers=headers, json=payload)

# === MAIN ===
java_files = get_changed_java_files()
all_violations = []

for file in java_files:
    diff = get_diff(file)
    violations = call_llm(diff)
    all_violations.extend(violations)

    for v in violations:
        message = f"🔍 **{v['rule']}**\n{v['explanation']}\n💡 _{v['suggestion']}_"
        post_comment(file, v['line'], message)

if any(v['severity'] == "error" for v in all_violations):
    post_status("failure", "Critical issues found in PR.")
else:
    post_status("success", "All code review checks passed.")
