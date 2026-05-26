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
        
        stage('Deploy') {
            steps {
                sh 'docker save tictactoe:${BUILD_NUMBER} > tictactoe.tar'
                sh 'sudo microk8s ctr image import tictactoe.tar'
                sh 'sudo microk8s kubectl set image deployment/tictactoe tictactoe=tictactoe:${BUILD_NUMBER}'
            }
        }
    }
}
