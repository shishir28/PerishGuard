FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY training/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY training/ /app/training/

CMD ["bash", "-lc", "python training/seed_local_db.py --batches ${BATCHES:-400} && python training/train_spoilage_model.py"]
