# Business Objective

**Improve key lending KPIs via predictive risk modeling:**

- **Default rate reduction** – lower the proportion of loan applicants who default
- **Loan approval efficiency** – increase approvals for low-risk borrowers
- **Loss mitigation** – reduce financial losses from write-offs
- **Customer retention** – minimize rejection of good customers and reduce churn
- **Risk-adjusted revenue growth** – enable differentiated pricing for different risk tiers

*(All entities are fictional—“Alpha Lending” is a placeholder.)*

## Situation

Alpha Lending processes thousands of loan applications monthly. A large share of applicants have limited or no formal credit history. This creates two challenges:

- **Revenue loss**: Many low-risk customers are wrongly rejected due to insufficient information.  
- **Credit losses**: Some high-risk applicants are incorrectly approved, leading to higher default rates.  

The company has diverse data sources—application forms, bureau records, past loan performance, credit card balances, and repayment histories—but lacks a unified, data-driven solution to leverage them for accurate decision-making.

## Task

Design and implement a **machine learning solution** that predicts the probability of default for each applicant.  
The solution must directly support the business objective by:

- Reducing default rates among approved loans  
- Increasing approvals of creditworthy applicants  
- Providing interpretable outputs for decision-makers  
- Allowing integration into the existing loan approval pipeline  

## Action

### Data Science Team
- **Data integration**: Consolidate application, bureau, previous credit, and repayment datasets into a single analytical view.  
- **Feature engineering**: Derive risk indicators (e.g., debt-to-income ratios, missed payment counts, external risk scores).  
- **Model development**: Train and validate predictive models (e.g., gradient boosting) with ROC-AUC as the primary evaluation metric.  
- **Interpretability**: Provide probability scores and explanations (e.g., SHAP values) to ensure business usability.  
- **Deployment readiness**: Deliver APIs or batch scoring pipelines that can be embedded into operational systems.  

### Business Team
- **Define acceptance thresholds**: Work with DS team to set default-probability cutoffs that balance growth vs. risk.  
- **Policy alignment**: Adapt credit approval rules and pricing strategies based on model outputs.  
- **Operational integration**: Train loan officers on interpreting model results and using them in decision-making.  
- **Monitoring & feedback**: Establish KPIs to continuously track impact (default rates, approval rates, revenue changes).  

## Result

*To be determined after deployment and monitoring phase.*

# Dataset

# Repository Structure

# High-level System Architecture 

# Application Port Allocation

## Port Ranges and Purpose

### Infrastructure Services (9000-9099)
- 9000: MinIO Object Storage API
- 9001: MinIO Management Console
- 9010: PostgreSQL Main Database
- 9020: Redis Cache (if added later)
- 9030: Elasticsearch (if added later)

### Risk Assessment Services (8000-8099)
- 8000: Personal Loan Risk Service
- 8001: Mortgage Risk Service  
- 8002: Credit Card Risk Service
- 8010: Risk Model Training Service (if added later)
- 8020: Risk Model Validation Service (if added later)

### API and Web Services (7000-7099)
- 7000: Main API Gateway
- 7010: Authentication Service (if added later)
- 7020: Notification Service (if added later)

### Development and Monitoring (6000-6999)
- 6000: Application Monitoring Dashboard
- 6010: Log Aggregation Service
- 6020: Health Check Service

## Service Communication Patterns

Risk assessment services communicate internally using service names:
- risk-service-personal communicates with postgres-main:5432
- risk-service-personal communicates with minio-storage:9000
- api-gateway routes requests to risk-service-personal:8080

External access uses mapped ports:
- Client applications connect to api-gateway via localhost:7000
- Administrators access MinIO console via localhost:9001
- Database administrators connect to PostgreSQL via localhost:9010

# Guide to Install and Run Code

## Use nbstripout --install