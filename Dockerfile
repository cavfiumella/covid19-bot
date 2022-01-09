FROM python:3.9-slim

WORKDIR /usr/src/app

# install app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["sh", "-c", "./run -t $TOKEN"]
