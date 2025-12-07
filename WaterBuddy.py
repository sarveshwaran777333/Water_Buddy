import streamlit as st
import streamlit.components.v1 as components
import requests
import json
from datetime import date, timedelta
import random
import base64
import matplotlib.pyplot as plt

# -----------------------
# Lottie support (optional)
# -----------------------
try:
    from streamlit_lottie import st_lottie
except Exception:
    st_lottie = None

# -----------------------
# Configuration
# -----------------------
FIREBASE_URL = "https://waterhydrator-9ecad-default-rtdb.asia-southeast1.firebasedatabase.app"
USERS_NODE = "users"
DATE_STR = date.today().isoformat()

AGE_GOALS_ML = {
    "6-12": 1600,
    "13-18": 2000,
    "19-50": 2500,
    "65+": 2000,
}

DEFAULT_QUICK_LOG_ML = 250
CUPS_TO_ML = 236.588
REQUEST_TIMEOUT = 8

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

def firebase_get(path: str):
    try:
        r = requests.get(firebase_url(path), timeout=REQUEST_TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except:
        return None

def firebase_post(path: str, value):
    try:
        r = requests.post(firebase_url(path), data=json.dumps(value), timeout=REQUEST_TIMEOUT)
        return r.json() if r.status_code in (200, 201) else None
    except:
        return None

def firebase_patch(path: str, value_dict: dict):
    try:
        r = requests.patch(firebase_url(path), data=json.dumps(value_dict), timeout=REQUEST_TIMEOUT)
        return r.status_code in (200, 201)
    except:
        return False

# -----------------------
# User/helpers
# -----------------------
def find_user_by_username(username: str):
    data = firebase_get(USERS_NODE)
    if not isinstance(data, dict):
        return None, None
    for uid, rec in data.items():
        if isinstance(rec, dict) and rec.get("username") == username:
            return uid, rec
    return None, None

def create_user(username: str, password: str):
    if not username or not password:
        return None
    uid, _ = find_user_by_username(username)
    if uid:
        return None
    payload = {
        "username": username,
        "password": password,
        "created_at": DATE_STR,
        "profile": {
            "age_group": "19-50",
            "user_goal_ml": AGE_GOALS_ML["19-50"]
        }
    }
    res = firebase_post(USERS_NODE, payload)
    return res.get("name") if isinstance(res, dict) else None

def validate_login(username: str, password: str):
    uid, rec = find_user_by_username(username)
    if uid and rec.get("password") == password:
        return True, uid
    return False, None

def get_today_intake(uid: str):
    value = firebase_get(f"{USERS_NODE}/{uid}/days/{DATE_STR}/intake")
    try:
        return int(value) if value is not None else 0
    except:
        return 0

def set_today_intake(uid: str, ml_value: int):
    ml = int(max(0, ml_value))
    return firebase_patch(f"{USERS_NODE}/{uid}/days/{DATE_STR}", {"intake": ml})

def reset_today_intake(uid: str):
    return set_today_intake(uid, 0)

def get_user_profile(uid: str):
    prof = firebase_get(f"{USERS_NODE}/{uid}/profile")
    if not isinstance(prof, dict):
        return {"age_group": "19-50", "user_goal_ml": AGE_GOALS_ML["19-50"]}
    goal = prof.get("user_goal_ml", AGE_GOALS_ML["19-50"])
    try:
        goal = int(goal)
    except:
        goal = AGE_GOALS_ML["19-50"]
    return {"age_group": prof.get("age_group", "19-50"), "user_goal_ml": goal}

def update_user_profile(uid: str, updates: dict):
    return firebase_patch(f"{USERS_NODE}/{uid}/profile", updates)

def get_past_intake(uid: str, days_count=7):
    out = {}
    today = date.today()
    for i in range(days_count):
        d = (today - timedelta(days=i)).isoformat()
        v = firebase_get(f"{USERS_NODE}/{uid}/days/{d}/intake")
        try:
            out[d] = int(v) if v else 0
        except:
            out[d] = 0
    return out

# -----------------------
# Session_state safe init
# -----------------------
st.set_page_config(page_title="WaterBuddy", layout="wide")

DEFAULT_KEYS = {
    "logged_in": False,
    "uid": None,
    "page": "login",
    "nav": "Home",
    "theme": "Light",
    "tip": random.choice(TIPS),
    "login_username": "",
    "login_password": "",
    "signup_username": "",
    "signup_password": "",
    "custom_input": 0,
}

for k, v in DEFAULT_KEYS.items():
    st.session_state.setdefault(k, v)

# -----------------------
# Theme CSS
# -----------------------
def apply_theme(theme_name: str):
    if theme_name == "Light":
        st.markdown("""
        <style>
        .stApp { background-color: #ffffff !important; color: #000000 !important; }
        </style>
        """, unsafe_allow_html=True)
    elif theme_name == "Aqua":
        st.markdown("""
        <style>
        .stApp { background-color: #e8fbff !important; color: #004455 !important; }
        </style>
        """, unsafe_allow_html=True)
    else:  # Dark
        st.markdown("""
        <style>
        .stApp { background-color: #0f1720 !important; color: #e6eef6 !important; }
        </style>
        """, unsafe_allow_html=True)

apply_theme(st.session_state.theme)

# -----------------------
# SVG Bottle
# -----------------------
def generate_bottle_svg(percent: float):
    percent = min(max(percent, 0), 100)
    height = 300
    fill_height = int((percent / 100) * height)
    return f"""
    <svg width="120" height="350" xmlns="http://www.w3.org/2000/svg">
      <rect x="30" y="20" width="60" height="300" rx="20" ry="20"
            fill="none" stroke="#3498db" stroke-width="4"/>
      <rect x="34" y="{320-fill_height}" width="52" height="{fill_height}"
            rx="16" ry="16" fill="#5dade2"/>
      <text x="60" y="340" text-anchor="middle"
            font-size="20" fill="#333">{percent:.0f}%</text>
    </svg>
    """

# -----------------------
# Plot History
# -----------------------
def plot_water_intake(intake_data, goal):
    try:
        sorted_days = sorted(intake_data.keys())
        sorted_days.reverse()
        values = [intake_data[d] for d in sorted_days]
        labels = [f"{d[5:7]}-{d[8:10]}" for d in sorted_days]

        fig, ax = plt.subplots(figsize=(9, 5))
        ax.plot(labels, values, marker="o", color="#3498db", linewidth=2)
        ax.axhline(goal, linestyle="--", color="#2ecc71", label="Goal")
        ax.set_title("Water Intake (Last 7 Days)")
        ax.set_ylabel("ml")
        ax.grid(True, alpha=0.4)
        plt.tight_layout()
        return fig
    except Exception as e:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, f"Graph Error:\n{e}", ha="center")
        return fig

