pipeline {
    agent any
    stages {
        stage('Checkout and Prepare') {
            steps {
                checkout scm
                sh 'python3 -m pip install -r requirements.txt --user'
            }
        }
        stage('Run Script') {
            steps {
                sh 'python3 deploy.py'
            }
        }
    }
    post {
        always {
            cleanWs()
        }
    }
}
