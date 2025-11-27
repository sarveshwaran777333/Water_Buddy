#FIREBASE_URL = "https://waterhydrator-9ecad-default-rtdb.asia-southeast1.firebasedatabase.app"

"""
WaterBuddy - Streamlit app using Firebase Realtime DB REST API (no firebase_admin)
Features in this full version:
- Username/password signup + login (no email)
- Left navigation pane + theme selector (Light / Aqua / Dark)
- Age-based hydration goals and editable profile
- Daily logging (+250 quick log, custom add, reset/end-day save to history)
- Lottie animated progress (optional)
- Weekly (7-day) grouped bar & Monthly (30-day) trend line
- Weekly % vs Goal and grouped hydrated / not-hydrated bars
- Small embedded 2D mini game (click-the-droplet)
- Firebase REST helpers with small optimisations

Instructions: Replace FIREBASE_URL with your Firebase RTDB URL. Ensure rules allow REST reads/writes for the path used in this demo.
"""

import streamlit as st
import requests
import json
import datetime
import time
import random
import os
from typing import Any, Dict

# Visualization libs
import matplotlib.pyplot as plt
import plotly.graph_objects as go

# Optional Lottie
try:
    from streamlit_lottie import st_lottie
except Exception:
    st_lottie = None

# -----------------------
# Configuration
# -----------------------
FIREBASE_URL = "https://waterhydrator-9ecad-default-rtdb.asia-southeast1.firebasedatabase.app"
USERS_NODE = "users"
DATE_STR = datetime.date.today().isoformat()

AGE_GOALS_ML = {
    "6-12": 1600,
    "13-18": 2000,
    "19-50": 2500,
    "65+": 2000,
}

DEFAULT_QUICK_LOG_ML = 250
CUPS_TO_ML = 236.588
REQUEST_TIMEOUT = 8  # seconds

TIPS = [
    "Keep a filled water bottle visible on your desk.",
    "Drink a glass (250 ml) after every bathroom break.",
    "Start your day with a glass of water.",
    "Add lemon or cucumber for natural flavor.",
    "Set small hourly reminders and sip regularly.",
]

# -----------------------
# Firebase REST helpers
# -----------------------
def firebase_url(path: str) -> str:
    path = path.strip("/")
    return f"{FIREBASE_URL}/{path}.json"


def firebase_get(path: str) -> Any:
    url = firebase_url(path)
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                return None
        return None
    except requests.RequestException:
        return None


def firebase_post(path: str, value: Any) -> Any:
    url = firebase_url(path)
    try:
        r = requests.post(url, data=json.dumps(value), timeout=REQUEST_TIMEOUT)
        if r.status_code in (200, 201):
            try:
                return r.json()
            except ValueError:
                return None
        return None
    except requests.RequestException:
        return None


def firebase_patch(path: str, value_dict: Dict) -> bool:
    url = firebase_url(path)
    try:
        r = requests.patch(url, data=json.dumps(value_dict), timeout=REQUEST_TIMEOUT)
        return r.status_code in (200, 201)
    except requests.RequestException:
        return False

# Lightweight put for overwriting a node
def firebase_put(path: str, value: Any) -> bool:
    url = firebase_url(path)
    try:
        r = requests.put(url, data=json.dumps(value), timeout=REQUEST_TIMEOUT)
        return r.status_code in (200, 201)
    except requests.RequestException:
        return False

# -----------------------
# User helpers
# -----------------------

def find_user_by_username(username: str):
    """Return (uid, user_obj) if found, else (None, None)."""
    data = firebase_get(USERS_NODE)
    if not isinstance(data, dict):
        return None, None
    for uid, rec in data.items():
        if isinstance(rec, dict) and rec.get("username") == username:
            return uid, rec
    return None, None


