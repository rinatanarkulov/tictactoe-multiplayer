from flask import Flask, render_template, request, Response
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")


# Custom metrics route
@app.route('/metrics')
def metrics_endpoint():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

# Track game count
games_created = Counter('tictactoe_games_created_total', 'Total games created')
moves_made = Counter('tictactoe_moves_made_total', 'Total moves made')



# Store active games
games = {}

@app.route('/')
def index():
    return render_template('index.html')
# WebSocket events
@socketio.on('create_game')
def on_create_game():
    game_id = create_game()
    join_room(game_id)
    games[game_id]['players'].append(request.sid)
    games_created.inc()  #  Counter for metrics
    emit('game_created', {'game_id': game_id, 'symbol': 'X'})

@socketio.on('join_game')
def on_join_game(data):
    game_id = data['game_id']
    if game_id in games and len(games[game_id]['players']) < 2:
        join_room(game_id)
        games[game_id]['players'].append(request.sid)
        emit('game_joined', {'symbol': 'O'})
        emit('start_game', {'board': games[game_id]['board']}, room=game_id, include_self=True)  # Changed this line

@socketio.on('make_move')
def on_make_move(data):
    game_id = data['game_id']
    position = data['position']
    game = games[game_id]
    
    if game['board'][position] == '' and not game['winner']:
        game['board'][position] = game['current_turn']
        moves_made.inc()
        winner = check_winner(game['board'])
        
        if winner:
            game['winner'] = winner
            emit('game_over', {'winner': winner, 'board': game['board']}, room=game_id)
        else:
            game['current_turn'] = 'O' if game['current_turn'] == 'X' else 'X'
            emit('move_made', {'board': game['board'], 'turn': game['current_turn']}, room=game_id, include_self=True)

@socketio.on('reset_game')
def on_reset_game(data):
    game_id = data['game_id']
    if game_id in games:
        game = games[game_id]
        # Switch symbols
        game['players'].reverse()
        game['board'] = [''] * 9
        game['current_turn'] = 'X'
        game['winner'] = None
        emit('game_reset', {}, room=game_id)

# Game logic functions
def create_game():
    import random
    import string
    game_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    games[game_id] = {
        'board': [''] * 9,
        'players': [],
        'current_turn': 'X',
        'winner': None
    }
    return game_id

def check_winner(board):
    wins = [
        [0,1,2], [3,4,5], [6,7,8],  # rows
        [0,3,6], [1,4,7], [2,5,8],  # columns
        [0,4,8], [2,4,6]             # diagonals
    ]
    for combo in wins:
        if board[combo[0]] == board[combo[1]] == board[combo[2]] != '':
            return board[combo[0]]
    if '' not in board:
        return 'draw'
    return None

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
