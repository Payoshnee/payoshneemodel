import os
import subprocess
import json
import requests
import openai

client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPOSITORY"]
GITHUB_SHA = os.environ["GITHUB_SHA"]
PR_NUMBER = os.environ["GITHUB_REF"].split("/")[-2]

def get_changed_java_files():
    result = subprocess.run(["git", "diff", "--name-only", "origin/main"], stdout=subprocess.PIPE, check=True)
    return [f for f in result.stdout.decode().splitlines() if f.endswith(".java")]

def get_diff(file_path):
    result = subprocess.run(["git", "diff", "origin/main", "--", file_path], stdout=subprocess.PIPE, check=True)
    return result.stdout.decode()

def call_llm(diff_text):
    prompt = """You are a senior Java reviewer. Apply these 10 rules:

1. Java naming conventions (PascalCase for class names).
2. Prefer lambdas/streams over raw for-loops.
3. Handle nulls safely (Optional/@Nullable).
4. Don't expose mutable internal state.
5. Use proper exception handling.
6. Use the right data structure.
7. Keep variables/methods private unless needed.
8. Program to interfaces.
9. Avoid pointless interfaces.
10. Override hashCode if equals is overridden.

Respond with a JSON list of violations:
- line
- rule
- explanation
- suggestion
- severity (error/warning/info)
- code_fix (if possible)
"""
    user_input = f"Review this Java diff:\n\n{diff_text}"
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input}
        ],
        temperature=0.2
    )
    return json.loads(response.choices[0].message.content)

def post_inline_comment(file_path, line, body):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls/{PR_NUMBER}/comments"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "body": body,
        "commit_id": GITHUB_SHA,
        "path": file_path,
        "line": line,
        "side": "RIGHT"
    }
    response = requests.post(url, headers=headers, json=payload)
    print(f"Posted inline comment → {response.status_code}: {response.text}")

def post_summary_comment(body):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues/{PR_NUMBER}/comments"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    requests.post(url, headers=headers, json={"body": body})

def post_status(state, description):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/statuses/{GITHUB_SHA}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    requests.post(url, headers=headers, json={
        "state": state,
        "description": description,
        "context": "AutoReviewBot"
    })

# === MAIN ===
violations_total = []
for file in get_changed_java_files():
    diff = get_diff(file)
    violations = call_llm(diff)
    for v in violations:
        v['file'] = file  # track file in summary
        violations_total.append(v)
        try:
            post_inline_comment(f"**{v['rule']}**\n\n"
    f"{v['explanation']}\n\n"
    f"💡 **Suggestion**: {v['suggestion']}\n\n"
    f"```java\n{v.get('code_fix', '// no fix provided')}\n```")
        except Exception as e:
            print(f"Failed to post inline comment: {e}")

# ✅ Summary fallback
if violations_total:
    summary = "\n\n".join([
        f"🔍 **{v['rule']}** in `{v['file']}` (line {v['line']}):\n{v['explanation']}\n💡 {v['suggestion']}\n```java\n{v.get('code_fix', '// no fix provided')}\n```"
        for v in violations_total
    ])
    post_summary_comment(f"### 🧠 AutoReviewBot Summary\n\n{summary}")

# ✅ Set status
if any(v["severity"] == "error" for v in violations_total):
    post_status("failure", "Critical rule violations found")
else:
    post_status("success", "All checks passed")
#hhhhh
#hhhhh