def create_user(username: str, password: str):
    """Create user - returns uid string on success, None on failure."""
    if not username or not password:
        return None
    # Ensure uniqueness
    uid, _ = find_user_by_username(username)
    if uid:
        return None
    payload = {
        "username": username,
        "password": password,   # plaintext for demo; use hashing in production
        "created_at": DATE_STR,
        "profile": {
            "age_group": "19-50",
            "user_goal_ml": AGE_GOALS_ML["19-50"]
        },
        "days": {},
        "todays_intake_ml": 0
    }
    res = firebase_post(USERS_NODE, payload)
    if isinstance(res, dict) and "name" in res:
        return res["name"]
    return None


def validate_login(username: str, password: str):
    """Return (True, uid) if credentials match, else (False, None)."""
    uid, rec = find_user_by_username(username)
    if uid and isinstance(rec, dict) and rec.get("password") == password:
        return True, uid
    return False, None

# -----------------------
# Intake & profile helpers
# -----------------------

def get_today_intake(uid: str):
    if not uid:
        return 0
    path = f"{USERS_NODE}/{uid}/days/{DATE_STR}/intake"
    val = firebase_get(path)
    if isinstance(val, (int, float)):
        return int(val)
    # fallback to todays_intake_ml
    user_root = firebase_get(f"{USERS_NODE}/{uid}")
    if isinstance(user_root, dict):
        legacy = user_root.get("todays_intake_ml")
        if isinstance(legacy, (int, float)):
            return int(legacy)
    return 0


def set_today_intake(uid: str, ml_value: int):
    if not uid:
        return False
    ml = int(max(0, ml_value))
    path = f"{USERS_NODE}/{uid}/days/{DATE_STR}"
    return firebase_patch(path, {"intake": ml})


def reset_today_intake(uid: str):
    return set_today_intake(uid, 0)


def get_user_profile(uid: str):
    if not uid:
        return {"age_group": "19-50", "user_goal_ml": AGE_GOALS_ML["19-50"]}
    profile = firebase_get(f"{USERS_NODE}/{uid}/profile")
    if isinstance(profile, dict):
        user_goal = profile.get("user_goal_ml", AGE_GOALS_ML["19-50"])
        try:
            user_goal = int(user_goal)
        except Exception:
            user_goal = AGE_GOALS_ML["19-50"]
        return {
            "age_group": profile.get("age_group", "19-50"),
            "user_goal_ml": user_goal
        }
    return {"age_group": "19-50", "user_goal_ml": AGE_GOALS_ML["19-50"]}


def update_user_profile(uid: str, updates: dict):
    if not uid:
        return False
    return firebase_patch(f"{USERS_NODE}/{uid}/profile", updates)


def get_username_by_uid(uid: str):
    rec = firebase_get(f"{USERS_NODE}/{uid}")
    if isinstance(rec, dict):
        return rec.get("username", "user")
    return "user"

# -----------------------
# Graph Helpers
# -----------------------

def get_all_days(uid: str):
    if not uid:
        return {}
    path = f"{USERS_NODE}/{uid}/days"
    data = firebase_get(path)
    if isinstance(data, dict):
        return data
    return {}


def get_last_n_days_data_from_days(days_obj: dict, n: int):
    today = datetime.date.today()
    labels = []
    values = []
    dates = []
    for i in range(n-1, -1, -1):
        day = today - datetime.timedelta(days=i)
        key = day.strftime("%Y-%m-%d")
        label = day.strftime("%b %d")
        val = 0
        if isinstance(days_obj, dict) and key in days_obj:
            rec = days_obj.get(key)
            if isinstance(rec, dict):
                val = int(rec.get("intake", 0))
            elif isinstance(rec, (int, float)):
                val = int(rec)
        labels.append(label)
        values.append(val)
        dates.append(key)
    return labels, values, dates


