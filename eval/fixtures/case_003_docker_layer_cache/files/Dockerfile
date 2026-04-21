FROM python:3.12-slim AS builder
WORKDIR /app
COPY app.py ./
RUN python3 -c "import ast; ast.parse(open('app.py').read())"

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /app/app.py ./
CMD ["python3", "app.py"]
