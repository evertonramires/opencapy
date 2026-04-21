from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

incoming_queue: list[str] = []  # messages from client to bot
outgoing_queue: list[str] = []  # messages from bot to client

class MessageRequest(BaseModel):
    message: str

# Client sends a message to the bot
@app.post("/inbox")
def client_send(body: MessageRequest):
    incoming_queue.append(body.message)
    return {"ok": True}

# Bot polls for messages sent by the client
@app.get("/inbox")
def bot_read():
    messages = list(incoming_queue)
    incoming_queue.clear()
    return {"messages": messages}

# Bot sends a response to the client
@app.post("/outbox")
def bot_send(body: MessageRequest):
    outgoing_queue.append(body.message)
    return {"ok": True}

# Client polls for bot responses
@app.get("/outbox")
def client_read():
    messages = list(outgoing_queue)
    outgoing_queue.clear()
    return {"messages": messages}