# -----------------------
# LOGIN UI
# -----------------------
def login_ui():
    st.header("Login")
    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")
    if st.button("Login"):
        if not username or not password:
            st.warning("Enter username and password.")
        else:
            ok, uid = validate_login(username.strip(), password)
            if ok:
                st.session_state.logged_in = True
                st.session_state.uid = uid
                st.session_state.page = "dashboard"
                st.success("Logged in!")
                st.rerun()
            else:
                st.error("Invalid credentials.")
    if st.button("Create account"):
        st.session_state.page = "signup"
        st.rerun()

# -----------------------
# SIGNUP UI
# -----------------------
def signup_ui():
    st.header("Sign Up")
    username = st.text_input("Choose a username", key="signup_username")
    password = st.text_input("Choose a password", type="password", key="signup_password")
    if st.button("Register"):
        if not username or not password:
            st.warning("Enter all fields.")
        else:
            uid = create_user(username.strip(), password)
            if uid:
                st.success("Account created! Please log in.")
                st.session_state.page = "login"
                st.rerun()
            else:
                st.error("Username taken or network error.")
    if st.button("Back to login"):
        st.session_state.page = "login"
        st.rerun()

# -----------------------
# LOG WATER UI
# -----------------------
def log_water_ui(uid: str, intake: int, user_goal: int):
    st.header("Log Water Intake")
    st.write(f"**Current intake:** {intake} ml")
    st.write(f"**Goal:** {user_goal} ml")
    if st.button(f"+ {DEFAULT_QUICK_LOG_ML} ml"):
        set_today_intake(uid, intake + DEFAULT_QUICK_LOG_ML)
        st.rerun()
    custom = st.number_input("Custom amount (ml)", min_value=0)
    if st.button("Add Custom"):
        if custom > 0:
            set_today_intake(uid, intake + custom)
            st.success("Added!")
            st.rerun()
    if st.button("Reset Today"):
        reset_today_intake(uid)
        st.success("Daily intake reset.")
        st.rerun()

