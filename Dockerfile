FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py config.py fetcher.py filter.py store.py accounts.json keywords.json ./
CMD ["python", "bot.py"]
