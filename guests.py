import sqlite3, sys

c = sqlite3.connect("reservations.db")
cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

if cmd == "list":        # active bookings only
    rows = c.execute("SELECT id,name,party_size,start,table_id FROM reservations "
                     "WHERE status='confirmed' ORDER BY start").fetchall()
    for r in rows: print(r)
    print(f"{len(rows)} active booking(s)")
elif cmd == "all":       # including cancelled
    for r in c.execute("SELECT id,name,party_size,start,status FROM reservations ORDER BY id"):
        print(r)
elif cmd == "clear":     # delete everything
    c.execute("DELETE FROM reservations"); c.commit(); print("All bookings deleted.")
elif cmd == "delete" and len(sys.argv) > 2:
    c.execute("DELETE FROM reservations WHERE id=?", (sys.argv[2],)); c.commit()
    print(f"Booking {sys.argv[2]} deleted.")
else:
    print("Usage: py guests.py [list | all | clear | delete ID]")