Manage only the secenv project mounted at /managed/secenv.
Apply changes through the operator. Do not call the Docker socket yourself.

- status: GET http://operator:3199/secenv
- create/start: POST http://operator:3199/secenv/up
- stop: POST http://operator:3199/secenv/down

Send Authorization: Bearer $OPERATOR_TOKEN.
The local model is mlx/mlx-community/DeepSeek-R1-Distill-Qwen-7B-4bit.
Inside secenv the only LLM path is http://llm-proxy:8080/v1.
