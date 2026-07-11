from flask import Flask, render_template, request, Response
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
import random
import string
import redis
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", message_queue='redis://redis-service:6379', async_mode='threading')

r = redis.Redis(host='redis-service', port=6379, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)

@app.route('/metrics')
def metrics_endpoint():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

games_created = Counter('tictactoe_games_created_total', 'Total games created')
moves_made = Counter('tictactoe_moves_made_total', 'Total moves made')

@app.route('/')
def index():
    return render_template('index.html')

def save_game(game_id, game):
    r.set(f'game:{game_id}', json.dumps(game), ex=3600)

def load_game(game_id):
    data = r.get(f'game:{game_id}')
    return json.loads(data) if data else None

def set_sid_game(sid, game_id):
    r.set(f'sid:{sid}', game_id, ex=3600)

def get_sid_game(sid):
    return r.get(f'sid:{sid}')

def clear_sid(sid):
    r.delete(f'sid:{sid}')

# Three fixed modes. Each maps to size / style / win_len.
MODES = {
    '3-classic':  {'size': 3, 'style': 'classic',  'win_len': 3},
    '3-infinite': {'size': 3, 'style': 'infinite', 'win_len': 3},
    '4-infinite': {'size': 4, 'style': 'infinite', 'win_len': 4},
}

def sanitize_mode_key(key):
    return key if key in MODES else '3-infinite'

def new_board(m):
    return [''] * (m['size'] * m['size'])

def create_game_data(name, mode_key):
    game_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    m = MODES[mode_key]
    game = {
        'mode_key': mode_key,
        'board': new_board(m),
        'players': {},
        'names': {'X': name or "X-avier", 'O': "O-liver"},
        'score': {'X': 0, 'O': 0},
        'current_turn': 'X',
        'winner': None,
        'x_moves': [],
        'o_moves': [],
        'pending_mode': None,
        'mode_locked_by': None
    }
    save_game(game_id, game)
    return game_id

def check_winner(board, size, win_len):
    def cell(rrow, ccol):
        return board[rrow * size + ccol]
    dirs = [(0,1),(1,0),(1,1),(1,-1)]
    for row in range(size):
        for col in range(size):
            start = cell(row, col)
            if start == '':
                continue
            for dr, dc in dirs:
                cells = [(row + dr*k, col + dc*k) for k in range(win_len)]
                if all(0 <= rr < size and 0 <= cc < size for rr, cc in cells):
                    if all(cell(rr, cc) == start for rr, cc in cells):
                        return start, [rr*size + cc for rr, cc in cells]
    return None, None

@socketio.on('create_game')
def on_create_game(data=None):
    data = data or {}
    name = data.get('name', '').strip()
    mode_key = sanitize_mode_key(data.get('mode_key', '3-infinite'))
    game_id = create_game_data(name, mode_key)
    join_room(game_id)
    game = load_game(game_id)
    game['players'][request.sid] = 'X'
    save_game(game_id, game)
    set_sid_game(request.sid, game_id)
    games_created.inc()
    emit('game_created', {'game_id': game_id, 'symbol': 'X', 'names': game['names'], 'score': game['score'], 'mode_key': mode_key})

@socketio.on('join_game')
def on_join_game(data):
    game_id = data['game_id']
    name = data.get('name', '').strip()
    game = load_game(game_id)
    if not game:
        emit('error', {'message': 'Game not found'})
        return
    if request.sid in game['players']:
        emit('game_joined', {'symbol': game['players'][request.sid], 'names': game['names'], 'score': game['score'], 'mode_key': game['mode_key']})
        return
    if len(game['players']) >= 2:
        emit('error', {'message': 'Game is full'})
        return
    join_room(game_id)
    game['players'][request.sid] = 'O'
    if name:
        game['names']['O'] = name
    save_game(game_id, game)
    set_sid_game(request.sid, game_id)
    emit('game_joined', {'symbol': 'O', 'names': game['names'], 'score': game['score'], 'mode_key': game['mode_key']})
    emit('start_game', {'names': game['names'], 'score': game['score'], 'mode_key': game['mode_key']}, room=game_id, include_self=True)

