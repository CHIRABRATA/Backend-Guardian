# Backend Guardian

Backend Guardian is a human-approved, multi-agent debugging workflow for backend repositories. It uses LangGraph and Groq to inspect a codebase, explain a reported issue, propose a repair, apply the approved change, run the repository's tests, and optionally push a branch and open a GitHub pull request.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-workflow-orange)
![Groq](https://img.shields.io/badge/Groq-LLM-F55036)

## How It Works

1. Enter a public GitHub repository URL and describe the problem.
2. The agent inspects the repository and returns affected files, evidence, root cause, confidence, and a proposed fix.
3. Review the diagnosis and approve or reject the change.
4. After approval, the agent patches the workspace and runs its test harness.
5. When tests pass, a GitHub branch and pull request can be created for remote repositories.

For a local demonstration, enter `local` as the repository value. The included `mock_repo` is used instead of cloning a remote repository.

## Requirements

- Python 3.10 or newer
- Git CLI
- A Groq API key
- A GitHub personal access token only when pushing changes or opening pull requests

The dashboard is a single HTML file. It loads React, ReactDOM, Babel, and Tailwind CSS from CDNs, so Node.js and `npm` are not required to run the included frontend.

## Setup

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/CHIRABRATA/Backend-Guardian.git
cd Backend-Guardian

python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# macOS/Linux
source .venv/bin/activate
```

Install the Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Create a `.env` file in the project root:

```dotenv
GROQ_API_KEY=your_groq_api_key_here
GITHUB_TOKEN=your_github_token_here
```

`GROQ_API_KEY` is required. `GITHUB_TOKEN` is optional for local investigations, but is needed for authenticated GitHub operations. Never commit `.env` or expose either token in frontend code.

## Run The App

Start the API from the project root:

```bash
python server.py
```

The API is available at `http://127.0.0.1:8000`.

Open `frontend/index.html` directly in a browser. The dashboard communicates with the API at `http://127.0.0.1:8000`.

## Deploy On Render

Deploy the backend and frontend as two Render services from the same GitHub repository.

### 1. Deploy the backend

Create a **Web Service** with these settings:

| Setting | Value |
| --- | --- |
| Root Directory | leave blank |
| Runtime | `Python 3` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn server:app --host 0.0.0.0 --port $PORT` |

Add these environment variables in Render:

```text
GROQ_API_KEY=your_groq_api_key
GITHUB_TOKEN=your_github_token
```

Copy the deployed backend URL, for example `https://backend-guardian-api.onrender.com`.

### 2. Deploy the frontend

Create a **Static Site** using the same repository with these settings:

| Setting | Value |
| --- | --- |
| Root Directory | `frontend` |
| Build Command | `sed -i 's|http://127.0.0.1:8000|https://backend-guardian-6mem.onrender.com|g' index.html` |
| Publish Directory | `.` |

The build command changes the local fallback URL in the published copy only; it does not modify the GitHub source file. The current frontend source already uses `https://backend-guardian-6mem.onrender.com` as its production fallback.

After both services deploy, open the frontend URL and use `local` for the repository field to test the included demo repository. Render services may sleep on free plans, so the first request can take longer. Local SQLite history and cloned workspaces are ephemeral on Render.

## API Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/investigate` | Inspect a repository and prepare a diagnosis |
| `POST` | `/api/approve` | Reject or apply the proposed fix and run tests |
| `GET` | `/api/history` | Read saved successful session history |

Example investigation request:

```bash
curl -X POST http://127.0.0.1:8000/api/investigate \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"local","problem":"Find the booking concurrency bug"}'
```

## Project Layout

```text
server.py       FastAPI application and API endpoints
graph_agent.py  LangGraph investigation, planning, and patch nodes
tools.py        Repository, file, test, and GitHub operations
memory.py       SQLite-backed debugging history
frontend/       Browser dashboard
mock_repo/      Local demo repository
workspace_repo/ Cloned target repository workspace
```

## Important Safety Notes

- Review every proposed change before approving it.
- Only use repositories and tokens you are authorized to modify.
- The current test runner is optimized for JavaScript repositories and looks for `test.js` or an `npm test` script.
- Remote repositories are cloned into `workspace_repo`, which is replaced on the next remote investigation.
- Arbitrary repository code may execute during testing. Run this tool in a controlled environment.

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.
