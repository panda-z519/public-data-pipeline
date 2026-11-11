FROM apify/actor-python:3.12
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[apify]"
CMD ["python", "-m", "data_pipeline.apify_main"]
