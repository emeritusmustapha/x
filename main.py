import os, hashlib
from datetime import datetime, timedelta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, or_, and_
from sqlalchemy.orm import sessionmaker, declarative_base

# --- IDENTITY CONFIGURATION ---
ADMIN_KEY = "7days"
PUBLIC_CREATOR = "emeritusmustapha" 

DATABASE_URL = "postgresql://neondb_owner:npg_bkvBP32eGqjU@ep-wandering-darkness-a82zt5s2-pooler.eastus2.azure.neon.tech/neondb?sslmode=require"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserDB(Base):
    __tablename__ = "users"
    username = Column(String, primary_key=True)
    password = Column(String); is_admin = Column(Boolean, default=False)

class MessageDB(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    sender = Column(String); receiver = Column(String) 
    content = Column(String); time_label = Column(String) 
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)
app = FastAPI()

class AuthData(BaseModel):
    username: str; password: str

def get_now_time():
    # Nigeria Time (UTC+1)
    return (datetime.utcnow() + timedelta(hours=1)).strftime("%I:%M %p")

def purge_old_messages(db):
    """Auto-delete messages older than 3 days."""
    cutoff = datetime.utcnow() - timedelta(days=3)
    db.query(MessageDB).filter(MessageDB.created_at < cutoff).delete()
    db.commit()

@app.get("/")
async def serve_ui(): return FileResponse("index.html")

@app.get("/me.jpeg")
async def serve_image(): return FileResponse("me.jpeg") if os.path.exists("me.jpeg") else HTTPException(404)

@app.post("/register")
async def register(data: AuthData):
    db = SessionLocal()
    try:
        hashed = hashlib.sha256(data.password.encode()).hexdigest()
        if db.query(UserDB).filter(UserDB.username.ilike(data.username)).first():
            raise HTTPException(400, "User exists")
        is_admin = (data.username.lower() == ADMIN_KEY.lower())
        db.add(UserDB(username=data.username, password=hashed, is_admin=is_admin))
        welcome = f"Hello {data.username}! 🌟 I'm emeritusmustapha. Welcome to LinkUp!"
        db.add(MessageDB(sender=PUBLIC_CREATOR, receiver=data.username, content=welcome, time_label=get_now_time()))
        db.commit(); return {"message": "Success"}
    finally: db.close()

@app.post("/login")
async def login(data: AuthData):
    db = SessionLocal()
    try:
        hashed = hashlib.sha256(data.password.encode()).hexdigest()
        user = db.query(UserDB).filter(UserDB.username.ilike(data.username), UserDB.password == hashed).first()
        if not user: raise HTTPException(401, "Invalid login")
        return {"username": user.username, "is_admin": user.is_admin}
    finally: db.close()

@app.get("/users")
async def get_users():
    db = SessionLocal()
    try: return db.query(UserDB).all()
    finally: db.close()

@app.get("/messages/{u1}/{u2}")
async def get_history(u1: str, u2: str):
    db = SessionLocal()
    try:
        purge_old_messages(db)
        if u2 == "Global": return db.query(MessageDB).filter(MessageDB.receiver == "Global").order_by(MessageDB.created_at).all()
        return db.query(MessageDB).filter(or_(and_(MessageDB.sender==u1, MessageDB.receiver==u2), and_(MessageDB.sender==u2, MessageDB.receiver==u1))).order_by(MessageDB.created_at).all()
    finally: db.close()

@app.get("/stats")
async def get_stats():
    db = SessionLocal()
    try: return {"users": db.query(UserDB).count(), "messages": db.query(MessageDB).count()}
    finally: db.close()

@app.post("/admin/purge")
async def manual_purge(admin: str):
    if admin.lower() != ADMIN_KEY.lower(): raise HTTPException(403)
    db = SessionLocal(); purge_old_messages(db); db.close(); return {"status": "Purged"}

class ConnectionManager:
    def __init__(self): self.active = {}
    async def connect(self, ws, uid): await ws.accept(); self.active[uid] = ws
    def disconnect(self, uid): 
        if uid in self.active: del self.active[uid]
    async def broadcast(self, msg):
        for uid in self.active: await self.active[uid].send_json(msg)
    async def send(self, msg, rid):
        if rid in self.active: await self.active[rid].send_json(msg)

manager = ConnectionManager()

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_json()
            db = SessionLocal(); t_label = get_now_time()
            db.add(MessageDB(sender=user_id, receiver=data['to'], content=data['content'], time_label=t_label))
            db.commit(); db.close()
            payload = {"from": user_id, "to": data['to'], "content": data['content'], "time": t_label}
            if data['to'] == "Global": await manager.broadcast(payload)
            else: await manager.send(payload, data['to'])
    except WebSocketDisconnect: manager.disconnect(user_id)
