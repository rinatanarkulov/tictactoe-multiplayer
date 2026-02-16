# Multiplayer Tic-Tac-Toe

Real-time multiplayer Tic-Tac-Toe game with WebSockets, deployed on Kubernetes.

## Features
- ✅ Real-time multiplayer gameplay
- ✅ WebSocket communication (Flask-SocketIO)
- ✅ 4-character game codes for easy matchmaking
- ✅ Dockerized application
- ✅ Kubernetes deployment with 2 replicas
- ✅ Mobile-friendly interface

## Tech Stack
- **Backend:** Python, Flask, Flask-SocketIO
- **Frontend:** HTML, CSS, JavaScript
- **Containerization:** Docker
- **Orchestration:** Kubernetes (microk8s)
- **Deployment:** NodePort service on port 30500

## How to Run Locally

### With Docker
```bash
docker build -t tictactoe:v1 .
docker run -d -p 5000:5000 tictactoe:v1
```

### With Kubernetes
```bash
kubectl apply -f k8s/deployment.yaml
# Access at http://localhost:30500
```

## How to Play
1. Player 1: Click "Create Game" and share the 4-character code
2. Player 2: Enter the code and click "Join Game"
3. Take turns playing - symbols switch after each game!

## Screenshots
[Add screenshots here]

## What I Learned
- Real-time WebSocket communication
- Stateful application deployment
- Container orchestration with Kubernetes
- Managing game state across multiple clients
