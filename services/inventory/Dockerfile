FROM python:3.12-slim
WORKDIR /app
COPY services/inventory/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common ./common
COPY services/inventory/app.py ./app.py
EXPOSE 5002
CMD ["python", "app.py"]

