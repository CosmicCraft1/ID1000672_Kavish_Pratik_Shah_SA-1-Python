"""
MedTimer - Daily Medicine Companion
===================================
A calm, senior-friendly Streamlit app that helps people with chronic
conditions remember their medicines.

  * Add, edit and delete daily medicines (one or more times per day)
  * Live, colour-coded checklist: green = taken, yellow = upcoming / due, red = missed
  * Weekly adherence score, streaks and badges
  * Turtle graphics reward (trophy, smiley or seedling) drawn stroke by stroke
  * Before / after food guidance for every medicine
  * Common illnesses with typical medicines you can add in one tap
  * Gamified: XP for every dose, plant-themed levels and daily quests
  * Motivational tips and quotes, a mood check-in, read-aloud and sound reminders

Run locally:          streamlit run app.py
Real turtle window:   python app.py --turtle trophy      (needs tkinter)

Sections of this file:
  1-3. Pure Python logic (data structures, calculations, turtle drawing)
  4.   Visual components (React Bits designs; the two-way widget page is at the end)
  5.   The Streamlit interface, which only reads from / writes to the logic
"""

import html
import json
import math
import random
import sys
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import tempfile
from pathlib import Path

# =============================================================================
# 1. DATA AND RULES
# =============================================================================

# How each dose status looks. Colour is never used alone: every status also
# has an icon and a written label (important for colour-blind users).
STATUS_LABEL = {"taken": "Taken", "due": "Due now", "upcoming": "Upcoming", "missed": "Missed"}

# Adherence thresholds used by the gauge, the chart and the turtle reward.
GOOD_ADHERENCE = 80      # percent - "good week" (green)
GREAT_ADHERENCE = 90     # percent - trophy territory
ON_TIME_MINUTES = 15     # a dose taken within this many minutes counts as "on time"
EARLY_WINDOW = 60        # a dose can only be ticked this many minutes early

MOODS = ["Wonderful", "Good", "Okay", "Tired", "In pain", "Unwell"]

TIPS = [
    {"short": "Pair it with a habit", "full": "Take your morning tablets right after brushing your teeth. Linking a dose to a daily habit makes it much easier to remember."},
    {"short": "Pill organiser", "full": "A weekly pill box with a slot for each day shows at a glance whether today's dose has been taken."},
    {"short": "Sip some water", "full": "Most tablets are best taken with a full glass of water. It helps them go down and keeps you hydrated."},
    {"short": "Missed one?", "full": "If you miss a dose, do not double the next one. Check the leaflet or ask your pharmacist what to do."},
    {"short": "Keep a list", "full": "Carry a list of your medicines and doses in your wallet. It is very helpful in an emergency or at a new clinic."},
    {"short": "Refill early", "full": "Order refills when you have about a week left, so you never run out over a weekend or holiday."},
    {"short": "Ask questions", "full": "Feeling side effects? Write them down and share them with your doctor. Never stop a medicine on your own."},
    {"short": "Gentle walk", "full": "A 10-minute walk after a meal can help with blood sugar and blood pressure. Small steps count."},
]

QUOTES = [
    ("Take care of your body. It's the only place you have to live.", "Jim Rohn"),
    ("Small daily improvements are the key to staggering long-term results.", "Robin Sharma"),
    ("The greatest wealth is health.", "Virgil"),
    ("Every day may not be good, but there is something good in every day.", "Alice Morse Earle"),
    ("It does not matter how slowly you go as long as you do not stop.", "Confucius"),
    ("A good laugh and a long sleep are the best cures in the doctor's book.", "Irish proverb"),
    ("Health is a state of complete harmony of the body, mind and spirit.", "B.K.S. Iyengar"),
]

PRAISE = [
    "Well done! One more step to feeling your best.",
    "Lovely - your body thanks you.",
    "Great job remembering.",
    "Ticked off. You're doing brilliantly.",
    "Another dose done. Proud of you!",
]

BADGES = [
    # id, title, how to earn, icon
    ("first", "First Step", "Take your first dose", "spark"),
    ("perfect_day", "Perfect Day", "Every dose in one day", "sun"),
    ("on_time", "On-Time Hero", f"5 doses within {ON_TIME_MINUTES} min", "clock"),
    ("streak3", "3-Day Streak", "Three perfect days in a row", "flame"),
    ("week90", "Week Warrior", f"{GREAT_ADHERENCE}% this week", "trophy"),
    ("mood", "Feelings Matter", "Mood check-in on 3 days", "heart"),
]

FOOD_OPTIONS = ["Any time", "Before food", "After food", "With food"]
SENIOR_AGE = 65          # from this age some medicines show an extra caution
REMIND_OPTIONS = [0, 5, 10, 15, 30]   # "remind me N minutes before" choices
GRACE_OPTIONS = [15, 30, 60, 90, 120]  # minutes before an untaken dose turns red

# Gamification: XP rules and plant-themed levels (they grow like the turtle's seedling).
XP_DOSE = 10             # every dose taken
XP_ON_TIME = 5           # bonus when taken within ON_TIME_MINUTES
XP_PERFECT_DAY = 20      # every dose of a day taken
XP_MOOD = 5              # daily mood check-in
LEVELS = [(0, "Seedling"), (100, "Sprout"), (250, "Sapling"), (450, "Blossom"),
          (700, "Evergreen"), (1000, "Mighty Oak"), (1400, "Ancient Forest")]

# Common illnesses and medicines typically used for them. Doses and times are only
# starting points: the user edits them to match their own prescription.
CONDITIONS = [
    {"name": "Common cold & flu", "about": "Blocked nose, sneezing, sore throat.", "meds": [
        {"name": "Paracetamol", "dose": "500 mg tablet", "times": ["08:00", "14:00", "20:00"], "food": "After food"},
        {"name": "Cetirizine", "dose": "10 mg tablet", "times": ["21:00"], "food": "Any time"}]},
    {"name": "Fever", "about": "High temperature, chills, body ache.", "meds": [
        {"name": "Paracetamol", "dose": "650 mg tablet", "times": ["08:00", "20:00"], "food": "After food"}]},
    {"name": "Headache & body pain", "about": "Aches, sprains, joint pain.", "meds": [
        {"name": "Ibuprofen", "dose": "400 mg tablet", "times": ["09:00", "21:00"], "food": "After food",
         "senior_caution": "Over 65? Ask your doctor first. It can upset the stomach and kidneys."}]},
    {"name": "Acidity & heartburn", "about": "Burning chest, sour taste after meals.", "meds": [
        {"name": "Pantoprazole", "dose": "40 mg tablet", "times": ["07:30"], "food": "Before food"},
        {"name": "Antacid gel", "dose": "10 ml", "times": ["13:30"], "food": "After food"}]},
    {"name": "Cough", "about": "Dry or tickly cough.", "meds": [
        {"name": "Cough syrup (Dextromethorphan)", "dose": "10 ml", "times": ["08:00", "20:00"], "food": "Any time"}]},
    {"name": "Allergy", "about": "Itchy eyes, rash, hay fever.", "meds": [
        {"name": "Loratadine", "dose": "10 mg tablet", "times": ["09:00"], "food": "Any time"}]},
    {"name": "Type 2 diabetes", "about": "Long-term blood sugar control.", "meds": [
        {"name": "Metformin", "dose": "500 mg tablet", "times": ["08:00", "20:00"], "food": "After food"}]},
    {"name": "High blood pressure", "about": "Long-term blood pressure control.", "meds": [
        {"name": "Amlodipine", "dose": "5 mg tablet", "times": ["09:00"], "food": "Any time"}]},
    {"name": "High cholesterol", "about": "Protects the heart and blood vessels.", "meds": [
        {"name": "Atorvastatin", "dose": "10 mg tablet", "times": ["21:00"], "food": "Any time"}]},
    {"name": "Thyroid (underactive)", "about": "Taken on an empty stomach every morning.", "meds": [
        {"name": "Levothyroxine", "dose": "50 mcg tablet", "times": ["06:30"], "food": "Before food"}]},
    {"name": "Low vitamin D", "about": "Bones, muscles and energy.", "meds": [
        {"name": "Vitamin D3", "dose": "1000 IU capsule", "times": ["13:00"], "food": "With food"}]},
    {"name": "Constipation", "about": "Gentle fibre to keep things regular.", "meds": [
        {"name": "Isabgol (psyllium husk)", "dose": "1 teaspoon in water", "times": ["21:30"], "food": "After food"}]},
]


# =============================================================================
# 2. CORE LOGIC (pure functions - easy to test, no Streamlit here)
# =============================================================================

def fmt_time(hhmm):
    """'08:00' -> '8:00 AM' (12-hour clocks are easier for most older adults)."""
    t = datetime.strptime(hhmm, "%H:%M")
    return t.strftime("%I:%M %p").lstrip("0")


def time_options(step_minutes=15):
    """All clock times in a day, every `step_minutes`, as 'HH:MM' strings."""
    return [f"{m // 60:02d}:{m % 60:02d}" for m in range(0, 24 * 60, step_minutes)]


def validate_medicine(name, times, medicines, editing_id=None):
    """Return a list of friendly error messages (empty list = valid)."""
    errors = []
    clean = name.strip()
    if not clean:
        errors.append("Please type the medicine's name.")
    elif len(clean) > 40:
        errors.append("Please keep the name under 40 letters.")
    if not times:
        errors.append("Please choose at least one time of day.")
    for med in medicines:
        if med["id"] != editing_id and med["name"].lower() == clean.lower():
            errors.append(f"'{clean}' is already in your list. Edit it instead of adding it twice.")
    return errors


def new_medicine(name, dose, times, notes, start_day, from_time="00:00", food="Any time", added_day=None):
    """Create a medicine record (a dictionary).

    `start_day` is when the patient starts (or started) taking it - it can be in
    the past, today or the future. `added_day` + `from_time` record the moment it
    was added to MedTimer: doses before that moment are never counted as missed.
    """
    added_day = added_day or start_day
    return {
        "id": uuid.uuid4().hex[:8],
        "name": name.strip(),
        "dose": dose.strip(),
        "times": sorted(set(times)),
        "notes": notes.strip(),
        "food": food if food in FOOD_OPTIONS else "Any time",
        "start": start_day.isoformat(),   # the patient's start date
        "added": added_day.isoformat(),   # the day it was added to the app
        "from": from_time,                # time it was added (only matters on that day)
    }


START_CHOICES = ["Today", "Tomorrow", "Pick a date"]


def resolve_start(choice, picked, today):
    """Turn the 'Start taking it' choice into a date."""
    if choice == "Tomorrow":
        return today + timedelta(days=1)
    if choice == "Pick a date" and picked:
        return picked
    return today


def start_label(med, today):
    """'Starts tomorrow', 'Since 20 Oct', 'Started today' - for the medicine list."""
    start = date.fromisoformat(med["start"])
    if start == today:
        return "Started today"
    if start == today + timedelta(days=1):
        return "Starts tomorrow"
    if start > today:
        return f"Starts {start.strftime('%a %d %b').replace(' 0', ' ')}"
    return f"Since {start.strftime('%d %b %Y').lstrip('0')}"


def dose_key(med_id, hhmm):
    """Unique key of one scheduled dose within a day."""
    return f"{med_id}@{hhmm}"


def doses_for_day(medicines, day):
    """List of (medicine, 'HH:MM') pairs scheduled on `day`, sorted by time."""
    pairs = []
    for med in medicines:
        start = date.fromisoformat(med["start"])
        added = date.fromisoformat(med.get("added", med["start"]))
        if day < start or day < added:
            continue                                  # not started yet, or before it was in the app
        for t in med["times"]:
            if day == added and t < med.get("from", "00:00"):
                continue                              # already past when it was added
            pairs.append((med, t))
    return sorted(pairs, key=lambda p: (p[1], p[0]["name"].lower()))


def dose_status(scheduled, taken_at, now, grace_minutes):
    """Decide the colour-coded status of a single dose.

    taken    -> the user ticked it
    upcoming -> its time has not arrived yet
    due      -> its time has arrived, still inside the grace window
    missed   -> grace window is over and it was not taken
    """
    if taken_at:
        return "taken"
    if now < scheduled:
        return "upcoming"
    if now <= scheduled + timedelta(minutes=grace_minutes):
        return "due"
    return "missed"


def build_checklist(medicines, log, now, grace_minutes):
    """Today's live checklist: one dictionary per scheduled dose."""
    today = now.date()
    taken_today = log.get(today.isoformat(), {})
    rows = []
    for med, hhmm in doses_for_day(medicines, today):
        scheduled = datetime.combine(today, time.fromisoformat(hhmm), tzinfo=now.tzinfo)
        key = dose_key(med["id"], hhmm)
        taken_at = taken_today.get(key)
        rows.append({
            "key": key,
            "med": med,
            "time": hhmm,
            "scheduled": scheduled,
            "taken_at": taken_at,
            "status": dose_status(scheduled, taken_at, now, grace_minutes),
        })
    return rows


def pick_next_dose(checklist):
    """The dose to mention first: one that is due, otherwise the next upcoming."""
    for wanted in ("due", "upcoming"):
        for row in checklist:
            if row["status"] == wanted:
                return row
    return None


def too_early(row, now):
    """Safety rule: a dose can't be ticked more than EARLY_WINDOW minutes early."""
    return row["status"] == "upcoming" and (row["scheduled"] - now).total_seconds() / 60 > EARLY_WINDOW


def day_counts(medicines, log, day, now, grace_minutes):
    """(taken, counted) for one day.

    Past days count every scheduled dose. Today only counts doses that are
    already taken or whose grace window is over - upcoming doses are not
    held against the user.
    """
    taken_map = log.get(day.isoformat(), {})
    taken = counted = 0
    for med, hhmm in doses_for_day(medicines, day):
        key = dose_key(med["id"], hhmm)
        scheduled = datetime.combine(day, time.fromisoformat(hhmm), tzinfo=now.tzinfo)
        if key in taken_map:
            taken += 1
            counted += 1
        elif day < now.date() or now > scheduled + timedelta(minutes=grace_minutes):
            counted += 1
    return taken, counted


def weekly_summary(medicines, log, now, grace_minutes):
    """Adherence for the last 7 days (oldest first) and the overall score."""
    days = [now.date() - timedelta(days=i) for i in range(6, -1, -1)]
    rows = []
    for d in days:
        taken, counted = day_counts(medicines, log, d, now, grace_minutes)
        rows.append({
            "day": d,
            "label": "Today" if d == now.date() else d.strftime("%a %d"),
            "taken": taken,
            "scheduled": counted,
            "missed": counted - taken,
            "pct": round(100 * taken / counted) if counted else None,
        })
    total_taken = sum(r["taken"] for r in rows)
    total_counted = sum(r["scheduled"] for r in rows)
    score = round(100 * total_taken / total_counted) if total_counted else 0
    return rows, score, total_taken, total_counted


def perfect_day_streak(medicines, log, now, grace_minutes):
    """Number of consecutive perfect days, counting back from today/yesterday."""
    streak = 0
    day = now.date()
    taken, counted = day_counts(medicines, log, day, now, grace_minutes)
    if not (counted and taken == counted):
        day -= timedelta(days=1)      # today is still in progress
    for _ in range(366):
        taken, counted = day_counts(medicines, log, day, now, grace_minutes)
        if not counted or taken != counted:
            break
        streak += 1
        day -= timedelta(days=1)
    return streak


def on_time_count(medicines, log, now):
    """How many doses in the last 7 days were taken within ON_TIME_MINUTES."""
    count = 0
    for i in range(7):
        day = now.date() - timedelta(days=i)
        taken_map = log.get(day.isoformat(), {})
        for med, hhmm in doses_for_day(medicines, day):
            taken_at = taken_map.get(dose_key(med["id"], hhmm))
            if taken_at:
                planned = datetime.combine(day, time.fromisoformat(hhmm))
                actual = datetime.combine(day, time.fromisoformat(taken_at))
                if abs((actual - planned).total_seconds()) <= ON_TIME_MINUTES * 60:
                    count += 1
    return count


def earned_badges(medicines, log, moods, week_rows, score, streak, now):
    """Return {badge_id: True/False} using simple, explainable rules."""
    any_taken = any(log.values())
    perfect = any(r["scheduled"] and r["taken"] == r["scheduled"] for r in week_rows)
    return {
        "first": any_taken,
        "perfect_day": perfect,
        "on_time": on_time_count(medicines, log, now) >= 5,
        "streak3": streak >= 3,
        "week90": score >= GREAT_ADHERENCE and sum(r["scheduled"] for r in week_rows) >= 7,
        "mood": len(moods) >= 3,
    }


def reward_level(score, has_data):
    """Which turtle picture to draw for this weekly score."""
    if not has_data:
        return "seedling"
    if score >= GREAT_ADHERENCE:
        return "trophy"
    if score >= GOOD_ADHERENCE:
        return "smiley"
    return "seedling"


def adherence_message(score, has_data):
    if not has_data:
        return "Your score appears after your first dose time."
    if score >= GREAT_ADHERENCE:
        return "Outstanding week. You earned a trophy."
    if score >= GOOD_ADHERENCE:
        return "A good week. Keep the routine going."
    if score >= 50:
        return "Getting there. Small steps every day."
    return "Let's start fresh today. Every dose counts."


def greeting_for(now, name):
    part = "morning" if now.hour < 12 else "afternoon" if now.hour < 17 else "evening"
    return f"Good {part}, {name}" if name else f"Good {part}"


def time_of_day(hhmm):
    """Group label used in the checklist."""
    hour = int(hhmm[:2])
    return "Morning" if hour < 12 else "Afternoon" if hour < 17 else "Evening" if hour < 21 else "Night"


def tip_of_the_day(day):
    """Same tip all day, a new one tomorrow."""
    return TIPS[day.toordinal() % len(TIPS)]


def quote_of_the_day(day):
    return QUOTES[day.toordinal() % len(QUOTES)]


def speech_text(name, checklist):
    """What the 'Read aloud' button says."""
    if not checklist:
        return f"Hello {name}. You have no medicines scheduled today."
    parts = [f"Hello {name}. Here are your medicines for today."]
    for row in checklist:
        med = row["med"]
        food = f", {food_label(med).lower()}" if food_label(med) else ""
        parts.append(f"At {fmt_time(row['time'])}, {med['name']} {med['dose']}{food}. {STATUS_LABEL[row['status']]}.")
    left = sum(r["status"] in ("due", "upcoming") for r in checklist)
    parts.append(f"You have {left} left to take today." if left else "You have finished everything for today. Well done.")
    return " ".join(parts)


def medicine_breakdown(medicines, log, now, grace_minutes):
    """Per-medicine taken / missed counts for the last 7 days (for the report)."""
    rows = []
    for med in medicines:
        taken = counted = 0
        for i in range(7):
            day = now.date() - timedelta(days=i)
            for _, hhmm in doses_for_day([med], day):
                scheduled = datetime.combine(day, time.fromisoformat(hhmm), tzinfo=now.tzinfo)
                if dose_key(med["id"], hhmm) in log.get(day.isoformat(), {}):
                    taken += 1
                    counted += 1
                elif day < now.date() or now > scheduled + timedelta(minutes=grace_minutes):
                    counted += 1
        rows.append({
            "Medicine": med["name"],
            "Dose": med["dose"],
            "Times": ", ".join(fmt_time(t) for t in med["times"]),
            "Taken": taken,
            "Missed": counted - taken,
            "Adherence %": round(100 * taken / counted) if counted else None,
        })
    return rows


def food_label(med):
    """'After food' etc., or '' when it doesn't matter."""
    food = med.get("food", "Any time")
    return "" if food == "Any time" else food


