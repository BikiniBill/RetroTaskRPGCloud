# app.py
# Retro Task RPG V7.9 – Web Edition (Hybrid Streamlit + iCloud Sync)
# Single-file Streamlit app implementing: tasks with difficulties, XP/levels, streaks,
# Pomodoro, session/game-time management, Windows-only EXE launch, iCloud Drive JSON sync,
# achievements/badges, quotes, hardcore mode, scoreboard/logs, CRT retro UI, and sounds.

import os
import json
import time
import math
import random
import platform
import subprocess
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional

import streamlit as st
from streamlit.components.v1 import html

APP_TITLE = "🕹️ Retro Task RPG V7.9 – Web Edition (Hybrid Streamlit + iCloud Sync)"
VERSION = "7.9"

# -----------------------------
# Utility: Paths & iCloud logic
# -----------------------------

def windows_icloud_documents_default() -> str:
    # Common iCloud Drive path on Windows (user may need to adjust)
    # Usually: C:\\Users\\<User>\\iCloudDrive\\Documents
    home = os.path.expanduser("~")
    return os.path.join(home, "iCloudDrive", "Documents")


def macos_icloud_documents_default() -> str:
    # macOS iCloud Drive Documents folder
    # ~/Library/Mobile Documents/com~apple~CloudDocs/Documents
    home = os.path.expanduser("~")
    return os.path.join(
        home,
        "Library",
        "Mobile Documents",
        "com~apple~CloudDocs",
        "Documents",
    )


def detect_icloud_documents_path() -> str:
    system = platform.system()
    if system == "Windows":
        cand = windows_icloud_documents_default()
        return cand
    elif system == "Darwin":
        cand = macos_icloud_documents_default()
        return cand
    else:
        # Linux / Streamlit Cloud or other servers – fallback to local folder only
        return ""


# -----------------------------
# Data & Persistence
# -----------------------------

LOCAL_SAVE_DIR = os.path.join(".", "save")
LOCAL_SAVE_PATH = os.path.join(LOCAL_SAVE_DIR, "retro_task_rpg_state.json")
CLOUD_FOLDER_DEFAULT = detect_icloud_documents_path()
CLOUD_SAVE_DIR = os.path.join(CLOUD_FOLDER_DEFAULT, "RetroTaskRPG") if CLOUD_FOLDER_DEFAULT else ""
CLOUD_SAVE_PATH = os.path.join(CLOUD_SAVE_DIR, "retro_task_rpg_state.json") if CLOUD_SAVE_DIR else ""


DEFAULT_STATE = {
    "meta": {
        "version": VERSION,
        "created": datetime.utcnow().isoformat(),
        "last_opened": datetime.utcnow().isoformat(),
        "hardcore": False,
        "dead": False,
    },
    "player": {
        "name": "Player One",
        "level": 1,
        "xp": 0,
        "xp_for_next": 100,
        "streak_days": 0,
        "last_checkin": None,
        "minutes_bank": 0,  # earned play minutes
        "quotes_level_index": 0,
    },
    "timers": {
        "pomodoro_length": 25,  # minutes
        "pomodoro_start": None,  # iso
        "pomodoro_running": False,
        "pomodoro_paused_seconds": 0,
        "session_start": None,  # iso
        "session_running": False,
        "session_target_minutes": 0,
        "session_spent_seconds": 0,
    },
    "tasks": {
        "log": [],  # list of {ts, title, difficulty, xp_gain, minutes_gain}
        "counts": {"Noob": 0, "Normal": 0, "Hardcore": 0, "Höllenfeuer": 0},
    },
    "quests": {
        "daily": {
            "Power-Up Workout": {"xp": 30, "minutes": 5, "done_on": None},
            "Deep Focus 60": {"xp": 40, "minutes": 10, "done_on": None},
        },
        "weekly": {
            "NoPo Weekly": {"xp": 60, "minutes": 15, "done_on_week": None},
            "Project Push": {"xp": 80, "minutes": 20, "done_on_week": None},
        },
    },
    "achievements": {
        "level_badges": [],  # Bronze/Silver/Gold/Platinum/Diamond
        "special": [],        # list of strings
    },
    "logs": [],  # textual log lines
}