def show_week_month_graphs(uid: str, user_goal: int):
    days_obj = get_all_days(uid)

    # Weekly (7 days) grouped hydrated vs not-hydrated bars
    labels7, vals7, dates7 = get_last_n_days_data_from_days(days_obj, 7)
    not_hyd7 = [max(user_goal - v, 0) for v in vals7]

    fig1 = go.Figure(data=[
        go.Bar(name='Hydrated', x=labels7, y=vals7),
        go.Bar(name='Not Hydrated', x=labels7, y=not_hyd7)
    ])
    fig1.update_layout(barmode='group', title='Last 7 days: Hydrated vs Not Hydrated', xaxis_title='Day', yaxis_title='ml', height=360)

    st.plotly_chart(fig1, use_container_width=True)

    # Weekly percentage
    total_week = sum(vals7)
    perc_week = (total_week / (user_goal * 7)) * 100 if user_goal and user_goal * 7 > 0 else 0
    st.write(f"Week total: **{total_week} ml** — {perc_week:.1f}% of 7-day goal ({user_goal*7} ml)")

    # Monthly (30 days) trend line with goal line
    labels30, vals30, dates30 = get_last_n_days_data_from_days(days_obj, 30)

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=labels30, y=vals30, mode='lines+markers', name='Intake'))
    fig2.add_trace(go.Scatter(x=labels30, y=[user_goal]*len(labels30), mode='lines', name='Daily Goal', line=dict(dash='dash')))
    fig2.update_layout(title='30-Day Hydration Trend', xaxis_title='Day', yaxis_title='ml', height=380)

    st.plotly_chart(fig2, use_container_width=True)

# -----------------------
# SVG Bottle helper
# -----------------------

def generate_bottle_svg(percent: float, width:int=140, height:int=360) -> str:
    pct = max(0.0, min(100.0, float(percent)))
    inner_w = width - 36
    inner_h = height - 80
    fill_h = (pct / 100.0) * inner_h
    empty_h = inner_h - fill_h

    svg = f"""
<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
  <rect x="12" y="12" rx="20" ry="20" width="{width-24}" height="{height-24}" fill="none" stroke="#5dade2" stroke-width="3"/>
  <rect x="18" y="18" width="{inner_w}" height="{inner_h}" rx="12" ry="12" fill="#f3fbff"/>
  <rect x="18" y="{18 + empty_h}" width="{inner_w}" height="{fill_h}" rx="12" ry="12" fill="#67b3df"/>
  <rect x="{(width/2)-18}" y="0" width="36" height="18" rx="4" ry="4" fill="#3498db"/>
  <text x="{width/2}" y="{height-8}" font-size="14" text-anchor="middle" fill="#023047" font-family="Arial">{pct:.0f}%</text>
</svg>
"""
    return svg

# -----------------------
# Theme CSS
# -----------------------

def apply_theme(theme_name: str):
    if theme_name == "Light":
        st.markdown("""
        <style>
        .stApp { background-color: #ffffff !important; color: #000000 !important; }
        .stButton>button { background-color: #e6e6e6 !important; color: #000000 !important; border-radius: 8px !important; }
        div[data-testid="metric-container"] { background-color: #f7f7f7 !important; border-radius: 12px !important; padding: 12px !important; }
        </style>
        """, unsafe_allow_html=True)
    elif theme_name == "Aqua":
        st.markdown("""
        <style>
        .stApp { background-color: #e8fbff !important; color: #004455 !important; }
        .stButton>button { background-color: #c6f3ff !important; color: #004455 !important; }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
        .stApp { background-color: #0f1720 !important; color: #e6eef6 !important; }
        .stButton>button { background-color: #1e2933 !important; color: #e6eef6 !important; }
        </style>
        """, unsafe_allow_html=True)

# -----------------------
# Lottie loader (safe)
# -----------------------

def load_lottie_safe(path: str):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

LOTTIE_PROGRESS = None
if st_lottie is not None:
    assets_path = os.path.join('assets', 'progress_bar.json')
    if os.path.exists(assets_path):
        LOTTIE_PROGRESS = load_lottie_safe(assets_path)

