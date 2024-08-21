FROM python:3.9
WORKDIR /opt
RUN git clone https://github.com/fang0645/LinkedInt
WORKDIR /opt/Linkedint
RUN pip install -r requirements.txt

ENTRYPOINT ["python", "LinkedInt.py"]
