from flask import Flask, render_template
from flask_socketio import SocketIO, emit, join_room
import random
import string
import time

app = Flask(__name__)
app.config["SECRET_KEY"] = "spyfall"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

SPY_POINTS = 3
TEAM_POINTS = 2

LOCATIONS = [
    {"id": "mall", "icon": "🏬"},
    {"id": "aquapark", "icon": "🏊"},
    {"id": "airport", "icon": "✈️"},
    {"id": "train_station", "icon": "🚉"},
    {"id": "bus_station", "icon": "🚌"},
    {"id": "metro", "icon": "🚇"},
    {"id": "police", "icon": "👮"},
    {"id": "hospital", "icon": "🏥"},
    {"id": "fire_station", "icon": "🚒"},
    {"id": "car_wash", "icon": "🚗"},
    {"id": "barbershop", "icon": "💈"},
    {"id": "school", "icon": "🏫"},
    {"id": "university", "icon": "🎓"},
    {"id": "office_building", "icon": "🏢"},
    {"id": "music_school", "icon": "🎵"},
    {"id": "post_office", "icon": "📮"},
    {"id": "bank", "icon": "🏦"},
    {"id": "night_club", "icon": "🎧"},
    {"id": "restaurant", "icon": "🍽️"},
    {"id": "cafe", "icon": "☕"},
    {"id": "bar", "icon": "🍺"},
    {"id": "cinema", "icon": "🎬"},
    {"id": "gym", "icon": "🏋️"},
    {"id": "football_stadium", "icon": "⚽"},
    {"id": "basketball_court", "icon": "🏀"},
    {"id": "tennis_court", "icon": "🎾"},
    {"id": "pool", "icon": "🏊‍♂️"},
    {"id": "skate_park", "icon": "🛹"},
    {"id": "bowling_club", "icon": "🎳"},
    {"id": "passenger_train", "icon": "🚆"},
    {"id": "cruise_ship", "icon": "🛳️"},
    {"id": "cargo_ship", "icon": "🚢"},
    {"id": "airplane", "icon": "🛫"},
    {"id": "submarine", "icon": "🛥️"},
    {"id": "space_station", "icon": "🛰️"},
    {"id": "factory", "icon": "🏭"},
    {"id": "construction_site", "icon": "🚧"},
    {"id": "farm", "icon": "🚜"},
    {"id": "bakery", "icon": "🥐"},
    {"id": "tv_studio", "icon": "📺"},
    {"id": "radio_station", "icon": "📻"},
    {"id": "fire_department", "icon": "🚒"},
    {"id": "court", "icon": "⚖️"},
    {"id": "beach", "icon": "🏖️"},
    {"id": "forest", "icon": "🌲"},
    {"id": "mountain", "icon": "⛰️"},
    {"id": "camp", "icon": "🏕️"},
    {"id": "fishing_base", "icon": "🎣"},
    {"id": "amusement_park", "icon": "🎡"},
    {"id": "zoo", "icon": "🦁"},
    {"id": "aquarium", "icon": "🐠"},
    {"id": "military_base", "icon": "🪖"},
    {"id": "laboratory", "icon": "🧪"},
    {"id": "bunker", "icon": "🚷"},
    {"id": "prison", "icon": "🚔"},
    {"id": "castle", "icon": "🏰"},
    {"id": "magic_school", "icon": "🧙‍♂️"},
]


class Player:
    def __init__(self, sid, nick):
        self.sid = sid
        self.nick = nick
        self.is_spy = False
        self.score = 0


class Lobby:
    def __init__(self, code, host_sid):
        self.code = code
        self.host = host_sid
        self.players: dict[str, Player] = {}
        self.state = "waiting"   # waiting / active / finished
        self.location = None     # dict from LOCATIONS
        self.cards = []          # list of dicts from LOCATIONS
        self.answer_order = []   # list of sids
        self.end_time = None
        self.duration = 180
        self.votes: dict[str, set[str]] = {}  # target_sid -> set(voter_sid)


lobbies: dict[str, Lobby] = {}


def code4():
    return "".join(random.choice(string.ascii_uppercase) for _ in range(4))


