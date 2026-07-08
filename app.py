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

# map a connection id -> which game it's in (for disconnect handling)
def set_sid_game(sid, game_id):
    r.set(f'sid:{sid}', game_id, ex=3600)

def get_sid_game(sid):
    return r.get(f'sid:{sid}')

def clear_sid(sid):
    r.delete(f'sid:{sid}')

def create_game_data(name):
    game_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    game = {
        'board': [''] * 9,
        'players': {},          # sid -> symbol
        'names': {'X': name or "X'avier", 'O': "O'liver"},
        'score': {'X': 0, 'O': 0},
        'current_turn': 'X',
        'winner': None,
        'x_moves': [],
        'o_moves': []
    }
    save_game(game_id, game)
    return game_id

def check_winner(board):
    wins = [
        [0,1,2], [3,4,5], [6,7,8],
        [0,3,6], [1,4,7], [2,5,8],
        [0,4,8], [2,4,6]
    ]
    for combo in wins:
        if board[combo[0]] == board[combo[1]] == board[combo[2]] != '':
            return board[combo[0]], combo
    return None, None

@socketio.on('create_game')
def on_create_game(data=None):
    name = (data or {}).get('name', '').strip() if data else ''
    game_id = create_game_data(name)
    join_room(game_id)
    game = load_game(game_id)
    game['players'][request.sid] = 'X'
    save_game(game_id, game)
    set_sid_game(request.sid, game_id)
    games_created.inc()
    emit('game_created', {
        'game_id': game_id,
        'symbol': 'X',
        'names': game['names'],
        'score': game['score']
    })

@socketio.on('join_game')
def on_join_game(data):
    game_id = data['game_id']
    name = data.get('name', '').strip()
    game = load_game(game_id)

    if not game:
        emit('error', {'message': 'Game not found'})
        return

    if request.sid in game['players']:
        emit('game_joined', {'symbol': game['players'][request.sid], 'names': game['names'], 'score': game['score']})
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

    emit('game_joined', {'symbol': 'O', 'names': game['names'], 'score': game['score']})
    emit('start_game', {'names': game['names'], 'score': game['score']}, room=game_id, include_self=True)

@socketio.on('make_move')
def on_make_move(data):
    game_id = data['game_id']
    position = data['position']
    game = load_game(game_id)

    if not game:
        return

    symbol = game['players'].get(request.sid)
    if symbol is None:
        return
    if symbol != game['current_turn']:
        return
    if position < 0 or position > 8:
        return
    if game['board'][position] != '' or game['winner']:
        return

    moves_key = 'x_moves' if symbol == 'X' else 'o_moves'

    oldest_position = None
    if len(game[moves_key]) >= 3:
        oldest_position = game[moves_key].pop(0)
        game['board'][oldest_position] = ''

    game['board'][position] = symbol
    game[moves_key].append(position)
    moves_made.inc()

    opponent_key = 'o_moves' if symbol == 'X' else 'x_moves'
    next_to_disappear = None
    if len(game[opponent_key]) >= 3:
        next_to_disappear = game[opponent_key][0]

    winner, win_cells = check_winner(game['board'])

    if winner:
        game['winner'] = winner
        game['score'][winner] += 1
        save_game(game_id, game)
        emit('game_over', {
            'winner': winner,
            'board': game['board'],
            'win_cells': win_cells,
            'score': game['score']
        }, room=game_id)
    else:
        game['current_turn'] = 'O' if symbol == 'X' else 'X'
        save_game(game_id, game)
        emit('move_made', {
            'board': game['board'],
            'turn': game['current_turn'],
            'removed': oldest_position,
            'fading': next_to_disappear
        }, room=game_id, include_self=True)

@socketio.on('reset_game')
def on_reset_game(data):
    game_id = data['game_id']
    game = load_game(game_id)
    if game:
        for sid in game['players']:
            game['players'][sid] = 'O' if game['players'][sid] == 'X' else 'X'
        # swap names too so symbols stay consistent with the person
        game['names']['X'], game['names']['O'] = game['names']['O'], game['names']['X']
        game['score']['X'], game['score']['O'] = game['score']['O'], game['score']['X']
        game['board'] = [''] * 9
        game['current_turn'] = 'X'
        game['winner'] = None
        game['x_moves'] = []
        game['o_moves'] = []
        save_game(game_id, game)
        emit('game_reset', {'names': game['names'], 'score': game['score']}, room=game_id)

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
        save_game(game_id, game)
    clear_sid(request.sid)
    emit('opponent_left', {'name': name}, room=game_id)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
