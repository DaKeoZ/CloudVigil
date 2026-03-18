FROM python:3.12-slim

WORKDIR /app

COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY proto/ ./proto/
COPY server/ ./server/

# Régénère les stubs depuis le proto au build (nécessite grpcio-tools)
RUN python -m grpc_tools.protoc \
        --proto_path=proto \
        --python_out=server/pb \
        --grpc_python_out=server/pb \
        proto/monitor.proto

EXPOSE 8000 50051

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
