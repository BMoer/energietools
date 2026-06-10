FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for numpy/pandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install pvtool from bundled source
COPY pvtool-src/ /pvtool-src/
RUN pip install --no-cache-dir /pvtool-src/

# Copy application code
COPY app/ /app/app/

# Copy sample data and create upload directory
COPY data/ /app/data/
RUN mkdir -p /app/data/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
