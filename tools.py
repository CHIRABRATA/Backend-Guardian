import os

def list_files(base_dir: str = "mock_repo") -> list[str]:
    """
    Recursively scans the target directory and returns a list of all relative file paths.
    Excludes hidden files and node_modules for safety.
    """
    if not os.path.exists(base_dir):
        return [f"Error: Directory '{base_dir}' does not exist."]

    file_list = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in [".git", "node_modules", "__pycache__", "venv"]]
        
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, base_dir).replace("\\", "/")
            file_list.append(rel_path)

    return sorted(file_list)


def read_file(file_path: str, base_dir: str = "mock_repo") -> str:
    """
    Reads the content of a specific file safely inside the base directory.
    Prevents directory traversal attacks.
    """
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
    """
    Searches for a keyword or phrase across all files in the repository.
    Returns matching file paths, line numbers, and line contents.
    """
    results = []
    files = list_files(base_dir)

    for file_path in files:
        # Skip error messages from list_files
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


# Direct test
if __name__ == "__main__":
    print("--- Testing search_code('seats') ---")
    matches = search_code("seats", "mock_repo")
    for match in matches:
        print(f"[{match['file']}:{match['line']}] -> {match['code']}")