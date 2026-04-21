import os
import requests

def _headers() -> dict:
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    return {"Accept": "application/vnd.github+json"}

def search_github(query: str, type: str) -> list[dict]:
    response = requests.get(
        f"https://api.github.com/search/{type}",
        headers=_headers(),
        params={"q": query, "per_page": 10},
    ).json()
    items = response.get("items", [])
    if type == "repositories":
        return [{"name": i["full_name"], "url": i["html_url"], "description": i["description"], "stars": i["stargazers_count"]} for i in items]
    if type == "users":
        return [{"login": i["login"], "url": i["html_url"]} for i in items]
    if type == "issues":
        return [{"title": i["title"], "url": i["html_url"], "state": i["state"]} for i in items]
    if type == "code":
        return [{"name": i["name"], "url": i["html_url"], "repo": i["repository"]["full_name"]} for i in items]
    return items

def get_github_repo(owner: str, repo: str) -> dict:
    r = requests.get(f"https://api.github.com/repos/{owner}/{repo}", headers=_headers()).json()
    return {
        "name": r["full_name"],
        "description": r["description"],
        "stars": r["stargazers_count"],
        "forks": r["forks_count"],
        "language": r["language"],
        "topics": r.get("topics", []),
        "homepage": r.get("homepage"),
        "url": r["html_url"],
    }

def get_github_issues(owner: str, repo: str, state: str) -> list[dict]:
    items = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/issues",
        headers=_headers(),
        params={"state": state, "per_page": 10},
    ).json()
    return [{"number": i["number"], "title": i["title"], "url": i["html_url"], "state": i["state"]} for i in items]

def get_github_releases(owner: str, repo: str) -> list[dict]:
    items = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/releases",
        headers=_headers(),
        params={"per_page": 5},
    ).json()
    return [{"tag": i["tag_name"], "name": i["name"], "published": i["published_at"], "url": i["html_url"]} for i in items]

# def get_github_file(owner: str, repo: str, path: str) -> str:
#     import base64
#     r = requests.get(f"https://api.github.com/repos/{owner}/{repo}/contents/{path}", headers=_headers()).json()
#     return base64.b64decode(r["content"]).decode("utf-8")
