"""
CORE_ENGINE/GITHUB_SYNC.PY  --  Post issues & changelogs to the GitHub repo. (W3-32)

Repo: https://github.com/castleism/Kalandra_Git  (config key: "github_repo")

Auth: a GitHub personal-access token stored in the OS keychain under the
service id "github" (Settings -> GitHub row). Classic token with `repo`
scope, or a fine-grained token with Issues read/write + Contents read/write
on the one repo.

Everything degrades politely: no token / no requests / no network -> a clear
error string, never an exception into the UI.
"""

import json
import re
import time

try:
    import requests
except Exception:
    requests = None

API = "https://api.github.com"
UA = {"User-Agent": "KalandraOverlay/0.1"}

# entry type -> GitHub label set (labels are created on first use by GitHub
# automatically? no — nonexistent labels 404; so we send only safe defaults
# and include the type in the body instead).
_TYPE_LABELS = {"bug": ["bug"], "idea": ["enhancement"],
                "data": ["documentation"], "ai": ["question"]}


def parse_repo(repo_or_url):
    """Accept 'owner/repo' or a full github.com URL; return 'owner/repo'."""
    s = (repo_or_url or "").strip().rstrip("/")
    if not s:
        return None
    m = re.search(r"github\.com[:/]+([^/]+)/([^/#?]+)", s)
    if m:
        return f"{m.group(1)}/{m.group(2).removesuffix('.git')}"
    if re.fullmatch(r"[\w.-]+/[\w.-]+", s):
        return s
    return None


class GitHubSync:
    def __init__(self, repo="castleism/Kalandra_Git", token_provider=None,
                 logger=None):
        self.repo = parse_repo(repo) or "castleism/Kalandra_Git"
        self.token_provider = token_provider   # callable(service_id) -> secret
        self.logger = logger

    # -- plumbing -----------------------------------------------------------
    def _log(self, msg):
        if self.logger:
            try:
                self.logger("GITHUB", msg)
            except Exception:
                pass

    def _token(self):
        if not self.token_provider:
            return None
        try:
            return self.token_provider("github")
        except Exception:
            return None

    def _headers(self):
        tok = self._token()
        h = dict(UA)
        h["Accept"] = "application/vnd.github+json"
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        return h

    def _precheck(self):
        if requests is None:
            return "The 'requests' library is not installed."
        if not self._token():
            return ("No GitHub token saved. Settings -> GitHub (issue sync): "
                    "paste a personal-access token with 'repo' scope.")
        return None

    # -- operations ----------------------------------------------------------
    def test_connection(self):
        """Returns (ok, message)."""
        err = self._precheck()
        if err:
            return False, err
        try:
            r = requests.get(f"{API}/repos/{self.repo}", headers=self._headers(),
                             timeout=15)
            if r.status_code == 200:
                d = r.json()
                return True, (f"Connected to {d.get('full_name')} "
                              f"({d.get('open_issues_count', '?')} open issues).")
            if r.status_code == 404:
                return False, (f"Repo '{self.repo}' not found — private repo "
                               "with a token that can't see it, or a typo.")
            if r.status_code == 401:
                return False, "Token rejected (401). Re-check the token."
            return False, f"GitHub returned HTTP {r.status_code}."
        except Exception as e:
            return False, f"Connection failed: {e}"

    def post_issue(self, entry):
        """Post one issue-tracker entry as a GitHub Issue.

        `entry` is an issue_tracker dict (title, details, type, severity,
        context, created). Returns (ok, message_or_url)."""
        err = self._precheck()
        if err:
            return False, err
        title = (entry.get("title") or "(untitled)").strip()
        sev = entry.get("severity", "medium")
        body = (
            f"**Type:** {entry.get('type', 'other')}  \n"
            f"**Severity:** {sev}  \n"
            f"**Logged in-app:** {entry.get('created', '?')}  \n"
            f"**Kalandra id:** `{entry.get('id', '?')}`\n\n"
            f"{entry.get('details', '').strip() or '_no details_'}\n"
        )
        ctx = (entry.get("context") or "").strip()
        if ctx:
            body += f"\n<details><summary>Context</summary>\n\n```\n{ctx}\n```\n</details>\n"
        body += "\n---\n_Posted from the Kalandra overlay's Issues tab._"
        payload = {"title": f"[{entry.get('type', 'issue')}] {title}",
                   "body": body}
        try:
            r = requests.post(f"{API}/repos/{self.repo}/issues",
                              headers=self._headers(),
                              data=json.dumps(payload), timeout=20)
            if r.status_code == 201:
                url = r.json().get("html_url", "")
                self._log(f"Issue posted: {url}")
                # Best-effort labels (ignored if they don't exist in the repo).
                labels = _TYPE_LABELS.get(entry.get("type"), [])
                if labels:
                    try:
                        num = r.json().get("number")
                        requests.post(
                            f"{API}/repos/{self.repo}/issues/{num}/labels",
                            headers=self._headers(),
                            data=json.dumps({"labels": labels}), timeout=10)
                    except Exception:
                        pass
                return True, url
            if r.status_code in (401, 403):
                return False, (f"GitHub refused (HTTP {r.status_code}) — token "
                               "needs Issues write access to the repo.")
            return False, f"GitHub returned HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return False, f"Post failed: {e}"

    def publish_changelog(self, markdown, title=None):
        """Publish the exported changelog as a GitHub Release (visible, linkable,
        no git plumbing). Returns (ok, message_or_url)."""
        err = self._precheck()
        if err:
            return False, err
        stamp = time.strftime("%Y-%m-%d %H:%M")
        tag = "changelog-" + time.strftime("%Y%m%d-%H%M%S")
        payload = {
            "tag_name": tag,
            "name": title or f"Kalandra changelog — {stamp}",
            "body": markdown or "_empty changelog_",
            "draft": False,
            "prerelease": True,
        }
        try:
            r = requests.post(f"{API}/repos/{self.repo}/releases",
                              headers=self._headers(),
                              data=json.dumps(payload), timeout=20)
            if r.status_code == 201:
                url = r.json().get("html_url", "")
                self._log(f"Changelog published: {url}")
                return True, url
            if r.status_code in (401, 403):
                return False, (f"GitHub refused (HTTP {r.status_code}) — token "
                               "needs Contents write access to the repo.")
            return False, f"GitHub returned HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return False, f"Publish failed: {e}"


if __name__ == "__main__":
    # Smoke: parsing only (no network without a token).
    for s in ("castleism/Kalandra_Git",
              "https://github.com/castleism/Kalandra_Git",
              "https://github.com/castleism/Kalandra_Git.git/",
              "git@github.com:castleism/Kalandra_Git.git",
              "not a repo", ""):
        print(repr(s), "->", parse_repo(s))
