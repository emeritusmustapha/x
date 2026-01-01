import os, hashlib
from datetime import datetime, timedelta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, or_, and_
from sqlalchemy.orm import sessionmaker, declarative_base

# --- Database Configuration ---
DATABASE_URL = "postgresql://neondb_owner:npg_bkvBP32eGqjU@ep-wandering-darkness-a82zt5s2-pooler.eastus2.azure.neon.tech/neondb?sslmode=require"

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserDB(Base):
    __tablename__ = "users"
    username = Column(String, primary_key=True)
    password = Column(String)
    is_admin = Column(Boolean, default=False)

class MessageDB(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    sender = Column(String)
    receiver = Column(String)
    content = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)
app = FastAPI()

class AuthData(BaseModel):
    username: str; password: str

def purge_old_messages(db):
    cutoff = datetime.utcnow() - timedelta(days=3)
    db.query(MessageDB).filter(MessageDB.created_at < cutoff).delete()
    db.commit()

@app.get("/")
async def serve_ui(): return FileResponse("index.html")

@app.post("/register")
async def register(data: AuthData):
    db = SessionLocal()
    hashed = hashlib.sha256(data.password.encode()).hexdigest()
    if db.query(UserDB).filter(UserDB.username == data.username).first():
        db.close(); raise HTTPException(status_code=400, detail="User exists")
    is_admin = (data.username == "emeritusmustapha")
    user = UserDB(username=data.username, password=hashed, is_admin=is_admin)
    db.add(user)
    welcome_text = f"Hello {data.username}! 🌟 Welcome to LinkUp. I'm emeritusmustapha, the creator. Chats clear every 3 days. Enjoy!"
    db.add(MessageDB(sender="emeritusmustapha", receiver=data.username, content=welcome_text))
    db.commit(); db.close(); return {"message": "Success"}

@app.post("/login")
async def login(data: AuthData):
    db = SessionLocal()
    hashed = hashlib.sha256(data.password.encode()).hexdigest()
    user = db.query(UserDB).filter(UserDB.username == data.username, UserDB.password == hashed).first()
    if not user: db.close(); raise HTTPException(status_code=401, detail="Invalid login")
    res = {"username": user.username, "is_admin": user.is_admin}
    db.close(); return res

@app.get("/users")
async def get_users():
    db = SessionLocal(); users = db.query(UserDB).all(); db.close(); return users

@app.get("/messages/{u1}/{u2}")
async def get_history(u1: str, u2: str):
    db = SessionLocal()
    purge_old_messages(db) 
    msgs = db.query(MessageDB).filter(or_(and_(MessageDB.sender==u1, MessageDB.receiver==u2), and_(MessageDB.sender==u2, MessageDB.receiver==u1))).order_by(MessageDB.created_at).all()
    db.close(); return msgs

@app.get("/stats")
async def get_stats():
    db = SessionLocal()
    res = {"users": db.query(UserDB).count(), "messages": db.query(MessageDB).count()}
    db.close(); return res

@app.delete("/admin/delete_user/{target}")
async def delete_user(target: str, admin: str):
    if admin != "emeritusmustapha": raise HTTPException(status_code=403)
    db = SessionLocal()
    db.query(UserDB).filter(UserDB.username == target).delete()
    db.query(MessageDB).filter(or_(MessageDB.sender==target, MessageDB.receiver==target)).delete()
    db.commit(); db.close(); return {"status": "deleted"}

class ConnectionManager:
    def __init__(self): self.active = {}
    async def connect(self, ws, uid): await ws.accept(); self.active[uid] = ws
    def disconnect(self, uid): 
        if uid in self.active: del self.active[uid]
    async def send(self, msg, rid):
        if rid in self.active: await self.active[rid].send_json(msg)

manager = ConnectionManager()

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    db = SessionLocal()
    try:
        while True:
            data = await websocket.receive_json()
            new_m = MessageDB(sender=user_id, receiver=data['to'], content=data['content'])
            db.add(new_m); db.commit()
            await manager.send({"from": user_id, "content": data['content']}, data['to'])
    except: manager.disconnect(user_id)
    finally: db.close()
