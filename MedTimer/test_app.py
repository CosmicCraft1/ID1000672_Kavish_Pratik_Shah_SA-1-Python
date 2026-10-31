"""
Automated tests for MedTimer's Python logic.

Run with:  python -m pytest -q
Each test describes a real situation an older user could run into.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import app

TZ = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 31, 14, 0, tzinfo=TZ)        # Saturday, 2:00 PM
LAST_WEEK = NOW.date() - timedelta(days=7)


def med(name="Metformin", times=("08:00", "20:00"), start=LAST_WEEK, from_time="00:00", food="Any time"):
    return app.new_medicine(name, "500 mg", list(times), "", start, from_time, food)


def sample_week(now):
    """A realistic week of history used by several tests (the app itself starts empty)."""
    import random
    rng = random.Random(42)
    start = now.date() - timedelta(days=7)
    meds = [med("Metformin", ("08:00", "20:00"), start, food="After food"), med("Amlodipine", ("09:00",), start),
            med("Vitamin D3", ("13:00",), start, food="With food"), med("Atorvastatin", ("21:00",), start)]
    log, moods = {}, {}
    for i in range(7, -1, -1):
        day = now.date() - timedelta(days=i)
        taken = {}
        for m, hhmm in app.doses_for_day(meds, day):
            planned = datetime.combine(day, app.time.fromisoformat(hhmm), tzinfo=now.tzinfo)
            if day == now.date() and planned > now:
                continue
            if rng.random() < 0.88:
                taken[app.dose_key(m["id"], hhmm)] = (planned + timedelta(minutes=rng.randint(-5, 25))).strftime("%H:%M")
        log[day.isoformat()] = taken
        if i > 0 and rng.random() < 0.7:
            moods[day.isoformat()] = rng.choice(app.MOODS[:4])
    return meds, log, moods


# ---------------------------------------------------------------- status -----

def test_status_colours_follow_the_clock():
    planned = NOW.replace(hour=14, minute=0)
    assert app.dose_status(planned, None, planned - timedelta(minutes=1), 60) == "upcoming"   # yellow
    assert app.dose_status(planned, None, planned + timedelta(minutes=30), 60) == "due"       # yellow
    assert app.dose_status(planned, None, planned + timedelta(minutes=61), 60) == "missed"    # red
    assert app.dose_status(planned, "14:05", planned + timedelta(hours=5), 60) == "taken"     # green


def test_checklist_marks_morning_missed_and_evening_upcoming():
    m = med()
    rows = app.build_checklist([m], {}, NOW, 60)
    assert [(r["time"], r["status"]) for r in rows] == [("08:00", "missed"), ("20:00", "upcoming")]


def test_ticking_a_dose_turns_it_green():
    m = med()
    log = {NOW.date().isoformat(): {app.dose_key(m["id"], "08:00"): "08:10"}}
    rows = app.build_checklist([m], log, NOW, 60)
    assert rows[0]["status"] == "taken" and rows[0]["taken_at"] == "08:10"


def test_a_dose_hours_away_cannot_be_ticked_yet():
    m = med(times=("20:00", "14:30"))
    rows = {r["time"]: r for r in app.build_checklist([m], {}, NOW, 60)}
    assert app.too_early(rows["20:00"], NOW)          # 6 hours away: locked
    assert not app.too_early(rows["14:30"], NOW)      # 30 minutes away: allowed


def test_checklist_groups_by_time_of_day():
    assert [app.time_of_day(t) for t in ("08:00", "13:00", "19:00", "22:00")] == ["Morning", "Afternoon", "Evening", "Night"]


# ------------------------------------------------------------- adherence -----

def test_weekly_score_counts_only_doses_that_are_due():
    m = med(times=("08:00",))
    log = {(NOW.date() - timedelta(days=i)).isoformat(): {app.dose_key(m["id"], "08:00"): "08:00"} for i in range(1, 7)}
    rows, score, taken, counted = app.weekly_summary([m], log, NOW, 60)
    assert len(rows) == 7
    assert (taken, counted) == (6, 7)          # today's 8 AM dose was missed
    assert score == 86


def test_upcoming_doses_do_not_lower_the_score():
    m = med(times=("20:00",))
    _, score, taken, counted = app.weekly_summary([m], {}, NOW.replace(hour=9), 60)
    assert counted == 6                        # 6 past days, tonight's dose not counted yet


def test_medicine_added_late_in_the_day_is_not_counted_as_missed():
    m = med(times=("08:00", "21:00"), start=NOW.date(), from_time="13:30")
    rows = app.build_checklist([m], {}, NOW, 60)
    assert [r["time"] for r in rows] == ["21:00"]
    assert app.weekly_summary([m], {}, NOW, 60)[3] == 0


def test_streak_counts_perfect_days_back_from_yesterday():
    m = med(times=("08:00",))
    log = {(NOW.date() - timedelta(days=i)).isoformat(): {app.dose_key(m["id"], "08:00"): "08:00"} for i in range(1, 4)}
    assert app.perfect_day_streak([m], log, NOW, 60) == 3


# ---------------------------------------------------------- rewards/badges ---

def test_turtle_reward_levels():
    assert app.reward_level(95, True) == "trophy"
    assert app.reward_level(85, True) == "smiley"
    assert app.reward_level(40, True) == "seedling"
    assert app.reward_level(0, False) == "seedling"


def test_every_turtle_drawing_produces_animated_svg():
    for level in app.DRAWINGS:
        svg, seconds, alt = app.turtle_reward_svg(level)
        assert svg.startswith("<svg") and 'class="s"' in svg and seconds > 1 and alt


def test_svg_turtle_circle_returns_to_start_like_real_turtle():
    t = app.SvgTurtle()
    t.circle(50)
    angle = t.angle % 360
    assert abs(t.x) < 1e-6 and abs(t.y) < 1e-6 and min(angle, 360 - angle) < 1e-6


def test_badges_for_a_good_week():
    meds, log, moods = sample_week(NOW)
    rows, score, *_ = app.weekly_summary(meds, log, NOW, 60)
    badges = app.earned_badges(meds, log, moods, rows, score, 3, NOW)
    assert badges["first"] and badges["perfect_day"] and badges["streak3"]


# ------------------------------------------------------------- validation ----

def test_validation_gives_friendly_messages():
    existing = [med("Metformin")]
    assert "Please type the medicine's name." in app.validate_medicine("  ", ["08:00"], existing)
    assert "Please choose at least one time of day." in app.validate_medicine("Aspirin", [], existing)
    assert any("already in your list" in e for e in app.validate_medicine("metformin", ["08:00"], existing))
    assert app.validate_medicine("Metformin", ["09:00"], existing, editing_id=existing[0]["id"]) == []


def test_time_helpers():
    assert app.fmt_time("08:00") == "8:00 AM" and app.fmt_time("21:30") == "9:30 PM"
    assert len(app.time_options()) == 96


# ------------------------------------------------------------ start date ----

def test_start_choices_resolve_to_dates():
    today = NOW.date()
    assert app.resolve_start("Today", None, today) == today
    assert app.resolve_start("Tomorrow", None, today) == today + timedelta(days=1)
    picked = today + timedelta(days=10)
    assert app.resolve_start("Pick a date", picked, today) == picked


def test_medicine_starting_tomorrow_is_not_on_todays_list():
    m = app.new_medicine("Aspirin", "75 mg", ["09:00"], "", NOW.date() + timedelta(days=1), "14:00", added_day=NOW.date())
    assert app.build_checklist([m], {}, NOW, 60) == []
    assert app.start_label(m, NOW.date()) == "Starts tomorrow"
    assert len(app.doses_for_day([m], NOW.date() + timedelta(days=1))) == 1     # appears tomorrow, from 9 AM


def test_past_start_date_does_not_create_missed_history():
    m = app.new_medicine("Aspirin", "75 mg", ["09:00", "21:00"], "", NOW.date() - timedelta(days=20), "14:00", added_day=NOW.date())
    assert app.start_label(m, NOW.date()).startswith("Since")
    assert app.weekly_summary([m], {}, NOW, 60)[3] == 0                         # nothing counted before it was added
    assert [r["time"] for r in app.build_checklist([m], {}, NOW, 60)] == ["21:00"]


# --------------------------------------------------------- gamification -----

def test_xp_counts_doses_on_time_bonus_perfect_days_and_moods():
    m = med(times=("08:00",), start=NOW.date() - timedelta(days=1))
    yesterday = (NOW.date() - timedelta(days=1)).isoformat()
    log = {yesterday: {app.dose_key(m["id"], "08:00"): "08:05"}}        # on time + perfect day
    assert app.xp_total([m], log, {}) == app.XP_DOSE + app.XP_ON_TIME + app.XP_PERFECT_DAY
    log[yesterday][app.dose_key(m["id"], "08:00")] = "10:00"             # late: no on-time bonus
    assert app.xp_total([m], log, {yesterday: "Good"}) == app.XP_DOSE + app.XP_PERFECT_DAY + app.XP_MOOD


def test_levels_grow_like_a_plant():
    assert app.level_for(0)[:2] == (1, "Seedling")
    assert app.level_for(260)[:2] == (3, "Sapling")
    number, name, floor, nxt = app.level_for(5000)
    assert name == "Ancient Forest" and nxt is None


def test_daily_quests_track_progress():
    m = med(times=("13:55",))
    log = {NOW.date().isoformat(): {app.dose_key(m["id"], "13:55"): "13:58"}}
    quests = app.daily_quests(app.build_checklist([m], log, NOW, 60), {NOW.date().isoformat(): "Good"}, NOW)
    assert all(q["done"] for q in quests)


def test_food_timing_is_saved_and_spoken():
    m = med(times=("13:30",), food="Before food")
    assert m["food"] == "Before food" and app.food_label(m) == "Before food"
    assert app.food_label(med(food="Something odd")) == ""      # unknown values fall back to "Any time"
    text = app.speech_text("Asha", app.build_checklist([m], {}, NOW, 60))
    assert "before food" in text


def test_common_illness_medicines_are_valid():
    for cond in app.CONDITIONS:
        for m in cond["meds"]:
            assert m["food"] in app.FOOD_OPTIONS and m["times"] and app.validate_medicine(m["name"], m["times"], []) == []


# ------------------------------------------------------------------ voice ----

def test_read_aloud_text_mentions_every_dose():
    meds, log, _ = sample_week(NOW)
    text = app.speech_text("Asha", app.build_checklist(meds, log, NOW, 60))
    assert text.startswith("Hello Asha") and all(m["name"] in text for m in meds)


# ------------------------------------------------- reminders and report -----

def test_reminders_fire_the_chosen_minutes_early_and_mention_food():
    m = med(times=("20:00",), food="After food")
    rows = app.build_checklist([m], {}, NOW, 60)
    alarm = app.reminder_alarms(rows, 10)[0]
    assert alarm["at"] == int((rows[0]["scheduled"] - timedelta(minutes=10)).timestamp() * 1000)
    assert alarm["say"].startswith("In 10 minutes") and "after food" in alarm["say"]
    assert app.reminder_alarms(rows, 0)[0]["say"].startswith("It is time for")


def test_report_has_score_food_and_escapes_names():
    m = med("<b>Bad</b>", food="Before food")
    page = app.build_report_html("Asha", 70, [m], {}, {}, NOW, 60)
    assert "Weekly adherence" in page and "Before food" in page and "age 70" in page
    assert "&lt;b&gt;Bad&lt;/b&gt;" in page and "<b>Bad</b>" not in page
