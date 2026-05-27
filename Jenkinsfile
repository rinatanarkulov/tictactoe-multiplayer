pipeline {
    agent any
    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }
        stage('Build') {
            steps {
                sh 'docker build -t tictactoe:${BUILD_NUMBER} .'
            }
        }
        stage('Test') {
            steps {
                sh 'docker run --rm tictactoe:${BUILD_NUMBER} python -m unittest test_app.py'
            }
        }
        stage('Deploy to Dev') {
            steps {
                sh 'docker tag tictactoe:${BUILD_NUMBER} tictactoe:dev'
                sh 'docker save tictactoe:dev > tictactoe-dev.tar'
                sh 'sudo microk8s ctr image import tictactoe-dev.tar'
                sh 'rm -f tictactoe-dev.tar'
                sh 'sudo microk8s kubectl apply -f k8s/environments/dev.yaml'
                sh 'sudo microk8s kubectl rollout restart deployment/tictactoe -n dev'
            }
        }
        stage('Deploy to Staging') {
            steps {
                input message: 'Deploy to Staging?', ok: 'Yes'
                sh 'docker tag tictactoe:${BUILD_NUMBER} tictactoe:staging'
                sh 'docker save tictactoe:staging > tictactoe-staging.tar'
                sh 'sudo microk8s ctr image import tictactoe-staging.tar'
                sh 'rm -f tictactoe-staging.tar'
                sh 'sudo microk8s kubectl apply -f k8s/environments/staging.yaml'
                sh 'sudo microk8s kubectl rollout restart deployment/tictactoe -n staging'
            }
        }
        stage('Deploy to Production') {
            steps {
                input message: 'Deploy to Production?', ok: 'Deploy'
                sh 'docker tag tictactoe:${BUILD_NUMBER} tictactoe:prod'
                sh 'docker save tictactoe:prod > tictactoe-prod.tar'
                sh 'sudo microk8s ctr image import tictactoe-prod.tar'
                sh 'rm -f tictactoe-prod.tar'
                sh 'sudo microk8s kubectl apply -f k8s/environments/prod.yaml'
                sh 'sudo microk8s kubectl rollout restart deployment/tictactoe -n prod'
            }
        }
    }
    post {
        always {
            sh 'rm -f *.tar'
            sh 'docker image prune -af --filter "until=24h" || true'
        }
    }
}