# -----------------------
# HISTORY UI
# -----------------------
def history_ui(uid: str, user_goal: int):
    st.header("History - Last 7 Days")
    data = get_past_intake(uid, days_count=7)
    fig = plot_water_intake(data, user_goal)
    st.pyplot(fig)
    st.subheader("Raw Data")
    st.table({day: f"{amount} ml" for day, amount in data.items()})

# -----------------------
# SETTINGS UI
# -----------------------
def settings_ui(uid: str, profile: dict):
    st.header("Settings")
    st.subheader("Age Group & Water Goal")
    age_groups = list(AGE_GOALS_ML.keys())
    current_group = profile.get("age_group", "19-50")
    chosen_group = st.selectbox("Age Group", age_groups, index=age_groups.index(current_group))
    default_goal = AGE_GOALS_ML[chosen_group]
    custom_goal = st.number_input("Custom Daily Goal (ml)", min_value=0,
                                  value=profile.get("user_goal_ml", default_goal))
    if st.button("Save Settings"):
        update_user_profile(uid, {"age_group": chosen_group, "user_goal_ml": int(custom_goal)})
        st.success("Updated!")
        st.rerun()

# -----------------------
# 2D Runner Game UI
# -----------------------
def runner_game_ui():
    st.header("WaterBuddy 2D Runner Game")

    # Load robo.png
    with open("robo.png", "rb") as f:
        robo_data = f.read()
    robo_base64 = base64.b64encode(robo_data).decode()
    robo_url = f"data:image/png;base64,{robo_base64}"

    game_html = f"""
    <style>
    canvas {{
        background: linear-gradient(#ffefd5, #ffd5c8);
        display: block;
        margin: 0 auto;
        border-radius: 10px;
    }}
    </style>

    <canvas id="gameCanvas" width="900" height="500"></canvas>

    <script>
    const canvas = document.getElementById("gameCanvas");
    const ctx = canvas.getContext("2d");

    let playerImg = new Image();
    playerImg.src = "{robo_url}";

    let player = {{
        x: 150,
        y: 350,
        width: 120,
        height: 140,
        velocityY: 0,
        gravity: 1,
        jumpPower: -18,
        onGround: true,
    }};
    let obstacles = [];
    let droplets = [];
    let speed = 6;
    let score = 0;
    let frame = 0;

    document.addEventListener("keydown", function(e) {{
        if (e.code === "Space" && player.onGround) {{
            player.velocityY = player.jumpPower;
            player.onGround = false;
        }}
    }});

    function spawnObstacle() {{
        const type = Math.random() < 0.5 ? "block" : "flame";
        if (type === "block") {{
            obstacles.push({{type:"block", x:canvas.width+50, y:380, width:60, height:60}});
        }} else {{
            obstacles.push({{type:"flame", x:canvas.width+50, y:360, width:50, height:70}});
        }}
    }}

    function spawnDroplet() {{
        droplets.push({{x:canvas.width+50, y:Math.random()*200+150, width:30, height:40}});
    }}

    function drawPlayer() {{
        ctx.drawImage(playerImg, player.x, player.y, player.width, player.height);
    }}

    function drawObstacle(obs) {{
        if(obs.type==="block"){{
            ctx.fillStyle="#666";
            ctx.fillRect(obs.x, obs.y, obs.width, obs.height);
        }} else {{
            ctx.fillStyle="orange";
            ctx.beginPath();
            ctx.moveTo(obs.x+25, obs.y);
            ctx.lineTo(obs.x+obs.width, obs.y+obs.height);
            ctx.lineTo(obs.x, obs.y+obs.height);
            ctx.fill();
        }}
    }}

    function drawDroplet(drop){{
        ctx.fillStyle="#00aaff";
        ctx.beginPath();
        ctx.ellipse(drop.x+15, drop.y+20, 15, 20, 0, 0, Math.PI*2);
        ctx.fill();
    }}

    function gameLoop(){{
        ctx.clearRect(0,0,canvas.width,canvas.height);
        player.velocityY += player.gravity;
        player.y += player.velocityY;
        if(player.y >= 350){{
            player.y=350; player.velocityY=0; player.onGround=true;
        }}
        drawPlayer();
        if(frame%70===0) spawnObstacle();
        if(frame%50===0) spawnDroplet();

        for(let i=obstacles.length-1;i>=0;i--){{
            let obs=obstacles[i]; obs.x-=speed; drawObstacle(obs);
            if(player.x<obs.x+obs.width && player.x+player.width>obs.x &&
               player.y<obs.y+obs.height && player.y+player.height>obs.y){{
                alert("Game Over! Score: "+score);
                document.location.reload();
            }}
            if(obs.x<-100) obstacles.splice(i,1);
        }}

        for(let i=droplets.length-1;i>=0;i--){{
            let drop=droplets[i]; drop.x-=speed; drawDroplet(drop);
            if(player.x<drop.x+drop.width && player.x+player.width>drop.x &&
               player.y<drop.y+drop.height && player.y+player.height>drop.y){{
                score+=10; droplets.splice(i,1);
            }}
            if(drop.x<-50) droplets.splice(i,1);
        }}

        ctx.fillStyle="#000"; ctx.font="28px Arial";
        ctx.fillText("Score: "+score, 30, 40);
        speed+=0.002; frame++; requestAnimationFrame(gameLoop);
    }}

    gameLoop();
    </script>
    """
    components.html(game_html, height=600)

