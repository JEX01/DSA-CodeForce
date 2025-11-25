#!/usr/bin/env python3
# sync_cf.py
# Requires: requests

import os
import json
import time
import hashlib
import requests
import subprocess
from urllib.parse import quote, urlencode

# ---- Load local config ----
with open("config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

CF_HANDLE = cfg["cf_handle"]
API_KEY = cfg["cf_api_key"]
API_SECRET = cfg["cf_api_secret"]
GITHUB_REPO = cfg["github_repo"]
GITHUB_TOKEN = cfg["github_token"]

# Working dir (repo root)
repo_dir = os.path.dirname(os.path.abspath(__file__))

# Map common CF language names to extensions (add if you want)
ext_map = {
    "GNU G++17 11.2.0": ".cpp",
    "GNU G++17": ".cpp",
    "GNU C++17": ".cpp",
    "GNU C++14": ".cpp",
    "GNU C++20": ".cpp",
    "GCC 9.3.0": ".c",
    "Python 3": ".py",
    "Python": ".py",
    "PyPy 3": ".py",
    "Java 11": ".java",
    "Java": ".java",
}

# ---------- Helpers to call authenticated CF API ----------
def make_api_sig(method: str, params: dict) -> str:
    """
    Build apiSig as specified by Codeforces:
    apiSig = rand + sha512Hex( rand + '/' + method + '?' + sortedParams + '#' + secret )
    where sortedParams are "k=v" pairs sorted lexicographically by key then value.
    """

    rand = str(int(time.time() * 1000))[:6]  # 6-char random-ish prefix (must be different each time)
    # build query string with params sorted (key then value)
    items = sorted((k, str(v)) for k, v in params.items())
    qs = "&".join(f"{k}={quote(v, safe='')}" for k, v in items)
    to_hash = f"{rand}/{method}?{qs}#{API_SECRET}"
    sha = hashlib.sha512(to_hash.encode("utf-8")).hexdigest()
    return rand + sha

def cf_user_status_with_sources(handle: str, count: int = 10000):
    method = "user.status"
    t = int(time.time())
    params = {
        "apiKey": API_KEY,
        "handle": handle,
        "includeSources": "true",
        "count": str(count),
        "time": str(t)
    }
    apiSig = make_api_sig(method, params)
    params["apiSig"] = apiSig
    # Build request URL
    base = f"https://codeforces.com/api/{method}"
    res = requests.get(base, params=params, timeout=30)
    res.raise_for_status()
    data = res.json()
    if data.get("status") != "OK":
        raise RuntimeError("CF API failed: " + str(data.get("comment")))
    return data["result"]

# --------- Save a submission ----------
def safe_filename(s: str) -> str:
    # Make a filename friendly string
    return "".join(c if c.isalnum() or c in " -_." else "_" for c in s).strip()

def save_submission(sub):
    if sub.get("verdict") != "OK":
        return
    problem = sub["problem"]
    contest_id = problem.get("contestId")
    index = problem.get("index", "")
    name = problem.get("name", "unknown")
    if not contest_id:
        return

    folder_name = f"{contest_id} - {safe_filename(name)}"
    folder_path = os.path.join(repo_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    lang = sub.get("programmingLanguage", "")
    ext = ext_map.get(lang, ".txt")

    filename = f"{index} - {safe_filename(name)}{ext}"
    file_path = os.path.join(folder_path, filename)

    # If file exists already, skip (avoid duplicates)
    if os.path.exists(file_path):
        return

    # The authenticated 'user.status' with includeSources should provide 'source' or 'sourceCode'
    source = sub.get("source") or sub.get("sourceCode") or sub.get("programText") or ""
    if not source:
        # No source present (unexpected) -> place a short placeholder with a link to submission page
        submission_id = sub.get("id")
        submission_url = f"https://codeforces.com/contest/{contest_id}/submission/{submission_id}"
        source = f"// Source not available via API. Visit: {submission_url}\n"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(source)

# -------- Git commit & push ----------
def run(cmd, cwd=repo_dir):
    return subprocess.run(cmd, cwd=cwd, check=False)

def git_push():
    # Ensure config.json is ignored and not committed.
    run(["git", "add", "."])
    run(["git", "commit", "-m", "Auto-sync Codeforces solutions"])
    # Push using token in URL (works locally). Avoid storing token in git/config.
    # Build repo URL like: https://<token>@github.com/username/repo.git
    # GITHUB_REPO is expected like https://github.com/username/repo.git
    if GITHUB_REPO.startswith("https://"):
        push_url = GITHUB_REPO.replace("https://", f"https://{GITHUB_TOKEN}@")
    else:
        push_url = GITHUB_REPO
    run(["git", "push", push_url, "HEAD:main"])

# -------- Main ----------
def main():
    print("Fetching submissions from Codeforces (this requires valid CF apiKey/secret)...")
    subs = cf_user_status_with_sources(CF_HANDLE, count=5000)
    print(f"Got {len(subs)} submissions (will only save 'OK' verdicts).")
    for s in subs:
        save_submission(s)
    print("Files written. Committing & pushing to GitHub...")
    git_push()
    print("Done.")

if __name__ == "__main__":
    main()