def serialize_lobby(lobby: Lobby):
    return {
        "code": lobby.code,
        "state": lobby.state,
        "host": lobby.host,
        "players": [
            {
                "sid": p.sid,
                "nick": p.nick,
                "score": p.score,
                "isSpy": p.is_spy,
            }
            for p in lobby.players.values()
        ],
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return "OK"


@socketio.on("create")
def on_create(data):
    sid = data.get("sid")
    nick = data.get("nick") or "Player"
    if not sid:
        return

    code = code4()
    lobby = Lobby(code, sid)
    lobby.players[sid] = Player(sid, nick)
    lobbies[code] = lobby

    join_room(code)
    emit("joined", {"lobby": serialize_lobby(lobby)}, to=sid)


@socketio.on("join")
def on_join(data):
    sid = data.get("sid")
    nick = data.get("nick") or "Player"
    code = (data.get("code") or "").upper()
    if not sid or not code:
        return

    if code not in lobbies:
        emit("error", {"msg": "Lobby not found"}, to=sid)
        return

    lobby = lobbies[code]
    lobby.players[sid] = Player(sid, nick)
    join_room(code)

    emit("joined", {"lobby": serialize_lobby(lobby)}, to=sid)
    socketio.emit("update", {"lobby": serialize_lobby(lobby)}, room=code)


@socketio.on("start")
def on_start(data):
    code = data.get("code")
    sid = data.get("sid")
    if not code or not sid:
        return

    lobby = lobbies.get(code)
    if not lobby:
        return
    if sid != lobby.host:
        return

    if len(lobby.players) < 3:
        emit("error", {"msg": "Need at least 3 players"}, to=sid)
        return

    # reset flags and votes
    lobby.votes = {}
    for p in lobby.players.values():
        p.is_spy = False

    all_sids = list(lobby.players.keys())
    spy_sid = random.choice(all_sids)
    lobby.players[spy_sid].is_spy = True

    lobby.cards = random.sample(LOCATIONS, min(12, len(LOCATIONS)))
    lobby.location = random.choice(lobby.cards)
    lobby.answer_order = random.sample(all_sids, len(all_sids))

    lobby.state = "active"
    lobby.end_time = time.time() + lobby.duration

    for psid, p in lobby.players.items():
        role = "spy" if p.is_spy else "agent"
        loc_payload = None if p.is_spy else lobby.location
        emit(
            "round",
            {
                "role": role,
                "location": loc_payload,
                "cards": lobby.cards,
                "order": [lobby.players[x].nick for x in lobby.answer_order],
                "duration": lobby.duration,
            },
            to=psid,
        )

    socketio.start_background_task(timer_thread, lobby)


def timer_thread(lobby: Lobby):
    while lobby.state == "active":
        remaining = int(lobby.end_time - time.time())
        if remaining <= 0:
            finish_round(lobby, spy_win=False, reason="timeout")
            return
        socketio.emit("timer", {"remaining": remaining}, room=lobby.code)
        socketio.sleep(1)


@socketio.on("guess")
def on_guess(data):
    code = data.get("code")
    sid = data.get("sid")
    loc_id = data.get("loc")
    if not code or not sid or not loc_id:
        return

    lobby = lobbies.get(code)
    if not lobby or lobby.state != "active":
        return

    player = lobby.players.get(sid)
    if not player or not player.is_spy:
        return

    correct = lobby.location and lobby.location["id"] == loc_id
    finish_round(lobby, spy_win=correct, reason="spy_guess")


@socketio.on("vote")
def on_vote(data):
    code = data.get("code")
    voter_sid = data.get("sid")
    target_sid = data.get("target")
    if not code or not voter_sid or not target_sid:
        return

    lobby = lobbies.get(code)
    if not lobby or lobby.state != "active":
        return

    voter = lobby.players.get(voter_sid)
    target = lobby.players.get(target_sid)
    if not voter or not target:
        return

    if voter.is_spy:
        return

    if target_sid not in lobby.votes:
        lobby.votes[target_sid] = set()

    lobby.votes[target_sid].add(voter_sid)

    total_players = len(lobby.players)
    threshold = max(2, total_players - 1)
    count = len(lobby.votes[target_sid])

    socketio.emit(
        "vote_update",
        {"target": target_sid, "count": count, "threshold": threshold},
        room=lobby.code,
    )

    if count >= threshold:
        if target.is_spy:
            finish_round(lobby, spy_win=False, reason="vote_correct")
        else:
            finish_round(lobby, spy_win=True, reason="vote_wrong")


@socketio.on("next_round")
def next_round(data):
    code = data.get("code")
    sid = data.get("sid")
    if not code or not sid:
        return

    lobby = lobbies.get(code)
    if not lobby:
        return

    # Только хост
    if sid != lobby.host:
        return

    # Полный сброс состояния
    lobby.state = "waiting"
    lobby.votes.clear()
    lobby.location = None
    lobby.cards = []
    lobby.answer_order = []
    lobby.end_time = None

    # Сброс ролей (обязательно!)
    for p in lobby.players.values():
        p.is_spy = False

    # Вернуть всех в лобби
    socketio.emit("go_lobby", {"lobby": serialize_lobby(lobby)}, room=code)


def finish_round(lobby: Lobby, spy_win: bool, reason: str):
    if lobby.state != "active":
        return

    lobby.state = "finished"

    if spy_win:
        for p in lobby.players.values():
            if p.is_spy:
                p.score += SPY_POINTS
    else:
        for p in lobby.players.values():
            if not p.is_spy:
                p.score += TEAM_POINTS

    spy_names = [p.nick for p in lobby.players.values() if p.is_spy]

    payload = {
        "spyWin": spy_win,
        "reason": reason,
        "locationId": lobby.location["id"] if lobby.location else None,
        "spyNames": spy_names,
        "scores": {sid: p.score for sid, p in lobby.players.items()},
    }

    socketio.emit("finished", payload, room=lobby.code)
    socketio.emit("update", {"lobby": serialize_lobby(lobby)}, room=lobby.code)


if __name__ == "__main__":
    import eventlet
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