# -----------------------
# Mini Game (click droplet) - Embedded HTML+JS
# -----------------------

def droplet_game_html():
    return """
<div style='text-align:center;'>
  <h4>Catch the Droplet</h4>
  <p>Click the moving droplet as many times as you can in 20 seconds.</p>
  <div id='game' style='position:relative;width:100%;height:240px;border:1px solid #ddd;background:linear-gradient(#e6f7ff,#fff);overflow:hidden;'>
    <img id='drop' src='data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><circle cx="20" cy="15" r="12" fill="%23007acc" opacity="0.95"/><path d="M20 27 C18 22,22 22,20 27" fill="%23fff"/></svg>' style='position:absolute;left:10px;top:10px;cursor:pointer;'/>
  </div>
  <div style='margin-top:8px;'>
    <button id='start'>Start (20s)</button>
    <span style='margin-left:12px;'>Score: <span id='score'>0</span></span>
  </div>
</div>
<script>
  const drop = document.getElementById('drop');
  const area = document.getElementById('game');
  const scoreEl = document.getElementById('score');
  const startBtn = document.getElementById('start');
  let score = 0;
  let timer = null;
  let running = false;

  function moveDrop(){
    const rect = area.getBoundingClientRect();
    const x = Math.random() * (rect.width - 40);
    const y = Math.random() * (rect.height - 40);
    drop.style.left = x + 'px';
    drop.style.top = y + 'px';
  }

  drop.addEventListener('click', ()=>{
    if(!running) return;
    score += 1;
    scoreEl.innerText = score;
    moveDrop();
  });

  startBtn.addEventListener('click', ()=>{
    if(running) return;
    score = 0; scoreEl.innerText = '0'; running = true;
    moveDrop();
    let seconds = 20;
    startBtn.innerText = 'Running...';
    timer = setInterval(()=>{
      seconds -= 1;
      if(seconds <= 0){
        clearInterval(timer); running = false; startBtn.innerText = 'Start (20s)';
        // send score via Streamlit's URL hash (simple hacky comm)
        location.hash = 'score=' + score;
      }
    }, 1000);
  });
</script>
"""

# -----------------------
# UI: Login / Signup / Dashboard
# -----------------------

st.set_page_config(page_title='WaterBuddy', layout='wide')

if 'theme' not in st.session_state:
    st.session_state.theme = 'Light'
apply_theme(st.session_state.theme)

st.title('WaterBuddy — Hydration Tracker')

# session defaults
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'uid' not in st.session_state:
    st.session_state.uid = None
if 'page' not in st.session_state:
    st.session_state.page = 'login'
if 'nav' not in st.session_state:
    st.session_state.nav = 'Home'
if 'tip' not in st.session_state:
    st.session_state.tip = random.choice(TIPS)

# Login UI

def login_ui():
    st.header('Login')
    col1, col2 = st.columns([3,1])
    with col1:
        username = st.text_input('Username', key='login_username')
        password = st.text_input('Password', type='password', key='login_password')
    with col2:
        if st.button('Login'):
            if not username or not password:
                st.warning('Enter both username and password.')
            else:
                ok, uid = validate_login(username.strip(), password)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.uid = uid
                    st.session_state.page = 'dashboard'
                    st.success('Login successful.')
                    time.sleep(0.25)
                    st.experimental_rerun()
                else:
                    st.error('Invalid username or password.')
    st.markdown('---')
    if st.button('Create new account'):
        st.session_state.page = 'signup'
        st.experimental_rerun()

# Signup UI

def signup_ui():
    st.header('Sign Up')
    col1, col2 = st.columns([3,1])
    with col1:
        username = st.text_input('Choose a username', key='signup_username')
        password = st.text_input('Choose a password', type='password', key='signup_password')
    with col2:
        if st.button('Register'):
            if not username or not password:
                st.warning('Enter both username and password.')
            else:
                uid = create_user(username.strip(), password)
                if uid:
                    st.success('Account created. Please log in.')
                    st.session_state.page = 'login'
                    time.sleep(0.25)
                    st.experimental_rerun()
                else:
                    st.error('Username already taken or network error.')
    st.markdown('---')
    if st.button('Back to Login'):
        st.session_state.page = 'login'
        st.experimental_rerun()

