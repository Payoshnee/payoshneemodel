import os
import subprocess
import json
import requests
import openai
import yaml
import time
import csv


# === ENV ===
client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPOSITORY"]
GITHUB_SHA = os.environ["GITHUB_SHA"]
GITHUB_REF = os.environ["GITHUB_REF"]
PR_NUMBER = GITHUB_REF.split("/")[-2]

# === RULES ===
with open("rules.yaml", "r") as f:
    RULES = yaml.safe_load(f)["rules"]

RULE_PROMPT = "\n".join([
    f"- id: {r['id']}  # {r['hint']}\n  severity: {r['severity']}\n  hint: \"{r['hint']}\""
    for r in RULES
])

LOG_FILE = "autoreviewbot_violations_log.csv"


def get_changed_java_files():
    result = subprocess.run(["git", "diff", "--name-only", "origin/main"], stdout=subprocess.PIPE, check=True)
    return [f for f in result.stdout.decode().splitlines() if f.endswith(".java")]


def get_diff(file_path):
    result = subprocess.run(["git", "diff", "--unified=0", "origin/main", "--", file_path], stdout=subprocess.PIPE, check=True)
    return result.stdout.decode()


def redact_sensitive_content(text):
    return text.replace(os.environ.get("OPENAI_API_KEY", "<redacted>"), "<API_KEY>")


def call_llm(diff_text):
    diff_text = redact_sensitive_content(diff_text)
    prompt = f"""
You are AutoReviewBot, an automated reviewer that enforces internal Java rules.  
Respond ONLY with a valid JSON array (no markdown).  

<<RULES
{RULE_PROMPT}
RULES

<<SCHEMA
Each array element must have:  
rule (string from id above)  
line (integer, line number in NEW file)  
explanation (<=200 chars)  
suggestion (<=100 chars)  
severity (error|warning|info)  
code_fix (string, may be empty)  
SCHEMA

<<DIFF
{diff_text}
DIFF

TASKS
1. Review only the changed lines in <<DIFF>> against <<RULES>>.  
2. Emit a JSON array that validates against <<SCHEMA>>.  
3. Include at most 40 elements.  
4. Think through steps internally but output ONLY the JSON array.  
5. If no violations, output [].
END
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"OpenAI call failed: {e}")
        return []


def get_pr_diff_positions(file_path):
    """Maps new-line numbers to diff position for GitHub API inline comments."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls/{PR_NUMBER}/files"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception("Failed to fetch PR files")

    diff_map = {}
    for file in response.json():
        if file["filename"] != file_path:
            continue
        position = 0
        new_line = None
        for line in file.get("patch", "").split("\n"):
            position += 1
            if line.startswith("@@"):
                # Example: @@ -1,3 +1,9 @@
                hunk = line.split(" ")
                new_line = int(hunk[2].split(",")[0].replace("+", "")) - 1
            elif line.startswith("+"):
                new_line += 1
                diff_map[new_line] = position
            elif not line.startswith("-"):
                new_line += 1  # context line
        break
    return diff_map


def post_inline_comment(repo, pr_number, body, commit_id, path, position):
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "body": body,
        "commit_id": commit_id,
        "path": path,
        "position": position
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

def log_violation(v):
    with open(LOG_FILE, "a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            datetime.utcnow().isoformat(),
            v["file"],
            v["line"],
            v["rule"],
            v["severity"],
            v["explanation"],
            v["suggestion"],
            v.get("code_fix", "")
        ])
        
def maintainer_override_exists():
    """Check if the PR has a label like 'override-autoreview' to skip validation."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues/{PR_NUMBER}/labels"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            labels = [label['name'] for label in response.json()]
            return "override-autoreview" in labels
        else:
            print(f"[WARN] Failed to fetch labels → {response.status_code}")
            return False
    except Exception as e:
        print(f"[ERROR] While checking override label: {e}")
        return False

# === MAIN ===
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["timestamp", "file", "line", "rule", "severity", "explanation", "suggestion", "code_fix"])

if maintainer_override_exists():
    print("[INFO] Maintainer override detected. Skipping review.")
    post_status("success", "Review skipped by maintainer override.")
    exit(0)


violations_total = []
for file in get_changed_java_files():
    diff = get_diff(file)
    violations = call_llm(diff)
    diff_positions = get_pr_diff_positions(file)

    for v in violations:
        v['file'] = file
        violations_total.append(v)
        body = f"**{v['rule']}**\n\n{v['explanation']}\n💡 Suggestion: {v['suggestion']}\n```java\n{v.get('code_fix', '// no fix provided')}\n```"
        position = diff_positions.get(v['line'])

        if position:
            try:
                post_inline_comment(GITHUB_REPO, PR_NUMBER, body, GITHUB_SHA, file, position)
            except Exception as e:
                print(f"[ERROR] Inline comment failed: {e}")
        else:
            print(f"[WARN] No diff position found for {file} line {v['line']}")

if violations_total:
    summary = "\n\n".join([
        f"🔍 **{v['rule']}** in `{v['file']}` (line {v['line']}):\n{v['explanation']}\n💡 {v['suggestion']}\n```java\n{v.get('code_fix', '// no fix provided')}\n```"
        for v in violations_total
    ])
    post_summary_comment(f"### 🧠 AutoReviewBot Summary\n\n{summary}")

post_status(
    "failure" if any(v["severity"] == "error" for v in violations_total) else "success",
    "Critical rule violations found" if any(v["severity"] == "error" for v in violations_total) else "All checks passed"
)
