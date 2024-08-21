FROM python:3.9
WORKDIR /opt
RUN git clone https://github.com/fang0654/LinkedInt
WORKDIR /opt/LinkedInt
RUN pip install -r requirements.txt

ENTRYPOINT ["python", "LinkedInt.py"]
# ENTRYPOINT ["/bin/sh"]