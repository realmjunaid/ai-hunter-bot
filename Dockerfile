FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy every module (providers.py was missing here and crashed the image on import)
# plus the runtime data files. State files stay out via .dockerignore/.gitignore.
COPY *.py ./
COPY accounts.json keywords.json ./
CMD ["python", "bot.py"]