# -----------------------
# DASHBOARD
# -----------------------
def dashboard_ui():
    uid = st.session_state.uid
    if not uid:
        st.session_state.logged_in = False
        st.session_state.page = "login"
        st.rerun()
        return

    profile = get_user_profile(uid)
    intake = get_today_intake(uid)
    user_goal = profile.get("user_goal_ml", 2500)
    percent = min((intake/user_goal)*100 if user_goal else 0, 100)

    left, right = st.columns([1, 2])
    with left:
        st.subheader("Navigation")
        for nav_item in ["Home", "Log Water", "History", "Settings", "Runner Game", "Logout"]:
            if st.button(nav_item):
                if nav_item == "Logout":
                    st.session_state.logged_in = False
                    st.session_state.uid = None
                    st.session_state.page = "login"
                    st.session_state.nav = "Home"
                else:
                    st.session_state.nav = nav_item
                st.rerun()

        theme = st.selectbox("Theme", ["Light", "Aqua", "Dark"], index=["Light","Aqua","Dark"].index(st.session_state.theme))
        if theme != st.session_state.theme:
            st.session_state.theme = theme
            apply_theme(theme)

        st.subheader("Tip of the day")
        st.info(st.session_state.tip)
        if st.button("New tip"):
            st.session_state.tip = random.choice(TIPS)

    with right:
        nav = st.session_state.nav
        if nav == "Home":
            st.header("Today's Summary")
            st.metric("Total intake", f"{intake} ml", f"{user_goal - intake} ml remaining")
            st.progress(percent/100)
            svg = generate_bottle_svg(percent)
            st.components.v1.html(svg, height=350)
            if percent>=100: st.success("You reached your goal!")
            elif percent>=75: st.info("Great progress — 75% reached!")
            elif percent>=50: st.info("Halfway there!")
            elif percent>=25: st.info("Nice start!")
        elif nav=="Log Water":
            log_water_ui(uid, intake, user_goal)
        elif nav=="History":
            history_ui(uid, user_goal)
        elif nav=="Settings":
            settings_ui(uid, profile)
        elif nav=="Runner Game":
            runner_game_ui()

# -----------------------
# MAIN
# -----------------------
def main():
    if not st.session_state.logged_in:
        if st.session_state.page=="login":
            login_ui()
        else:
            signup_ui()
    else:
        dashboard_ui()

if __name__=="__main__":
    main()
