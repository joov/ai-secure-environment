Manage only the secenv project mounted at /managed/secenv.
Apply changes through the operator. Do not call the Docker socket yourself.

- status: GET http://operator:3199/secenv
- create/start: POST http://operator:3199/secenv/up
- stop: POST http://operator:3199/secenv/down

Send Authorization: Bearer $OPERATOR_TOKEN.
The local Qwen model is described in /managed/secenv/config/model.json.
Inside secenv the only LLM path is http://llm-proxy:8080/v1.
Do not add a second model runtime.