# Dashboard UI

def dashboard_ui():
    uid = st.session_state.uid
    if not uid:
        st.error('Missing user id. Please login again.')
        st.session_state.logged_in = False
        st.session_state.page = 'login'
        st.experimental_rerun()
        return

    profile = get_user_profile(uid)
    intake = get_today_intake(uid)

    left_col, right_col = st.columns([1,3])

    with left_col:
        st.subheader('Navigate')
        theme_options = ['Light','Aqua','Dark']
        try:
            idx = theme_options.index(st.session_state.theme)
        except Exception:
            idx = 0
            st.session_state.theme = theme_options[0]
        theme_choice = st.selectbox('Theme', theme_options, index=idx)
        if theme_choice != st.session_state.theme:
            st.session_state.theme = theme_choice
            apply_theme(theme_choice)

        st.markdown('')
        if st.button('Home', key='nav_home'):
            st.session_state.nav = 'Home'
        if st.button('Log Water', key='nav_log'):
            st.session_state.nav = 'Log Water'
        if st.button('Settings', key='nav_settings'):
            st.session_state.nav = 'Settings'
        if st.button('Game', key='nav_game'):
            st.session_state.nav = 'Game'
        if st.button('Logout', key='nav_logout'):
            st.session_state.logged_in = False
            st.session_state.uid = None
            st.session_state.page = 'login'
            st.session_state.nav = 'Home'
            st.experimental_rerun()

        st.markdown('---')
        st.write('Tip of the day')
        st.info(st.session_state.tip)
        if st.button('New tip', key='new_tip'):
            st.session_state.tip = random.choice(TIPS)

    apply_theme(st.session_state.theme)

    with right_col:
        nav = st.session_state.nav

        if nav == 'Home':
            st.header("Today's Summary")
            st.write(f"User: **{get_username_by_uid(uid)}**")
            st.write(f"Date: {DATE_STR}")

            std_goal = AGE_GOALS_ML.get(profile.get('age_group','19-50'), 2500)
            user_goal = int(profile.get('user_goal_ml', std_goal))

            col1, col2 = st.columns(2)
            with col1:
                st.subheader('Standard target')
                st.write(f"**{std_goal} ml**")
            with col2:
                st.subheader('Your target')
                st.write(f"**{user_goal} ml**")

            remaining = max(user_goal - intake, 0)
            percent = min((intake / user_goal) * 100 if user_goal > 0 else 0, 100)

            st.metric('Total intake (ml)', f"{intake} ml", delta=f"{remaining} ml to goal" if remaining > 0 else 'Goal reached!')
            st.progress(percent / 100)

            svg = generate_bottle_svg(percent)
            st.components.v1.html(svg, height=360, scrolling=False)

            if st_lottie is not None and LOTTIE_PROGRESS is not None:
                try:
                    total_frames = 150
                    end_frame = int(total_frames * (percent / 100.0))
                    if end_frame < 1:
                        end_frame = 1
                    st_lottie(LOTTIE_PROGRESS, loop=False, start_frame=0, end_frame=end_frame, height=120)
                except Exception:
                    try:
                        st_lottie(LOTTIE_PROGRESS, loop=False, height=120)
                    except Exception:
                        pass
            else:
                st.write(f"Progress: {percent:.0f}%")

            if percent >= 100:
                st.success('Amazing — you reached your daily goal!')
            elif percent >= 75:
                st.info('Great — 75% reached!')
            elif percent >= 50:
                st.info('Nice — 50% reached!')
            elif percent >= 25:
                st.info('Good start — 25% reached!')

            st.markdown('---')
            st.subheader('Hydration History')
            show_week_month_graphs(uid, user_goal)

        elif nav == 'Log Water':
            st.header('Log Water Intake')
            st.write(f"Today's intake: **{intake} ml**")

            c1, c2, c3 = st.columns([1,1,1])
            with c1:
                if st.button(f'+{DEFAULT_QUICK_LOG_ML} ml', key='quick_log'):
                    new_val = intake + DEFAULT_QUICK_LOG_ML
                    ok = set_today_intake(uid, new_val)
                    if ok:
                        st.success(f'Added {DEFAULT_QUICK_LOG_ML} ml.')
                        st.experimental_rerun()
                    else:
                        st.error('Failed to update. Check network/DB rules.')

            with c2:
                custom = st.number_input('Custom amount (ml)', min_value=0, step=50, key='custom_input')
                if st.button('Add custom', key='add_custom'):
                    if custom <= 0:
                        st.warning('Enter amount > 0')
                    else:
                        new_val = intake + int(custom)
                        ok = set_today_intake(uid, new_val)
                        if ok:
                            st.success(f'Added {int(custom)} ml.')
                            st.experimental_rerun()
                        else:
                            st.error('Failed to update. Check network/DB rules.')

            with c3:
                if st.button('Reset today', key='reset_today'):
                    ok = reset_today_intake(uid)
                    if ok:
                        st.info('Reset successful.')
                        st.experimental_rerun()
                    else:
                        st.error('Failed to reset. Check network/DB rules.')

            st.markdown('---')
            st.subheader('Unit converter')
            cc1, cc2 = st.columns(2)
            with cc1:
                cups = st.number_input('Cups', min_value=0.0, step=0.5, key='conv_cups')
                if st.button('Convert cups → ml', key='conv_to_ml'):
                    ml_conv = round(cups * CUPS_TO_ML, 1)
                    st.success(f"{cups} cups = {ml_conv} ml")
            with cc2:
                ml_in = st.number_input('Milliliters', min_value=0.0, step=50.0, key='conv_ml')
                if st.button('Convert ml → cups', key='conv_to_cups'):
                    cups_conv = round(ml_in / CUPS_TO_ML, 2)
                    st.success(f"{ml_in} ml = {cups_conv} cups")

        elif nav == 'Settings':
            st.header('Settings & Profile')
            age_keys = list(AGE_GOALS_ML.keys())
            try:
                idx = age_keys.index(profile.get('age_group', '19-50'))
            except Exception:
                idx = 2
            age_choice = st.selectbox('Select age group', age_keys, index=idx)
            suggested = AGE_GOALS_ML[age_choice]
            st.write(f"Suggested: {suggested} ml")
            user_goal_val = st.number_input('Daily goal (ml)', min_value=500, max_value=10000, value=int(profile.get('user_goal_ml', suggested)), step=50)
            if st.button('Save profile', key='save_profile'):
                ok = update_user_profile(uid, {'age_group': age_choice, 'user_goal_ml': int(user_goal_val)})
                if ok:
                    st.success('Profile saved.')
                else:
                    st.error('Failed to save profile. Check network/DB rules.')

        elif nav == 'Game':
            st.header('Mini Game — Catch the Droplet')
            st.markdown(droplet_game_html(), unsafe_allow_html=True)
            # read score from URL hash (simple client->display hack)
            st.write('When the game ends the score appears in the browser hash: use the browser address bar to see it (hash like #score=3).')

        elif nav == 'Logout':
            st.session_state.logged_in = False
            st.session_state.uid = None
            st.session_state.page = 'login'
            st.session_state.nav = 'Home'
            st.experimental_rerun()

# -----------------------
# App routing
# -----------------------
if not st.session_state.logged_in:
    if st.session_state.page == 'signup':
        signup_ui()
    else:
        login_ui()
else:
    dashboard_ui()

