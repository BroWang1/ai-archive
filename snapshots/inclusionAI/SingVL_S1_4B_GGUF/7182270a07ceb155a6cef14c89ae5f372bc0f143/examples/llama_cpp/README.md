# SingVL-4B llama.cpp backend

This directory provides the CPU backend for the SingVL-4B GGUF release. It uses the public libllama and libmtmd APIs at commit `f3b407ca1bfeeecebf9e9ef19fcd6eed565bd70a`.

- `runner.cpp` loads the decoder and vision projector, executes one complete bidirectional input per question, and returns candidate logits.
- `build.py` compiles the external adapter against a local llama.cpp build.
- `model.py` exposes `SingVLS1.predict()` using the shared processor and answer protocol.
- `serve.py` exposes the FastAPI `/v1/systemone` endpoint and runtime information at `/health`.

The model card contains the Python and HTTP examples. The build guide contains compiler commands, environment settings and validation commands. [Model card](../../README.md) · [Build guide](../../docs/build.md)