@socketio.on('make_move')
def on_make_move(data):
    game_id = data['game_id']
    position = data['position']
    game = load_game(game_id)
    if not game:
        return
    symbol = game['players'].get(request.sid)
    if symbol is None or symbol != game['current_turn']:
        return
    m = MODES[game['mode_key']]
    total = m['size'] * m['size']
    if position < 0 or position >= total:
        return
    if game['board'][position] != '' or game['winner']:
        return

    moves_key = 'x_moves' if symbol == 'X' else 'o_moves'
    oldest_position = None
    if m['style'] == 'infinite' and len(game[moves_key]) >= m['win_len']:
        oldest_position = game[moves_key].pop(0)
        game['board'][oldest_position] = ''

    game['board'][position] = symbol
    game[moves_key].append(position)
    moves_made.inc()

    opponent_key = 'o_moves' if symbol == 'X' else 'x_moves'
    next_to_disappear = None
    if m['style'] == 'infinite' and len(game[opponent_key]) >= m['win_len']:
        next_to_disappear = game[opponent_key][0]

    winner, win_cells = check_winner(game['board'], m['size'], m['win_len'])

    if winner:
        game['winner'] = winner
        game['score'][winner] += 1
        save_game(game_id, game)
        emit('game_over', {'winner': winner, 'board': game['board'], 'win_cells': win_cells, 'score': game['score']}, room=game_id)
    elif '' not in game['board'] and m['style'] == 'classic':
        save_game(game_id, game)
        emit('game_over', {'winner': 'draw', 'board': game['board'], 'win_cells': None, 'score': game['score']}, room=game_id)
    else:
        game['current_turn'] = 'O' if symbol == 'X' else 'X'
        save_game(game_id, game)
        emit('move_made', {'board': game['board'], 'turn': game['current_turn'], 'removed': oldest_position, 'fading': next_to_disappear}, room=game_id, include_self=True)

@socketio.on('reset_game')
def on_reset_game(data):
    game_id = data['game_id']
    game = load_game(game_id)
    if game:
        for sid in game['players']:
            game['players'][sid] = 'O' if game['players'][sid] == 'X' else 'X'
        game['names']['X'], game['names']['O'] = game['names']['O'], game['names']['X']
        game['score']['X'], game['score']['O'] = game['score']['O'], game['score']['X']
        game['board'] = new_board(MODES[game['mode_key']])
        game['current_turn'] = 'X'
        game['winner'] = None
        game['x_moves'] = []
        game['o_moves'] = []
        save_game(game_id, game)
        emit('game_reset', {'names': game['names'], 'score': game['score'], 'mode_key': game['mode_key']}, room=game_id)

@socketio.on('open_mode_change')
def on_open_mode_change(data):
    game_id = data['game_id']
    game = load_game(game_id)
    if not game:
        return
    if game.get('mode_locked_by'):
        emit('error', {'message': 'Opponent is already choosing.'})
        return
    who = game['players'].get(request.sid)
    if who is None:
        return
    game['mode_locked_by'] = who
    save_game(game_id, game)
    emit('mode_locked', {'by': game['names'][who]}, room=game_id, include_self=False)

@socketio.on('cancel_mode_change')
def on_cancel_mode_change(data):
    game_id = data['game_id']
    game = load_game(game_id)
    if not game:
        return
    game['mode_locked_by'] = None
    game['pending_mode'] = None
    save_game(game_id, game)
    emit('mode_unlocked', {}, room=game_id, include_self=False)

@socketio.on('request_mode_change')
def on_request_mode_change(data):
    game_id = data['game_id']
    mode_key = sanitize_mode_key(data.get('mode_key', '3-infinite'))
    game = load_game(game_id)
    if not game:
        return
    if game.get('pending_mode'):
        emit('error', {'message': 'A mode change request is already pending.'})
        return
    requester = game['players'].get(request.sid)
    if requester is None:
        return
    game['pending_mode'] = mode_key
    save_game(game_id, game)
    emit('mode_change_requested', {'mode_key': mode_key, 'by': game['names'][requester]}, room=game_id, include_self=False)

@socketio.on('respond_mode_change')
def on_respond_mode_change(data):
    game_id = data['game_id']
    accepted = data.get('accepted', False)
    game = load_game(game_id)
    if not game or not game['pending_mode']:
        return
    if accepted:
        game['mode_key'] = game['pending_mode']
        game['board'] = new_board(MODES[game['mode_key']])
        game['current_turn'] = 'X'
        game['winner'] = None
        game['x_moves'] = []
        game['o_moves'] = []
    game['pending_mode'] = None
    game['mode_locked_by'] = None
    save_game(game_id, game)
    if accepted:
        emit('mode_changed', {'mode_key': game['mode_key'], 'score': game['score'], 'names': game['names']}, room=game_id)
    else:
        emit('mode_change_declined', {}, room=game_id)

@socketio.on('disconnect')
def on_disconnect():
    game_id = get_sid_game(request.sid)
    if not game_id:
        return
    game = load_game(game_id)
    if not game:
        clear_sid(request.sid)
        return
    symbol = game['players'].get(request.sid)
    name = game['names'].get(symbol, 'Opponent') if symbol else 'Opponent'
    if request.sid in game['players']:
        del game['players'][request.sid]
    game['mode_locked_by'] = None
    game['pending_mode'] = None
    save_game(game_id, game)
    clear_sid(request.sid)
    emit('opponent_left', {'name': name}, room=game_id)
    emit('mode_unlocked', {}, room=game_id)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