def xp_total(medicines, log, moods):
    """All XP earned so far, worked out from the history (nothing extra is stored)."""
    xp = 0
    for day_iso, taken_map in log.items():
        day = date.fromisoformat(day_iso)
        scheduled = doses_for_day(medicines, day)
        for med, hhmm in scheduled:
            taken_at = taken_map.get(dose_key(med["id"], hhmm))
            if taken_at:
                xp += XP_DOSE
                planned = datetime.combine(day, time.fromisoformat(hhmm))
                actual = datetime.combine(day, time.fromisoformat(taken_at))
                if abs((actual - planned).total_seconds()) <= ON_TIME_MINUTES * 60:
                    xp += XP_ON_TIME
        if scheduled and all(dose_key(m["id"], t) in taken_map for m, t in scheduled):
            xp += XP_PERFECT_DAY
    return xp + XP_MOOD * len(moods)


def level_for(xp):
    """(level number, name, XP where it started, XP for the next level or None)."""
    number = max(i for i, (floor, _) in enumerate(LEVELS) if xp >= floor)
    floor, name = LEVELS[number]
    nxt = LEVELS[number + 1][0] if number + 1 < len(LEVELS) else None
    return number + 1, name, floor, nxt


def dose_xp(row, now):
    """XP a dose would earn if ticked right now (shown as '+15 XP')."""
    on_time = abs((now - row["scheduled"]).total_seconds()) <= ON_TIME_MINUTES * 60
    return XP_DOSE + (XP_ON_TIME if on_time else 0)


def daily_quests(checklist, moods, now):
    """Three small goals for today. Their rewards match the XP rules above."""
    taken = [r for r in checklist if r["status"] == "taken"]
    on_time = any(abs((datetime.combine(now.date(), time.fromisoformat(r["taken_at"]), tzinfo=now.tzinfo)
                       - r["scheduled"]).total_seconds()) <= ON_TIME_MINUTES * 60 for r in taken)
    return [
        {"title": "Take every dose today", "xp": XP_PERFECT_DAY, "done": bool(checklist) and len(taken) == len(checklist),
         "progress": f"{len(taken)}/{len(checklist)}"},
        {"title": f"Take one dose within {ON_TIME_MINUTES} minutes", "xp": XP_ON_TIME, "done": on_time, "progress": ""},
        {"title": "Check in how you feel", "xp": XP_MOOD, "done": now.date().isoformat() in moods, "progress": ""},
    ]


def reminder_alarms(checklist, minutes_before):
    """When the browser should chime, and what it should say (user-defined lead time)."""
    alarms = []
    for r in checklist:
        if r["status"] != "upcoming":
            continue
        med = r["med"]
        food = f", {food_label(med).lower()}" if food_label(med) else ""
        say = (f"In {minutes_before} minutes, time for {med['name']} {med['dose']}{food}." if minutes_before
               else f"It is time for {med['name']} {med['dose']}{food}.")
        alarms.append({"at": int((r["scheduled"] - timedelta(minutes=minutes_before)).timestamp() * 1000),
                       "label": f"{med['name']} {med['dose']}", "say": say})
    return alarms


def build_report_html(name, age, medicines, log, moods, now, grace_minutes):
    """A clean, printable weekly report for a doctor or family (Print -> Save as PDF)."""
    week, score, taken, counted = weekly_summary(medicines, log, now, grace_minutes)
    per_med = medicine_breakdown(medicines, log, now, grace_minutes)
    esc = html.escape
    pct = lambda v: "" if v is None else f"{v}%"
    day_rows = "".join(
        f"<tr><td>{r['day'].strftime('%a %d %b')}</td><td>{r['taken']}</td><td>{r['missed']}</td>"
        f"<td>{pct(r['pct'])}</td><td>{esc(moods.get(r['day'].isoformat(), '-'))}</td></tr>" for r in week)
    by_name = {m["name"]: m for m in medicines}
    med_rows = "".join(
        f"<tr><td>{esc(m['Medicine'])}</td><td>{esc(m['Dose'])}</td><td>{esc(m['Times'])}</td>"
        f"<td>{esc(by_name[m['Medicine']].get('food', 'Any time'))}</td><td>{esc(start_label(by_name[m['Medicine']], now.date()))}</td>"
        f"<td>{m['Taken']}</td><td>{m['Missed']}</td><td>{pct(m['Adherence %'])}</td></tr>" for m in per_med)
    colour = "#2F6B52" if score >= GOOD_ADHERENCE else "#8A5B12" if score >= 50 else "#A23B30"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>MedTimer report - {esc(name or 'patient')}</title>
