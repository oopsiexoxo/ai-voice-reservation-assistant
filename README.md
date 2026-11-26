# AI Voice Reservation Assistant (Proof of Concept)

A phone agent built on Retell AI that checks availability, books and cancels
restaurant tables through a custom FastAPI backend.

## Features
- Availability check, booking and cancellation endpoints (FastAPI + SQLite)
- Smallest-fit table allocation, 90-minute overlap detection, opening-hours rules
- Name-verified cancellation
- Retell request signature verification
- Web page showing per-day table availability

## Run locally
    pip install -r requirements.txt
    set RETELL_API_KEY=your_key
    set STAFF_PIN=your_pin
    python -m uvicorn main:app --port 8000

Expose it with ngrok and add the endpoints as custom functions in Retell.

## Status
Tested with Retell web calls. Telephone integration (SIP trunk) is planned.
