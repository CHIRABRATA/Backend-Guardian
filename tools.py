import os
import stat
import shutil
import subprocess
import json

def _remove_readonly(func, path, exc_info):
    """Clear the read-only bit on Windows so files can be deleted."""
    os.chmod(path, stat.S_IWRITE)
    func(path)

def clone_github_repo(repo_url: str, target_dir: str = "workspace_repo") -> dict:
    safe_target = os.path.abspath(target_dir)

    if os.path.exists(safe_target):
        try:
            shutil.rmtree(safe_target, onerror=_remove_readonly)
        except Exception as e:
            return {"status": "FAILED", "message": f"Could not clear directory: {str(e)}"}

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, safe_target],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return {"status": "SUCCESS", "workspace_path": target_dir}
        else:
            return {"status": "FAILED", "message": f"Git clone failed: {result.stderr.strip()}"}
    except Exception as e:
        return {"status": "FAILED", "message": f"Error running git clone: {str(e)}"}

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
        return f"Error: Access denied outside '{base_dir}'."

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
        return f"Error: Access denied outside '{base_dir}'."

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
            except Exception:
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

def push_fix_to_github(
    repo_url: str,
    base_dir: str = "workspace_repo",
    branch_name: str = "fix/backend-guardian-patch",
    commit_message: str = "fix: autonomous bug remediation by Backend Guardian"
) -> dict:
    token = os.getenv("GITHUB_TOKEN")
    cwd = os.path.abspath(base_dir)

    try:
        subprocess.run(["git", "config", "user.name", "Backend-Guardian-Agent"], cwd=cwd, check=True)
        subprocess.run(["git", "config", "user.email", "agent@backend-guardian.ai"], cwd=cwd, check=True)
        subprocess.run(["git", "checkout", "-B", branch_name], cwd=cwd, check=True)
        subprocess.run(["git", "add", "."], cwd=cwd, check=True)
        subprocess.run(["git", "commit", "-m", commit_message], cwd=cwd, capture_output=True, text=True)

        remote_url = repo_url
        if token and repo_url.startswith("https://"):
            clean_url = repo_url.replace("https://", "")
            remote_url = f"https://{token}@{clean_url}"

        push_res = subprocess.run(
            ["git", "push", "-u", remote_url, branch_name, "--force"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if push_res.returncode == 0:
            return {
                "status": "SUCCESS",
                "branch": branch_name,
                "message": f"Successfully pushed patch to branch '{branch_name}' on GitHub."
            }
        else:
            return {"status": "FAILED", "message": f"Git push failed: {push_res.stderr.strip()}"}
    except Exception as e:
        return {"status": "FAILED", "message": f"Error executing git push: {str(e)}"}