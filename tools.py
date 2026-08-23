import os
import subprocess
import shutil

def clone_github_repo(repo_url: str, target_dir: str = "workspace_repo") -> dict:
    """
    Clones a remote GitHub repository into an isolated local workspace folder.
    Cleans up any existing folder first.
    """
    safe_target = os.path.abspath(target_dir)

    # Remove previous workspace if it exists
    if os.path.exists(safe_target):
        shutil.rmtree(safe_target, ignore_errors=True)

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
    if not os.path.exists(target_path):
        return {"status": "FAILED", "output": f"Error: Test file '{test_file}' not found."}

    try:
        result = subprocess.run(
            ["node", target_path],
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