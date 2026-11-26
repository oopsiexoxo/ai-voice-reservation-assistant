import os, json, sqlite3
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from retell import Retell
from fastapi.responses import JSONResponse, FileResponse    
from pydantic import BaseModel
from zoneinfo import ZoneInfo

app = FastAPI()
retell = Retell(api_key=os.environ["RETELL_API_KEY"])
DB = "reservations.db"
DURATION = timedelta(minutes=90)
OPEN_H, CLOSE_H = 11, 22  # opening hours, adjust

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def init():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS tables(id INTEGER PRIMARY KEY, name TEXT, capacity INT);
    CREATE TABLE IF NOT EXISTS reservations(
      id INTEGER PRIMARY KEY AUTOINCREMENT, table_id INT, name TEXT, phone TEXT,
      party_size INT, start TEXT, end TEXT, status TEXT DEFAULT 'confirmed');
    """)
    if not c.execute("SELECT 1 FROM tables").fetchone():
        c.executemany("INSERT INTO tables(name,capacity) VALUES(?,?)",
          [("T1",2),("T2",2),("T3",4),("T4",4),("T5",6),("T6",8)])
    c.commit(); c.close()
init()

def free_table(c, start, party):
    end = start + DURATION
    return c.execute("""
      SELECT * FROM tables WHERE capacity >= ? AND id NOT IN (
        SELECT table_id FROM reservations
        WHERE status='confirmed' AND start < ? AND end > ?)
      ORDER BY capacity LIMIT 1""",
      (party, end.isoformat(), start.isoformat())).fetchone()

def parse(date, time):
    return datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")

def in_hours(dt):
    open_t = dt.replace(hour=OPEN_H, minute=0, second=0, microsecond=0)
    close_t = dt.replace(hour=CLOSE_H, minute=0, second=0, microsecond=0)
    return open_t <= dt and dt + DURATION <= close_t

async def verified(request):
    raw = (await request.body()).decode()
    sig = request.headers.get("X-Retell-Signature", "")
    if not retell.verify(raw, api_key=os.environ["RETELL_API_KEY"], signature=sig):
        return None
    return json.loads(raw)

@app.post("/check_availability")
async def check_availability(request: Request):
    body = await verified(request)
    if not body: return JSONResponse({"message": "Unauthorized"}, 401)
    a = body["args"]
    try:
        start = parse(a["date"], a["time"]); party = int(a["party_size"])
    except Exception:
        return {"result": f"Missing or invalid details. Received: {a}"}
    c = db()
    if in_hours(start) and free_table(c, start, party):
        return {"available": True}
    alts = []
    for m in range(-120, 121, 30):           # suggest nearby times
        t = start + timedelta(minutes=m)
        if m and in_hours(t) and free_table(c, t, party):
            alts.append(t.strftime("%H:%M"))
    return {"available": False, "alternative_times": alts[:4]}

@app.post("/create_reservation")
async def create_reservation(request: Request):
    body = await verified(request)
    if not body: return JSONResponse({"message": "Unauthorized"}, 401)
    a = body["args"]
    phone = a.get("phone") or body["call"].get("from_number", "")
    try:
        start = parse(a["date"], a["time"]); party = int(a["party_size"])
    except Exception:
        return {"result": f"Missing or invalid details. Received: {a}"}
    print("CREATE:", a, "in_hours =", in_hours(start))
    c = db()
    t = free_table(c, start, party) if in_hours(start) else None
    if not t:
        return {"success": False, "message": "No table available at that time."}
    cur = c.execute(
      "INSERT INTO reservations(table_id,name,phone,party_size,start,end) VALUES(?,?,?,?,?,?)",
      (t["id"], a["name"], phone, party, start.isoformat(), (start+DURATION).isoformat()))
    c.commit()
    return {"success": True, "confirmation_id": cur.lastrowid,
        "message": f"Reservation confirmed. Confirmation number {cur.lastrowid}."}

@app.post("/cancel_reservation")
async def cancel_reservation(request: Request):
    body = await verified(request)
    if not body: return JSONResponse({"message": "Unauthorized"}, 401)
    a = body["args"]
    c = db()
    cur = c.execute(
        "UPDATE reservations SET status='cancelled' "
        "WHERE id=? AND lower(name)=lower(?) AND status='confirmed'",
        (a.get("confirmation_id"), a.get("name", "")))
    c.commit()
    if cur.rowcount > 0:
        return {"success": True, "message": "Reservation cancelled."}
    return {"success": False,
            "message": "No active booking found with that confirmation number and name."}

## Bookings management

STAFF_PIN = os.environ.get("STAFF_PIN", "")

def now_my():
    return datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).replace(tzinfo=None)

def is_staff(request: Request):
    return bool(STAFF_PIN) and request.headers.get("X-Staff-Pin") == STAFF_PIN

@app.get("/")
def home():
    return FileResponse("index.html")

@app.get("/api/day")
def day(date: str, request: Request):
    c = db()
    staff = is_staff(request)
    rows = c.execute("SELECT * FROM reservations WHERE status='confirmed' AND start LIKE ?",
                     (date + "%",)).fetchall()
    tables = []
    for t in c.execute("SELECT * FROM tables ORDER BY id").fetchall():
        tables.append({
            "id": t["id"], "name": t["name"], "capacity": t["capacity"],
            "bookings": [{"id": r["id"], "start": r["start"][11:16], "end": r["end"][11:16],
                          "name": r["name"] if staff else None,
                          "party_size": r["party_size"] if staff else None}
                         for r in rows if r["table_id"] == t["id"]]})
    return {"date": date, "tables": tables}

class Book(BaseModel):
    name: str
    phone: str = ""
    date: str
    time: str
    party_size: int

@app.post("/api/book")
def book(b: Book):
    try:
        start = parse(b.date, b.time)
    except Exception:
        return JSONResponse({"success": False, "message": "Invalid date or time."}, 400)
    if not b.name.strip() or not (1 <= b.party_size <= 8):
        return JSONResponse({"success": False, "message": "Enter a name and 1 to 8 guests."}, 400)
    if start < now_my():
        return {"success": False, "message": "That time has already passed."}
    c = db()
    t = free_table(c, start, b.party_size) if in_hours(start) else None
    if not t:
        return {"success": False, "message": "No table available at that time."}
    cur = c.execute(
        "INSERT INTO reservations(table_id,name,phone,party_size,start,end) VALUES(?,?,?,?,?,?)",
        (t["id"], b.name.strip(), b.phone, b.party_size,
         start.isoformat(), (start + DURATION).isoformat()))
    c.commit()
    return {"success": True, "message": f"Booked table {t['name']}. Confirmation number {cur.lastrowid}."}

@app.post("/api/cancel/{rid}")
def cancel(rid: int, request: Request):
    if not is_staff(request):
        return JSONResponse({"success": False, "message": "Staff PIN required."}, 401)
    c = db()
    cur = c.execute("UPDATE reservations SET status='cancelled' WHERE id=? AND status='confirmed'", (rid,))
    c.commit()
    return {"success": cur.rowcount > 0}