import os, json, http.server, subprocess, socket, threading, re, uuid, hashlib
from urllib.parse import urlparse, parse_qs
from datetime import datetime

try:
    import pymysql
    DB = {"host":"localhost","user":"root","password":"5034","database":"personal_website","charset":"utf8mb4"}
    def db():
        return pymysql.connect(**DB)
    DB_OK = True
except: DB_OK = False

PORT = 8080
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
POSTS_FILE = os.path.join(DATA, "posts.json")
if not os.path.exists(DATA): os.makedirs(DATA)
SESSIONS = {}

def load_posts():
    if os.path.exists(POSTS_FILE):
        try:
            with open(POSTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return []
    return []

def save_posts(posts):
    with open(POSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

class H(http.server.SimpleHTTPRequestHandler):
    def read_body(self):
        try:
            l = int(self.headers.get("Content-Length", 0))
            if l: return json.loads(self.rfile.read(l).decode("utf-8"))
        except: pass
        return {}

    def get_session(self):
        c = self.headers.get("Cookie", "")
        for part in c.split(";"):
            part = part.strip()
            if part.startswith("session="):
                tok = part[8:]
                return SESSIONS.get(tok)
        return None

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/api/posts": return self.json(load_posts())
        if p.startswith("/api/post/"):
            pid = p[10:]
            for x in load_posts():
                if x["id"] == pid: return self.json(x)
            return self.err(404)
        if p == "/api/me":
            s = self.get_session()
            if s: return self.json({"ok": True, "user": s["user"]})
            return self.json({"ok": False})
        return super().do_GET()

    def do_POST(self):
        p = urlparse(self.path).path
        body = self.read_body()
        if p == "/api/post":
            posts = load_posts()
            post = {"id": str(uuid.uuid4())[:8], "title": body.get("title",""), "content": body.get("content",""), "summary": body.get("summary","") or body.get("content","")[:200], "created": datetime.now().isoformat(), "updated": datetime.now().isoformat()}
            posts.insert(0, post); save_posts(posts); return self.json(post)
        if p == "/api/run":
            code = body.get("code", "")
            blocked = ["import os","import subprocess","import sys","import shutil","import socket","import ctypes","__import__","eval(","exec(","compile("]
            for w in blocked:
                if w in code: return self.json({"output":"","error":"Blocked: "+w})
            try:
                r = subprocess.run(["python","-c",code],capture_output=True,text=True,timeout=10)
                return self.json({"output":r.stdout,"error":r.stderr})
            except subprocess.TimeoutExpired: return self.json({"output":"","error":"Timeout"})
            except Exception as e: return self.json({"output":"","error":str(e)})
        if p == "/api/login":
            if not DB_OK: return self.json({"ok":False,"error":"Database not available"})
            user = body.get("user","")
            pw = body.get("pass","")
            try:
                c = db(); cur = c.cursor()
                cur.execute("SELECT id FROM users WHERE username=%s AND password=%s", (user, hashlib.sha256(pw.encode()).hexdigest()))
                row = cur.fetchone()
                c.close()
                if row:
                    tok = str(uuid.uuid4())
                    SESSIONS[tok] = {"user": user, "id": row[0]}
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Set-Cookie", "session="+tok+"; Path=/; HttpOnly")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok":True,"user":user},ensure_ascii=False).encode("utf-8"))
                    return
                return self.json({"ok":False,"error":"Wrong username or password"})
            except Exception as e: return self.json({"ok":False,"error":str(e)})
        if p == "/api/register":
            if not DB_OK: return self.json({"ok":False,"error":"Database not available"})
            user = body.get("user","").strip()
            pw = body.get("pass","").strip()
            if len(user) < 2: return self.json({"ok":False,"error":"Username too short"})
            if len(pw) < 3: return self.json({"ok":False,"error":"Password too short"})
            try:
                c = db(); cur = c.cursor()
                cur.execute("SELECT id FROM users WHERE username=%s", (user,))
                if cur.fetchone(): c.close(); return self.json({"ok":False,"error":"Username already exists"})
                cur.execute("INSERT INTO users(username,password) VALUES(%s,%s)", (user, hashlib.sha256(pw.encode()).hexdigest()))
                c.commit(); c.close()
                return self.json({"ok":True})
            except Exception as e: return self.json({"ok":False,"error":str(e)})
        if p == "/api/logout":
            c = self.headers.get("Cookie", "")
            for part in c.split(";"):
                part = part.strip()
                if part.startswith("session="):
                    SESSIONS.pop(part[8:], None)
            return self.json({"ok": True})
        return self.err(404)

    def do_PUT(self):
        p = urlparse(self.path).path
        if p.startswith("/api/post/"):
            pid = p[10:]
            body = self.read_body()
            posts = load_posts()
            for i,x in enumerate(posts):
                if x["id"] == pid:
                    posts[i]["title"] = body.get("title",x["title"])
                    posts[i]["content"] = body.get("content",x["content"])
                    posts[i]["summary"] = body.get("summary","") or body.get("content","")[:200]
                    posts[i]["updated"] = datetime.now().isoformat()
                    save_posts(posts); return self.json(posts[i])
            return self.err(404)
        return self.err(404)

    def do_DELETE(self):
        p = urlparse(self.path).path
        if p.startswith("/api/post/"):
            pid = p[10:]
            posts = [x for x in load_posts() if x["id"] != pid]
            save_posts(posts); return self.json({"status":"ok"})
        return self.err(404)

    def json(self,d):
        self.send_response(200)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        self.wfile.write(json.dumps(d,ensure_ascii=False).encode("utf-8"))

    def err(self,c):
        self.send_response(c)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.end_headers()

def run():
    os.chdir(BASE)
    s = http.server.HTTPServer(("0.0.0.0",PORT),H)
    print("="*45)
    print("  Personal Website Started")
    print("  DB:", "MySQL OK" if DB_OK else "NO DB")
    print("="*45)
    print(f"  http://localhost:{PORT}")
    print("  Ctrl+C to stop")
    print("="*45)
    try: s.serve_forever()
    except KeyboardInterrupt: print("\nStopped."); s.server_close()

if __name__ == "__main__": run()