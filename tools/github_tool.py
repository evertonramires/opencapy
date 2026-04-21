from connectors.tools_connector import notify_tool_use
from connectors.github_connector import (
    search_github as connector_search_github,
    get_github_repo as connector_get_github_repo,
    get_github_issues as connector_get_github_issues,
    get_github_releases as connector_get_github_releases,
    # get_github_file as connector_get_github_file,
)

def search_github(query: str, type: str) -> list[dict]:
    notify_tool_use(f"🔧🐙 github_tool.search_github called")
    return connector_search_github(query, type)

def get_github_repo(owner: str, repo: str) -> dict:
    notify_tool_use(f"🔧🐙 github_tool.get_github_repo called")
    return connector_get_github_repo(owner, repo)

def get_github_issues(owner: str, repo: str, state: str) -> list[dict]:
    notify_tool_use(f"🔧🐙 github_tool.get_github_issues called")
    return connector_get_github_issues(owner, repo, state)

def get_github_releases(owner: str, repo: str) -> list[dict]:
    notify_tool_use(f"🔧🐙 github_tool.get_github_releases called")
    return connector_get_github_releases(owner, repo)

# def get_github_file(owner: str, repo: str, path: str) -> str:
#     notify_tool_use(f"🔧🐙 github_tool.get_github_file called")
#     return connector_get_github_file(owner, repo, path)

search_github_tool = {
    "type": "function",
    "function": {
        "name": "search_github",
        "description": "Search GitHub for repositories, users, issues, or code.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "type": {"type": "string", "enum": ["repositories", "users", "issues", "code"], "description": "What to search for."},
            },
            "required": ["query", "type"],
        },
    },
}

get_github_repo_tool = {
    "type": "function",
    "function": {
        "name": "get_github_repo",
        "description": "Get general information about a GitHub repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "The repository owner (user or org)."},
                "repo": {"type": "string", "description": "The repository name."},
            },
            "required": ["owner", "repo"],
        },
    },
}

get_github_issues_tool = {
    "type": "function",
    "function": {
        "name": "get_github_issues",
        "description": "Get issues from a GitHub repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "The repository owner."},
                "repo": {"type": "string", "description": "The repository name."},
                "state": {"type": "string", "enum": ["open", "closed"], "description": "Filter issues by state."},
            },
            "required": ["owner", "repo", "state"],
        },
    },
}

get_github_releases_tool = {
    "type": "function",
    "function": {
        "name": "get_github_releases",
        "description": "Get the latest releases from a GitHub repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "The repository owner."},
                "repo": {"type": "string", "description": "The repository name."},
            },
            "required": ["owner", "repo"],
        },
    },
}

# get_github_file_tool = {
#     "type": "function",
#     "function": {
#         "name": "get_github_file",
#         "description": "Read the contents of a file from a public GitHub repository.",
#         "parameters": {
#             "type": "object",
#             "properties": {
#                 "owner": {"type": "string", "description": "The repository owner."},
#                 "repo": {"type": "string", "description": "The repository name."},
#                 "path": {"type": "string", "description": "The file path within the repo (e.g. 'README.md')."},
#             },
#             "required": ["owner", "repo", "path"],
#         },
#     },
# }
