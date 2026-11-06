FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY dados/ dados/
EXPOSE 8001
CMD ["python", "-m", "uvicorn", "dados.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