DIFF_MULTIPLIER = {"Noob": 1.0, "Normal": 1.5, "Hardcore": 2.5, "Höllenfeuer": 4.0}
HARDCORE_GLOBAL_BONUS = 1.25  # if hardcore mode enabled, multiply xp further
LEVEL_MINUTES_BONUS = 5  # minutes granted per level up (configurable)

LEVEL_BADGES = [
    (5, "Bronze"), (10, "Silver"), (20, "Gold"), (30, "Platinum"), (40, "Diamond")
]

RETRO_QUOTES = [
    "\u2694\ufe0f \u201cIt\'s dangerous to go alone! Take this.\u201d",
    "\ud83d\udd2e \u201cFinish him!\u201d",
    "\ud83d\udca5 \u201cHadouken!\u201d",
    "\ud83d\udc7e \u201cDo a barrel roll!\u201d",
    "\ud83c\udfae \u201cAll your base are belong to us.\u201d",
]

SOUNDS = {
    "click": "sounds/click.wav",
    "popup": "sounds/popup.wav",
    "levelup": "sounds/levelup.wav",
    "warning": "sounds/warning.wav",
}


def ensure_dirs():
    os.makedirs(LOCAL_SAVE_DIR, exist_ok=True)
    if CLOUD_SAVE_DIR:
        try:
            os.makedirs(CLOUD_SAVE_DIR, exist_ok=True)
        except Exception:
            pass


def safe_read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        st.warning(f"Konnte Datei nicht lesen: {path} – {e}")
    return None


def safe_write_json(path: str, data: Dict[str, Any]):
    try:
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.warning(f"Konnte Datei nicht schreiben: {path} – {e}")


def load_state() -> Dict[str, Any]:
    ensure_dirs()
    # Prefer iCloud if available and file exists there
    cloud_first = safe_read_json(CLOUD_SAVE_PATH) if CLOUD_SAVE_PATH else None
    if cloud_first:
        return cloud_first
    # Fallback local
    local = safe_read_json(LOCAL_SAVE_PATH)
    if local:
        return local
    return DEFAULT_STATE.copy()


def save_state(state: Dict[str, Any]):
    # Always save local
    safe_write_json(LOCAL_SAVE_PATH, state)
    # Mirror to iCloud if available
    if CLOUD_SAVE_PATH:
        safe_write_json(CLOUD_SAVE_PATH, state)


# -----------------------------
# Game Mechanics Helpers
# -----------------------------

