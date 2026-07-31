MANIFESTS = {
    "kubernetes/namespace.yaml": """apiVersion: v1
kind: Namespace
metadata:
  name: ecom
""",
    "kubernetes/configmap.yaml": """apiVersion: v1
kind: ConfigMap
metadata:
  name: ecom-config
  namespace: ecom
data:
  POSTGRES_DB: ecom_db
  POSTGRES_USER: ecom_user
  RABBITMQ_DEFAULT_USER: ecom_user
  RABBITMQ_DEFAULT_PASS: ecom_password
""",
    "kubernetes/secrets.yaml": """apiVersion: v1
kind: Secret
metadata:
  name: ecom-secrets
  namespace: ecom
type: Opaque
stringData:
  POSTGRES_PASSWORD: ecom_password
  JWT_SECRET: super_secret_jwt_key
  INTERNAL_CLUSTER_SECRET: super_secret_cluster_key
  STRIPE_SECRET_KEY: sk_test_...
  STRIPE_WEBHOOK_SECRET: whsec_...
""",
    "kubernetes/postgres.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: ecom
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: postgres:15-alpine
          ports:
            - containerPort: 5432
          envFrom:
            - configMapRef:
                name: ecom-config
            - secretRef:
                name: ecom-secrets
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: ecom
spec:
  selector:
    app: postgres
  ports:
    - protocol: TCP
      port: 5432
      targetPort: 5432
""",
    "kubernetes/rabbitmq.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: rabbitmq
  namespace: ecom
spec:
  replicas: 1
  selector:
    matchLabels:
      app: rabbitmq
  template:
    metadata:
      labels:
        app: rabbitmq
    spec:
      containers:
        - name: rabbitmq
          image: rabbitmq:3.13-management-alpine
          ports:
            - containerPort: 5672
            - containerPort: 15672
          envFrom:
            - configMapRef:
                name: ecom-config
---
apiVersion: v1
kind: Service
metadata:
  name: rabbitmq
  namespace: ecom
spec:
  selector:
    app: rabbitmq
  ports:
    - name: amqp
      protocol: TCP
      port: 5672
      targetPort: 5672
    - name: management
      protocol: TCP
      port: 15672
      targetPort: 15672
""",
    "kubernetes/redis.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: ecom
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
        - name: redis
          image: redis:7-alpine
          ports:
            - containerPort: 6379
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: ecom
spec:
  selector:
    app: redis
  ports:
    - protocol: TCP
      port: 6379
      targetPort: 6379
""",
    "kubernetes/elasticsearch.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: elasticsearch
  namespace: ecom
spec:
  replicas: 1
  selector:
    matchLabels:
      app: elasticsearch
  template:
    metadata:
      labels:
        app: elasticsearch
    spec:
      containers:
        - name: elasticsearch
          image: elasticsearch:8.13.0
          env:
            - name: discovery.type
              value: single-node
            - name: xpack.security.enabled
              value: "false"
          ports:
            - containerPort: 9200
---
apiVersion: v1
kind: Service
metadata:
  name: elasticsearch
  namespace: ecom
spec:
  selector:
    app: elasticsearch
  ports:
    - protocol: TCP
      port: 9200
      targetPort: 9200
""",
    "kubernetes/identity-service.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: identity-service
  namespace: ecom
spec:
  replicas: 2
  selector:
    matchLabels:
      app: identity-service
  template:
    metadata:
      labels:
        app: identity-service
    spec:
      containers:
        - name: identity-service
          image: ecom/identity-service:latest
          ports:
            - containerPort: 8001
          envFrom:
            - configMapRef:
                name: ecom-config
            - secretRef:
                name: ecom-secrets
          env:
            - name: DATABASE_URL
              value: "postgresql://ecom_user:$(POSTGRES_PASSWORD)@postgres:5432/ecom_db"
---
apiVersion: v1
kind: Service
metadata:
  name: identity-service
  namespace: ecom
spec:
  selector:
    app: identity-service
  ports:
    - protocol: TCP
      port: 8001
      targetPort: 8001
""",
    "kubernetes/order-service.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  namespace: ecom
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-service
          image: ecom/order-service:latest
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: ecom-config
            - secretRef:
                name: ecom-secrets
          env:
            - name: DATABASE_URL
              value: "postgresql://ecom_user:$(POSTGRES_PASSWORD)@postgres:5432/ecom_db"
            - name: CELERY_BROKER_URL
              value: "amqp://ecom_user:ecom_password@rabbitmq:5672//"
            - name: REDIS_URL
              value: "redis://redis:6379/0"
            - name: ELASTICSEARCH_URL
              value: "http://elasticsearch:9200"
---
apiVersion: v1
kind: Service
metadata:
  name: order-service
  namespace: ecom
spec:
  selector:
    app: order-service
  ports:
    - protocol: TCP
      port: 8000
      targetPort: 8000
""",
    "kubernetes/celery-worker.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-worker
  namespace: ecom
spec:
  replicas: 2
  selector:
    matchLabels:
      app: celery-worker
  template:
    metadata:
      labels:
        app: celery-worker
    spec:
      containers:
        - name: celery-worker
          image: ecom/order-service:latest
          command: ["celery", "-A", "config", "worker", "-l", "info"]
          envFrom:
            - configMapRef:
                name: ecom-config
            - secretRef:
                name: ecom-secrets
          env:
            - name: DATABASE_URL
              value: "postgresql://ecom_user:$(POSTGRES_PASSWORD)@postgres:5432/ecom_db"
            - name: CELERY_BROKER_URL
              value: "amqp://ecom_user:ecom_password@rabbitmq:5672//"
            - name: REDIS_URL
              value: "redis://redis:6379/0"
            - name: ELASTICSEARCH_URL
              value: "http://elasticsearch:9200"
""",
    "kubernetes/analytics-service.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: analytics-service
  namespace: ecom
spec:
  replicas: 1
  selector:
    matchLabels:
      app: analytics-service
  template:
    metadata:
      labels:
        app: analytics-service
    spec:
      containers:
        - name: analytics-service
          image: ecom/analytics-service:latest
          env:
            - name: RABBITMQ_URL
              value: "amqp://ecom_user:ecom_password@rabbitmq:5672//"
            - name: DB_PATH
              value: "/app/data/analytics.db"
          volumeMounts:
            - name: analytics-data
              mountPath: /app/data
      volumes:
        - name: analytics-data
          persistentVolumeClaim:
            claimName: analytics-pvc
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: analytics-pvc
  namespace: ecom
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
""",
    "kubernetes/notification-service.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: notification-service
  namespace: ecom
spec:
  replicas: 1
  selector:
    matchLabels:
      app: notification-service
  template:
    metadata:
      labels:
        app: notification-service
    spec:
      containers:
        - name: notification-service
          image: ecom/notification-service:latest
          env:
            - name: RABBITMQ_URL
              value: "amqp://ecom_user:ecom_password@rabbitmq:5672//"
""",
    "kubernetes/gateway.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: gateway
  namespace: ecom
spec:
  replicas: 1
  selector:
    matchLabels:
      app: gateway
  template:
    metadata:
      labels:
        app: gateway
    spec:
      containers:
        - name: gateway
          image: kong:3.4
          env:
            - name: KONG_DATABASE
              value: "off"
            - name: KONG_DECLARATIVE_CONFIG
              value: "/usr/local/kong/kong.yml"
            - name: KONG_PROXY_ACCESS_LOG
              value: "/dev/stdout"
            - name: KONG_PROXY_ERROR_LOG
              value: "/dev/stderr"
            - name: KONG_ADMIN_ACCESS_LOG
              value: "/dev/stdout"
            - name: KONG_ADMIN_ERROR_LOG
              value: "/dev/stderr"
            - name: KONG_ADMIN_LISTEN
              value: "0.0.0.0:8001, 0.0.0.0:8444 ssl"
          ports:
            - containerPort: 8000
            - containerPort: 8001
          volumeMounts:
            - name: kong-config
              mountPath: /usr/local/kong
      volumes:
        - name: kong-config
          configMap:
            name: kong-declarative-config
---
apiVersion: v1
kind: Service
metadata:
  name: gateway
  namespace: ecom
spec:
  type: LoadBalancer
  selector:
    app: gateway
  ports:
    - name: proxy
      protocol: TCP
      port: 80
      targetPort: 8000
    - name: admin
      protocol: TCP
      port: 8001
      targetPort: 8001
""",
}

for path, content in MANIFESTS.items():
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

print("Created Kubernetes manifests")
