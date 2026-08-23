import os
import json
import subprocess
import shutil
import os
import stat
import shutil
import subprocess
import urllib.error
import urllib.request

def _remove_readonly(func, path, exc_info):
    """Clear the read-only bit on Windows so files can be deleted."""
    os.chmod(path, stat.S_IWRITE)
    func(path)

def clone_github_repo(repo_url: str, target_dir: str = "workspace_repo") -> dict:
    """
    Clones a remote GitHub repository into an isolated local workspace folder.
    Cleans up any existing folder first, handling Windows permission locks.
    """
    safe_target = os.path.abspath(target_dir)

    # Force delete existing directory if present
    if os.path.exists(safe_target):
        try:
            shutil.rmtree(safe_target, onerror=_remove_readonly)
        except Exception as e:
            return {
                "status": "FAILED",
                "message": f"Could not clear existing workspace folder: {str(e)}"
            }

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, safe_target],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return {
                "status": "SUCCESS",
                "workspace_path": target_dir,
                "message": f"Successfully cloned {repo_url} into {target_dir}"
            }
        else:
            return {
                "status": "FAILED",
                "message": f"Git clone failed: {result.stderr.strip()}"
            }
    except Exception as e:
        return {"status": "FAILED", "message": f"Error running git clone: {str(e)}"}


def create_pull_request(
    repo_name: str,
    branch_name: str,
    title: str,
    body: str,
    workspace_dir: str = "workspace_repo",
) -> dict:
    """Push local changes to a branch and open a GitHub pull request."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return {"status": "SKIPPED", "message": "No GITHUB_TOKEN provided."}

    if not repo_name or repo_name.count("/") != 1:
        return {"status": "FAILED", "message": "repo_name must use the 'owner/repository' format."}
    if not branch_name.strip() or branch_name in {"main", "master"}:
        return {"status": "FAILED", "message": "A non-default branch name is required."}

    workspace = os.path.abspath(workspace_dir)
    if not os.path.isdir(os.path.join(workspace, ".git")):
        return {"status": "FAILED", "message": f"Git workspace not found: {workspace_dir}"}

    def run_git(*args: str, capture_output: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=workspace,
            capture_output=capture_output,
            text=True,
            timeout=30,
        )

    try:
        branch_result = run_git("checkout", "-b", branch_name, capture_output=True)
        if branch_result.returncode != 0:
            return {"status": "FAILED", "message": branch_result.stderr.strip()}

        add_result = run_git("add", ".", capture_output=True)
        if add_result.returncode != 0:
            return {"status": "FAILED", "message": add_result.stderr.strip()}

        commit_result = run_git("commit", "-m", title, capture_output=True)
        if commit_result.returncode != 0:
            return {"status": "FAILED", "message": commit_result.stderr.strip()}

        auth_header = f"AUTHORIZATION: bearer {token}"
        push_result = run_git(
            "-c", f"http.extraheader={auth_header}",
            "push", "origin", branch_name,
            capture_output=True,
        )
        if push_result.returncode != 0:
            return {"status": "FAILED", "message": push_result.stderr.strip()}

        request = urllib.request.Request(
            f"https://api.github.com/repos/{repo_name}/pulls",
            data=json.dumps({"title": title, "head": branch_name, "base": "main", "body": body}).encode(),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "Backend-Guardian",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            pull_request = json.loads(response.read().decode())

        return {
            "status": "SUCCESS",
            "message": "Pull request created successfully.",
            "url": pull_request.get("html_url"),
            "number": pull_request.get("number"),
        }
    except (OSError, subprocess.SubprocessError, urllib.error.HTTPError) as exc:
        return {"status": "FAILED", "message": str(exc)}
    
def list_files(base_dir: str = "mock_repo") -> list[str]:
    if not os.path.exists(base_dir):
        return [f"Error: Directory '{base_dir}' does not exist."]

    file_list = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in [".git", "node_modules", "__pycache__", "venv", ".venv"]]
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, base_dir).replace("\\", "/")
            file_list.append(rel_path)
    return sorted(file_list)


def read_file(file_path: str, base_dir: str = "mock_repo") -> str:
    target_path = os.path.abspath(os.path.join(base_dir, file_path))
    safe_base = os.path.abspath(base_dir)

    if not target_path.startswith(safe_base):
        return f"Error: Access denied. Cannot read files outside '{base_dir}'."

    if not os.path.exists(target_path):
        return f"Error: File '{file_path}' not found."

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


def search_code(query: str, base_dir: str = "mock_repo") -> list[dict]:
    results = []
    files = list_files(base_dir)
    for file_path in files:
        if file_path.startswith("Error:"):
            continue
        target_path = os.path.join(base_dir, file_path)
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                for line_number, line in enumerate(f, start=1):
                    if query.lower() in line.lower():
                        results.append({
                            "file": file_path,
                            "line": line_number,
                            "code": line.strip()
                        })
        except Exception:
            continue
    return results


def write_file(file_path: str, content: str, base_dir: str = "mock_repo") -> str:
    target_path = os.path.abspath(os.path.join(base_dir, file_path))
    safe_base = os.path.abspath(base_dir)

    if not target_path.startswith(safe_base):
        return f"Error: Access denied. Cannot write files outside '{base_dir}'."

    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Success: File '{file_path}' updated successfully."
    except Exception as e:
        return f"Error writing file: {str(e)}"


def run_tests(test_file: str = "tests/booking.test.js", base_dir: str = "mock_repo") -> dict:
    target_path = os.path.abspath(os.path.join(base_dir, test_file))
    command = None
    if os.path.isfile(target_path):
        command = ["node", target_path]
    else:
        package_path = os.path.join(base_dir, "package.json")
        if os.path.isfile(package_path):
            try:
                with open(package_path, "r", encoding="utf-8") as package_file:
                    package = json.load(package_file)
                if package.get("scripts", {}).get("test"):
                    command = ["npm", "test"]
            except (OSError, json.JSONDecodeError):
                pass

    if command is None:
        return {
            "status": "SKIPPED",
            "output": f"No test file '{test_file}' or package test script found in '{base_dir}'."
        }

    try:
        result = subprocess.run(
            command,
            cwd=os.path.abspath(base_dir),
            capture_output=True,
            text=True,
            timeout=10
        )
        output = (result.stdout + "\n" + result.stderr).strip()
        return {
            "status": "PASSED" if result.returncode == 0 else "FAILED",
            "output": output
        }
    except Exception as e:
        return {"status": "FAILED", "output": f"Execution error: {str(e)}"}