def add_log(state: Dict[str, Any], text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state["logs"].append(f"[{ts}] {text}")


def add_xp(state: Dict[str, Any], amount: int):
    if amount <= 0:
        return
    state["player"]["xp"] += amount
    # Level up loop
    leveled = 0
    while state["player"]["xp"] >= state["player"]["xp_for_next"]:
        state["player"]["xp"] -= state["player"]["xp_for_next"]
        state["player"]["level"] += 1
        state["player"]["xp_for_next"] = int(math.ceil(state["player"]["xp_for_next"] * 1.25))
        state["player"]["minutes_bank"] += LEVEL_MINUTES_BONUS
        leveled += 1
    if leveled:
        add_log(state, f"Level-Up x{leveled}! +{LEVEL_MINUTES_BONUS*leveled} Min Spielzeit")
        maybe_add_level_badge(state)
        play_sound("levelup")


def maybe_add_level_badge(state: Dict[str, Any]):
    lvl = state["player"]["level"]
    have = set(state["achievements"]["level_badges"]) if state["achievements"]["level_badges"] else set()
    for thresh, name in LEVEL_BADGES:
        if lvl >= thresh and name not in have:
            state["achievements"]["level_badges"].append(name)
            add_log(state, f"Badge freigeschaltet: {name}")


def complete_task(state: Dict[str, Any], title: str, difficulty: str):
    base_xp = 10
    xp = base_xp * DIFF_MULTIPLIER.get(difficulty, 1.0)
    if state["meta"]["hardcore"]:
        xp *= HARDCORE_GLOBAL_BONUS
    xp = int(round(xp))

    minutes_gain = 1 * DIFF_MULTIPLIER.get(difficulty, 1.0)
    minutes_gain = int(round(minutes_gain))

    state["tasks"]["counts"][difficulty] += 1
    state["tasks"]["log"].append({
        "ts": datetime.utcnow().isoformat(),
        "title": title,
        "difficulty": difficulty,
        "xp_gain": xp,
        "minutes_gain": minutes_gain,
    })
    add_xp(state, xp)
    state["player"]["minutes_bank"] += minutes_gain
    add_log(state, f"Task erledigt: {title} [{difficulty}] +{xp} XP, +{minutes_gain} Min")
    check_special_achievements(state)


def check_special_achievements(state: Dict[str, Any]):
    total_tasks = sum(state["tasks"]["counts"].values())
    xp_total = state["player"]["level"] * 0  # placeholder; using current xp only isn't cumulative
    # Achievements for tasks count
    milestones = [10, 25, 50, 100, 200]
    for m in milestones:
        name = f"Grinder {m}"
        if total_tasks >= m and name not in state["achievements"]["special"]:
            state["achievements"]["special"].append(name)
            add_log(state, f"Achievement freigeschaltet: {name}")


# -----------------------------
# Streaks, Quests, Game Over
# -----------------------------

def today_str() -> str:
    return date.today().isoformat()


def week_id(dt: Optional[date] = None) -> str:
    d = dt or date.today()
    year, week, _ = d.isocalendar()
    return f"{year}-W{week}"


def check_in(state: Dict[str, Any]):
    last = state["player"].get("last_checkin")
    today = today_str()
    if last == today:
        return False
    # Streak logic
    if last:
        prev = datetime.fromisoformat(last).date()
        if (date.today() - prev) == timedelta(days=1):
            state["player"]["streak_days"] += 1
        else:
            state["player"]["streak_days"] = 1
    else:
        state["player"]["streak_days"] = 1
    state["player"]["last_checkin"] = today
    add_log(state, f"Daily Check-in! Streak: {state['player']['streak_days']} Tage")
    # Streak bonuses
    if state["player"]["streak_days"] in (3, 7, 14):
        add_xp(state, 20)
        state["player"]["minutes_bank"] += 5
        play_sound("popup")
        add_log(state, f"Streak-Bonus! +20 XP, +5 Min")
    return True


def reset_if_game_over(state: Dict[str, Any]):
    # If last_opened > 7 days ago -> GAME OVER
    last_iso = state["meta"].get("last_opened")
    if not last_iso:
        return
    try:
        last = datetime.fromisoformat(last_iso)
    except Exception:
        return
    if datetime.utcnow() - last > timedelta(days=7):
        state["meta"]["dead"] = True


def respawn(state: Dict[str, Any]):
    # Hard reset except meta version
    meta_keep = {"version": state["meta"].get("version", VERSION)}
    state.clear()
    state.update(DEFAULT_STATE.copy())
    state["meta"].update(meta_keep)
    state["meta"]["dead"] = False
    add_log(state, "Respawn! Zurück auf Anfang.")


def claim_daily_quest(state: Dict[str, Any], name: str):
    q = state["quests"]["daily"].get(name)
    if not q:
        return
    if q["done_on"] == today_str():
        return
    add_xp(state, q["xp"])
    state["player"]["minutes_bank"] += q["minutes"]
    q["done_on"] = today_str()
    add_log(state, f"Daily Quest abgeschlossen: {name} +{q['xp']} XP, +{q['minutes']} Min")
    play_sound("popup")


def claim_weekly_quest(state: Dict[str, Any], name: str):
    q = state["quests"]["weekly"].get(name)
    if not q:
        return
    wk = week_id()
    if q["done_on_week"] == wk:
        return
    add_xp(state, q["xp"])
    state["player"]["minutes_bank"] += q["minutes"]
    q["done_on_week"] = wk
    add_log(state, f"Weekly Quest abgeschlossen: {name} +{q['xp']} XP, +{q['minutes']} Min")
    play_sound("popup")


# -----------------------------
# Timers (Pomodoro & Session)
# -----------------------------

def now_ts() -> float:
    return time.time()


def seconds_since(iso: Optional[str]) -> int:
    if not iso:
        return 0
    try:
        dt = datetime.fromisoformat(iso)
        return int((datetime.now() - dt).total_seconds())
    except Exception:
        return 0


def pomodoro_remaining_seconds(state: Dict[str, Any]) -> int:
    if not state["timers"]["pomodoro_running"]:
        return 0
    start = state["timers"].get("pomodoro_start")
    length_min = state["timers"].get("pomodoro_length", 25)
    elapsed = seconds_since(start)
    remaining = max(0, length_min * 60 - elapsed - state["timers"].get("pomodoro_paused_seconds", 0))
    return remaining


def start_pomodoro(state: Dict[str, Any]):
    if state["timers"]["pomodoro_running"]:
        return
    state["timers"]["pomodoro_start"] = datetime.now().isoformat()
    state["timers"]["pomodoro_paused_seconds"] = 0
    state["timers"]["pomodoro_running"] = True
    add_log(state, f"Pomodoro gestartet: {state['timers']['pomodoro_length']} min")


def stop_pomodoro(state: Dict[str, Any]):
    if not state["timers"]["pomodoro_running"]:
        return
    state["timers"]["pomodoro_running"] = False
    rem = pomodoro_remaining_seconds(state)
    spent = max(0, state["timers"]["pomodoro_length"] * 60 - rem)
    add_log(state, f"Pomodoro gestoppt: {spent//60}m {spent%60}s")


def pomodoro_block_index(state: Dict[str, Any]) -> int:
    # 5 blocks, blink current
    length = state["timers"].get("pomodoro_length", 25)
    secs = length * 60
    elapsed = max(0, secs - pomodoro_remaining_seconds(state))
    block = min(4, int((elapsed / secs) * 5)) if secs > 0 else 0
    return block


def start_session(state: Dict[str, Any], minutes: int):
    if state["timers"]["session_running"] or minutes <= 0:
        return
    if state["player"]["minutes_bank"] < minutes:
        add_log(state, "Nicht genug Spielzeit im Konto.")
        play_sound("warning")
        return
    state["player"]["minutes_bank"] -= minutes
    state["timers"]["session_target_minutes"] = minutes
    state["timers"]["session_start"] = datetime.now().isoformat()
    state["timers"]["session_spent_seconds"] = 0
    state["timers"]["session_running"] = True
    add_log(state, f"Spielzeit gestartet: {minutes} Minuten")


def stop_session(state: Dict[str, Any]):
    if not state["timers"]["session_running"]:
        return
    spent = seconds_since(state["timers"]["session_start"]) + state["timers"]["session_spent_seconds"]
    target = state["timers"]["session_target_minutes"] * 60
    rem = max(0, target - spent)
    # credit back remaining seconds as minutes (rounded down)
    credit_min = rem // 60
    if credit_min:
        state["player"]["minutes_bank"] += credit_min
    state["timers"]["session_running"] = False
    add_log(state, f"Spielzeit gestoppt. Zurückerstattet: {credit_min} Minuten")


def session_remaining_seconds(state: Dict[str, Any]) -> int:
    if not state["timers"]["session_running"]:
        return 0
    spent = seconds_since(state["timers"]["session_start"]) + state["timers"]["session_spent_seconds"]
    return max(0, state["timers"]["session_target_minutes"] * 60 - spent)


# -----------------------------
# Sounds (HTML5 audio injection)
# -----------------------------

def play_sound(kind: str):
    path = SOUNDS.get(kind)
    if not path or not os.path.exists(path):
        return
    # Inject a tiny autoplay audio tag. Browsers may block if not user-initiated.
    with st.container():
        html(f"""
        <audio autoplay>
            <source src="{path}" type="audio/wav">
        </audio>
        """, height=0)


# -----------------------------
# CRT / Retro CSS
# -----------------------------
RETRO_CSS = """
<style>
@keyframes flicker { 0% {opacity:1} 50% {opacity:0.98} 100% {opacity:1} }
@keyframes scanlines { from { background-position: 0 0; } to { background-position: 0 4px; } }

:root{ --neon:#00ff88; --bg:#000000; --muted:#00ff8877; }
html, body, .stApp { background: var(--bg)!important; }

.crt {
  color: var(--neon);
  font-family: "Courier New", monospace;
  text-shadow: 0 0 5px var(--neon), 0 0 10px var(--neon);
  border: 1px solid var(--neon);
  border-radius: 10px;
  padding: 12px 16px;
  position: relative;
  box-shadow: 0 0 20px #00ff8844 inset, 0 0 20px #00ff8844;
  animation: flicker 2s infinite;
}
.crt:before {
  content:"";
  position:absolute; inset:0; pointer-events:none;
  background: repeating-linear-gradient(transparent, transparent 2px, rgba(0,255,136,0.05) 3px);
  animation: scanlines 1s linear infinite;
  border-radius:10px;
}

.neon-btn {
  display:inline-block; padding:8px 12px; margin:4px 6px;
  color: var(--bg); background: var(--neon);
  border:none; border-radius:8px; font-weight:bold; font-family: "Courier New", monospace;
  box-shadow: 0 0 10px var(--neon), 0 0 20px var(--neon);
}
.small { font-size: 12px; opacity: 0.9; }
.progress {
  font-family: "Courier New", monospace; white-space: pre; font-size: 14px;
}
.blink { animation: flicker 0.8s infinite; }
</style>
"""

# -----------------------------
# UI Helpers
# -----------------------------

def pixel_bar(progress: float, width: int = 30) -> str:
    # progress in [0,1]
    filled = int(round(progress * width))
    return "█" * filled + "▁" * (width - filled)


def header_section(state: Dict[str, Any]):
    st.markdown(RETRO_CSS, unsafe_allow_html=True)
    st.markdown(f"<div class='crt'><h1>{APP_TITLE}</h1></div>", unsafe_allow_html=True)

    with st.container():
        c1, c2, c3 = st.columns([2,2,1])
        with c1:
            st.markdown("## 👤 Charakter")
            state["player"]["name"] = st.text_input("Name", value=state["player"]["name"])  # simple avatar-less
            st.write(f"Level: {state['player']['level']}")
            xp = state["player"]["xp"]
            xpn = state["player"]["xp_for_next"]
            bar = pixel_bar(min(1.0, xp/xpn))
            st.markdown(f"XP: {xp} / {xpn}")
            st.markdown(f"<div class='progress crt'>{bar}</div>", unsafe_allow_html=True)
            st.write(f"Streak: {state['player']['streak_days']} Tage")
            st.write(f"Hardcore: {'Aktiv' if state['meta']['hardcore'] else 'Aus'}")
        with c2:
            st.markdown("## ⚙️ Einstellungen & Sync")
            system = platform.system()
            st.caption(f"System: {system}")
            st.write(f"Lokaler Speicherpfad: `{LOCAL_SAVE_PATH}`")
            if CLOUD_SAVE_PATH:
                st.write(f"iCloud-Speicherpfad: `{CLOUD_SAVE_PATH}`")
            else:
                st.write("iCloud-Speicherpfad: (nicht verfügbar auf diesem System)")

            # Hardcore toggle (one-way)
            if not state["meta"]["hardcore"]:
                if st.button("☠️ Hardcore-Modus dauerhaft aktivieren", type="primary"):
                    state["meta"]["hardcore"] = True
                    add_log(state, "Hardcore-Modus aktiviert!")
                    play_sound("popup")

            # Daily check-in
            if st.button("✅ Daily Check-in"):
                if check_in(state):
                    play_sound("popup")
            
            # Save / Load controls
            save_col, load_col = st.columns(2)
            with save_col:
                if st.button("💾 Speichern"):
                    save_state(state)
                    add_log(state, "Spielstand gespeichert (lokal + iCloud, falls verfügbar)")
            with load_col:
                if st.button("📂 Neu laden (bevorzugt iCloud)"):
                    loaded = load_state()
                    state.clear(); state.update(loaded)
                    add_log(state, "Spielstand neu geladen")

        with c3:
            st.markdown("## 🕒 Konto")
            st.write(f"Bank: {state['player']['minutes_bank']} Min")
            if st.button("↺ Respawn (Reset)"):
                respawn(state)



def pomodoro_section(state: Dict[str, Any]):
    st.markdown("### ⏱️ Pomodoro-Timer", unsafe_allow_html=True)
    with st.container():
        lcol, rcol = st.columns([2,1])
        with lcol:
            state["timers"]["pomodoro_length"] = int(st.slider("Länge (Min)", 5, 60, state["timers"]["pomodoro_length"]))
            rem = pomodoro_remaining_seconds(state)
            mins, secs = rem // 60, rem % 60
            blocks = ["[ ]"]*5
            bi = pomodoro_block_index(state)
            for i in range(5):
                if i < bi:
                    blocks[i] = "[█]"
                elif i == bi and state["timers"]["pomodoro_running"]:
                    blocks[i] = "<span class='blink'>[█]</span>"
            st.markdown(f"<div class='crt'>Verbleibend: **{mins:02d}:{secs:02d}** | Blöcke: {' '.join(blocks)}</div>", unsafe_allow_html=True)
        with rcol:
            b1, b2 = st.columns(2)
            with b1:
                if st.button("▶️ Start"):
                    start_pomodoro(state)
            with b2:
                if st.button("⏹️ Stop"):
                    stop_pomodoro(state)



def tasks_section(state: Dict[str, Any]):
    st.markdown("### 📝 Aufgaben", unsafe_allow_html=True)
    with st.container():
        task = st.text_input("Neue Aufgabe (Titel)", key="task_title")
        cols = st.columns(4)
        labels = ["Noob", "Normal", "Hardcore", "Höllenfeuer"]
        for i, label in enumerate(labels):
            if cols[i].button(label, key=f"btn_{label}"):
                if task.strip():
                    complete_task(state, task.strip(), label)
                    play_sound("click")
                else:
                    st.warning("Bitte zuerst einen Aufgabentitel eingeben.")
    # recent tasks
    if state["tasks"]["log"]:
        st.markdown("#### Letzte Aufgaben")
        for item in list(reversed(state["tasks"]["log"]))[:10]:
            st.markdown(
                f"- {item['ts']} · **{item['title']}** [{item['difficulty']}] +{item['xp_gain']} XP, +{item['minutes_gain']} Min"
            )



def session_section(state: Dict[str, Any]):
    st.markdown("### 🎮 Spielzeit (Session)")
    with st.container():
        left, right = st.columns([2,1])
        with left:
            rem = session_remaining_seconds(state)
            mins, secs = rem // 60, rem % 60
            st.markdown(f"<div class='crt'>Countdown: **{mins:02d}:{secs:02d}**</div>", unsafe_allow_html=True)
            cols = st.columns(3)
            minutes = cols[0].number_input("Minuten einsetzen", min_value=5, max_value=300, value=15, step=5)
            if cols[1].button("▶️ Start Session"):
                start_session(state, int(minutes))
            if cols[2].button("⏹️ Stop Session (Rest gutschreiben)"):
                stop_session(state)
        with right:
            # Windows-only EXE Launch
            system = platform.system()
            st.markdown("**Start das Spiel (.exe)**")
            if system == "Windows":
                exe_path = st.text_input("Pfad zur .exe", value=st.session_state.get("exe_path", ""))
                st.session_state["exe_path"] = exe_path
                if st.button("🚀 Starten (Windows)"):
                    if exe_path and os.path.exists(exe_path) and exe_path.lower().endswith(".exe"):
                        try:
                            os.startfile(exe_path)
                            add_log(state, f"EXE gestartet: {exe_path}")
                        except Exception as e:
                            st.error(f"Konnte .exe nicht starten: {e}")
                            play_sound("warning")
                    else:
                        st.warning("Ungültiger Pfad oder Datei nicht gefunden.")
            else:
                st.caption("Nur lokal auf Windows verfügbar. Hier: Simulation aktiv.")
                st.markdown("<div class='crt small'>🎮 Simulation: Stelle dir vor, dein Spiel läuft jetzt!</div>", unsafe_allow_html=True)



def quests_section(state: Dict[str, Any]):
    st.markdown("### 🏆 Quests")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Daily Quests")
        for name, q in state["quests"]["daily"].items():
            done = q["done_on"] == today_str()
            cols = st.columns([3,1])
            cols[0].markdown(f"**{name}** · +{q['xp']} XP, +{q['minutes']} Min" + (" · ✅" if done else ""))
            if not done and cols[1].button("Claim", key=f"dq_{name}"):
                claim_daily_quest(state, name)
    with c2:
        st.markdown("#### Weekly Quests")
        for name, q in state["quests"]["weekly"].items():
            done = q["done_on_week"] == week_id()
            cols = st.columns([3,1])
            cols[0].markdown(f"**{name}** · +{q['xp']} XP, +{q['minutes']} Min" + (" · ✅" if done else ""))
            if not done and cols[1].button("Claim", key=f"wq_{name}"):
                claim_weekly_quest(state, name)



def scoreboard_tabs(state: Dict[str, Any]):
    tabs = st.tabs(["📜 Scoreboard", "🎖️ Achievements", "📗 Anleitung"])
    with tabs[0]:
        counts = state["tasks"]["counts"]
        st.markdown("#### Aufgaben-Statistik")
        st.write({k: int(v) for k, v in counts.items()})
        st.markdown("#### Logs")
        if state["logs"]:
            for line in reversed(state["logs"][-200:]):
                st.markdown(f"<div class='small'>{line}</div>", unsafe_allow_html=True)
        else:
            st.write("Noch keine Logs.")
    with tabs[1]:
        st.markdown("#### Level-Badges")
        if state["achievements"]["level_badges"]:
            st.write(", ".join(state["achievements"]["level_badges"]))
        else:
            st.write("Noch keine Badges.")
        st.markdown("#### Sonder-Achievements")
        if state["achievements"]["special"]:
            for a in state["achievements"]["special"]:
                st.markdown(f"- {a}")
        else:
            st.write("Noch keine Sonder-Achievements.")
    with tabs[2]:
        st.markdown("""
        ### Anleitung
        - **Aufgaben** mit Schwierigkeitsgrad anlegen → XP und Spielminuten verdienen.
        - **Level-Ups** geben automatisch +5 Minuten Spielzeit.
        - **Daily/Weekly Quests** einzeln pro Tag/Woche claimen.
        - **Streak** via Daily Check-in pflegen (Boni bei 3/7/14 Tagen).
        - **Spielzeit starten** und ggf. **.exe** (nur Windows) lokal starten.
        - **Speichern** schreibt lokal **und** in iCloud-Drive (falls vorhanden). Beim Laden wird iCloud bevorzugt.
        - **Hardcore** erhöht XP-Multiplikator global und ist dauerhaft.
        - **Game Over** nach 7 Tagen Inaktivität → Respawn möglich.
        """)



def quotes_footer(state: Dict[str, Any]):
    idx = state["player"].get("quotes_level_index", 0)
    # Change quote by level
    idx = state["player"]["level"] % len(RETRO_QUOTES)
    q = RETRO_QUOTES[idx]
    st.markdown(f"<div class='crt' style='margin-top:12px;'>🗨️ {q}</div>", unsafe_allow_html=True)


# -----------------------------
# Main App
# -----------------------------

def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="🕹️", layout="wide")

    # Keep a single state dict in session_state
    if "state" not in st.session_state:
        st.session_state["state"] = load_state()
    state = st.session_state["state"]

    # Game over check
    reset_if_game_over(state)
    if state["meta"]["dead"]:
        st.markdown("""
        <div class='crt'>
        <h2>☠️ You seem to be dead! GAME OVER</h2>
        <p>7 Tage Inaktivität erkannt. Du kannst einen <b>Respawn</b> durchführen.</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔄 Respawn jetzt"):
            respawn(state)
            save_state(state)
        return

    # Update last_opened
    state["meta"]["last_opened"] = datetime.utcnow().isoformat()

    # Header and sections
    header_section(state)
    pomodoro_section(state)
    tasks_section(state)
    session_section(state)
    quests_section(state)
    scoreboard_tabs(state)
    quotes_footer(state)

    # Auto-save small throttle (avoid too frequent writes)
    if st.button("💾 Sofort speichern"):
        save_state(state)
        st.success("Gespeichert (lokal + iCloud, falls verfügbar)")


if __name__ == "__main__":
    main()

