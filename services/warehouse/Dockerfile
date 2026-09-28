FROM python:3.12-slim
WORKDIR /app
COPY services/warehouse/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common ./common
COPY services/warehouse/app.py ./app.py
EXPOSE 5003
CMD ["python", "app.py"]

