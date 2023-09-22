# apt install qemu-user-static
# DOCKER_BUILDKIT=1 docker buildx build --platform linux/arm64 -t 192.168.1.51:5000/sdso/skycam:latest .
# docker push 192.168.1.51:5000/sdso/skycam:latest
# docker run -d -p 80:80 --device=/dev/bus/usb/001/003 --pull=always --restart unless-stopped --name=skycam 192.168.1.51:5000/sdso/skycam:latest

FROM arm64v8/python:3.9-slim
LABEL authors="Alex Helms"
WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
RUN apt-get update && apt-get install -y libusb-1.0-0
COPY app /code/app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]