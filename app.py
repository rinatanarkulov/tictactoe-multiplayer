from flask import Flask, render_template, request, Response
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid
import random
import string
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Metrics
@app.route('/metrics')
def metrics_endpoint():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

games_created = Counter('tictactoe_games_created_total', 'Total games created')
moves_made = Counter('tictactoe_moves_made_total', 'Total moves made')

# Store active games
games = {}

@app.route('/')
def index():
    return render_template('index.html')

# Helper functions
def create_game_data():
    game_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    games[game_id] = {
        'board': [''] * 9,
        'players': [],
        'current_turn': 'X',
        'winner': None,
        'x_moves': [],
        'o_moves': []
    }
    return game_id

def check_winner(board):
    wins = [
        [0,1,2], [3,4,5], [6,7,8],
        [0,3,6], [1,4,7], [2,5,8],
        [0,4,8], [2,4,6]
    ]
    for combo in wins:
        if board[combo[0]] == board[combo[1]] == board[combo[2]] != '':
            return board[combo[0]]
    return None

# WebSocket events
@socketio.on('create_game')
def on_create_game():
    game_id = create_game_data()
    join_room(game_id)
    games[game_id]['players'].append(request.sid)
    games_created.inc()
    emit('game_created', {'game_id': game_id, 'symbol': 'X'})

@socketio.on('join_game')
def on_join_game(data):
    game_id = data['game_id']
    if game_id in games and len(games[game_id]['players']) < 2:
        join_room(game_id)
        games[game_id]['players'].append(request.sid)
        emit('game_joined', {'symbol': 'O'})
        emit('start_game', {}, room=game_id, include_self=True)

@socketio.on('make_move')
def on_make_move(data):
    game_id = data['game_id']
    position = data['position']
    
    if game_id not in games:
        return
    
    game = games[game_id]
    
    if game['board'][position] == '' and not game['winner']:
        symbol = game['current_turn']
        moves_key = 'x_moves' if symbol == 'X' else 'o_moves'
        
        # Remove oldest if player has 3 already
        oldest_position = None
        if len(game[moves_key]) >= 3:
            oldest_position = game[moves_key].pop(0)
            game['board'][oldest_position] = ''
        
        game['board'][position] = symbol
        game[moves_key].append(position)
        moves_made.inc()
        
        # Mark which cell will disappear next (opponent's oldest if they have 3)
        opponent_key = 'o_moves' if symbol == 'X' else 'x_moves'
        next_to_disappear = None
        if len(game[opponent_key]) >= 3:
            next_to_disappear = game[opponent_key][0]
        
        winner = check_winner(game['board'])
        
        if winner:
            game['winner'] = winner
            emit('game_over', {'winner': winner, 'board': game['board']}, room=game_id)
        else:
            game['current_turn'] = 'O' if symbol == 'X' else 'X'
            emit('move_made', {
                'board': game['board'],
                'turn': game['current_turn'],
                'removed': oldest_position,
                'fading': next_to_disappear
            }, room=game_id, include_self=True)

@socketio.on('reset_game')
def on_reset_game(data):
    game_id = data['game_id']
    if game_id in games:
        game = games[game_id]
        game['players'].reverse()
        game['board'] = [''] * 9
        game['current_turn'] = 'X'
        game['winner'] = None
        game['x_moves'] = []
        game['o_moves'] = []
        emit('game_reset', {}, room=game_id)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
