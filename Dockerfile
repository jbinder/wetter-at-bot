FROM python:3.12-slim

WORKDIR /app

# DejaVu fonts are bundled with matplotlib; this adds extra system fonts
# and ensures the font cache can be built without a writable home dir
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-build matplotlib font cache so the first request is fast
RUN python -c "import matplotlib.font_manager"

COPY bot.py weather.py chart.py ./

VOLUME ["/data"]

CMD ["python", "bot.py"]
