#!/usr/bin/env python3
import json
import os
import sys
from urllib.request import Request, urlopen

prompt = " ".join(sys.argv[1:]) or "Say hello in one sentence."
payload = json.dumps(
    {
        "model": os.environ["MLX_MODEL"],
        "messages": [{"role": "user", "content": prompt}],
    }
).encode()
request = Request(
    os.environ["OPENAI_BASE_URL"].rstrip("/") + "/chat/completions",
    data=payload,
    headers={
        "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
        "Content-Type": "application/json",
    },
    method="POST",
)
print(urlopen(request, timeout=300).read().decode())
