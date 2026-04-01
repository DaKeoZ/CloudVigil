FROM python:3.12-slim

WORKDIR /app

COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

# Les stubs gRPC / protobuf dans server/pb/ sont versionnés (imports server.pb.*).
# Ne pas régénérer ici avec protoc : sortirait un monitor_pb2_grpc.py avec
# « import monitor_pb2 », ce qui casse au runtime dans le conteneur.

COPY server/ ./server/

EXPOSE 8000 50051

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
