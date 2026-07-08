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

# Redis connection for game state
r = redis.Redis(host='redis-service', port=6379, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)

# Metrics
@app.route('/metrics')
def metrics_endpoint():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

games_created = Counter('tictactoe_games_created_total', 'Total games created')
moves_made = Counter('tictactoe_moves_made_total', 'Total moves made')

@app.route('/')
def index():
    return render_template('index.html')

# Redis game helpers
def save_game(game_id, game):
    r.set(f'game:{game_id}', json.dumps(game), ex=3600)  # expire after 1 hour

def load_game(game_id):
    data = r.get(f'game:{game_id}')
    return json.loads(data) if data else None

def create_game_data():
    game_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    game = {
        'board': [''] * 9,
        'players': {},          # sid -> symbol ('X' or 'O')
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

# WebSocket events
@socketio.on('create_game')
def on_create_game():
    game_id = create_game_data()
    join_room(game_id)
    game = load_game(game_id)
    game['players'][request.sid] = 'X'
    save_game(game_id, game)
    games_created.inc()
    emit('game_created', {'game_id': game_id, 'symbol': 'X'})

@socketio.on('join_game')
def on_join_game(data):
    game_id = data['game_id']
    game = load_game(game_id)

    if not game:
        emit('error', {'message': 'Game not found'})
        return

    # Already in this game? just re-send their symbol, don't add again
    if request.sid in game['players']:
        emit('game_joined', {'symbol': game['players'][request.sid]})
        return

    # Game already has 2 players
    if len(game['players']) >= 2:
        emit('error', {'message': 'Game is full'})
        return

    join_room(game_id)
    game['players'][request.sid] = 'O'
    save_game(game_id, game)
    emit('game_joined', {'symbol': 'O'})
    emit('start_game', {}, room=game_id, include_self=True)

@socketio.on('make_move')
def on_make_move(data):
    game_id = data['game_id']
    position = data['position']
    game = load_game(game_id)

    if not game:
        return

    # Who is this player?
    symbol = game['players'].get(request.sid)
    if symbol is None:
        return  # not a player in this game

    # Not this player's turn -> ignore
    if symbol != game['current_turn']:
        return

    # Invalid position or occupied or game over -> ignore
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
        save_game(game_id, game)
        emit('game_over', {'winner': winner, 'board': game['board'], 'win_cells': win_cells}, room=game_id)
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
        # swap symbols between the two players
        for sid in game['players']:
            game['players'][sid] = 'O' if game['players'][sid] == 'X' else 'X'
        game['board'] = [''] * 9
        game['current_turn'] = 'X'
        game['winner'] = None
        game['x_moves'] = []
        game['o_moves'] = []
        save_game(game_id, game)
        emit('game_reset', {}, room=game_id)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
