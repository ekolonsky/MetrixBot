FROM python:3
ADD . /code
WORKDIR /code
RUN python -m pip install -r requirements.txt
CMD ["python", "mbot.py"]
