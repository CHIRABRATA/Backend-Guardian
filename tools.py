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
        # Ignore common unnecessary directories
        dirs[:] = [d for d in dirs if d not in [".git", "node_modules", "__pycache__", "venv"]]
        
        for file in files:
            full_path = os.path.join(root, file)
            # Make path relative and standardized with forward slashes
            rel_path = os.path.relpath(full_path, base_dir).replace("\\", "/")
            file_list.append(rel_path)

    return sorted(file_list)


def read_file(file_path: str, base_dir: str = "mock_repo") -> str:
    """
    Reads the content of a specific file safely inside the base directory.
    Prevents directory traversal attacks (e.g., ../../etc/passwd).
    """
    # Build safe path
    target_path = os.path.abspath(os.path.join(base_dir, file_path))
    safe_base = os.path.abspath(base_dir)

    # Security check: ensure target is strictly inside the base directory
    if not target_path.startswith(safe_base):
        return f"Error: Access denied. Cannot read files outside '{base_dir}'."

    if not os.path.exists(target_path):
        return f"Error: File '{file_path}' not found."

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


# Self-test when running tools.py directly
if __name__ == "__main__":
    print("--- 1. Testing list_files() ---")
    files = list_files("mock_repo")
    print(files)

    print("\n--- 2. Testing read_file() ---")
    content = read_file("src/services/booking.service.js", "mock_repo")
    print(content)