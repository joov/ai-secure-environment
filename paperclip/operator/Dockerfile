FROM python:3.12-alpine
RUN apk add --no-cache docker-cli docker-cli-compose
COPY operator.py /app/serve.py
EXPOSE 3199
CMD ["python", "-u", "/app/serve.py"]
