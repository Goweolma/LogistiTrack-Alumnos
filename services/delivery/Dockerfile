FROM python:3.12-slim
WORKDIR /app
COPY services/delivery/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common ./common
COPY services/delivery/app.py ./app.py
EXPOSE 5004
CMD ["python", "app.py"]

