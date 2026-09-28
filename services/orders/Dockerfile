FROM python:3.12-slim
WORKDIR /app
COPY services/orders/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common ./common
COPY services/orders/app.py ./app.py
EXPOSE 5001
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "1", "--threads", "4", "app:app"]