<style>body{{font-family:-apple-system,'Segoe UI',Arial,sans-serif;color:#1E2B26;max-width:820px;margin:32px auto;padding:0 16px;font-size:16px}}
h1{{color:#2F6B52;margin-bottom:4px}} .score{{font-size:48px;font-weight:700;color:{colour};margin:0}}
table{{border-collapse:collapse;width:100%;margin:10px 0 28px}} th,td{{border-bottom:1px solid #D5DDD5;padding:8px 10px;text-align:left}}
th{{background:#EEF3F1}} .muted{{color:#4F5F58}} @media print{{button{{display:none}}}}</style></head><body>
<button onclick="window.print()" style="float:right;font-size:16px;padding:10px 18px;border-radius:999px;border:1px solid #ccc">Print / Save as PDF</button>
<h1>MedTimer weekly report</h1>
<p class="muted">Patient: <b>{esc(name or 'Not given')}</b>, age {age} &middot; {week[0]['day'].strftime('%d %b')} - {week[-1]['day'].strftime('%d %b %Y')}
&middot; created {now.strftime('%d %b %Y, %I:%M %p')}</p>
<p class="muted">Weekly adherence</p><p class="score">{score}%</p><p class="muted">{taken} of {counted} doses taken. Upcoming doses are not counted.</p>
<h2>Medicines</h2><table><tr><th>Medicine</th><th>Dose</th><th>Times</th><th>Food</th><th>Started</th><th>Taken</th><th>Missed</th><th>Adherence</th></tr>{med_rows}</table>
<h2>Day by day</h2><table><tr><th>Day</th><th>Taken</th><th>Missed</th><th>Adherence</th><th>Mood</th></tr>{day_rows}</table>
<p class="muted">MedTimer is a memory aid, not medical advice. Please discuss any changes with your doctor or pharmacist.</p></body></html>"""


# =============================================================================
# 3. TURTLE GRAPHICS
# =============================================================================
# Python's turtle module needs a desktop window (tkinter), which does not exist
# on Streamlit Cloud. SvgTurtle offers the same commands (forward, left,
# circle, begin_fill ...) but records the path and turns it into an animated
# SVG. The draw_* functions below work with BOTH SvgTurtle and the real
# turtle.Turtle - try `python app.py --turtle trophy` on your own computer.

class SvgTurtle:
    """A drop-in subset of turtle.Turtle that records drawings as SVG."""

    def __init__(self):
        self.x, self.y, self.angle = 0.0, 0.0, 0.0
        self.is_down = True
        self.pen, self.fill, self.width = "#1E2B26", "#1E2B26", 2
        self.items = []          # strokes, fills, dots and text in drawing order
        self._stroke = None
        self._filling = None

    # --- movement -----------------------------------------------------------
    def _move_to(self, x, y):
        if self.is_down:
            if self._stroke is None:
                self._stroke = {"kind": "stroke", "pts": [(self.x, self.y)], "color": self.pen, "width": self.width}
                self.items.append(self._stroke)
            self._stroke["pts"].append((x, y))
        if self._filling is not None:
            self._filling["pts"].append((x, y))
        self.x, self.y = x, y

    def forward(self, distance):
        rad = math.radians(self.angle)
        self._move_to(self.x + distance * math.cos(rad), self.y + distance * math.sin(rad))

    def backward(self, distance):
        self.forward(-distance)

    def left(self, degrees):
        self.angle = (self.angle + degrees) % 360

    def right(self, degrees):
        self.left(-degrees)

    def setheading(self, degrees):
        self.angle = degrees % 360

    def goto(self, x, y):
        self._move_to(x, y)

    def circle(self, radius, extent=360):
        """Same maths as CPython's turtle.circle (centre is `radius` to the left)."""
        steps = 1 + int(min(11 + abs(radius) / 6.0, 59.0) * abs(extent) / 360) * 2
        w = extent / steps
        half = 0.5 * w
        length = 2.0 * radius * math.sin(math.radians(half))
        if radius < 0:
            length, w, half = -length, -w, -half
        self.left(half)
        for _ in range(steps):
            self.forward(length)
            self.left(w)
        self.left(-half)

    # --- pen ----------------------------------------------------------------
    def penup(self):
        self.is_down = False
        self._stroke = None

    def pendown(self):
        self.is_down = True

    def pensize(self, width):
        self.width = width
        self._stroke = None

    def color(self, pen, fill=None):
        self.pen = pen
        self.fill = fill or pen
        self._stroke = None

    def begin_fill(self):
        self._filling = {"kind": "fill", "pts": [(self.x, self.y)], "color": self.fill}
        self.items.append(self._filling)

    def end_fill(self):
        if self._filling is not None:
            self._filling["ends_at"] = len(self.items)   # appears after its outline
        self._filling = None

    def dot(self, size, color=None):
        self.items.append({"kind": "dot", "x": self.x, "y": self.y, "r": size / 2, "color": color or self.pen})

    def write(self, text, align="center", font=("Arial", 16, "bold")):
        self.items.append({"kind": "text", "x": self.x, "y": self.y, "text": str(text), "size": font[1], "color": self.pen})

    # Accepted for compatibility with the real turtle, nothing to do here.
    def speed(self, *_):
        pass

    def hideturtle(self):
        pass

    # --- output -------------------------------------------------------------
    def to_svg(self, seconds=3.2):
        """Return (svg_markup, total_animation_seconds)."""
        xs, ys = [], []
        for it in self.items:
            if it["kind"] in ("stroke", "fill"):
                xs += [p[0] for p in it["pts"]]
                ys += [p[1] for p in it["pts"]]
            else:
                xs.append(it["x"])
                ys.append(it["y"])
        pad = 26
        min_x, max_x = min(xs) - pad, max(xs) + pad
        min_y, max_y = min(ys) - pad, max(ys) + pad
        size = max(max_x - min_x, max_y - min_y)
        cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
        view = f"{cx - size / 2:.1f} {-cy - size / 2:.1f} {size:.1f} {size:.1f}"

        def length(pts):
            return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))

        total_len = sum(length(it["pts"]) for it in self.items if it["kind"] == "stroke") or 1
        clock, out, stroke_end = 0.0, [], {}
        for i, it in enumerate(self.items):
            if it["kind"] == "stroke":
                dur = max(0.06, seconds * length(it["pts"]) / total_len)
                d = "M" + " L".join(f"{x:.1f},{-y:.1f}" for x, y in it["pts"])
                out.append(
                    f'<path class="s" d="{d}" pathLength="1" fill="none" stroke="{it["color"]}" stroke-width="{it["width"]}" '
                    f'stroke-linecap="round" stroke-linejoin="round" style="--t:{clock:.2f}s;--d:{dur:.2f}s"/>'
                )
                clock += dur
            stroke_end[i + 1] = clock
        # Fills/dots/text are inserted at the moment their outline finishes.
        layered = []
        clock_at = {0: 0.0, **stroke_end}
        for i, it in enumerate(self.items):
            if it["kind"] == "fill" and len(it["pts"]) > 2:
                when = clock_at.get(it.get("ends_at", i + 1), clock)
                d = "M" + " L".join(f"{x:.1f},{-y:.1f}" for x, y in it["pts"]) + " Z"
                layered.append((i, f'<path class="f" d="{d}" fill="{it["color"]}" style="--t:{when:.2f}s"/>'))
            elif it["kind"] == "dot":
                layered.append((10_000 + i, f'<circle class="f" cx="{it["x"]:.1f}" cy="{-it["y"]:.1f}" r="{it["r"]:.1f}" fill="{it["color"]}" style="--t:{clock_at.get(i, 0):.2f}s"/>'))
            elif it["kind"] == "text":
                layered.append((20_000 + i, f'<text class="w" x="{it["x"]:.1f}" y="{-it["y"]:.1f}" text-anchor="middle" font-size="{it["size"]}" font-weight="700" '
                                            f'font-family="Roboto Flex, Arial, sans-serif" fill="{it["color"]}" style="--t:{clock:.2f}s">{html.escape(it["text"])}</text>'))
        fills = [svg for idx, svg in sorted(layered) if idx < 10_000]
        extras = [svg for idx, svg in sorted(layered) if idx >= 10_000]
        # Python turtle's own "turtle" shape, pointing along +x, follows the pen.
        shape = [(0, 16), (-2, 14), (-1, 10), (-4, 7), (-7, 9), (-9, 8), (-6, 5), (-7, 1), (-5, -3), (-8, -6), (-6, -8), (-4, -5),
                 (0, -7), (4, -5), (6, -8), (8, -6), (5, -3), (7, 1), (6, 5), (9, 8), (7, 9), (4, 7), (1, 10), (2, 14)]
        k = size / 260
        head = " ".join(f"{sy * k:.1f},{sx * k:.1f}" for sx, sy in shape)
        turtle_head = f'<g class="turtle"><polygon points="{head}" fill="#2F6B52" stroke="#fff" stroke-width="{k:.2f}"/></g>'
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" aria-hidden="true">'
               + "".join(fills) + "".join(out) + "".join(extras) + turtle_head + "</svg>")
        return svg, clock + 0.6


# Turtle colours follow the app palette.
INK, GOLD, GOLD_DARK, SAGE, SAGE_DARK, SKY, CLAY = "#1E2B26", "#E9B949", "#8A5B12", "#6FA587", "#2F6B52", "#8DB3CF", "#C4805A"


def _filled_shape(t, pen, fill, start, draw):
    t.penup()
    t.goto(*start)
    t.pendown()
    t.color(pen, fill)
    t.begin_fill()
    draw()
    t.end_fill()


def draw_trophy(t):
    """Gold trophy with a star - weekly adherence of GREAT_ADHERENCE% or more."""
    t.pensize(4)

    def cup():
        t.setheading(0)
        t.forward(120)
        t.setheading(-90)
        t.circle(-60, 180)                 # round bottom of the cup
    _filled_shape(t, GOLD_DARK, GOLD, (-60, 60), cup)

    for x, heading, r in ((60, 0, -22), (-60, 180, 22)):   # two handles
        t.penup()
        t.goto(x, 52)
        t.setheading(heading)
        t.pendown()
        t.circle(r, 180)

    def rect(w, h):
        def go():
            t.setheading(0)
            for side in (w, h, w, h):
                t.forward(side)
                t.right(90)
        return go
    _filled_shape(t, GOLD_DARK, "#D9A63A", (-10, 0), rect(20, 34))     # stem
    _filled_shape(t, INK, SAGE_DARK, (-46, -34), rect(92, 22))          # base

    def star():
        t.setheading(0)
        for _ in range(5):
            t.forward(34)
            t.right(144)
    _filled_shape(t, GOLD_DARK, "#FFF6D5", (-17, 40), star)

    t.penup()
    for x, y, c in ((-95, 75, SKY), (95, 85, SAGE), (-105, 0, CLAY), (100, 10, SKY), (0, 110, GOLD)):
        t.goto(x, y)
        t.dot(12, c)
    t.goto(0, -95)
    t.color(INK)
    t.write("Trophy week!", align="center", font=("Arial", 22, "bold"))


def draw_smiley(t):
    """Smiling face - a good week (GOOD_ADHERENCE% or more)."""
    t.pensize(5)

    def face():
        t.setheading(0)
        t.circle(90)
    _filled_shape(t, GOLD_DARK, GOLD, (0, -90), face)
    t.penup()
    for x in (-32, 32):
        t.goto(x, 28)
        t.dot(22, INK)
    for x in (-58, 58):
        t.goto(x, -6)
        t.dot(22, "#E8A28F")
    t.goto(-50, -10)
    t.setheading(-60)
    t.color(INK)
    t.pensize(7)
    t.pendown()
    t.circle(58, 120)                    # the smile
    t.penup()
    t.goto(0, -125)
    t.write("Nice going!", align="center", font=("Arial", 22, "bold"))


def draw_seedling(t):
    """A little plant in a pot - encouragement, never blame."""
    t.pensize(4)

    def pot():
        t.goto(40, -60)
        t.goto(30, -110)
        t.goto(-30, -110)
        t.goto(-40, -60)
    _filled_shape(t, "#7A3F14", CLAY, (-40, -60), pot)

    t.penup()
    t.goto(0, -60)
    t.setheading(90)
    t.color(SAGE_DARK)
    t.pensize(7)
    t.pendown()
    t.forward(75)                         # stem
    t.pensize(4)

    def leaf(heading, r):
        def go():
            t.setheading(heading)
            t.circle(r, 90)
            if r > 0:
                t.left(90)
            else:
                t.right(90)
            t.circle(r, 90)
        return go
    _filled_shape(t, SAGE_DARK, SAGE, (0, -25), leaf(20, 45))
    _filled_shape(t, SAGE_DARK, SAGE, (0, -5), leaf(160, -45))
    t.penup()
    t.goto(85, 85)
    t.dot(46, GOLD)                       # sunshine
    t.goto(0, -145)
    t.color(INK)
    t.write("Every dose helps you grow", align="center", font=("Arial", 18, "bold"))


DRAWINGS = {
    "trophy": (draw_trophy, "A gold trophy with a star, drawn by the turtle"),
    "smiley": (draw_smiley, "A smiling face, drawn by the turtle"),
    "seedling": (draw_seedling, "A small plant growing in a pot, drawn by the turtle"),
}


def turtle_reward_svg(level):
    draw, alt = DRAWINGS[level]
    t = SvgTurtle()
    draw(t)
    svg, seconds = t.to_svg()
    return svg, seconds, alt


# =============================================================================
# 4. VISUAL COMPONENTS (React Bits designs in plain JavaScript)
# =============================================================================
# Designs from React Bits (reactbits.dev), rewritten in plain JavaScript so no
# Node build is needed, and restyled to one theme:
#   Aurora + TextPressure + Counter -> header  |  SloshGauge -> medicine bottle
#   FolderFloat -> tips (matter-js)            |  turtle player -> animated drawing
#   SpringCheck / LineSidebar / WakeSlider / OptionWheel -> two-way widgets in
#   _WIDGETS_HTML (end of this file) that send values back to Python.
# Each helper only builds HTML and hands it to Streamlit.

# One palette for the whole app (also used by app.py's CSS).
THEME = {
    "paper": "#EEF3F1", "paper2": "#E2E8E1", "card": "#FAFBF8",
    "ink": "#1E2B26", "ink2": "#4F5F58", "rule": "rgba(30,43,38,.14)",
    "accent": "#2F6B52", "accentSoft": "#CFE3D6",
    "amber": "#8A5B12", "amberSoft": "#F3E6C9",
    "brick": "#A23B30", "brickSoft": "#F4DAD5",
    "sky": "#8DB3CF",
}

FONTS = ("https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700"
         "&family=Roboto+Flex:opsz,wdth,wght@8..144,25..151,100..1000&display=swap")

_BASE_CSS = """
:root{--paper:%(paper)s;--paper2:%(paper2)s;--card:%(card)s;--ink:%(ink)s;--ink2:%(ink2)s;--rule:%(rule)s;
--accent:%(accent)s;--accentSoft:%(accentSoft)s;--amber:%(amber)s;--amberSoft:%(amberSoft)s;--brick:%(brick)s;--brickSoft:%(brickSoft)s;
--display:'Roboto Flex','Helvetica Neue',Arial,sans-serif;--text:'Atkinson Hyperlegible',system-ui,sans-serif;--ease:cubic-bezier(.23,1,.32,1)}
*{box-sizing:border-box} html,body{margin:0;background:transparent;color:var(--ink);font-family:var(--text);-webkit-font-smoothing:antialiased}
button{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
""" % THEME

# The two-way widgets live in one small HTML page (_WIDGETS_HTML, at the end of
# this file). Streamlit loads custom components from a folder, so the page is
# written to a temporary folder at start-up - no extra files to upload.
def _widget_folder():
    folder = Path(tempfile.gettempdir()) / "medtimer_widgets"
    folder.mkdir(parents=True, exist_ok=True)
    page = folder / "index.html"
    if not page.exists() or page.read_text(encoding="utf-8") != _WIDGETS_HTML:
        page.write_text(_WIDGETS_HTML, encoding="utf-8")
    return folder


_bridge = None


def _get_bridge():
    """Declare the component once, on first use (after _WIDGETS_HTML exists)."""
    global _bridge
    if _bridge is None:
        _bridge = components.declare_component("medtimer_widgets", path=str(_widget_folder()))
    return _bridge


def _json(data):
    """JSON that is safe to drop inside a <script> tag."""
    return json.dumps(data).replace("</", "<\\/")


def _page(body, extra_head=""):
    return (f'<!doctype html><html><head><meta charset="utf-8"><link href="{FONTS}" rel="stylesheet">'
            f"{extra_head}<style>{_BASE_CSS}</style></head><body>{body}</body></html>")


# ------------------------------------------------------- two-way widgets ----

def _widget(kind, key, height, **args):
    return _get_bridge()(kind=kind, key=key, default=None, height=height, theme=THEME, **args)


def checklist_widget(groups, key):
    """Today's doses as SpringCheck rows. Returns {"key", "checked", "ts"} on a tap."""
    rows = sum(len(g["rows"]) for g in groups)
    return _widget("checklist", key, 60 + rows * 76 + len(groups) * 44, groups=groups)


def line_sidebar(items, active, key):
    """Sidebar navigation. Returns {"index", "label", "ts"} when an item is clicked."""
    return _widget("nav", key, 40 + len(items) * 52, items=items, active=active)


def wake_slider(value, key, low=18, high=100, label="Age"):
    """Bar slider whose bars rise in a wake behind the handle. Returns {"value", "ts"}."""
    return _widget("slider", key, 110, value=value, min=low, max=high, label=label)


def option_wheel(items, selected, key):
    """Curved scroll wheel used for the daily mood check-in."""
    return _widget("wheel", key, 290, items=items, selected=selected)


# ---------------------------------------------------------------- header ----

_HERO = r"""
<style>
 .hero{position:relative;padding:22px 4px 0;min-height:100vh;display:flex;flex-direction:column}
 .aurora{position:absolute;left:0;right:0;top:-40px;height:320px;pointer-events:none;z-index:0;
         -webkit-mask-image:radial-gradient(ellipse 65% 70% at 58% 48%,#000 25%,transparent 72%);mask-image:radial-gradient(ellipse 65% 70% at 58% 48%,#000 25%,transparent 72%)}
 .aurora canvas{width:100%;height:100%;display:block}
 .top,.title,.greet,.stats{position:relative;z-index:1}
 .top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
 .date{font-size:16px;color:var(--ink2);letter-spacing:.02em}
 .actions{display:flex;gap:8px}
 .chip{display:inline-flex;align-items:center;gap:8px;min-height:44px;padding:0 16px;border-radius:999px;border:1px solid rgba(255,255,255,.85);
       background:linear-gradient(180deg,rgba(255,255,255,.75),rgba(255,255,255,.45));backdrop-filter:blur(16px) saturate(170%);-webkit-backdrop-filter:blur(16px) saturate(170%);
       box-shadow:inset 0 1px 0 #fff,0 6px 14px -6px rgba(28,58,48,.25);cursor:pointer;font-size:16px;font-weight:700;
       transition:background-color .2s var(--ease),transform .15s var(--ease)}
 .chip:hover{background:var(--card)} .chip:active{transform:scale(.97)}
 .chip[aria-pressed="true"]{background:var(--accent);color:#fff;border-color:var(--accent)}
 .chip svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
 .title{height:clamp(56px,13vw,160px);margin:18px 0 6px}
 .title h1{margin:0;font-family:var(--display);text-transform:uppercase;line-height:1;white-space:nowrap;display:flex;justify-content:space-between;
           user-select:none;font-weight:100;color:var(--ink)}
 .title h1 span{display:inline-block}
 .greet{font-size:clamp(19px,2.1vw,24px);line-height:1.4;margin:0 0 26px;max-width:46ch}
 .greet b{font-weight:700} .greet .due{color:var(--accent)}
 .stats{display:grid;grid-template-columns:repeat(5,1fr);padding:4px 10px;border-radius:28px;border:1px solid rgba(255,255,255,.8);
        background:linear-gradient(180deg,rgba(255,255,255,.38),rgba(255,255,255,.12));-webkit-backdrop-filter:blur(16px) saturate(200%);backdrop-filter:blur(16px) saturate(200%);
        box-shadow:inset 0 1px 0 rgba(255,255,255,.95),0 18px 40px -14px rgba(28,58,48,.22)}
 .stats:empty{display:none}
 .stat{padding:14px clamp(8px,1.6vw,16px) 10px;min-width:0} .stat+.stat{border-left:1px solid rgba(30,43,38,.08)}
 .num{font-family:var(--display);font-size:clamp(22px,4.4vw,52px);font-weight:700;font-variation-settings:'wdth' 112;line-height:1;
      display:flex;align-items:baseline;font-variant-numeric:tabular-nums}
 .lbl{font-size:clamp(12px,1.6vw,15px);color:var(--ink2);margin-top:6px;line-height:1.25}
 .tone-taken .num{color:var(--accent)} .tone-missed .num{color:var(--brick)} .tone-left .num{color:var(--amber)}
 /* Counter (React Bits): each digit is a strip of 0-9 that rolls into place */
 .dg{position:relative;display:inline-block;height:1em;overflow:hidden;width:.62em}
 .dg i{position:absolute;left:0;right:0;top:0;display:flex;flex-direction:column;font-style:normal;text-align:center;will-change:transform}
 .dg i b{height:1em;line-height:1em;font-weight:inherit}
 .sym{display:inline-block}
 @media (max-width:760px){.stats{padding:2px 4px}}
</style>
<div class="hero">
  <div class="aurora" id="aurora"><canvas id="au"></canvas></div>
  <div class="top">
    <span class="date">__DATE__</span>
    <div class="actions">
      <button class="chip" id="speak" type="button"><svg viewBox="0 0 24 24"><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M19 5a10 10 0 0 1 0 14"/></svg>Read aloud</button>
      <button class="chip" id="beep" type="button" aria-pressed="false"><svg viewBox="0 0 24 24"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg><span>Reminders off</span></button>
    </div>
  </div>
  <div class="title" id="title" aria-label="MedTimer"></div>
  <p class="greet">__GREETING__</p>
  <div class="stats" id="stats"></div>
  <p class="sr" role="status" id="live"></p>
</div>
<script>
const CFG = __CONFIG__;
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches || CFG.reduceMotion;

/* ---------- Counter (React Bits): rolling odometer digits ---------- */
(function counters(){
  const box = document.getElementById('stats');
  CFG.stats.forEach((s, n) => {
    const el = document.createElement('div'); el.className = 'stat tone-' + s.tone;
    el.innerHTML = `<div class="num" aria-label="${s.text}"></div><div class="lbl">${s.label}</div>`;
    const num = el.firstChild;
    [...s.text].forEach((ch, i) => {
      if (!/[0-9]/.test(ch)) { const sp = document.createElement('span'); sp.className = 'sym'; sp.textContent = ch; num.appendChild(sp); return; }
      const d = document.createElement('span'); d.className = 'dg';
      d.innerHTML = '<i>' + Array.from({length: 10}, (_, k) => `<b>${k}</b>`).join('') + '</i>';
      num.appendChild(d);
      const strip = d.firstChild, target = +ch;
      if (reduce) { strip.style.transform = `translateY(${-target}em)`; return; }
      strip.animate([{ transform: 'translateY(0em)', filter: 'blur(2px)' }, { transform: `translateY(${-target}em)`, filter: 'blur(0)' }],
        { duration: 900 + target * 60, delay: 250 + n * 90 + i * 40, easing: 'cubic-bezier(.34,1.25,.64,1)', fill: 'both' });
    });
    box.appendChild(el);
  });
})();

/* ---------- TextPressure (React Bits): letters swell near the pointer ---------- */
(function textPressure(){
  const box = document.getElementById('title');
  const h1 = document.createElement('h1');
  const chars = Array.from(CFG.title);
  const spans = chars.map(c => { const s = document.createElement('span'); s.textContent = c; h1.appendChild(s); return s; });
  box.appendChild(h1);
  const fit = () => { h1.style.fontSize = Math.min(box.clientHeight * 0.98, box.clientWidth / (chars.length * 0.62)) + 'px'; };
  fit(); new ResizeObserver(fit).observe(box);
  const mouse = {x:0,y:0}, cur = {x:0,y:0,seen:false}; let ripples = [], clock = 0, engage = 0, last = 0, raf = 0;
  const r0 = box.getBoundingClientRect(); mouse.x = cur.x = r0.left + r0.width/2; mouse.y = cur.y = r0.top + r0.height/2;
  const dist = (a,b) => Math.hypot(b.x-a.x, b.y-a.y), c01 = v => Math.min(1, Math.max(0, v));
  addEventListener('pointermove', e => { cur.x = e.clientX; cur.y = e.clientY; cur.seen = true; wake(); });
  document.documentElement.addEventListener('pointerleave', () => { cur.seen = false; wake(); });
  box.addEventListener('pointerdown', e => { ripples.push({x:e.clientX,y:e.clientY,start:performance.now()}); if (ripples.length>6) ripples.shift(); wake(); });
  function tick(now){
    raf = 0; const el = last ? Math.min(now-last,64) : 16; last = now;
    const follow = 1 - Math.exp(-el / 250);
    mouse.x += (cur.x-mouse.x)*follow; mouse.y += (cur.y-mouse.y)*follow;
    const b = box.getBoundingClientRect();
    const present = cur.seen && cur.x>=b.left && cur.x<=b.right && cur.y>=b.top-40 && cur.y<=b.bottom+40 ? 1 : 0;
    engage += (present-engage)*(1-Math.exp(-el/320));
    const idling = !reduce && engage < 1; if (idling) clock += el/1000;
    ripples = ripples.filter(r => now - r.start < 1300);
    const tr = h1.getBoundingClientRect(), maxD = Math.max(tr.width*0.45,1);
    spans.forEach(s => {
      const r = s.getBoundingClientRect(), c = {x:r.x+r.width/2, y:r.y+r.height/2};
      let p = c01(1 - dist(mouse,c)/maxD);
      if (idling) { const pos=(c.x-tr.left)/Math.max(tr.width,1); const crest=.5+.5*Math.cos(Math.PI*2*(pos/1.1-clock/4)); const rest=.15+.75*crest*crest; p = rest+(p-rest)*engage; }
      for (const rp of ripples) { const age=(now-rp.start)/1000; const off=(dist(rp,c)-age*tr.width*1.25)/Math.max(tr.width*.14,32); if (age>0&&age<1.3&&off>-1&&off<1){ const f=1-age/1.3; p = 1-(1-p)*(1-(1-off*off)**2*f*f); } }
      s.style.fontVariationSettings = `'wght' ${Math.floor(150+850*p)}, 'wdth' ${Math.floor(25+126*p)}, 'opsz' 144`;
      s.style.color = `color-mix(in oklab, var(--accent) ${Math.round(p*p*100)}%, var(--ink))`;
    });
    const moving = Math.abs(cur.x-mouse.x)>.1 || Math.abs(cur.y-mouse.y)>.1;
    if (moving || idling || ripples.length || Math.abs(present-engage)>.002) raf = requestAnimationFrame(tick); else last = 0;
  }
  function wake(){ if (!raf) raf = requestAnimationFrame(tick); }
  document.fonts && document.fonts.ready.then(wake); wake();
})();

/* ---------- Aurora (React Bits, WebGL2, light mode) ---------- */
(function aurora(){
  const container = document.getElementById('aurora'), canvas = document.getElementById('au');
  const gl = canvas.getContext('webgl2', { alpha:true, premultipliedAlpha:true, antialias:false, depth:false, stencil:false });
  if (!gl) return;
  const V = `#version 300 es
in vec2 aPosition; void main(){ gl_Position = vec4(aPosition,0.0,1.0); }`;
  const F = `#version 300 es
precision highp float; precision highp int;
uniform vec2 uResolution; uniform float uTime; uniform vec3 uStops[5]; uniform int uStopCount; uniform float uAmplitude;
uniform float uBlend; uniform float uHeight; uniform float uScale; uniform float uGlow; uniform float uBrightness; uniform int uLayers;
uniform vec3 uPointer; uniform float uReveal; uniform float uOpacity;
out vec4 outColor;
vec3 permute(vec3 x){ return mod(((x*34.0)+1.0)*x,289.0); }
float snoise(vec2 v){ const vec4 C=vec4(0.211324865405187,0.366025403784439,-0.577350269189626,0.024390243902439);
  vec2 i=floor(v+dot(v,C.yy)); vec2 x0=v-i+dot(i,C.xx); vec2 i1=(x0.x>x0.y)?vec2(1.0,0.0):vec2(0.0,1.0);
  vec4 x12=x0.xyxy+C.xxzz; x12.xy-=i1; i=mod(i,289.0);
  vec3 p=permute(permute(i.y+vec3(0.0,i1.y,1.0))+i.x+vec3(0.0,i1.x,1.0));
  vec3 m=max(0.5-vec3(dot(x0,x0),dot(x12.xy,x12.xy),dot(x12.zw,x12.zw)),0.0); m=m*m; m=m*m;
  vec3 x=2.0*fract(p*C.www)-1.0; vec3 h=abs(x)-0.5; vec3 ox=floor(x+0.5); vec3 a0=x-ox;
  m*=1.79284291400159-0.85373472095314*(a0*a0+h*h); vec3 g; g.x=a0.x*x0.x+h.x*x0.y; g.yz=a0.yz*x12.xz+h.yz*x12.yw; return 130.0*dot(m,g); }
float smootherstep(float e0,float e1,float x){ float t=clamp((x-e0)/(e1-e0),0.0,1.0); return t*t*t*(t*(t*6.0-15.0)+10.0); }
vec3 oklabToLinear(vec3 c){ float l=c.x+0.3963377774*c.y+0.2158037573*c.z; float m=c.x-0.1055613458*c.y-0.0638541728*c.z; float s=c.x-0.0894841775*c.y-1.2914855480*c.z;
  l=l*l*l; m=m*m*m; s=s*s*s; return vec3(4.0767416621*l-3.3077115913*m+0.2309699292*s,-1.2684380046*l+2.6097574011*m-0.3413193965*s,-0.0041960863*l-0.7034186147*m+1.7076147010*s); }
vec3 toSrgb(vec3 c){ c=clamp(c,0.0,1.0); return mix(c*12.92,1.055*pow(c,vec3(1.0/2.4))-0.055,step(0.0031308,c)); }
vec3 ramp(float t){ float x=clamp(t,0.0,1.0)*float(uStopCount-1); int i=int(min(floor(x),float(uStopCount-2))); float f=x-float(i); f=f*f*(3.0-2.0*f);
  vec3 lch=mix(uStops[i],uStops[i+1],f); lch.x=min(lch.x,0.7); return toSrgb(oklabToLinear(vec3(lch.x,lch.y*cos(lch.z),lch.y*sin(lch.z)))); }
float hash(vec2 p){ p=fract(p*vec2(123.34,456.21)); p+=dot(p,p+45.32); return fract(p.x*p.y); }
void main(){
  vec2 frag=gl_FragCoord.xy; float y=1.0-frag.y/uResolution.y; float u=frag.x/uResolution.x; float X=(frag.x-uResolution.x*0.5)/uResolution.y; float t=uTime;
  float reach=uPointer.z*exp(-pow((X-uPointer.x)/0.38,2.0)); vec3 glow=vec3(0.0); float cover=0.0;
  for(int k=0;k<3;k++){ if(k>=uLayers) break; float layer=float(k); float seed=layer*13.7; float pace=t*(1.0-layer*0.18);
    float warp=snoise(vec2(X*0.45*uScale+pace*0.02+seed,pace*0.05+seed));
    float wave=snoise(vec2(X*0.75*uScale+warp*0.35-pace*0.03+seed,pace*0.07-seed))*0.72+snoise(vec2(X*1.6*uScale+warp*0.5+pace*0.04-seed,pace*0.1+seed*0.5))*0.28;
    float hem=uHeight+layer*0.07+wave*0.15*uAmplitude; hem+=reach*0.08*(layer<0.5?1.0:0.4); hem=mix(-0.25,hem,uReveal);
    float soft=(0.04+uBlend*0.16)*(1.0+layer*0.9); float rise=hem-y; float low=-soft-uGlow*0.14; float high=0.26+soft*0.6;
    float body=pow(smootherstep(low,high,rise),1.5+uGlow*0.6);
    float lobes=0.86+0.14*snoise(vec2(X*0.9*uScale-pace*0.025+seed,y*0.3+pace*0.04));
    float alpha=body*lobes*(layer<0.5?1.0:0.32/layer); alpha=clamp(alpha*(1.0+reach*0.25*smootherstep(0.9,0.0,abs(y-hem))),0.0,1.0);
    vec3 tint=ramp(u+0.05*sin(pace*0.08+layer*2.3)+layer*0.1+max(rise,0.0)*0.05);
    glow=1.0-(1.0-glow)*(1.0-tint*alpha); cover=1.0-(1.0-cover)*(1.0-alpha); }
  float fade=smootherstep(0.0,0.7,uReveal)*uOpacity; float strength=clamp(uBrightness,0.0,2.0);
  glow*=fade*min(strength,1.0); cover*=fade*min(strength,1.0); glow=1.0-pow(1.0-glow,vec3(max(strength,1.0)));
  float dither=(hash(frag)-0.5)/255.0;
  vec3 tint=cover>0.0001?glow/cover:vec3(0.0); cover*=smootherstep(0.0,0.25,cover); float alpha=cover*0.7;
  outColor=vec4(tint*alpha+dither,clamp(alpha+dither,0.0,1.0)); }`;
  const sh = (t, s) => { const o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o); return gl.getShaderParameter(o, gl.COMPILE_STATUS) ? o : null; };
  const vs = sh(gl.VERTEX_SHADER, V), fs = sh(gl.FRAGMENT_SHADER, F); if (!vs || !fs) return;
  const prog = gl.createProgram(); gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.bindAttribLocation(prog, 0, 'aPosition'); gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
  const U = {}; for (let i = 0; i < gl.getProgramParameter(prog, gl.ACTIVE_UNIFORMS); i++) { const inf = gl.getActiveUniform(prog, i); U[inf.name.replace('[0]', '')] = gl.getUniformLocation(prog, inf.name); }
  const vao = gl.createVertexArray(); gl.bindVertexArray(vao); gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW); gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  const oklch = h => { const n = parseInt(h.slice(1), 16); const rgb = [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255].map(c => c <= .04045 ? c / 12.92 : Math.pow((c + .055) / 1.055, 2.4));
    const [r, g, b] = rgb, l = Math.cbrt(.4122214708 * r + .5363325363 * g + .0514459929 * b), m = Math.cbrt(.2119034982 * r + .6806995451 * g + .1073969566 * b), s = Math.cbrt(.0883024619 * r + .2817188376 * g + .6299787005 * b);
    const A = 1.9779984951 * l - 2.428592205 * m + .4505937099 * s, B = .0259040371 * l + .7827717662 * m - .808675766 * s; return [.2104542553 * l + .793617785 * m - .0040720468 * s, Math.hypot(A, B), Math.atan2(B, A)]; };
  let prev = null; const stops = CFG.aurora.map(oklch).map(s => { let h = s[2]; if (prev !== null) { while (h - prev > Math.PI) h -= 2 * Math.PI; while (h - prev < -Math.PI) h += 2 * Math.PI; } prev = h; return [s[0], s[1], h]; });
  const pal = new Float32Array(15); stops.forEach((s, i) => pal.set(s, i * 3));
  const st = { clock: 0, px: 0, reach: 0, reveal: reduce ? 1 : 0 }, ptr = { x: 0, y: 0, inside: false }; let raf = 0, last = 0;
  function render() { gl.viewport(0, 0, canvas.width, canvas.height); gl.clearColor(0,0,0,0); gl.clear(gl.COLOR_BUFFER_BIT); gl.useProgram(prog); gl.bindVertexArray(vao);
    gl.uniform2f(U.uResolution, canvas.width, canvas.height); gl.uniform1f(U.uTime, st.clock); gl.uniform3fv(U.uStops, pal); gl.uniform1i(U.uStopCount, stops.length);
    gl.uniform1f(U.uAmplitude, 1.1); gl.uniform1f(U.uBlend, .65); gl.uniform1f(U.uHeight, .55); gl.uniform1f(U.uScale, .9); gl.uniform1f(U.uGlow, .7);
    gl.uniform1f(U.uBrightness, 1); gl.uniform1i(U.uLayers, 2); gl.uniform3f(U.uPointer, st.px, 0, st.reach);
    gl.uniform1f(U.uReveal, 1 - Math.pow(1 - st.reveal, 3)); gl.uniform1f(U.uOpacity, .85); gl.drawArrays(gl.TRIANGLES, 0, 3); }
  function frame(now) { raf = 0; if (document.hidden) return; const dt = last ? Math.min(.05, (now - last) / 1000) : 1 / 60; last = now;
    if (!reduce) st.clock += dt * .55;
    const rect = container.getBoundingClientRect(), on = ptr.inside && !reduce;
    if (on) st.px += ((ptr.x - rect.width / 2) / rect.height - st.px) * (1 - Math.exp(-dt / .6));
    st.reach += ((on ? 1 : 0) - st.reach) * (1 - Math.exp(-dt / (on ? .9 : 1.4)));
    if (st.reveal < 1) st.reveal = Math.min(1, st.reveal + dt / 2.4);
    render(); if (!reduce || st.reveal < 1) raf = requestAnimationFrame(frame); }
  const wake = () => { if (!raf) raf = requestAnimationFrame(frame); };
  function resize() { const r = Math.min(devicePixelRatio || 1, 2); canvas.width = Math.round(container.clientWidth * r); canvas.height = Math.round(container.clientHeight * r); render(); wake(); }
  addEventListener('pointermove', e => { const b = container.getBoundingClientRect(); ptr.x = e.clientX - b.left; ptr.y = e.clientY - b.top; ptr.inside = ptr.y >= 0 && ptr.y <= b.height + 120; wake(); }, { passive: true });
  document.documentElement.addEventListener('pointerleave', () => { ptr.inside = false; });
  document.addEventListener('visibilitychange', () => { last = 0; wake(); });
  new ResizeObserver(resize).observe(container); resize();
})();

/* ---------- Read aloud + sound reminders ---------- */
const live = document.getElementById('live');
document.getElementById('speak').addEventListener('click', () => {
  if (!('speechSynthesis' in window)) { live.textContent = 'Sorry, this browser cannot read aloud.'; return; }
  speechSynthesis.cancel(); speechSynthesis.speak(say(CFG.speech));
});
/* A softer, friendlier voice: prefer well-known female English voices where the device has one. */
const PREFERRED = ['Samantha', 'Google UK English Female', 'Microsoft Aria', 'Microsoft Jenny', 'Microsoft Zira', 'Karen',
                   'Moira', 'Tessa', 'Serena', 'Fiona', 'Veena', 'Google US English'];
function pickVoice() {
  const voices = speechSynthesis.getVoices().filter(v => v.lang && v.lang.startsWith('en'));
  for (const name of PREFERRED) { const v = voices.find(x => x.name.includes(name)); if (v) return v; }
  return voices.find(v => /female|woman/i.test(v.name)) || null;
}
if ('speechSynthesis' in window) speechSynthesis.getVoices();
function say(text) { const u = new SpeechSynthesisUtterance(text); const v = pickVoice(); if (v) u.voice = v;
  u.rate = .92; u.pitch = 1.08; return u; }
let actx = null, timers = [];
function chime(){ if(!actx) return; const t=actx.currentTime;
  [660,880,660].forEach((f,i)=>{const o=actx.createOscillator(),g=actx.createGain();o.type='sine';o.frequency.value=f;
    g.gain.setValueAtTime(0,t+i*.35);g.gain.linearRampToValueAtTime(.25,t+i*.35+.04);g.gain.exponentialRampToValueAtTime(.001,t+i*.35+.32);
    o.connect(g).connect(actx.destination);o.start(t+i*.35);o.stop(t+i*.35+.34);}); }
const beepBtn = document.getElementById('beep');
beepBtn.addEventListener('click', () => {
  const on = beepBtn.getAttribute('aria-pressed') !== 'true';
  beepBtn.setAttribute('aria-pressed', on); beepBtn.querySelector('span').textContent = on ? 'Reminders on' : 'Reminders off';
  timers.forEach(clearTimeout); timers = []; if (!on) return;
  actx = actx || new (window.AudioContext || window.webkitAudioContext)(); actx.resume(); chime();
  CFG.alarms.forEach(a => { const wait = a.at - Date.now(); if (wait > 0 && wait < 864e5)
    timers.push(setTimeout(() => { chime(); live.textContent = a.say || ('Time for ' + a.label);
      if ('speechSynthesis' in window) speechSynthesis.speak(say(a.say || ('It is time for ' + a.label))); }, wait)); });
  live.textContent = 'Reminders are on while this page stays open.';
});
</script>
"""


def hero(date_text, greeting_html, stats, speech, alarms, reduce_motion=False, height=430):
    """Light header: Aurora, TextPressure title, one-line greeting and rolling stats.

    `stats` is a list of {"text": "94%", "label": "this week", "tone": "taken|left|missed|plain"}.
    """
    cfg = {"title": "MedTimer", "stats": stats, "speech": speech, "alarms": alarms,
           "reduceMotion": reduce_motion, "aurora": ["#A9DCC4", "#8DB8E0", "#B7C6F2", "#9FD6C7"]}
    body = (_HERO.replace("__CONFIG__", _json(cfg)).replace("__DATE__", _esc(date_text))
            .replace("__GREETING__", greeting_html))
    components.html(_page(body), height=height)


# ------------------------------------------------------------ gauge ---------

_GAUGE = r"""
<style>
 body{display:flex;flex-direction:column;align-items:center;gap:12px;padding-top:6px}
 .cap{width:54px;height:16px;border-radius:6px 6px 3px 3px;background:linear-gradient(180deg,#3B5249,var(--ink));margin-bottom:-10px;position:relative;z-index:2}
 .slosh{position:relative;width:__W__px;height:__H__px;border-radius:30px;overflow:clip;isolation:isolate;
        background:linear-gradient(180deg,rgba(255,255,255,.75),rgba(255,255,255,.35));
        box-shadow:inset 0 0 0 1.5px rgba(255,255,255,.95),inset 0 2px 10px rgba(28,58,48,.08),0 18px 34px -14px rgba(28,58,48,.3);font-family:var(--display);font-size:34px;font-weight:700;font-variation-settings:'wdth' 110;
        font-variant-numeric:tabular-nums;line-height:1;user-select:none}
 .v{position:absolute;inset:0;display:grid;place-items:center;color:var(--ink);pointer-events:none}
 .liq{position:absolute;inset:0;background:__LIQ__;clip-path:polygon(0 100%,100% 100%,100% 100%,0 100%)}
 .liq .v{color:#fff}
 .slosh::after{content:'';position:absolute;top:8px;bottom:8px;left:12px;width:14px;border-radius:999px;pointer-events:none;
   background:linear-gradient(180deg,rgba(255,255,255,.85),rgba(255,255,255,.1));opacity:.8}
 .ticks{position:absolute;right:0;bottom:0;width:20%;height:100%;background-image:linear-gradient(to top,var(--rule) 0 2px,transparent 2px);
        background-size:100% 25%;background-repeat:repeat-y;background-position:bottom;pointer-events:none}
 .msg{font-size:17px;color:var(--ink2);margin:0;text-align:center;max-width:24ch;line-height:1.4}
</style>
<div class="cap" aria-hidden="true"></div>
<div class="slosh" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="__VAL__" aria-label="Weekly adherence __VAL__ percent">
  <span class="v" aria-hidden="true">__VAL__%</span>
  <div class="liq" id="liq" aria-hidden="true"><span class="v">__VAL__%</span></div>
  <div class="ticks" aria-hidden="true"></div>
</div>
<p class="msg">__HINT__</p>
<script>
/* SloshGauge (React Bits): spring-driven liquid that leans with its speed */
const L=__VAL__, W=__W__, reduce=matchMedia('(prefers-reduced-motion: reduce)').matches || __REDUCE__;
const liq=document.getElementById('liq'), H=1/120, s={x:0,v:0,last:0};
const vis=.15,k=1224-1044*vis,zeta=reduce?1:.26-.17*vis,c=2*zeta*Math.sqrt(k),give=reduce?0:.42;
function paint(){const th=reduce?0:Math.max(-30,Math.min(30,.45*s.v*.07));const lean=Math.tan(th*Math.PI/180)*W/2;const top=100-s.x;
  liq.style.clipPath=`polygon(0 calc(${top}% + ${lean}px),100% calc(${top}% - ${lean}px),100% 100%,0 100%)`;}
function tick(now){const dt=s.last?Math.min((now-s.last)/1000,.05):H;s.last=now;
  for(let n=Math.ceil(dt/H),h=dt/n;n>0;n--){s.v=s.v*Math.exp(-c*h)+k*(L-s.x)*h;s.x+=s.v*h;if(s.x>100){s.x=100;s.v=-s.v*give}else if(s.x<0){s.x=0;s.v=-s.v*give}}
  if(Math.abs(L-s.x)<.05&&Math.abs(s.v)<2){s.x=L;s.v=0;paint();return;} paint(); requestAnimationFrame(tick);}
if(reduce){s.x=L;paint();}else setTimeout(()=>requestAnimationFrame(tick),350);
</script>
"""


def slosh_gauge(value, hint, reduce_motion=False):
    """Weekly adherence shown as liquid filling a medicine bottle."""
    value = max(0, min(100, int(round(value))))
    liquid = ("linear-gradient(180deg,#4F8D70,var(--accent))" if value >= 80
              else "linear-gradient(180deg,#B98A3A,var(--amber))" if value >= 50
              else "linear-gradient(180deg,#C2665B,var(--brick))")
    body = (_GAUGE.replace("__VAL__", str(value)).replace("__HINT__", _esc(hint)).replace("__W__", "112")
            .replace("__H__", "200").replace("__LIQ__", liquid).replace("__REDUCE__", "true" if reduce_motion else "false"))
    components.html(_page(body), height=290)


# ----------------------------------------------------------- folder ---------

_FOLDER = r"""
<style>
 body{height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;overflow:hidden}
 .ff{--w:210px;--h:140px;--r:16px;--tab:14px;--open:520ms;--close:312ms;--stagger:60ms;--n:__N__;--spring:cubic-bezier(.34,1.57,.64,1);
     position:relative;display:inline-block;width:var(--w);padding-top:var(--tab);font-size:16px;font-weight:700;line-height:1}
 .folder{position:relative;width:var(--w);height:var(--h)}
 .back{position:absolute;inset:0;border-radius:var(--r);background:var(--accent);transform:perspective(600px) rotateX(8deg);transform-origin:50% 100%}
 .back::before{content:'';position:absolute;top:calc(-1*var(--tab));left:0;width:42%;height:calc(var(--tab) + var(--r));border-radius:var(--r) var(--r) 0 0;background:inherit}
 .paper{position:absolute;top:10%;left:8%;right:8%;height:50%;z-index:1;border-radius:6px;background:var(--card);opacity:0;transform:translateY(10px);transition:transform var(--close) var(--ease),opacity var(--close) ease}
 .front{position:absolute;left:0;right:0;bottom:0;z-index:2;height:76%;display:flex;flex-direction:column;justify-content:flex-end;gap:6px;padding:16px 18px;
        border-radius:var(--r);background:linear-gradient(180deg,#4F8D70,#3B7A5E 60%);color:#fff;box-shadow:0 -10px 24px rgba(30,43,38,.18);
        transform:perspective(600px) rotateX(-16deg);transform-origin:50% 100%;transition:transform var(--open) var(--ease)}
 .front small{font-size:14px;opacity:.85;font-weight:400}
 .trig{position:absolute;left:0;right:0;bottom:0;z-index:3;height:76%;border:0;border-radius:var(--r);background:transparent;cursor:pointer}
 .ff[data-open] .front{transform:perspective(600px) rotateX(-34deg)}
 .ff[data-open] .paper{opacity:1;transform:none;transition:transform var(--open) var(--ease),opacity .2s ease}
 .items{position:absolute;top:var(--tab);left:50%;width:0;height:0;z-index:1}
 .item{position:absolute;top:0;left:50%;margin:0;padding:0 16px;height:40px;border:0;border-radius:20px;background:var(--card);color:var(--ink);font-size:16px;font-weight:700;white-space:nowrap;
       box-shadow:0 4px 14px rgba(30,43,38,.14);cursor:pointer;opacity:0;transform:translate(-50%,44px) scale(.6);pointer-events:none;
       transition:transform var(--close) var(--ease) calc((var(--n) - 1 - var(--i))*var(--stagger)*.5),opacity .16s ease calc((var(--n) - 1 - var(--i))*var(--stagger)*.5 + 140ms),scale .16s var(--ease)}
 .ff[data-open] .item{opacity:1;transform:translate(calc(-50% + var(--x)),var(--y)) rotate(var(--rr)) scale(1);pointer-events:auto;
       transition:transform var(--open) var(--spring) calc(var(--i)*var(--stagger)),opacity .16s ease calc(var(--i)*var(--stagger)),scale .16s var(--ease)}
 .ff[data-live] .item{cursor:grab;transition:scale .16s var(--ease)}
 .item:hover{scale:1.05}
 .tip{order:2;min-height:56px;max-width:520px;margin:14px 12px 2px;font-size:18px;line-height:1.45;text-align:center;color:var(--ink2)}
 @media (prefers-reduced-motion: reduce){.front,.paper,.item{transition:opacity .2s ease!important}}
</style>
<p class="tip" id="tip" role="status">Tap the folder.</p>
<div class="ff" id="ff">
  <div class="items" id="items"></div>
  <div class="folder">
    <span class="back"></span><span class="paper"></span>
    <span class="front"><span>Healthy habits</span><small>__N__ tips</small></span>
    <button class="trig" id="trig" type="button" aria-expanded="false" aria-label="Open the folder of health tips"></button>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/matter-js/0.19.0/matter.min.js"></script>
<script>
/* FolderFloat (React Bits): pills fly out of a folder, then float in a zero-gravity matter-js world */
const TIPS=__TIPS__, ff=document.getElementById('ff'), wrap=document.getElementById('items'), tipBox=document.getElementById('tip');
const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
const SPREAD=Math.min(260,innerWidth/2-16), LIFT=30, ROW=54, GAP=10;
const jitter=i=>{const x=Math.sin(i*12.9898+4.1414)*43758.5453;return x-Math.floor(x);};
let dragMoved=false;
const pills=TIPS.map((t,i)=>{const b=document.createElement('button');b.type='button';b.className='item';b.textContent=t.short;b.style.setProperty('--i',i);
  b.tabIndex=-1;b.addEventListener('click',()=>{if(!dragMoved)show(i);});wrap.appendChild(b);return b;});
function layout(){const rows=[];let row=[],w=0;pills.forEach((p,i)=>{const pw=p.offsetWidth;if(row.length&&w+GAP+pw>SPREAD*2){rows.push({row,w});row=[];w=0;}row.push({i,pw});w+=(row.length>1?GAP:0)+pw;});
  if(row.length)rows.push({row,w});const pos=[];rows.forEach((r,ri)=>{let x=-r.w/2;const shift=(ri%2?1:-1)*12;r.row.forEach(({i,pw})=>{const j=jitter(i);
  pos[i]={x:x+pw/2+shift+(j-.5)*6,y:-LIFT-ri*ROW-j*6,r:7*(j*2-1)};x+=pw+GAP;});});return pos;}
let pos=[];
function place(){pos=layout();pills.forEach((p,i)=>{p.style.setProperty('--x',pos[i].x.toFixed(1)+'px');p.style.setProperty('--y',pos[i].y.toFixed(1)+'px');p.style.setProperty('--rr',pos[i].r.toFixed(2)+'deg');});}
document.fonts.ready.then(place);place();
function show(i){tipBox.textContent=TIPS[i].full;tipBox.style.color='var(--ink)';pills[i].animate([{scale:1},{scale:1.1},{scale:1}],{duration:320});}
let open=false,eng=null,bodies=[],raf=0,liveT=0,drag=null;
function setOpen(v){open=v;ff.toggleAttribute('data-open',v);document.getElementById('trig').setAttribute('aria-expanded',v);
  pills.forEach(p=>p.tabIndex=v?0:-1);clearTimeout(liveT);
  if(v){tipBox.textContent='Pick a tip. You can drag them too.';if(!reduce&&window.Matter)liveT=setTimeout(start,520+TIPS.length*60+80);}else{stop();tipBox.textContent='Tap the folder.';tipBox.style.color='';}}
document.getElementById('trig').addEventListener('click',()=>setOpen(!open));
addEventListener('keydown',e=>{if(e.key==='Escape'&&open)setOpen(false);});
function stop(){cancelAnimationFrame(raf);raf=0;if(eng){Matter.Composite.clear(eng.world,false,true);Matter.Engine.clear(eng);eng=null;}bodies=[];ff.removeAttribute('data-live');}
function start(){if(eng||!open)return;const{Bodies,Body,Composite,Engine}=Matter;eng=Engine.create({gravity:{x:0,y:0}});
  const sizes=pills.map(p=>({w:p.offsetWidth,h:p.offsetHeight}));const ys=pos.map(p=>p.y);
  const z={l:-SPREAD-8,r:SPREAD+8,t:Math.min(...ys)-8,b:-LIFT+Math.max(...sizes.map(s=>s.h))};
  bodies=pills.map((p,i)=>{const b=Bodies.rectangle(pos[i].x,pos[i].y+sizes[i].h/2,sizes[i].w,sizes[i].h,{chamfer:{radius:16},restitution:.55,friction:0,frictionAir:.08,inertia:Infinity});b.plugin={ph:jitter(i)*6.28};return b;});
  const T=80;Composite.add(eng.world,[...bodies,Bodies.rectangle((z.l+z.r)/2,z.t-T/2,z.r-z.l+2*T,T,{isStatic:true}),Bodies.rectangle((z.l+z.r)/2,z.b+T/2,z.r-z.l+2*T,T,{isStatic:true}),
    Bodies.rectangle(z.l-T/2,(z.t+z.b)/2,T,z.b-z.t+2*T,{isStatic:true}),Bodies.rectangle(z.r+T/2,(z.t+z.b)/2,T,z.b-z.t+2*T,{isStatic:true})]);
  ff.setAttribute('data-live','');const t0=performance.now();let last=0;
  const tick=now=>{if(!eng)return;const dt=last?Math.min(32,now-last):16;last=now;const t=(now-t0)/1000,k=.5*.00005*Math.min(1,t/2);
    bodies.forEach((b,i)=>{if(drag&&drag.i===i)return;Body.applyForce(b,b.position,{x:Math.sin(t*.9+b.plugin.ph)*k*b.mass,y:Math.cos(t*1.3+b.plugin.ph*1.7)*k*b.mass});});
    Engine.update(eng,dt);bodies.forEach((b,i)=>{pills[i].style.setProperty('--x',b.position.x.toFixed(1)+'px');pills[i].style.setProperty('--y',(b.position.y-sizes[i].h/2).toFixed(1)+'px');});
    raf=requestAnimationFrame(tick);};raf=requestAnimationFrame(tick);
  pills.forEach((p,i)=>{p.onpointerdown=e=>{if(!eng)return;const a=wrap.getBoundingClientRect(),b=bodies[i];drag={i,id:e.pointerId,dx:b.position.x-(e.clientX-a.left),dy:b.position.y-(e.clientY-a.top),sx:e.clientX,sy:e.clientY};dragMoved=false;p.setPointerCapture(e.pointerId);};
    p.onpointermove=e=>{if(!drag||drag.i!==i||!eng)return;if(Math.hypot(e.clientX-drag.sx,e.clientY-drag.sy)>=4)dragMoved=true;if(!dragMoved)return;
      const a=wrap.getBoundingClientRect(),b=bodies[i],x=Math.min(z.r-sizes[i].w/2,Math.max(z.l+sizes[i].w/2,e.clientX-a.left+drag.dx)),y=Math.min(z.b-sizes[i].h/2,Math.max(z.t+sizes[i].h/2,e.clientY-a.top+drag.dy));
      Matter.Body.setVelocity(b,{x:(x-b.position.x)*.6,y:(y-b.position.y)*.6});Matter.Body.setPosition(b,{x,y});};
    p.onpointerup=p.onpointercancel=()=>{drag=null;setTimeout(()=>dragMoved=false,0);};});
}
</script>
"""


def folder_float(tips):
    """Folder of health tips. `tips` is a list of {"short": ..., "full": ...}."""
    body = _FOLDER.replace("__TIPS__", _json(tips)).replace("__N__", str(len(tips)))
    components.html(_page(body), height=520)


# ----------------------------------------------------------- turtle ---------

_TURTLE = r"""
<style>
 body{display:flex;flex-direction:column;align-items:center}
 .stage{width:100%;max-width:300px;aspect-ratio:1/1;display:grid;place-items:center;position:relative}
 svg{width:100%;height:100%}
 .s{stroke-dasharray:1;stroke-dashoffset:1;animation:draw var(--d) ease-out forwards;animation-delay:var(--t)}
 .f,.w{opacity:0;animation:fill .45s ease forwards;animation-delay:var(--t)}
 .turtle{opacity:0;animation:fill .2s ease forwards}
 @keyframes draw{to{stroke-dashoffset:0}} @keyframes fill{to{opacity:1}}
 .again{margin-top:4px;border:0;background:none;color:var(--accent);font-size:16px;font-weight:700;cursor:pointer;min-height:44px;padding:0 10px;
        text-decoration:underline;text-underline-offset:4px;text-decoration-thickness:1px}
 @media (prefers-reduced-motion: reduce){.s,.f,.w{animation:none;stroke-dashoffset:0;opacity:1}}
</style>
<div class="stage" role="img" aria-label="__ALT__">__SVG__</div>
<button class="again" type="button" onclick="replay()">Draw it again</button>
<script>
function replay(){const st=document.querySelector('.stage');const h=st.innerHTML;st.innerHTML='';void st.offsetWidth;st.innerHTML=h;follow();}
/* A little turtle follows the pen along each stroke, like Python's turtle window */
function follow(){const svg=document.querySelector('svg'),head=svg.querySelector('.turtle');if(!head)return;
  const strokes=[...svg.querySelectorAll('.s')];if(matchMedia('(prefers-reduced-motion: reduce)').matches){head.remove();return;}
  const t0=performance.now();
  function step(now){const t=(now-t0)/1000;let active=null,f=1;
    for(const s of strokes){const st=parseFloat(s.style.getPropertyValue('--t')),d=parseFloat(s.style.getPropertyValue('--d'));
      if(t>=st&&t<=st+d){active=s;f=(t-st)/d;break;} if(t>st+d)active=s;}
    if(active){const L=active.getTotalLength(),p=active.getPointAtLength(Math.min(1,f)*L),q=active.getPointAtLength(Math.min(L,Math.min(1,f)*L+1));
      head.setAttribute('transform',`translate(${p.x} ${p.y}) rotate(${Math.atan2(q.y-p.y,q.x-p.x)*180/Math.PI})`);}
    if(t<__TOTAL__+0.3)requestAnimationFrame(step);else head.style.opacity=0;}
  requestAnimationFrame(step);}
follow();
</script>
"""


def turtle_player(svg, total_seconds, alt):
    """Play the turtle drawing stroke by stroke."""
    body = _TURTLE.replace("__SVG__", svg).replace("__ALT__", _esc(alt)).replace("__TOTAL__", f"{total_seconds:.2f}")
    components.html(_page(body), height=360)


def _esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# =============================================================================
# 5. STREAMLIT INTERFACE
# =============================================================================

PAGES = ["Today", "My medicines", "Common illnesses", "Progress", "Wellbeing", "Settings"]

ICONS = {  # Lucide-style stroke icons (consistent 2px stroke, no emoji)
    "spark": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "flame": '<path d="M12 22c4 0 7-3 7-7 0-4-3-6-4-9-1 3-3 4-4 4 0-2-1-4-3-6-1 4-3 7-3 11 0 4 3 7 7 7z"/>',
    "trophy": '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>',
    "heart": '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8z"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "leaf": '<path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/>',
}


def icon(name, color="currentColor", size=26):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def inject_css():
    """One theme for everything: sage paper, deep green ink, one accent."""
    T = THEME
    base = 18
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&family=Roboto+Flex:opsz,wdth,wght@8..144,25..151,100..1000&display=swap');
:root {{ --ink:{T['ink']}; --ink2:{T['ink2']}; --rule:{T['rule']}; --paper:{T['paper']}; --paper2:{T['paper2']}; --card:{T['card']};
        --accent:{T['accent']}; --accentSoft:{T['accentSoft']}; --amber:{T['amber']}; --brick:{T['brick']};
        --display:'Roboto Flex','Helvetica Neue',Arial,sans-serif; --text:'Atkinson Hyperlegible',system-ui,sans-serif; }}
html, body, .stApp, .stMarkdown, button, input, textarea, select, label {{ font-family:var(--text) !important; }}
/* Liquid glass: a soft blue-and-mint backdrop for the frosted panels to sit on */
.stApp {{ color:var(--ink); background:
  radial-gradient(900px 520px at 8% -6%, #CFE4F4 0%, transparent 62%),
  radial-gradient(800px 560px at 96% 4%, #D4EEDF 0%, transparent 58%),
  radial-gradient(1000px 700px at 60% 112%, #DCE6F6 0%, transparent 60%),
  linear-gradient(180deg, #F2F6F5, #EAF0EE) fixed; background-attachment:fixed; }}
:root {{ --glass:linear-gradient(180deg, rgba(255,255,255,.66), rgba(255,255,255,.40));
        --glass-edge:rgba(255,255,255,.75);
        --glass-shadow:inset 0 1px 0 rgba(255,255,255,.95), inset 0 -1px 0 rgba(255,255,255,.35),
                       0 18px 40px -12px rgba(28,58,48,.18), 0 2px 8px rgba(28,58,48,.06); }}
[class*="st-key-glass"] {{ position:relative; background:var(--glass); border:1px solid var(--glass-edge); border-radius:30px;
  padding:22px 26px 18px !important; margin-bottom:18px; box-shadow:var(--glass-shadow);
  -webkit-backdrop-filter:blur(24px) saturate(180%); backdrop-filter:blur(24px) saturate(180%); overflow:hidden; }}
[class*="st-key-glass"]::before {{ content:''; position:absolute; inset:0; border-radius:inherit; pointer-events:none;
  background:radial-gradient(120% 60% at 15% -10%, rgba(255,255,255,.55), transparent 55%),
             linear-gradient(115deg, transparent 60%, rgba(255,255,255,.18) 75%, transparent 85%); }}
[class*="st-key-glass"] > * {{ position:relative; }}
.st-key-glass-add {{ padding:6px 18px !important; border-radius:26px; }}
[data-testid="stHeader"] {{ background:transparent; }}
[data-testid="stAppDeployButton"], .stDeployButton, [data-testid="stMainMenu"] {{ display:none !important; }}
.block-container {{ padding-top:1.6rem; max-width:1180px; }}
.stMarkdown p, .stMarkdown li, label, [data-testid="stWidgetLabel"] p {{ font-size:{base}px !important; line-height:1.55; color:var(--ink); }}
h1, h2, h3 {{ font-family:var(--display) !important; color:var(--ink) !important; font-variation-settings:'wdth' 112; letter-spacing:-.02em; }}
h2 {{ font-size:{base + 16}px !important; font-weight:750 !important; line-height:1.05 !important; padding:0 0 .2rem !important; }}
h3 {{ font-size:{base + 4}px !important; font-weight:700 !important; }}
[data-testid="stHeadingWithActionElements"] a {{ display:none !important; }}
.eyebrow {{ font-size:14px !important; letter-spacing:.14em; text-transform:uppercase; color:var(--ink2) !important; font-weight:700; margin:0 0 .3rem; }}
.lead {{ font-size:{base}px; color:var(--ink2); margin:-.2rem 0 1rem; }}
/* Buttons: pills */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
  min-height:48px; border-radius:999px; padding:0 22px; color:var(--ink);
  background:linear-gradient(180deg, rgba(255,255,255,.85), rgba(255,255,255,.55)); border:1px solid rgba(255,255,255,.9);
  box-shadow:inset 0 1px 0 #fff, 0 6px 16px -6px rgba(28,58,48,.25), 0 0 0 1px rgba(28,58,48,.06);
  -webkit-backdrop-filter:blur(14px) saturate(170%); backdrop-filter:blur(14px) saturate(170%);
  transition:transform .15s ease, box-shadow .2s ease; }}
[data-testid="stDownloadButton"] button {{ min-height:48px; border-radius:999px; padding:0 22px; }}
.stButton button p, .stFormSubmitButton button p, .stDownloadButton button p, [data-testid="stDownloadButton"] button p {{ font-size:{base - 1}px !important; font-weight:700; }}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"], .stDownloadButton > button[kind="primary"],
button[data-testid="stBaseButton-primary"], [data-testid="stDownloadButton"] button[kind="primary"] {{
  color:#fff; border-color:rgba(255,255,255,.35); background:linear-gradient(180deg, #4A9877 0%, #2F6B52 100%);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.45), inset 0 -2px 6px rgba(0,0,0,.12), 0 10px 22px -8px rgba(47,107,82,.55); }}
.stButton > button:hover, .stDownloadButton > button:hover {{ transform:translateY(-1px); }}
.stButton > button:active {{ transform:scale(.97); }}
.stButton > button:disabled {{ background:var(--accentSoft); border-color:transparent; color:var(--accent); opacity:1; }}
button:focus-visible, input:focus-visible {{ outline:2px solid var(--accent) !important; outline-offset:3px; }}
/* Inputs, forms and expanders blend into the paper */
[data-testid="stForm"] {{ border:0; border-top:1px solid var(--rule); border-radius:0; padding:1.2rem 0 0; }}
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="base-input"] {{ background:rgba(255,255,255,.7) !important;
  border-radius:14px !important; border-color:rgba(255,255,255,.9) !important; box-shadow:inset 0 1px 2px rgba(28,58,48,.08); }}
[data-baseweb="input"] input, [data-baseweb="base-input"] input, [data-baseweb="select"] input, textarea {{ background:transparent !important; }}
[data-baseweb="input"] > div, [data-baseweb="base-input"] > div, [data-baseweb="select"] > div > div {{ background:transparent !important; }}
[data-testid="stExpander"] details {{ border:0; border-radius:0; background:transparent; }}
[data-testid="stExpander"] summary {{ padding:10px 4px; }}
[data-testid="stExpander"] summary p {{ font-family:var(--display) !important; font-weight:700; font-size:{base + 2}px !important; }}
.st-key-glass-meds [data-testid="stExpander"] summary p {{ font-family:var(--text) !important; font-weight:400; font-size:{base - 1}px !important; }}
[data-testid="stSegmentedControl"] button {{ border-radius:999px !important; }}
[data-testid="stExpander"] summary p {{ font-size:{base}px !important; }}
/* Sidebar holds the LineSidebar navigation */
[data-testid="stSidebar"] {{ background:linear-gradient(180deg, rgba(255,255,255,.55), rgba(255,255,255,.32)) !important;
  -webkit-backdrop-filter:blur(30px) saturate(180%); backdrop-filter:blur(30px) saturate(180%);
  border-right:1px solid rgba(255,255,255,.8); box-shadow:inset -1px 0 0 rgba(28,58,48,.06), 12px 0 40px -20px rgba(28,58,48,.25); }}
[data-testid="stSidebar"] .block-container, [data-testid="stSidebarUserContent"] {{ padding-top:1rem; }}
.side-brand {{ font-family:var(--display); font-size:26px; font-weight:800; font-variation-settings:'wdth' 125; letter-spacing:-.02em; margin:0 0 .2rem; }}
.side-brand span {{ color:var(--accent); }}
/* Level card, quests, illnesses */
.lvl {{ padding:4px 0 10px; margin-bottom:6px; }}
.lvl .top {{ display:flex; align-items:baseline; justify-content:space-between; gap:10px; }}
.lvl .name {{ font-family:var(--display); font-size:30px; font-weight:750; font-variation-settings:'wdth' 115; line-height:1; }}
.lvl .num {{ font-size:15px; color:var(--ink2); font-weight:700; }}
.lvl .bar {{ height:12px; border-radius:999px; background:rgba(255,255,255,.6); margin:12px 0 8px; overflow:hidden; box-shadow:inset 0 0 0 1px var(--rule); }}
.lvl .bar span {{ display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,#6FA587,var(--accent)); animation:grow 1.1s cubic-bezier(.23,1,.32,1) both; transform-origin:left; }}
@keyframes grow {{ from {{ transform:scaleX(0); }} }}
.lvl small {{ font-size:15px; color:var(--ink2); }}
.quest {{ display:flex; align-items:center; gap:12px; padding:10px 0; border-bottom:1px solid var(--rule); font-size:{base - 1}px; }}
.quest .dot {{ flex:none; width:26px; height:26px; border-radius:50%; box-shadow:inset 0 0 0 2px var(--rule); display:grid; place-items:center; }}
.quest.done .dot {{ background:var(--accent); box-shadow:none; }}
.quest.done .t {{ color:var(--ink2); text-decoration:line-through; text-decoration-thickness:1px; }}
.quest .t {{ flex:1; }} .quest .xp {{ font-weight:700; color:var(--accent); font-size:15px; white-space:nowrap; }}
.cond {{ padding:16px 0 6px; border-top:1px solid var(--rule); }}
.cond b {{ font-family:var(--display); font-size:22px; font-variation-settings:'wdth' 110; }}
.cond p {{ color:var(--ink2) !important; margin:.1rem 0 .2rem !important; font-size:16px !important; }}
.cmed {{ font-size:{base}px; padding-top:6px; }} .cmed span {{ color:var(--ink2); font-size:16px; }}
.note {{ font-size:16px; padding:12px 16px; border-radius:14px; background:var(--card); border:1px solid var(--rule); margin:.2rem 0 1rem; }}
.empty-cta {{ font-size:20px; max-width:34ch; margin:.4rem 0 1.2rem; color:var(--ink2); }}
/* Badges, quote, score, medicine list */
.mt-badges {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); border-top:1px solid var(--rule); }}
.mt-badge {{ padding:18px 14px 16px 0; display:flex; gap:12px; align-items:flex-start; border-bottom:1px solid var(--rule); }}
.mt-badge b {{ display:block; font-size:{base - 1}px; }}
.mt-badge small {{ font-size:{base - 4}px; color:var(--ink2); }}
.mt-badge.off {{ opacity:.55; }}
.mt-badge .ring {{ flex:none; width:44px; height:44px; border-radius:50%; display:grid; place-items:center; background:var(--accentSoft); }}
.mt-badge.off .ring {{ background:var(--paper2); }}
.stMarkdown p.mt-quote {{ font-family:var(--display) !important; font-size:clamp(26px,3.2vw,40px) !important; color:var(--ink); line-height:1.15;
             font-weight:600; font-variation-settings:'wdth' 100; letter-spacing:-.02em; max-width:28ch; margin:.4rem 0 .2rem; }}
.mt-score {{ white-space:nowrap; font-family:var(--display); font-size:clamp(46px,5.4vw,72px); font-weight:750; font-variation-settings:'wdth' 115; line-height:1; color:var(--accent); }}
.mt-med {{ display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 14px; padding:14px 0 4px; border-top:1px solid var(--rule); }}
.mt-med b {{ font-size:{base + 3}px; }} .mt-med span {{ color:var(--ink2); }}
.mt-pill {{ display:inline-block; padding:2px 10px; border-radius:999px; background:linear-gradient(180deg,rgba(255,255,255,.9),rgba(255,255,255,.55)); border:1px solid rgba(255,255,255,.95); box-shadow:0 3px 8px -5px rgba(28,58,48,.35); font-size:{base - 3}px; color:var(--ink); }}
.mt-pill.soon {{ background:var(--paper2); border-color:transparent; color:var(--amber); font-weight:700; }}
.mt-pill.since {{ border-color:transparent; background:transparent; color:var(--ink2); padding-left:0; }}
.mt-pill.food {{ background:var(--accentSoft); border-color:transparent; color:var(--accent); font-weight:700; }}
.mt-foot {{ font-size:14px !important; color:var(--ink2) !important; margin-top:2.5rem; }}
/* ===== Liquid glass, round two ===== */
/* Drifting colour fields behind everything, so the glass has something to bend */
.stApp {{ background:
  radial-gradient(38% 42% at 12% 8%, rgba(120,186,236,.75), transparent 70%),
  radial-gradient(34% 40% at 88% 10%, rgba(130,214,172,.75), transparent 70%),
  radial-gradient(40% 46% at 70% 60%, rgba(176,184,246,.6), transparent 70%),
  radial-gradient(30% 34% at 25% 70%, rgba(248,206,166,.5), transparent 70%),
  linear-gradient(180deg, #F3F7F6, #EAF0EF) !important;
  background-size:140% 140%, 140% 140%, 140% 140%, 140% 140%, 100% 100% !important;
  background-attachment:fixed !important; animation:drift 28s ease-in-out infinite alternate; }}
@keyframes drift {{
  from {{ background-position:0% 0%, 100% 0%, 60% 100%, 0% 100%, 0 0; }}
  to   {{ background-position:18% 12%, 82% 16%, 40% 84%, 14% 86%, 0 0; }} }}
/* Floating panels: a rim of light that fades round the edge, plus a soft lift on hover */
[class*="st-key-glass"] {{ border:1.5px solid transparent !important;
  background:linear-gradient(180deg, rgba(255,255,255,.34), rgba(255,255,255,.10)) padding-box,
             linear-gradient(140deg, rgba(255,255,255,1), rgba(255,255,255,.30) 32%, rgba(255,255,255,.06) 58%, rgba(255,255,255,.9)) border-box !important;
  -webkit-backdrop-filter:blur(18px) saturate(200%) brightness(1.06); backdrop-filter:blur(18px) saturate(200%) brightness(1.06);
  box-shadow:inset 0 1px 1px rgba(255,255,255,.95), inset 0 -10px 24px -14px rgba(255,255,255,.9), inset 0 0 0 1px rgba(255,255,255,.15),
             0 24px 48px -18px rgba(28,58,48,.22), 0 4px 12px rgba(28,58,48,.05) !important;
  transition:transform .35s cubic-bezier(.23,1,.32,1), box-shadow .35s cubic-bezier(.23,1,.32,1); }}
[class*="st-key-glass"]:hover {{ transform:translateY(-2px);
  box-shadow:inset 0 1px 1px rgba(255,255,255,.95), inset 0 -10px 24px -14px rgba(255,255,255,.9),
             0 32px 60px -20px rgba(28,58,48,.28), 0 6px 16px rgba(28,58,48,.06) !important; }}
[class*="st-key-glass"]::after {{ content:''; position:absolute; top:0; left:10%; right:10%; height:1px; pointer-events:none;
  background:linear-gradient(90deg, transparent, rgba(255,255,255,1), transparent); }}
/* Smaller glass cards inside lists */
[class*="st-key-glasscard"] {{ border-radius:22px; padding:14px 18px 10px !important; margin-bottom:10px; }}
/* Text boxes, selects and date pickers become frosted wells */
[data-testid="stTextInputRootElement"], [data-testid="stMultiSelect"] div:has(> [data-testid="stMultiSelectTagsContainer"]), [data-testid="stDateInput"] div:has(> div > input), [data-testid="stDateInput"] div:has(> input), [data-testid="stSelectbox"] div:has(> div > input), [data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {{
  border-radius:16px !important; border:1.5px solid transparent !important;
  background:linear-gradient(180deg, rgba(255,255,255,.80), rgba(255,255,255,.46)) padding-box,
             linear-gradient(165deg, #fff, rgba(255,255,255,.35) 45%, rgba(47,107,82,.16)) border-box !important;
  -webkit-backdrop-filter:blur(16px) saturate(180%); backdrop-filter:blur(16px) saturate(180%);
  box-shadow:inset 0 2px 6px rgba(28,58,48,.07), inset 0 -1px 0 rgba(255,255,255,.9), 0 8px 18px -12px rgba(28,58,48,.3) !important;
  transition:box-shadow .2s ease, background .2s ease; }}
[data-baseweb="base-input"] {{ background:transparent !important; border:0 !important; box-shadow:none !important; }}
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stMultiSelect"] div:has(> [data-testid="stMultiSelectTagsContainer"]):focus-within, [data-testid="stDateInput"] div:has(> div > input):focus-within, [data-testid="stDateInput"] div:has(> input):focus-within, [data-testid="stSelectbox"] div:has(> div > input):focus-within, [data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within, [data-baseweb="textarea"]:focus-within {{
  background:linear-gradient(180deg, rgba(255,255,255,.92), rgba(255,255,255,.62)) padding-box,
             linear-gradient(165deg, #fff, rgba(79,152,119,.55)) border-box !important;
  box-shadow:inset 0 2px 6px rgba(28,58,48,.06), 0 0 0 4px rgba(79,152,119,.16), 0 10px 22px -12px rgba(47,107,82,.45) !important; }}
input::placeholder, textarea::placeholder {{ color:rgba(79,95,88,.7) !important; }}
/* Chips inside the times box */
[data-baseweb="tag"], [data-testid="stMultiSelectTagsContainer"] span:has(> button) {{ border-radius:999px !important;
  background:linear-gradient(180deg,#4A9877,#2F6B52) !important; color:#fff !important; box-shadow:inset 0 1px 0 rgba(255,255,255,.4); }}
/* Segmented controls: a glass track with a raised glass thumb */
[data-testid="stButtonGroup"] > div {{ gap:4px; padding:4px; border-radius:999px; width:fit-content;
  background:linear-gradient(180deg, rgba(255,255,255,.55), rgba(255,255,255,.28));
  box-shadow:inset 0 1px 3px rgba(28,58,48,.10), inset 0 -1px 0 rgba(255,255,255,.8);
  -webkit-backdrop-filter:blur(14px); backdrop-filter:blur(14px); }}
[data-testid="stButtonGroup"] button {{ border-radius:999px !important; border:0 !important; background:transparent !important; box-shadow:none !important; min-height:38px; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] {{ background:linear-gradient(180deg, #fff, rgba(255,255,255,.75)) !important; color:var(--accent) !important;
  box-shadow:0 4px 12px -4px rgba(28,58,48,.3), inset 0 1px 0 #fff !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] p {{ font-weight:700; color:var(--accent); }}
/* Menus, calendar and toasts float as glass */
[data-baseweb="popover"] > div, [data-baseweb="menu"], [data-baseweb="calendar"] {{
  background:linear-gradient(180deg, rgba(255,255,255,.82), rgba(255,255,255,.6)) !important; border-radius:18px !important;
  -webkit-backdrop-filter:blur(26px) saturate(190%); backdrop-filter:blur(26px) saturate(190%);
  border:1px solid rgba(255,255,255,.9) !important; box-shadow:0 24px 48px -16px rgba(28,58,48,.3) !important; overflow:hidden; }}
[data-baseweb="menu"] li, [role="option"] {{ background:transparent !important; }}
[data-baseweb="menu"] li:hover, [role="option"]:hover {{ background:rgba(47,107,82,.08) !important; }}
[data-testid="stToast"] {{ background:linear-gradient(180deg, rgba(255,255,255,.85), rgba(255,255,255,.6)) !important; border-radius:20px !important;
  -webkit-backdrop-filter:blur(24px) saturate(190%); backdrop-filter:blur(24px) saturate(190%);
  border:1px solid rgba(255,255,255,.95) !important; box-shadow:0 18px 40px -14px rgba(28,58,48,.35) !important; }}
/* The "Add a medicine" bar opens like a glass drawer */
.st-key-glass-add [data-testid="stExpander"] summary {{ border-radius:18px; }}
.st-key-glass-add [data-testid="stExpander"] summary:hover {{ background:rgba(255,255,255,.35); }}
/* Badges become small glass tiles */
.mt-badges {{ border-top:0; gap:12px; }}
.mt-badge {{ border-bottom:0; border-radius:20px; padding:14px; background:linear-gradient(180deg, rgba(255,255,255,.4), rgba(255,255,255,.14)); border:1px solid rgba(255,255,255,.75);
  box-shadow:inset 0 1px 0 #fff, 0 8px 18px -12px rgba(28,58,48,.3); }}
.mt-badge .ring {{ background:linear-gradient(180deg, rgba(207,227,214,.95), rgba(207,227,214,.6)); box-shadow:inset 0 1px 0 #fff; }}
/* Medicine rows and illness cards */
[class*="st-key-glasscard-cond"] .cond {{ border-top:0; padding-top:0; }}
[class*="st-key-glasscard-cond"] .stButton > button {{ padding:0 10px !important; min-width:0; }}
[class*="st-key-glasscard-cond"] .stButton button p {{ white-space:nowrap; overflow:visible; text-overflow:clip; }}
[class*="st-key-glasscard-med"] [data-testid="stExpander"] details {{ border-top:1px solid rgba(30,43,38,.08); }}
.note {{ background:linear-gradient(180deg, rgba(255,255,255,.45), rgba(255,255,255,.18)); border:1px solid rgba(255,255,255,.95);
  border-radius:20px; -webkit-backdrop-filter:blur(18px); backdrop-filter:blur(18px); box-shadow:inset 0 1px 0 #fff, 0 10px 24px -14px rgba(28,58,48,.3); }}
[class*="st-key-glasscard-med"] .mt-med {{ border-top:0; padding-top:2px; }}
/* Theme accents that used to come from .streamlit/config.toml */
[data-baseweb="calendar"] [aria-selected="true"] > div, [data-baseweb="calendar"] [aria-selected="true"]::after {{ background:var(--accent) !important; border-color:var(--accent) !important; }}
[data-baseweb="calendar"] [aria-selected="true"] {{ color:#fff !important; }}
a, a:visited {{ color:var(--accent); }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important; animation:none !important; }} }}
</style>""", unsafe_allow_html=True)


def eyebrow(text):
    st.markdown(f'<p class="eyebrow">{html.escape(text)}</p>', unsafe_allow_html=True)


def init_state():
    ss = st.session_state
    if "meds" in ss:
        return
    try:
        browser_tz = st.context.timezone or "UTC"
    except Exception:
        browser_tz = "UTC"
    ss.meds, ss.log, ss.moods = [], {}, {}       # empty: the user sets up their own medicines
    ss.settings = {"name": "", "age": 65, "age_set": False, "tz": browser_tz, "grace": 60, "remind_before": 0}
    ss.page = "Today"
    ss.seen = {}            # timestamps of widget events already handled
    ss.flash = None         # message to show after a rerun


def get_now():
    try:
        tz = ZoneInfo(st.session_state.settings["tz"])
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    return datetime.now(tz).replace(second=0, microsecond=0)


def is_new_event(name, value):
    """Two-way widgets keep their last value; only act on fresh ones."""
    if not value or not isinstance(value, dict):
        return False
    if st.session_state.seen.get(name) == value.get("ts"):
        return False
    st.session_state.seen[name] = value.get("ts")
    return True


def go(page):
    st.session_state.page = page
    st.rerun()


def mark_taken(row, now):
    level_before = level_for(xp_total(st.session_state.meds, st.session_state.log, st.session_state.moods))[0]
    st.session_state.log.setdefault(now.date().isoformat(), {})[row["key"]] = now.strftime("%H:%M")
    level_after, name, *_ = level_for(xp_total(st.session_state.meds, st.session_state.log, st.session_state.moods))
    if level_after > level_before:
        msg = f"Level up! You are now a {name}."
    elif row["status"] == "missed":
        msg = "Logged as taken late. Don't double your next dose."
    else:
        msg = f"+{dose_xp(row, now)} XP. {random.choice(PRAISE)}"
    st.session_state.flash = (msg, tip_of_the_day(now.date() + timedelta(days=random.randint(1, 7)))["full"],
                              level_after > level_before)


def undo_taken(row, now):
    st.session_state.log.get(now.date().isoformat(), {}).pop(row["key"], None)


def add_medicine(name, dose, times, notes, food, now, start=None):
    st.session_state.meds.append(new_medicine(name, dose, times, notes, start or now.date(), now.strftime("%H:%M"),
                                              food, added_day=now.date()))


# ------------------------------------------------------------------ sidebar ---

def render_sidebar(xp):

    number, name, floor, nxt = level_for(xp)
    with st.sidebar:
        st.markdown('<p class="side-brand">Med<span>Timer</span></p>', unsafe_allow_html=True)
        value = line_sidebar(PAGES, PAGES.index(st.session_state.page), key="nav")
        if is_new_event("nav", value) and value.get("label") in PAGES and value["label"] != st.session_state.page:
            go(value["label"])
        pct = 100 if nxt is None else round(100 * (xp - floor) / (nxt - floor))
        st.markdown(f'<div class="lvl" style="border:0;margin-top:1rem"><div class="top"><span class="name" style="font-size:22px">{name}</span>'
                    f'<span class="num">Lv {number}</span></div><div class="bar"><span style="width:{pct}%"></span></div>'
                    f'<small>{xp} XP</small></div>', unsafe_allow_html=True)


# --------------------------------------------------------------------- pages ---

def checklist_groups(checklist, now):
    """Shape today's doses for the SpringCheck checklist component."""
    groups = {}
    for row in checklist:
        status = row["status"]
        if status == "taken":
            chip = f"Taken {fmt_time(row['taken_at'])}"
        elif status == "due":
            chip = "Due now"
        elif status == "missed":
            chip = "Missed"
        else:
            mins = int((row["scheduled"] - now).total_seconds() // 60)
            chip = f"In {mins // 60}h {mins % 60:02d}m" if mins >= 60 else f"In {mins} min"
        groups.setdefault(time_of_day(row["time"]), []).append({
            "key": row["key"], "time": fmt_time(row["time"]), "name": row["med"]["name"], "dose": row["med"]["dose"],
            "food": food_label(row["med"]), "status": status, "chip": chip, "locked": too_early(row, now),
            "xp": dose_xp(row, now),
        })
    return [{"title": title, "rows": rows} for title, rows in groups.items()]


def level_card(xp):
    number, name, floor, nxt = level_for(xp)
    if nxt is None:
        pct, line = 100, f"{xp} XP · top level reached"
    else:
        pct = round(100 * (xp - floor) / (nxt - floor))
        line = f"{xp} XP · {nxt - xp} XP to {level_for(nxt)[1]}"
    st.markdown(f'<div class="lvl"><div class="top"><span class="name">{name}</span><span class="num">Level {number}</span></div>'
                f'<div class="bar"><span style="width:{pct}%"></span></div><small>{line}</small></div>', unsafe_allow_html=True)


def quests_block(quests):
    tick = icon("check", "#fff", 16)
    st.markdown("".join(
        f'<div class="quest {"done" if q["done"] else ""}"><span class="dot">{tick if q["done"] else ""}</span>'
        f'<span class="t">{html.escape(q["title"])} {"<small>(" + q["progress"] + ")</small>" if q["progress"] and not q["done"] else ""}</span>'
        f'<span class="xp">+{q["xp"]} XP</span></div>' for q in quests), unsafe_allow_html=True)


def add_form(now, prefix, title="Add a medicine"):
    """The add-medicine inputs, used at the top of Today and on My medicines.

    Plain widgets (not st.form) so the date picker appears only when needed.
    A new key suffix after each successful add gives an empty form, while a
    failed add keeps what the user typed so they only fix the mistake.
    """
    n = st.session_state.get("add_n", 0)
    k = f"{prefix}-{n}"
    if title:
        st.markdown(f"### {title}")
    c1, c2 = st.columns(2)
    name = c1.text_input("Name *", placeholder="Metformin", max_chars=40, key=f"name-{k}")
    dose = c2.text_input("Dose", placeholder="500 mg tablet", max_chars=40, key=f"dose-{k}")
    c3, c4 = st.columns(2)
    times = c3.multiselect("Times *", time_options(), default=["08:00"], format_func=fmt_time, key=f"times-{k}")
    food = c4.segmented_control("Food", FOOD_OPTIONS, default="Any time", key=f"food-{k}")
    c5, c6 = st.columns(2)
    choice = c5.segmented_control("Start taking it", START_CHOICES, default="Today", key=f"start-{k}")
    picked = None
    if choice == "Pick a date":
        picked = c6.date_input("Start date", value=now.date(), min_value=now.date() - timedelta(days=5 * 365),
                               max_value=now.date() + timedelta(days=365), format="DD/MM/YYYY", key=f"date-{k}")
    notes = st.text_input("Note", placeholder="e.g. with a full glass of water", max_chars=60, key=f"notes-{k}")
    if st.button("Add medicine", type="primary", key=f"go-{k}"):
        errors = validate_medicine(name, times, st.session_state.meds)
        if errors:
            for e in errors:
                st.error(e)
        else:
            start = resolve_start(choice, picked, now.date())
            add_medicine(name, dose, times, notes, food or "Any time", now, start)
            st.session_state.add_n = n + 1
            when = start_label(st.session_state.meds[-1], now.date()).lower()
            st.session_state.flash = (f"{name.strip()} added ({when}).", None, False)
            st.rerun()


def page_today(now, checklist, score, has_data, xp):

    if not st.session_state.meds:
        with st.container(key="glass-age"):
            eyebrow("Step 1 · How old is the patient?")
            age_input(wake_slider, "age-start")
        with st.container(key="glass-first"):
            eyebrow("Step 2 · Add your first medicine")
            add_form(now, "first", title="")
            st.markdown('<p class="lead" style="margin-top:.8rem">Not sure what to add?</p>', unsafe_allow_html=True)
            if st.button("Browse common illnesses", key="browse"):
                go("Common illnesses")
        return

    # Layout from the brief: inputs at the top, live checklist below, score + turtle on the side.
    with st.container(key="glass-add"):
        with st.expander("Add a medicine", icon=":material/add_circle:"):
            add_form(now, "today", title="")

    main, side = st.columns([1.85, 1], gap="large")
    with main:
        with st.container(key="glass-list"):
            st.markdown("## Tick as you take them")
            if not checklist:
                later = [m for m in st.session_state.meds if date.fromisoformat(m["start"]) > now.date()]
                msg = "Nothing to take today."
                if later:
                    first = min(later, key=lambda m: m["start"])
                    msg += f" <b>{html.escape(first['name'])}</b> {start_label(first, now.date()).lower()}."
                st.markdown(f'<p class="lead">{msg}</p>', unsafe_allow_html=True)
            value = checklist_widget(checklist_groups(checklist, now), key="checklist") if checklist else None
            if is_new_event("checklist", value):
                row = next((r for r in checklist if r["key"] == value.get("key")), None)
                if row and value.get("checked") and row["status"] != "taken" and not too_early(row, now):
                    mark_taken(row, now)
                elif row and not value.get("checked") and row["status"] == "taken":
                    undo_taken(row, now)
                st.rerun()
        with st.container(key="glass-game"):
            c1, c2 = st.columns(2, gap="large")
            with c1:
                eyebrow("Your level")
                level_card(xp)
            with c2:
                eyebrow("Today's quests")
                quests_block(daily_quests(checklist, st.session_state.moods, now))
    with side:
        with st.container(key="glass-score"):
            eyebrow("Weekly adherence")
            slosh_gauge(score if has_data else 0, adherence_message(score, has_data))
        with st.container(key="glass-turtle"):
            eyebrow("Your turtle reward")
            svg, seconds, alt = turtle_reward_svg(reward_level(score, has_data))
            turtle_player(svg, seconds, alt)


def page_medicines(now):
    eyebrow("My medicines")
    st.markdown("## Your daily list")
    _medicine_list(now)
    with st.container(key="glass-addpage"):
        add_form(now, "page")


def _medicine_list(now):
    meds = st.session_state.meds
    if not meds:
        st.markdown('<p class="lead">Nothing here yet. Add one below, or pick from <b>Common illnesses</b>.</p>',
                    unsafe_allow_html=True)
        return
    for med in list(meds):
        with st.container(key=f"glasscard-med-{med['id']}"):
            pills = "".join(f'<span class="mt-pill">{fmt_time(t)}</span>' for t in med["times"])
            food = f'<span class="mt-pill food">{food_label(med)}</span>' if food_label(med) else ""
            note = f"<span>{html.escape(med['notes'])}</span>" if med.get("notes") else ""
            upcoming = date.fromisoformat(med["start"]) > now.date()
            started = f'<span class="mt-pill {"soon" if upcoming else "since"}">{start_label(med, now.date())}</span>'
            st.markdown(f'<div class="mt-med"><b>{html.escape(med["name"])}</b><span>{html.escape(med["dose"])}</span>{pills}{food}{started}{note}</div>',
                        unsafe_allow_html=True)
            with st.expander("Edit"):
                with st.form(f"edit-{med['id']}", border=False):
                    c1, c2 = st.columns(2)
                    name = c1.text_input("Name *", med["name"], max_chars=40, key=f"name-{med['id']}")
                    dose = c2.text_input("Dose", med["dose"], max_chars=40, key=f"dose-{med['id']}")
                    c3, c4 = st.columns(2)
                    times = c3.multiselect("Times *", time_options(), default=med["times"], format_func=fmt_time, key=f"times-{med['id']}")
                    food = c4.segmented_control("Food", FOOD_OPTIONS, default=med.get("food", "Any time"), key=f"food-{med['id']}")
                    c5, c6 = st.columns(2)
                    start = c5.date_input("Start date", value=date.fromisoformat(med["start"]), format="DD/MM/YYYY",
                                          min_value=now.date() - timedelta(days=5 * 365), max_value=now.date() + timedelta(days=365),
                                          key=f"start-{med['id']}")
                    notes = c6.text_input("Note", med["notes"], max_chars=60, key=f"notes-{med['id']}")
                    if st.form_submit_button("Save changes", type="primary"):
                        errors = validate_medicine(name, times, meds, editing_id=med["id"])
                        if errors:
                            for e in errors:
                                st.error(e)
                        else:
                            med.update(name=name.strip(), dose=dose.strip(), times=sorted(set(times)), notes=notes.strip(),
                                       food=food or "Any time", start=start.isoformat())
                            st.session_state.flash = ("Changes saved.", None, False)
                            st.rerun()
                # Two-step delete: the first press asks "are you sure?".
                confirm_key = f"confirm-del-{med['id']}"
                if not st.session_state.get(confirm_key):
                    if st.button("Delete", key=f"del-{med['id']}"):
                        st.session_state[confirm_key] = True
                        st.rerun()
                else:
                    st.markdown(f'<p class="lead">Delete <b>{html.escape(med["name"])}</b> for good?</p>', unsafe_allow_html=True)
                    c1, c2, _ = st.columns([1, 1, 2])
                    if c1.button("Yes, delete", key=f"yes-{med['id']}", type="primary", width="stretch"):
                        st.session_state.meds = [m for m in meds if m["id"] != med["id"]]
                        st.session_state.pop(confirm_key, None)
                        st.session_state.flash = (f"{med['name']} removed.", None, False)
                        st.rerun()
                    if c2.button("Keep it", key=f"no-{med['id']}", width="stretch"):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()


def page_illnesses(now):
    eyebrow("Common illnesses")
    st.markdown("## Pick what you're treating")
    st.markdown('<div class="note"><b>Only add medicines your doctor or pharmacist has told you to take.</b> '
                'Doses and times here are typical starting points. Change them in <b>My medicines</b> to match your prescription.</div>',
                unsafe_allow_html=True)
    have = {m["name"].lower() for m in st.session_state.meds}
    cols = st.columns(2, gap="large")
    for i, cond in enumerate(CONDITIONS):
        with cols[i % 2], st.container(key=f"glasscard-cond-{i}"):
            st.markdown(f'<div class="cond"><b>{html.escape(cond["name"])}</b><p>{html.escape(cond["about"])}</p></div>',
                        unsafe_allow_html=True)
            for j, m in enumerate(cond["meds"]):
                when = ", ".join(fmt_time(t) for t in m["times"])
                food = f" · {m['food'].lower()}" if m["food"] != "Any time" else ""
                left, right = st.columns([2.3, 1], vertical_alignment="center")
                caution = ""
                if m.get("senior_caution") and st.session_state.settings["age"] >= SENIOR_AGE:
                    caution = f'<br><b style="color:var(--brick);font-size:15px">{html.escape(m["senior_caution"])}</b>'
                left.markdown(f'<div class="cmed"><b>{html.escape(m["name"])}</b> <span>{html.escape(m["dose"])}<br>{when}{food}</span>{caution}</div>',
                              unsafe_allow_html=True)
                added = m["name"].lower() in have
                if right.button("Added" if added else "Add", key=f"cond-{i}-{j}", disabled=added,
                                type="secondary" if added else "primary", width="stretch"):
                    add_medicine(m["name"], m["dose"], m["times"], "", m["food"], now)
                    st.session_state.flash = (f"{m['name']} added to your list.", None, False)
                    st.rerun()


def page_progress(now, week, score, has_data):
    s = st.session_state.settings
    with st.container(key="glass-week"):
        _progress_top(now, week, score, has_data, s)
    with st.container(key="glass-badges"):
        _progress_badges(now, week, score, s)


def _progress_top(now, week, score, has_data, s):
    import altair as alt
    T = THEME

    left, mid, right = st.columns([1.15, .75, 1.6], gap="large")
    with left:
        eyebrow("This week")
        st.markdown(f'<div class="mt-score">{score if has_data else "-"}{"%" if has_data else ""}</div>', unsafe_allow_html=True)
        st.markdown(f'<p class="lead" style="margin-top:.6rem">{adherence_message(score, has_data)}</p>', unsafe_allow_html=True)
        report = build_report_html(s["name"], s["age"], st.session_state.meds, st.session_state.log, st.session_state.moods,
                                   now, s["grace"])
        st.download_button("Share report", report, f"medtimer-report-{now.date()}.html", "text/html",
                           type="primary", icon=":material/ios_share:", width="stretch",
                           help="For your doctor or family. Open the file and press Print to save it as a PDF.")
    with mid:
        slosh_gauge(score if has_data else 0, "")
    with right:
        df = pd.DataFrame([{**r, "pct": r["pct"] if r["pct"] is not None else 0} for r in week])
        df["Result"] = pd.cut(df["pct"], [-1, 49, GOOD_ADHERENCE - 1, 100], labels=["Needs care", "Getting there", "Good"])
        bars = alt.Chart(df).mark_bar(cornerRadiusTopLeft=10, cornerRadiusTopRight=10, size=34).encode(
            x=alt.X("label:N", sort=None, title=None, axis=alt.Axis(labelFontSize=14, labelAngle=0, domain=False, ticks=False, labelColor=T["ink2"])),
            y=alt.Y("pct:Q", title=None, scale=alt.Scale(domain=[0, 110]), axis=None),
            color=alt.Color("Result:N", scale=alt.Scale(domain=["Good", "Getting there", "Needs care"],
                                                        range=[T["accent"], "#C99A3B", T["brick"]]), legend=None),
            tooltip=[alt.Tooltip("label:N", title="Day"), alt.Tooltip("taken:Q", title="Taken"),
                     alt.Tooltip("missed:Q", title="Missed"), alt.Tooltip("pct:Q", title="Adherence %")],
        )
        labels = bars.mark_text(dy=-12, fontSize=14, fontWeight="bold", color=T["ink"]).encode(text=alt.Text("pct:Q"))
        rule = alt.Chart(pd.DataFrame({"y": [GOOD_ADHERENCE]})).mark_rule(strokeDash=[4, 4], color=T["ink2"], opacity=.5).encode(y="y:Q")
        st.altair_chart((bars + labels + rule).properties(height=290, background="transparent").configure_view(stroke=None),
                        width="stretch")



def _progress_badges(now, week, score, s):
    eyebrow("Badges")
    earned = earned_badges(st.session_state.meds, st.session_state.log, st.session_state.moods, week, score,
                           perfect_day_streak(st.session_state.meds, st.session_state.log, now, s["grace"]), now)
    st.markdown('<div class="mt-badges">' + "".join(
        f'<div class="mt-badge {"on" if earned[bid] else "off"}"><span class="ring">{icon(ic, "var(--accent)" if earned[bid] else "var(--ink2)", 22)}</span>'
        f'<span><b>{title}</b><small>{"Earned" if earned[bid] else how}</small></span></div>'
        for bid, title, how, ic in BADGES
    ) + "</div>", unsafe_allow_html=True)

    st.write("")
    eyebrow("How XP works")
    st.markdown(f'<p class="lead">+{XP_DOSE} for every dose · +{XP_ON_TIME} if it is within {ON_TIME_MINUTES} minutes · '
                f'+{XP_PERFECT_DAY} for a perfect day · +{XP_MOOD} for the mood check-in.</p>', unsafe_allow_html=True)
    with st.expander("By medicine"):
        st.dataframe(pd.DataFrame(medicine_breakdown(st.session_state.meds, st.session_state.log, now, s["grace"])),
                     hide_index=True, width="stretch")


def page_wellbeing(now):

    q, who = quote_of_the_day(now.date())
    with st.container(key="glass-quote"):
        eyebrow("Thought for today")
        st.markdown(f'<p class="mt-quote">"{html.escape(q)}"</p><p>{html.escape(who)}</p>', unsafe_allow_html=True)

    left, right = st.columns([1.35, 1], gap="large")
    with left, st.container(key="glass-tips"):
        eyebrow("Tips")
        folder_float(TIPS)
    with right, st.container(key="glass-mood"):
        eyebrow(f"How do you feel today? (+{XP_MOOD} XP)")
        today = now.date().isoformat()
        current = st.session_state.moods.get(today)
        value = option_wheel(MOODS, current or "Good", key="mood")
        if is_new_event("mood", value):
            first = today not in st.session_state.moods
            st.session_state.moods[today] = value["mood"]
            if first:
                st.session_state.flash = (f"+{XP_MOOD} XP for checking in.", None, False)
            st.rerun()
        if current in ("In pain", "Unwell"):
            st.warning("Sorry you're not feeling well. If you're worried, call your doctor or a family member.")
        elif current:
            st.markdown(f'<p class="lead">Saved: you feel <b>{current.lower()}</b> today.</p>', unsafe_allow_html=True)


def age_input(wake_slider, key):
    """WakeSlider asking the patient's age; stored in settings."""
    s = st.session_state.settings
    value = wake_slider(s["age"], key=key, low=18, high=100, label="Patient's age")
    if is_new_event(key, value):
        s["age"], s["age_set"] = int(value["value"]), True
        st.rerun()


def page_settings():

    s = st.session_state.settings
    eyebrow("Settings")
    st.markdown("## Make it yours")
    c1, _ = st.columns([1.2, 1])
    with c1, st.container(key="glass-settings"):
        s["name"] = st.text_input("Your name", s["name"], max_chars=30, placeholder="So we can greet you")
        st.markdown('<p style="margin:.6rem 0 0;font-size:15px;color:var(--ink2)">Patient\'s age</p>', unsafe_allow_html=True)
        age_input(wake_slider, "age-settings")
        s["remind_before"] = st.segmented_control("Sound reminder: how early?", REMIND_OPTIONS, default=s["remind_before"],
                                                  format_func=lambda m: "On time" if m == 0 else f"{m} min") or 0
        s["grace"] = st.segmented_control("Minutes after the planned time before a dose turns red", GRACE_OPTIONS,
                                          default=s["grace"], format_func=lambda m: f"{m} min") or s["grace"]
        zones = sorted({s["tz"], "UTC", "Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London",
                        "America/New_York", "America/Los_Angeles", "Australia/Sydney", "Africa/Nairobi"})
        s["tz"] = st.selectbox("Time zone", zones, index=zones.index(s["tz"]))


def main():

    st.set_page_config(page_title="MedTimer - Daily Medicine Companion", page_icon=":material/medication:",
                       layout="wide", initial_sidebar_state="expanded")
    init_state()
    inject_css()
    s = st.session_state.settings

    now = get_now()
    meds, log, moods = st.session_state.meds, st.session_state.log, st.session_state.moods
    checklist = build_checklist(meds, log, now, s["grace"])
    week, score, _, counted = weekly_summary(meds, log, now, s["grace"])
    has_data = counted > 0
    streak = perfect_day_streak(meds, log, now, s["grace"])
    xp = xp_total(meds, log, moods)
    render_sidebar(xp)

    # One sentence in the header instead of a block of text.
    hello = html.escape(greeting_for(now, s["name"]))
    nxt = pick_next_dose(checklist)
    if not meds:
        line = f"{hello}. Let's set up your medicines."
    elif nxt and nxt["status"] == "due":
        food = f" ({food_label(nxt['med']).lower()})" if food_label(nxt["med"]) else ""
        line = f'{hello}. <b class="due">{html.escape(nxt["med"]["name"])}</b> is due now{food}.'
    elif nxt:
        line = f'{hello}. Next up: <b>{html.escape(nxt["med"]["name"])}</b> at {fmt_time(nxt["time"])}.'
    elif checklist:
        line = f"{hello}. <b>All done for today.</b> Well done."
    else:
        later = [m for m in meds if date.fromisoformat(m["start"]) > now.date()]
        first = min(later, key=lambda m: m["start"]) if later else None
        line = f"{hello}. Nothing to take today." + (
            f" <b>{html.escape(first['name'])}</b> {start_label(first, now.date()).lower()}." if first else "")

    number, level_name, *_ = level_for(xp)
    done = sum(r["status"] == "taken" for r in checklist)
    stats = [] if not meds else [
        {"text": f"{done}/{len(checklist)}", "label": "taken today", "tone": "taken"},
        {"text": str(sum(r["status"] in ("due", "upcoming") for r in checklist)), "label": "still to take", "tone": "left"},
        {"text": f"{score}%" if has_data else "0", "label": "this week", "tone": "plain"},
        {"text": str(streak), "label": "day streak", "tone": "plain"},
        {"text": str(xp), "label": f"XP · {level_name}", "tone": "taken"},
    ]
    alarms = reminder_alarms(checklist, s["remind_before"])
    hero(now.strftime("%A %d %B · %I:%M %p").replace(" 0", " "), line, stats,
         speech_text(s["name"] or "there", checklist), alarms, height=300 if not meds else 390)

    page = st.session_state.page
    if page == "Today":
        page_today(now, checklist, score, has_data, xp)
    elif page == "My medicines":
        page_medicines(now)
    elif page == "Common illnesses":
        page_illnesses(now)
    elif page == "Progress":
        page_progress(now, week, score, has_data)
    elif page == "Wellbeing":
        page_wellbeing(now)
    else:
        page_settings()
    st.markdown('<p class="mt-foot">MedTimer is a reminder aid, not medical advice. Always follow your doctor or pharmacist.</p>',
                unsafe_allow_html=True)

    # Toasts and balloons go last: adding them above the page would shift every
    # element's position and make Streamlit rebuild the checklist mid-animation.
    if st.session_state.flash:
        msg, tip, level_up = st.session_state.flash
        st.toast(msg, icon=":material/military_tech:" if level_up else ":material/check_circle:")
        if tip:
            st.toast(f"Tip: {tip}", icon=":material/lightbulb:")
        if level_up or (checklist and all(r["status"] == "taken" for r in checklist)):
            st.balloons()
        st.session_state.flash = None


def run_real_turtle(level):
    """Draw a reward in Python's own turtle window (desktop only)."""
    import turtle
    screen = turtle.Screen()
    screen.title(f"MedTimer turtle - {level}")
    screen.bgcolor("#EEF1EC")
    t = turtle.Turtle()
    t.speed(6)
    DRAWINGS[level][0](t)
    t.hideturtle()
    turtle.done()


# Two-way widgets (React Bits designs in plain JavaScript): SpringCheck checklist,
# LineSidebar navigation, WakeSlider age picker and OptionWheel mood wheel.
_WIDGETS_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<!--
  MedTimer two-way widgets (React Bits designs, plain JavaScript):
    kind = "checklist" -> SpringCheck rows (today's doses)
    kind = "nav"       -> LineSidebar    (sidebar navigation)
    kind = "slider"    -> WakeSlider     (age question)
    kind = "wheel"     -> OptionWheel    (daily mood check-in)
  Talks to Streamlit with the standard component messages, so no build step is needed.
-->
<link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=Roboto+Flex:opsz,wdth,wght@8..144,25..151,100..1000&display=swap" rel="stylesheet">
<style>
  * { box-sizing:border-box; }
  html,body { margin:0; background:transparent; font-family:'Atkinson Hyperlegible',system-ui,sans-serif; color:var(--ink); -webkit-font-smoothing:antialiased; }
  button { font:inherit; color:inherit; }
  .sr { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; }
  :focus-visible { outline:2px solid var(--accent); outline-offset:3px; }

  /* ---------- Checklist made of SpringCheck rows ---------- */
  .group { font-size:14px; letter-spacing:.12em; text-transform:uppercase; color:var(--ink2); margin:18px 0 4px; font-weight:700; }
  .group:first-child { margin-top:2px; }
  .row { display:grid; grid-template-columns:96px 1fr auto; align-items:center; gap:14px; min-height:72px; border-top:1px solid rgba(30,43,38,.08); }
  .time { font-family:'Roboto Flex',sans-serif; font-size:22px; font-weight:600; font-variation-settings:'wdth' 108; font-variant-numeric:tabular-nums; }
  .time small { font-size:14px; font-weight:500; margin-left:2px; color:var(--ink2); }
  .sc { display:flex; align-items:center; gap:16px; min-height:64px; padding:0; border:0; background:none; text-align:left; cursor:pointer;
        user-select:none; -webkit-tap-highlight-color:transparent; touch-action:manipulation; outline:none; width:100%; }
  .sc:disabled { cursor:not-allowed; }
  .press { flex:none; width:40px; height:40px; border-radius:12px; transition:transform .16s cubic-bezier(.23,1,.32,1); }
  .sc[data-pressed] .press { transform:scale(.94); }
  .sc:focus-visible .press { outline:2px solid var(--accent); outline-offset:3px; }
  .box { position:relative; display:grid; place-items:center; width:100%; height:100%; border-radius:inherit; overflow:hidden; }
  .box { background:linear-gradient(180deg,rgba(255,255,255,.85),rgba(255,255,255,.45)); box-shadow:inset 0 1px 0 #fff, 0 4px 10px -6px rgba(28,58,48,.35); }
  .ring { position:absolute; inset:0; border-radius:inherit; box-shadow:inset 0 0 0 2px var(--ink); opacity:.3; transition:opacity .12s; }
  .sc:not(:disabled):hover .ring { opacity:.6; }
  .sc:disabled .ring { opacity:.15; }
  .fill { position:absolute; inset:0; border-radius:inherit; background:linear-gradient(180deg,#5BA683,#2F6B52); box-shadow:inset 0 1px 0 rgba(255,255,255,.45); transform:scale(0); }
  .tick { position:relative; width:64%; height:64%; overflow:visible; fill:none; stroke:#fff; stroke-width:2.8; stroke-linecap:round; stroke-linejoin:round; }
  .label { position:relative; display:inline-block; }
  .word { display:block; }
  .name { font-size:21px; font-weight:700; line-height:1.2; }
  .dose { font-size:16px; color:var(--ink2); }
  .rule { position:absolute; left:0; right:0; top:.62em; height:2px; border-radius:2px; background:currentColor; transform-origin:left center; transform:scaleX(0); pointer-events:none; }
  .state { display:inline-flex; align-items:center; gap:6px; font-size:15px; font-weight:700; padding:6px 12px; border-radius:999px; white-space:nowrap;
           border:1px solid rgba(255,255,255,.85); box-shadow:inset 0 1px 0 rgba(255,255,255,.9), 0 4px 10px -6px rgba(28,58,48,.3); }
  .state svg { width:16px; height:16px; stroke:currentColor; fill:none; stroke-width:2.4; stroke-linecap:round; stroke-linejoin:round; }
  .s-taken { color:var(--accent); background:var(--accentSoft); }
  .s-due { color:#5C3D0A; background:#F2D27A; box-shadow:0 0 0 3px rgba(242,210,122,.35); }
  .s-upcoming { color:var(--amber); background:#FBF1D6; }
  .s-missed { color:var(--brick); background:var(--brickSoft); }
  .row.missed .ring { box-shadow:inset 0 0 0 2px var(--brick); opacity:.7; }
  .row.due .ring { box-shadow:inset 0 0 0 2px var(--amber); opacity:.9; }
  .row.due .press { animation:breathe 2.4s ease-in-out infinite; }
  @keyframes breathe { 50% { transform:scale(1.07); } }
  .empty { padding:22px 0; font-size:19px; color:var(--ink2); border-top:1px solid var(--rule); }
  @media (max-width:560px) { .row { grid-template-columns:72px 1fr; } .state { grid-column:2; justify-self:start; margin:-10px 0 10px 56px; } .time { font-size:19px; } }

  /* ---------- XP spark (ClickSpark-style) ---------- */
  .press { position:relative; }
  .spark { position:absolute; left:50%; top:50%; width:6px; height:6px; margin:-3px; border-radius:50%; background:var(--accent); pointer-events:none; }
  .xp-pop { position:absolute; left:46px; top:-6px; font-weight:700; font-size:16px; color:var(--accent); pointer-events:none; white-space:nowrap; }
  .food { color:var(--accent); font-weight:700; }

  /* ---------- LineSidebar ---------- */
  .line-sidebar { --effect:0; position:relative; display:flex; padding-left:46px; }
  .ls-list { list-style:none; margin:0; padding:.6rem 0; display:flex; flex-direction:column; gap:22px; width:100%; }
  .ls-item { position:relative; cursor:pointer; outline:none; }
  .ls-item::before { content:''; position:absolute; inset:-8px -40px; }
  .ls-label { position:relative; display:inline-flex; align-items:baseline; font-family:'Roboto Flex',sans-serif; font-size:19px; line-height:1.2;
              font-variation-settings:'wdth' 110; font-weight:calc(500 + var(--effect,0) * 250);
              color:color-mix(in srgb, var(--accent) calc(var(--effect,0) * 100%), var(--ink2)); transform:translateX(calc(var(--effect,0) * 16px)); }
  .ls-index { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; margin-right:.6rem; font-size:.75em; opacity:calc(.55 + var(--effect,0) * .45); }
  .ls-marker { position:absolute; top:50%; left:-46px; height:1.5px; width:36px; background:color-mix(in srgb, var(--accent) calc(var(--effect,0) * 100%), #9AA8A0);
               transform-origin:left center; transform:translateY(-50%) scaleX(calc(.6 + var(--effect,0) * .6)); }
  .ls-item:not(:last-child)::after { content:''; position:absolute; top:calc(100% + 11px); left:-46px; height:1px; width:18px; background:#9AA8A0; opacity:.5;
               transform-origin:left center; transform:translateY(-50%) scaleX(calc(.7 + var(--effect,0) * .6)); }
  .ls-item:focus-visible .ls-text { outline:2px solid var(--accent); outline-offset:4px; border-radius:4px; }

  /* ---------- WakeSlider ---------- */
  .ws { display:flex; align-items:center; gap:18px; width:100%; max-width:520px; }
  .ws-track { position:relative; display:flex; flex:1 1 auto; align-items:center; gap:4px; height:64px; touch-action:none; user-select:none; cursor:grab; }
  .ws-track:active { cursor:grabbing; }
  .ws-bar { flex:1 1 0; min-width:0; height:64px; border-radius:9999px; background:linear-gradient(180deg,rgba(255,255,255,.9),rgba(255,255,255,.5)); box-shadow:inset 0 0 0 1px rgba(255,255,255,.9), 0 2px 6px -3px rgba(28,58,48,.25);
            transform:scaleY(var(--rest)); transform-origin:50% 50%; transition:background-color .12s ease; }
  .ws-bar[data-on="true"] { background:linear-gradient(180deg,#5BA683,#2F6B52); box-shadow:inset 0 1px 0 rgba(255,255,255,.45); }
  .ws-handle { position:absolute; inset:0; margin:0; padding:0; border:0; border-radius:12px; background:transparent; cursor:inherit; }
  .ws-value { min-width:4.2ch; font-family:'Roboto Flex',sans-serif; font-size:40px; font-weight:750; font-variation-settings:'wdth' 115;
              font-variant-numeric:tabular-nums; text-align:right; line-height:1; }
  .ws-value small { display:block; font-family:'Atkinson Hyperlegible',sans-serif; font-size:14px; font-weight:400; color:var(--ink2); }

  /* ---------- OptionWheel ---------- */
  .wheel { position:relative; width:100%; height:280px; overflow:hidden; cursor:grab; user-select:none; touch-action:none; outline:none; }
  .wheel:focus-visible { box-shadow:inset 0 0 0 2px var(--accent); border-radius:16px; }
  .wheel::before { content:''; position:absolute; left:0; right:0; top:50%; height:1px; margin-top:-28px; background:var(--rule); }
  .wheel::after { content:''; position:absolute; left:0; right:0; top:50%; height:1px; margin-top:28px; background:var(--rule); }
  .wheel-item { position:absolute; top:50%; left:8px; white-space:nowrap; font-family:'Roboto Flex',sans-serif; font-size:36px; line-height:1;
                font-variation-settings:'wdth' 110; font-weight:300; transform-origin:left center; cursor:pointer; will-change:transform,opacity,filter;
                color:color-mix(in srgb, var(--ink) calc(var(--p,0)*100%), var(--ink2)); }
  .wheel-item[aria-selected="true"] { font-weight:700; }

  @media (prefers-reduced-motion: reduce) { .press { transition:none !important; animation:none !important; } }
</style>
</head>
<body>
<div id="root"></div>
<script>
/* ---------- Streamlit component protocol (no npm package needed) ---------- */
const send = (type, data = {}) => window.parent.postMessage({ isStreamlitMessage: true, type, ...data }, '*');
const setValue = value => send('streamlit:setComponentValue', { value, dataType: 'json' });
const setHeight = () => send('streamlit:setFrameHeight', { height: Math.ceil(document.getElementById('root').getBoundingClientRect().height) + 8 });
let mounted = null, update = null;
window.addEventListener('message', e => {
  if (e.data?.type !== 'streamlit:render') return;
  const a = e.data.args || {};
  if (a.theme) Object.entries(a.theme).forEach(([k, v]) => document.documentElement.style.setProperty('--' + k, v));
  if (!mounted) { mounted = a.kind; ({ checklist: mountChecklist, nav: mountNav, slider: mountSlider, wheel: mountWheel })[a.kind](a); }
  else update?.(a);
  requestAnimationFrame(setHeight);
});
send('streamlit:componentReady', { apiVersion: 1 });
new ResizeObserver(setHeight).observe(document.body);
const root = document.getElementById('root');
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const ICON = {
  check: '<path d="M20 6 9 17l-5-5"/>', clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 8v5"/><path d="M12 16.5v.5"/>', lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>'
};
const svg = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICON[name]}</svg>`;

/* ---------- SpringCheck: one spring fills the box, draws the tick and strikes the name ---------- */
function springCheck(btn, on) {
  const fill = btn.querySelector('.fill'), box = btn.querySelector('.box'), tick = btn.querySelector('.tick path'),
        word = btn.querySelector('.word'), rule = btn.querySelector('.rule');
  let t = on ? 1 : 0, v = 0, target = t, raf = 0, last = 0;
  const c01 = x => clamp(x, 0, 1);
  const write = () => { const held = c01(t);
    fill.style.transform = `scale(${Math.max(t, 0)})`; box.style.transform = `scale(${1 + .35 * Math.max(0, t - 1)})`;
    tick.style.strokeDashoffset = 1 - held; word.style.opacity = 1 - .5 * held;
    rule.style.transform = `scaleX(${c01((held - .12) / (.84 - .12))})`; };
  // Spring with a visual duration of 0.2 s and a little bounce, like the original.
  const omega = 2 * Math.PI / .2 * .5, zeta = .62;
  const step = now => { const dt = last ? Math.min(.032, (now - last) / 1000) : .016; last = now;
    const sub = 4; for (let i = 0; i < sub; i++) { const h = dt / sub; v += (-omega * omega * (t - target) - 2 * zeta * omega * v) * h; t += v * h; }
    write(); if (Math.abs(t - target) < .002 && Math.abs(v) < .01) { t = target; v = 0; write(); raf = 0; last = 0; return; }
    raf = requestAnimationFrame(step); };
  write();
  return { set(next, instant) { target = next ? 1 : 0; if (instant || reduce) { cancelAnimationFrame(raf); raf = 0; t = target; v = 0; write(); return; }
           if (!raf) raf = requestAnimationFrame(step); }, get: () => target === 1 };
}

/* ClickSpark-style burst and a floating "+XP" when a dose is ticked */
function burst(press, xp) {
  for (let i = 0; i < 10; i++) { const d = document.createElement('span'); d.className = 'spark'; press.appendChild(d);
    const an = (i / 10) * Math.PI * 2 + Math.random() * .3, r = 30 + Math.random() * 14;
    d.animate([{ transform: 'translate(0,0) scale(1)', opacity: 1 }, { transform: `translate(${Math.cos(an) * r}px,${Math.sin(an) * r}px) scale(.3)`, opacity: 0 }],
      { duration: 520, easing: 'cubic-bezier(.23,1,.32,1)' }).onfinish = () => d.remove(); }
  if (!xp) return;
  const pop = document.createElement('span'); pop.className = 'xp-pop'; pop.textContent = '+' + xp + ' XP'; press.appendChild(pop);
  pop.animate([{ transform: 'translateY(6px)', opacity: 0 }, { transform: 'translateY(-10px)', opacity: 1, offset: .25 }, { transform: 'translateY(-34px)', opacity: 0 }],
    { duration: 1300, easing: 'ease-out' }).onfinish = () => pop.remove();
}

function mountChecklist(a) {
  const rowsByKey = new Map();
  function chip(r) { const name = { taken: 'check', due: 'bell', upcoming: r.locked ? 'lock' : 'clock', missed: 'alert' }[r.status];
    return `<span class="state s-${r.status}">${svg(name)}${esc(r.chip)}</span>`; }
  function render(groups) {
    root.innerHTML = '';
    if (!groups.length) { root.innerHTML = '<div class="empty">No medicines yet. Add one in the Medicines tab.</div>'; return; }
    groups.forEach(g => {
      const h = document.createElement('div'); h.className = 'group'; h.textContent = g.title; root.appendChild(h);
      g.rows.forEach(r => {
        const row = document.createElement('div'); row.className = 'row ' + r.status;
        const [hm, ap] = r.time.split(' ');
        row.innerHTML = `<div class="time">${esc(hm)}<small>${esc(ap)}</small></div>
          <button class="sc" type="button" role="checkbox" aria-checked="${r.status === 'taken'}" ${r.locked ? 'disabled' : ''}
             aria-label="${esc(r.name)} ${esc(r.dose)} at ${esc(r.time)}, ${esc(r.chip)}">
            <span class="press"><span class="box"><span class="ring"></span><span class="fill"></span>
              <svg class="tick" viewBox="0 0 24 24"><path d="M5 14L8.5 17.5L19 6.5" pathLength="1" stroke-dasharray="1"/></svg></span></span>
            <span class="label"><span class="word"><span class="name">${esc(r.name)}</span><span class="dose"> ${esc(r.dose)}${r.food ? ` · <span class="food">${esc(r.food)}</span>` : ''}</span></span><span class="rule"></span></span>
          </button>
          <div class="chipwrap">${chip(r)}</div>`;
        const btn = row.querySelector('.sc'), spring = springCheck(btn, r.status === 'taken');
        btn.addEventListener('pointerdown', () => btn.setAttribute('data-pressed', ''));
        ['pointerup', 'pointerleave', 'pointercancel'].forEach(ev => btn.addEventListener(ev, () => btn.removeAttribute('data-pressed')));
        btn.addEventListener('click', () => { if (btn.disabled) return; const next = !spring.get(); spring.set(next);
          if (next && !reduce) burst(btn.querySelector('.press'), r.xp);
          btn.setAttribute('aria-checked', next); setValue({ key: r.key, checked: next, ts: Date.now() }); });
        rowsByKey.set(r.key, { row, btn, spring });
        root.appendChild(row);
      });
    });
  }
  render(a.groups);
  let lastSig = JSON.stringify(a.groups);
  update = b => {
    const sig = JSON.stringify(b.groups); if (sig === lastSig) return; lastSig = sig;
    const same = b.groups.flatMap(g => g.rows.map(r => r.key)).join() === [...rowsByKey.keys()].join();
    if (!same) { rowsByKey.clear(); render(b.groups); return; }
    // Same doses: update states in place so the spring animation is never interrupted.
    b.groups.forEach(g => g.rows.forEach(r => { const it = rowsByKey.get(r.key);
      it.row.className = 'row ' + r.status; it.row.querySelector('.chipwrap').innerHTML = chip(r);
      it.btn.disabled = !!r.locked; it.btn.setAttribute('aria-checked', r.status === 'taken');
      if (it.spring.get() !== (r.status === 'taken')) it.spring.set(r.status === 'taken'); }));
  };
}

/* ---------- LineSidebar: labels slide and tint as the pointer gets close ---------- */
function mountNav(a) {
  let active = a.active ?? 0;
  root.innerHTML = `<nav class="line-sidebar" aria-label="Pages"><ul class="ls-list" id="ls">
    ${a.items.map((t, i) => `<li class="ls-item" tabindex="0" role="link" data-i="${i}"><span class="ls-marker" aria-hidden="true"></span>
      <span class="ls-label"><span class="ls-index">${String(i + 1).padStart(2, '0')}</span><span class="ls-text">${esc(t)}</span></span></li>`).join('')}</ul></nav>`;
  const list = root.querySelector('#ls'), items = [...list.children];
  const targets = items.map(() => 0), cur = items.map(() => 0); let raf = 0, last = 0;
  const ease = p => p * p * (3 - 2 * p);
  function frame(now) { const dt = Math.min((now - last) / 1000, .05); last = now; const k = 1 - Math.exp(-dt / .1); let moving = false;
    items.forEach((el, i) => { const t = Math.max(targets[i], active === i ? 1 : 0); const nx = cur[i] + (t - cur[i]) * k;
      const done = Math.abs(t - nx) < .0015; cur[i] = done ? t : nx; el.style.setProperty('--effect', cur[i].toFixed(4)); if (!done) moving = true; });
    raf = moving ? requestAnimationFrame(frame) : 0; }
  const loop = () => { if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); } };
  list.addEventListener('pointermove', e => { const rect = list.getBoundingClientRect(), y = e.clientY - rect.top;
    items.forEach((el, i) => { const c = el.offsetTop + el.offsetHeight / 2; targets[i] = ease(Math.max(0, 1 - Math.abs(y - c) / 90)); }); loop(); });
  list.addEventListener('pointerleave', () => { targets.fill(0); loop(); });
  const choose = i => { active = i; loop(); setValue({ index: i, label: a.items[i], ts: Date.now() }); };
  items.forEach((el, i) => { el.addEventListener('click', () => choose(i));
    el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(i); } }); });
  update = b => { if (b.active !== active) { active = b.active; loop(); } };
  loop();
}

/* ---------- WakeSlider: bars rise in a wake behind the moving handle ---------- */
function mountSlider(a) {
  const BARS = 28, min = a.min, max = a.max, rest = 14 / 64;
  let value = clamp(a.value ?? 60, min, max);
  root.innerHTML = `<div class="ws" style="--rest:${rest}"><div class="ws-track" id="tr">
      ${Array.from({ length: BARS }, () => '<span class="ws-bar"></span>').join('')}
      <button class="ws-handle" id="hd" type="button" role="slider" aria-label="${esc(a.label)}" aria-valuemin="${min}" aria-valuemax="${max}"></button></div>
      <div class="ws-value" id="val"></div></div>`;
  const tr = root.querySelector('#tr'), hd = root.querySelector('#hd'), val = root.querySelector('#val'), bars = [...tr.querySelectorAll('.ws-bar')];
  const pct = v => (v - min) / (max - min) * 100;
  // A critically damped spring moves the head; its speed raises the wake (like the original's useSpring + useVelocity).
  let target = pct(value), head = target, vel = 0, speed = 0, raf = 0, last = 0, pid = null, sendT = 0;
  const w0 = 9.23 / .3;
  function paint() {
    const h = head / 100 * (BARS - 1), amp = reduce ? 0 : (s => s * s * (3 - 2 * s))(clamp(Math.abs(speed) / 320, 0, 1)), dir = Math.sign(speed) || 1;
    const r = 1.5 + (6 - 1.5) * amp, behind = r * 1.6, ahead = r * .7, lit = Math.round(target / 100 * (BARS - 1));
    bars.forEach((el, i) => { el.dataset.on = i <= lit; const d = i - h, R = d * dir < 0 ? behind : ahead;
      const lift = Math.abs(d) < R ? amp * Math.cos(Math.PI * d / (2 * R)) ** 2 : 0; el.style.transform = `scaleY(${rest + lift * (1 - rest)})`; });
    val.innerHTML = `${value}<small>years</small>`; hd.setAttribute('aria-valuenow', value); hd.setAttribute('aria-valuetext', value + ' years');
  }
  function frame(now) { const dt = last ? Math.min(.032, (now - last) / 1000) : .016; last = now;
    const acc = w0 * w0 * (target - head) - 2 * w0 * vel; vel += acc * dt; head += vel * dt;
    speed += (vel - speed) * (1 - Math.exp(-dt / .1)); paint();
    if (Math.abs(target - head) < .01 && Math.abs(vel) < .5 && Math.abs(speed) < 1) { head = target; vel = speed = 0; paint(); raf = 0; last = 0; return; }
    raf = requestAnimationFrame(frame); }
  const loop = () => { if (!raf) raf = requestAnimationFrame(frame); };
  const send = () => { clearTimeout(sendT); sendT = setTimeout(() => setValue({ value, ts: Date.now() }), 250); };
  const setV = v => { v = clamp(Math.round(v), min, max); if (v === value) return; value = v; target = pct(v); if (reduce) head = target; loop(); paint(); };
  const fromX = x => { const r = tr.getBoundingClientRect(); setV(min + clamp((x - r.left) / r.width, 0, 1) * (max - min)); };
  tr.addEventListener('pointerdown', e => { pid = e.pointerId; tr.setPointerCapture(pid); hd.focus({ preventScroll: true }); fromX(e.clientX); });
  tr.addEventListener('pointermove', e => { if (e.pointerId === pid) fromX(e.clientX); });
  const end = e => { if (e.pointerId !== pid) return; pid = null; send(); };
  tr.addEventListener('pointerup', end); tr.addEventListener('pointercancel', end);
  hd.addEventListener('keydown', e => { const j = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1, PageUp: 10, PageDown: -10 }[e.key];
    if (j == null) return; e.preventDefault(); setV(value + j); send(); });
  update = () => {};
  paint();
}

/* ---------- OptionWheel: curved, eased list (wheel, drag, click, arrow keys) ---------- */
function mountWheel(a) {
  const items = a.items; let sel = Math.max(0, items.indexOf(a.selected));
  root.innerHTML = `<div class="wheel" id="wh" role="listbox" tabindex="0" aria-label="How are you feeling today?">
      ${items.map((t, i) => `<div class="wheel-item" role="option" data-i="${i}">${esc(t)}</div>`).join('')}</div>`;
  const wh = root.querySelector('#wh'), els = [...wh.querySelectorAll('.wheel-item')];
  const rowH = 36 * 1.5, tilt = 7 * Math.PI / 180, Rr = rowH / tilt;
  let pos = sel, target = sel, raf = 0, last = 0, timer = 0, wtimer = 0, drag = null, moved = false;
  function frame(now) { const dt = Math.min((now - last) / 1000, .05); last = now; const kk = 1 - Math.exp(-dt / .2);
    let nx = pos + (target - pos) * kk; const done = Math.abs(target - nx) < .001; if (done) nx = target; pos = nx;
    els.forEach((el, i) => { const d = i - pos, dist = Math.abs(d), an = clamp(d * tilt, -Math.PI / 2, Math.PI / 2);
      const yy = Rr * Math.sin(an), xx = -Rr * (1 - Math.cos(an));
      el.style.transform = `translate(${xx.toFixed(2)}px, calc(${yy.toFixed(2)}px - 50%)) rotate(${(an * 180 / Math.PI).toFixed(3)}deg)`;
      el.style.opacity = Math.max(.08, 1 - dist * .3); el.style.filter = reduce ? 'none' : `blur(${(dist * 1.5).toFixed(2)}px)`;
      el.style.setProperty('--p', Math.max(0, 1 - Math.min(dist, 1)).toFixed(3)); });
    raf = done ? 0 : requestAnimationFrame(frame); }
  const loop = () => { if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); } };
  function go(v, snap) { v = clamp(v, 0, items.length - 1); if (snap) v = Math.round(v); target = v; if (reduce) pos = v;
    sel = Math.round(v); els.forEach((e, i) => e.setAttribute('aria-selected', i === sel)); loop();
    clearTimeout(timer); if (snap) timer = setTimeout(() => setValue({ mood: items[sel], ts: Date.now() }), 350); }
  wh.addEventListener('wheel', e => { e.preventDefault(); go(target + clamp((e.deltaMode === 1 ? e.deltaY * 24 : e.deltaY) / rowH, -1, 1), false);
    clearTimeout(wtimer); wtimer = setTimeout(() => go(target, true), 140); }, { passive: false });
  wh.addEventListener('pointerdown', e => { drag = { y: e.clientY, start: target, id: e.pointerId }; moved = false; });
  wh.addEventListener('pointermove', e => { if (!drag) return; const dy = e.clientY - drag.y;
    if (!moved && Math.abs(dy) > 4) { moved = true; wh.setPointerCapture(drag.id); } if (moved) go(drag.start - dy / rowH, false); });
  const end = () => { if (!drag) return; drag = null; if (moved) go(target, true); };
  wh.addEventListener('pointerup', end); wh.addEventListener('pointercancel', end);
  els.forEach((el, i) => el.addEventListener('click', () => { if (!moved) go(i, true); }));
  wh.addEventListener('keydown', e => { const d = { ArrowUp: -1, ArrowLeft: -1, ArrowDown: 1, ArrowRight: 1 }[e.key]; if (d == null) return; e.preventDefault(); go(Math.round(target) + d, true); });
  update = () => {};
  els.forEach((e, i) => e.setAttribute('aria-selected', i === sel)); loop();
}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    if "--turtle" in sys.argv:
        choice = sys.argv[-1] if sys.argv[-1] in DRAWINGS else "trophy"
        run_real_turtle(choice)
    else:
        main()
