FROM python:3.11-slim
WORKDIR /app
# requirements at root or inside api/
COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# copy backend code
COPY api/app ./api/app
# copy AMSI bypass script
COPY AMSI ./AMSI
EXPOSE 8000
CMD ["uvicorn", "api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]