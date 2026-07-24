FROM python:3.11-slim

WORKDIR /app

# Install the package (and its pinned dependencies) without dev tooling.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Local state file lives on a mounted volume — see README "Running locally".
VOLUME ["/data"]

ENV STATE_FILE_PATH=/data/state.json

ENTRYPOINT ["job-scrapper"]
