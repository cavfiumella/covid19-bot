FROM ubuntu:21.10

ARG DEBIAN_FRONTEND=noninteractive
WORKDIR /usr/local/app

# install requirements
RUN apt -y update; apt -y install python3 python3-pip
COPY requirements.txt .
RUN pip install --no-input --no-cache-dir -r requirements.txt

# install project
COPY . .

CMD ["sh", "-c", "python3.9 main.py $TOKEN"]
