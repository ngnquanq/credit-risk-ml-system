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

## Create network
We need to create network so that our services can communicate to each other
```shell
docker network create hc-network
```
The result will look like this: 
![Create network component](step1.create_network.png)

This network will be share among services, this step is **crucial** because it allow the DNS of our services to be resolve and can be reach out durring message transfer

## Run the important parts
For this, we need to spin up a few things. We will kinda assume that the company will already have this for up, including things like: 
- API services
- Data platform
- etc...

### Spin up API services and operational database
First, we need to bring up the API services and the operational database. 
```shell
docker compose --env-file ./services/core/.env.core \
    -f ./services/core/docker-compose.operationaldb.yml \
    -f ./services/core/docker-compose.api.yml \
    -f ./services/data/docker-compose.storage.yml \
    up -d
```
Just to be clear:
- API Services in this case including:
    - 1 Nginx to route customer requests.
    - 2 streamlit front-end for customer to navigate
    - 2 API services for sending and handling requests. 
- Operational database in this case including:
    - 1 file storage database (MinIO) for storing customer's documentation
    - 1 OLTP database (postgres) for storing day over day operational actions in the company. 
    - 1 PG Bouncer as a pooling layer in case there are multiple requests. 

![The core services are up and running](Step2.result.png)

### Spin up Data Platform
There are multiple things to work here, therefore stick with me.
#### Spin up CDC and Event Bus components
In order to serve request in real-time with an event-driven manner, we will use Debezium for the change-data-capture (CDC) and Kafka. To spin these up, run the following command:
```shell
docker compose  --env-file ./services/core/.env.core \
 --env-file ./services/data/.env.data \
 -f ./services/data/docker-compose.streaming.yml \
 -f ./services/data/docker-compose.cdc.yml \
 up -d
```
This code will bring up the kafka components as well as the cdc components. 

For the CDC, there will be a helper connector that help connect Debezium to postgres using the postgres connector. 

For the Kafka, we will use zookeper for managing kafka cluster, schema registry to handle schema evolution, kafka ui from provectus labs for easier debugging process.

![Debezium and Kafka components up successfully](step3.create_kafka_cdc.png)

After everything is up, we need to create kafka topics, by running this following command: 

```python
python ./services/data/scripts/kafka/create_topics.py 
```

If navigate to kafka ui, we will see that there are some topics that has been created

![Created Kafka topics](Step4.created_kafka_topics.png)

Additionally, if we check on debezium ui, we will also see that the Postgres connector is also created.

![Created Debezium connection](Step4.created_debezium_connection.png)

#### Spin up DWH, Data Mart and External Data.
In real life scenario, there are some data that we can not store in our datawarehouse or our operational database, because we basically dont have that kind of information and either are our customers. Therefore we need data from external sources, a dedicated third-party company that gather all the data and do some kind of transformation. And in that case, often we will need to get the data via some API being provided. 

In other to bring up the datawarehouse as well as external data, we will run: 

```shell
docker compose --env-file ./services/core/.env.core \
 --env-file ./services/data/.env.data  \
 -f ./services/data/docker-compose.warehouse.yml \ 
 up -d
```

Then, wait until all the container are started:

![DWH containers](Step5.DWH_started.png)

After that, we need to parse in some data. For simplicity, instead of create 2 different dwh (1 is the company's internal dwh and 1 is the bureau's external dwh), I will just merge it into 1 data warehouse with different naming convention. 

In terms of the Medallion Data Architecture, what we just bring up are called the *silver layer*. 

```shell
# For internal data
bash ./services/data/scripts/dwh/ch_load_internal.sh
# For external data
bash ./services/data/scripts/dwh/ch_load_external.sh
```

For data that are specialized and ready to use in our data mart, we will need to run dbt to perform the data transfomartion step from the *silver layer* to the *gold layer*. These transformation are applied only to our internal data warehouse because we dont have the audacity to do that with external sources.

```shell
cd ml_data_mart/
# Run the debug to see if we are missing anything
dbt debug --project-dir . --profiles-dir .
# Run the transformation
dbt run --project-dir . --profiles-dir . --target gold
```

After the transformation, it will output to be something like this:

![The DBT Results](Step5.DBT_results.png)

If you notice, you will see that these are under the data mart database with the prefix mart_. These will be run daily, thanks to the power of clickhouse, the transformation step will be very quick. 

After that, we also need to setup a query service. These query services will aggregate the query data that serve the modeling purpose. In some company, it's the ML Engineer that will do this step. The logic of the aggregation is taken from the ./notebooks/ folder. To bring these up, run the following: 

```shell
docker compose --env-file ./services/data/.env.data \
    -f ./services/data/docker-compose.query-services.yml \
    up -d
```

![Bring up query service](Step6.query-services.png)

**Note**: The query services here are written in python for the aggregation, based on historical data, these aggregation are fast and lightweight, however later on when we receive more and more request, these aggregation could become our bottleneck. The solution to this is maybe written code in another language/library that is faster, could be cython or maybe sth else. 

#### Spin up Flink and submit Flink Job
We need Flink to handle the streaming processing part of the incoming data from the kafka topic. 

```shell
docker compose --env-file ./services/data/.env.data \ 
    -f services/data/docker-compose.flink.yml \
    up -d
```
For now, this stream processing flow is quite simple, it just masking the data for PII. But later on when we acquire some of the new features, we can absolutely ref back and change the logic. 

#### Spin up feature store components


#### Spin up model registry components


#### Spin up serving components


#### Spin up training components


#### Spin up orchestration components


#### Spin up logging components


#### Spin up tracing components


#### Spin up BI components
  