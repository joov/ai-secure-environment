FROM python:3.12-alpine
RUN adduser -D -u 1000 secenv
COPY chat.py /usr/local/bin/chat.py
USER secenv
WORKDIR /workspace
CMD ["sleep", "infinity"]
