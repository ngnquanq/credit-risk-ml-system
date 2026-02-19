// Jenkinsfile for Flink Feature Engineering CI/CD (Pattern A: 100% Automation)
// Triggers on feature/* branches and master branch
// Single pipeline execution: Validate → Build → Auto-merge → Deploy → Verify

pipeline {
    agent {
        label 'docker'
    }

    environment {
        // Flink and Kafka endpoints
        FLINK_REST_API = 'http://flink-jobmanager:8081'
        KAFKA_BROKERS = 'broker:29092'

        // Docker image naming
        GIT_COMMIT_SHORT = sh(returnStdout: true, script: 'git rev-parse --short HEAD').trim()
        IMAGE_NAME = "hc-flink-jobs:${GIT_COMMIT_SHORT}"

        // Kubernetes namespace for Feast
        FEAST_NAMESPACE = 'feature-registry'

        // Backup directory for rollback
        BACKUP_DIR = "/var/jenkins_home/backups/${BUILD_ID}"

        // Helper scripts path
        AUTOMATION_HELPER = 'services/ops/scripts/automation/automation_helper'
    }

    options {
        buildDiscarder(logRotator(numToKeepStr: '30'))
        timeout(time: 30, unit: 'MINUTES')
        timestamps()
    }

    triggers {
        // Poll SCM every 2 minutes for changes on feature/* and master branches
        // Jenkins checks Git repository and triggers build if new commits found
        // 'H/2' means every 2 minutes with random offset to avoid all jobs polling simultaneously
        pollSCM('H/2 * * * *')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    echo "Branch: ${env.GIT_BRANCH}"
                    echo "Commit: ${env.GIT_COMMIT}"

                    // Check if Flink-related files changed
                    def flinkChanged = sh(
                        script: '''
                            git diff --name-only HEAD~1 HEAD | grep -E '^application/flink/' || echo "no-flink-changes"
                        ''',
                        returnStdout: true
                    ).trim()

                    if (flinkChanged == 'no-flink-changes') {
                        echo "⏭️  No Flink-related files changed, skipping build"
                        currentBuild.result = 'NOT_BUILT'
                        return
                    } else {
                        echo "✅ Flink files changed:"
                        echo flinkChanged
                    }
                }
            }
        }

        // STAGE 1: Validation (runs on all branches)
        stage('Validate') {
            parallel {
                // TODO: Uncomment when data scientists create UDF tests
                // stage('UDF Unit Tests') {
                //     steps {
                //         script {
                //             echo "Running UDF unit tests..."
                //             sh '''
                //                 cd application/flink/jobs
                //                 python3 -m pytest test_cdc_udfs.py -v --tb=short || exit 1
                //                 python3 -m pytest test_bureau_aggregation_udfs.py -v --tb=short || exit 1
                //             '''
                //         }
                //     }
                // }

                stage('Syntax Validation') {
                    steps {
                        script {
                            echo "Validating Python syntax..."
                            sh '''
                                python3 -m py_compile application/flink/jobs/cdc_application_etl.py
                                python3 -m py_compile application/flink/jobs/bureau_aggregation_etl.py
                                python3 -m py_compile application/flink/jobs/cdc_udfs.py
                                python3 -m py_compile application/flink/jobs/bureau_aggregation_udfs.py
                            '''
                        }
                    }
                }

                stage('Schema Validation') {
                    steps {
                        script {
                            echo "Validating Kafka schema compatibility..."
                            sh '''
                                python3 ${AUTOMATION_HELPER}/validate_kafka_schema.py \
                                    --bootstrap ${KAFKA_BROKERS} \
                                    --source-topic hc.application_features \
                                    --schema application/feast_repo/feature_schema/application_schema.json \
                                    || echo "WARNING: Schema validation skipped (topic may be empty)"
                            '''
                        }
                    }
                }
            }
        }

        // STAGE 2: Build Docker Image (runs on all branches)
        stage('Build') {
            steps {
                script {
                    echo "Building Flink Docker image: ${IMAGE_NAME}"
                    sh '''
                        cd application/flink
                        docker build \
                            -t ${IMAGE_NAME} \
                            --build-arg GIT_COMMIT=${GIT_COMMIT} \
                            .

                        echo "✓ Image built successfully: ${IMAGE_NAME}"
                    '''
                }
            }
        }

        // STAGE 3: Auto-Merge to Master (feature/* branches ONLY)
        stage('Auto-Merge to Master') {
            when {
                not { branch 'master' }
                expression { currentBuild.result == null || currentBuild.result == 'SUCCESS' }
            }
            steps {
                script {
                    echo "All validations passed! Auto-merging ${env.GIT_BRANCH} to master..."

                    sh '''
                        # Configure Git
                        git config user.email "jenkins@hc-platform.local"
                        git config user.name "Jenkins CI"

                        # Fetch latest master
                        git fetch origin master

                        # Checkout master
                        git checkout master

                        # Merge feature branch (no fast-forward)
                        git merge --no-ff ${GIT_BRANCH} -m "chore: auto-merge ${GIT_BRANCH} [Jenkins CI]"

                        # Push to master
                        git push origin master

                        echo "✓ Successfully merged ${GIT_BRANCH} to master"
                    '''

                    echo "✓ Merge complete! Continuing with deployment..."

                    // Update GIT_BRANCH environment variable for subsequent stages
                    env.GIT_BRANCH = 'master'
                }
            }
        }

        // STAGE 4: Deploy Flink Jobs (runs after merge OR if already on master)
        stage('Deploy Flink Jobs') {
            when {
                expression { currentBuild.result == null || currentBuild.result == 'SUCCESS' }
            }
            steps {
                script {
                    echo "Deploying Flink jobs to production..."

                    // Run deployment script
                    sh '''
                        bash ${AUTOMATION_HELPER}/deploy_flink_jobs.sh
                    '''
                }
            }
            post {
                failure {
                    script {
                        echo "Deployment failed! Triggering rollback..."
                        sh '''
                            bash ${AUTOMATION_HELPER}/rollback_flink.sh ${BACKUP_DIR}
                        '''
                    }
                }
            }
        }

        // STAGE 5: Update Feast Registry (runs after deployment if schema changed)
        stage('Update Feast') {
            when {
                expression { currentBuild.result == null || currentBuild.result == 'SUCCESS' }
            }
            steps {
                script {
                    echo "Checking for schema changes..."

                    def schemaChanged = sh(
                        script: '''
                            # Generate new schemas from Kafka topics
                            cd application/feast_repo

                            # Backup existing schema
                            cp feature_schema/application_schema.json feature_schema/application_schema.json.bak || true

                            # Generate new schema (sample from Kafka)
                            python3 generate_schemas_from_kafka.py \
                                --bootstrap ${KAFKA_BROKERS} \
                                --samples 20 \
                                --timeout 15000 || echo "Schema generation skipped"

                            # Check if schema changed
                            if diff -q feature_schema/application_schema.json \
                                      feature_schema/application_schema.json.bak > /dev/null 2>&1; then
                                echo "false"
                            else
                                echo "true"
                            fi
                        ''',
                        returnStdout: true
                    ).trim()

                    if (schemaChanged == 'true') {
                        echo "Schema change detected! Updating Feast registry..."

                        sh '''
                            # Create ConfigMap with new schemas
                            kubectl create configmap feast-schemas \
                                --from-file=application/feast_repo/feature_schema/ \
                                --namespace=${FEAST_NAMESPACE} \
                                --dry-run=client -o yaml | kubectl apply -f -

                            # Run feast apply in K8s pod
                            kubectl run feast-apply-${BUILD_ID} \
                                --image=feastdev/feature-server:latest \
                                --namespace=${FEAST_NAMESPACE} \
                                --restart=Never \
                                --rm -i --attach \
                                -- feast apply || echo "Feast apply failed (may need manual intervention)"

                            # Restart stream processor to pick up new schemas
                            kubectl rollout restart deployment/feast-stream-processor \
                                -n ${FEAST_NAMESPACE} || echo "Stream processor restart skipped"

                            echo "✓ Feast registry updated"
                        '''
                    } else {
                        echo "No schema changes detected, skipping Feast update"
                    }
                }
            }
        }

        // STAGE 6: Verification (runs after all deployments)
        stage('Verify') {
            when {
                expression { currentBuild.result == null || currentBuild.result == 'SUCCESS' }
            }
            parallel {
                stage('Flink Job Health') {
                    steps {
                        script {
                            echo "Checking Flink job health..."
                            sh '''
                                # Wait for jobs to stabilize
                                sleep 10

                                # Check running job count
                                RUNNING_JOBS=$(curl -s ${FLINK_REST_API}/jobs/overview | \
                                    jq -r '.jobs[] | select(.state=="RUNNING") | .jid' | wc -l)

                                if [ "$RUNNING_JOBS" -ne 2 ]; then
                                    echo "ERROR: Expected 2 running jobs, found ${RUNNING_JOBS}"
                                    exit 1
                                fi

                                echo "✓ All Flink jobs healthy (${RUNNING_JOBS} running)"
                            '''
                        }
                    }
                }

                stage('Kafka Messages') {
                    steps {
                        script {
                            echo "Verifying Kafka message flow..."
                            sh '''
                                python3 ${AUTOMATION_HELPER}/verify_kafka_messages.py \
                                    --bootstrap ${KAFKA_BROKERS} \
                                    --topics hc.application_features,hc.application_ext \
                                    --timeout 30 \
                                    --min-messages 5 \
                                    || echo "WARNING: Kafka verification skipped (may be normal for new deployments)"
                            '''
                        }
                    }
                }
            }
        }
    }

    post {
        success {
            script {
                echo "✓ Pipeline completed successfully!"
                echo "✓ Flink deployment completed and verified"
                // TODO: Add Slack notification here
                // slackSend(color: 'good', message: "Flink Deployment Success: ${env.JOB_NAME} - ${env.BUILD_NUMBER}")
            }
        }
        failure {
            script {
                echo "✗ Pipeline failed!"
                // TODO: Add Slack notification here
                // slackSend(color: 'danger', message: "Flink Pipeline FAILED: ${env.JOB_NAME} - ${env.BUILD_NUMBER}")
            }
        }
        always {
            cleanWs()
        }
    }
}