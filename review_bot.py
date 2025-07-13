# review_bot.py (FINAL PATCHED VERSION)
import os
import subprocess
import json
import requests
import openai
import yaml
import time
import csv
import re
from datetime import datetime

# === ENV ===
client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPOSITORY"]
GITHUB_SHA = os.environ["GITHUB_SHA"]
GITHUB_REF = os.environ["GITHUB_REF"]
PR_NUMBER = GITHUB_REF.split("/")[-2]

# === RULES ===
with open("rules/rules-java.yaml", "r") as f:
    CONFIG = yaml.safe_load(f)
    LANGUAGE = "java"
    RULES = CONFIG.get(LANGUAGE, {}).get("rules", CONFIG.get("rules", []))

RULE_PROMPT = "\n".join([
    f"- id: {r['id']}  # {r['hint']}\n  severity: {r['severity']}\n  hint: \"{r['hint']}\"\n  weight: {r.get('weight', 1.0)}"
    for r in RULES
])

LOG_FILE = "autoreviewbot_violations_log.csv"

# === UTILS ===
def retry_request(func, retries=3, delay=2):
    for attempt in range(retries):
        try:
            return func()
        except Exception as e:
            print(f"[WARN] Attempt {attempt+1} failed: {e}")
            time.sleep(delay)
    print(f"[ERROR] All {retries} attempts failed.")
    return None

def get_changed_java_files():
    result = subprocess.run(["git", "diff", "--name-only", "origin/main"], stdout=subprocess.PIPE, check=True)
    return [f for f in result.stdout.decode().splitlines() if f.endswith(".java")]

def get_diff(file_path):
    result = subprocess.run(["git", "diff", "--unified=0", "origin/main", "--", file_path], stdout=subprocess.PIPE, check=True)
    return result.stdout.decode()

def redact_sensitive_content(text):
    redactions = [
        (r"(?i)(api[-_]?key\s*[:=]\s*)['\"]?[a-z0-9_\-]{16,}['\"]?", r"\1<REDACTED>"),
        (r"(?i)(secret|token|passwd|password)\s*[:=]\s*['\"]?.+?['\"]?", r"\1=<REDACTED>"),
        (r"(OPENAI_API_KEY|GITHUB_TOKEN)\s*=\s*['\"]?.+?['\"]?", r"\1=<REDACTED>")
    ]
    for pattern, repl in redactions:
        text = re.sub(pattern, repl, text)
    return text

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
    def do_openai_call():
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return json.loads(response.choices[0].message.content)

    result = retry_request(do_openai_call)
    return result if result else []

def get_pr_diff_positions(file_path):
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
                hunk = line.split(" ")
                new_line = int(hunk[2].split(",")[0].replace("+", "")) - 1
            elif line.startswith("+"):
                new_line += 1
                diff_map[new_line] = position
            elif not line.startswith("-"):
                new_line += 1
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
    if response.status_code != 201:
        print(f"[ERROR] Inline comment failed: {response.status_code}\n{response.text}")
    else:
        print(f"✅ Posted inline comment at {path} (position {position})")

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
            v.get("model", "gpt-4"),
            v["file"],
            v["line"],
            v["rule"],
            v["severity"],
            v["explanation"],
            v["suggestion"],
            v.get("code_fix", "")
        ])

def maintainer_override_exists():
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

# === MAIN EXECUTION ===
start_time = time.time()

if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["timestamp", "model", "file", "line", "rule", "severity", "explanation", "suggestion", "code_fix"])

if maintainer_override_exists():
    print("[INFO] Maintainer override detected. Skipping review.")
    post_status("success", "Review skipped by maintainer override.")
    exit(0)

violations_total = []
changed_files = get_changed_java_files()
for file in changed_files:
    diff = get_diff(file)
    violations = call_llm(diff)
    diff_positions = get_pr_diff_positions(file)
    for v in violations:
        v['file'] = file
        violations_total.append(v)
        log_violation(v)
        body = f"**{v['rule']}**\n\n{v['explanation']}\n💡 Suggestion: {v['suggestion']}\n```java\n{v.get('code_fix', '// no fix provided')}\n```"
        position = diff_positions.get(v['line'])
        if position:
            retry_request(lambda: post_inline_comment(GITHUB_REPO, PR_NUMBER, body, GITHUB_SHA, file, position))
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

duration = round(time.time() - start_time, 2)
print(f"[METRIC] Review completed in {duration} seconds with {len(violations_total)} violations.")
with open("review_metrics.log", "a") as f:
    f.write(f"{datetime.utcnow().isoformat()}, {duration} sec, {len(violations_total)} violations\n")
