FROM python:3.11-slim

WORKDIR /app

# Set PYTHONPATH so relative imports in app.ims.* resolve correctly
# without this, uvicorn starts but imports fail inside the container
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.ims.main:app", "--host", "0.0.0.0", "--port", "8000"]