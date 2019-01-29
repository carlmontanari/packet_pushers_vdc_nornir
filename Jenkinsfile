pipeline {
    agent any
    stages {
        stage('Checkout and Prepare') {
            steps {
                checkout scm
                sh 'python3 -m pip install -r requirements.txt'
            }
        }
    }
    post {
        always {
            cleanWs()
        }
    }
}
