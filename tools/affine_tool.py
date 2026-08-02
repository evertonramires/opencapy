from connectors.tools_connector import notify_tool_use
from connectors.affine_connector import (
    list_affine_docs as connector_list_affine_docs,
    search_affine_docs as connector_search_affine_docs,
    read_affine_doc as connector_read_affine_doc,
    add_affine_doc as connector_add_affine_doc,
    append_affine_text as connector_append_affine_text,
)

def list_affine_docs() -> list[dict] | dict:
    notify_tool_use("🔧📘📚 AFFiNE tool used to list docs.")
    return connector_list_affine_docs()

def search_affine_docs(keyword: str, limit: int = 10) -> list[dict] | dict:
    notify_tool_use(f"🔧📘🔍 AFFiNE tool used to search docs for '{keyword}'.")
    return connector_search_affine_docs(keyword, limit)

def read_affine_doc(doc_id: str) -> dict:
    notify_tool_use(f"🔧📘📖 AFFiNE tool used to read doc {doc_id}.")
    return connector_read_affine_doc(doc_id)

def add_affine_doc(title: str, content: str = "") -> dict:
    notify_tool_use(f"🔧📘📄 AFFiNE tool used to create doc '{title}'.")
    return connector_add_affine_doc(title, content)

def append_affine_text(doc_id: str, text: str) -> dict:
    notify_tool_use(f"🔧📘✍️ AFFiNE tool used to append text to doc {doc_id}.")
    return connector_append_affine_text(doc_id, text)

list_affine_docs_tool = {
    "type": "function",
    "function": {
        "name": "list_affine_docs",
        "description": "List the docs in the user's AFFiNE workspace with their ids and titles. Use this to find a doc_id before reading or appending. AFFiNE is a notes and docs workspace; to-dos live in Vikunja instead. Prefer search_affine_docs when you know roughly what you are looking for, since this returns everything.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

search_affine_docs_tool = {
    "type": "function",
    "function": {
        "name": "search_affine_docs",
        "description": "Full text search across the user's AFFiNE docs, returning the matching doc ids, titles and a highlighted snippet of the matching text. This is the fastest way to find something the user wrote. Read the doc afterwards when you need its full content.",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "What to search for, e.g. 'apartment' or 'tax deadline'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "How many results to return at most. Defaults to 10.",
                },
            },
            "required": ["keyword"],
        },
    },
}

read_affine_doc_tool = {
    "type": "function",
    "function": {
        "name": "read_affine_doc",
        "description": "Read the full text of an AFFiNE doc, rendered as markdown with its headings, bullets and quotes. Use list_affine_docs or search_affine_docs to find the doc_id. Always read a doc before appending to it, so you know what is already there.",
        "parameters": {
            "type": "object",
            "properties": {
                "doc_id": {
                    "type": "string",
                    "description": "The id of the doc to read.",
                },
            },
            "required": ["doc_id"],
        },
    },
}

add_affine_doc_tool = {
    "type": "function",
    "function": {
        "name": "add_affine_doc",
        "description": "Create a new doc in the user's AFFiNE workspace. Write the content as markdown: '# ' to '###### ' headings, '- ' bullets and '> ' quotes become real AFFiNE blocks, everything else becomes a paragraph. Use this for notes, summaries and reports the user should keep.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The doc title, shown in the AFFiNE sidebar.",
                },
                "content": {
                    "type": "string",
                    "description": "The body as markdown, one block per line. Optional, a doc can start empty.",
                },
            },
            "required": ["title"],
        },
    },
}

append_affine_text_tool = {
    "type": "function",
    "function": {
        "name": "append_affine_text",
        "description": "Append markdown text to the end of an existing AFFiNE doc, one block per line, using the same markdown as add_affine_doc. Use this to add to a note instead of replacing it. Existing content is never changed.",
        "parameters": {
            "type": "object",
            "properties": {
                "doc_id": {
                    "type": "string",
                    "description": "The id of the doc to append to.",
                },
                "text": {
                    "type": "string",
                    "description": "The markdown to append, one block per line.",
                },
            },
            "required": ["doc_id", "text"],
        },
    },
}
