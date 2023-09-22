# SDSO Skycam

Capture an image as a FITS and serves it via a web API.

The SDSO skycam uses the following hardware:

 - ZWO ASI224MC
 - 1.55mm f/1.5 CS Mount Lens
 - Raspberry Pi Zero 2 W
 - Waveshare PoE / USB HAT

The pi is powered via PoE and the camera is connected via USB.
The ZWO SDK is used to capture an image and serve it via a
FastAPI web app. An external service starts an image exposure,
polls for status, and downloads the image. Prometheus metrics
are also exposed for integration into the observatory monitoring system.

## Run

A camera is required to run the app.

For development:

```shell
pip install -r requirements.txt
uvicorn app.main:app --reload
```

As a container:

You must pass through the USB camera. Use `lsusb` to determine the bus address.

```shell
alex@skycam:~ $ lsusb
Bus 001 Device 004: ID 0bda:8152 Realtek Semiconductor Corp. RTL8152 Fast Ethernet Adapter
Bus 001 Device 003: ID 03c3:224a ZWO ASI224MC
Bus 001 Device 002: ID 1a40:0101 Terminus Technology Inc. Hub
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
```

The camera is at on `Bus 001` as `Device 003` so the path is `/dev/bus/usb/001/003`.

```shell
docker run -d -p 80:80 --device=/dev/bus/usb/001/003 --pull=always --restart unless-stopped --name=skycam sdso/skycam:latest
```

Once up and running, you can start an exposure, poll for its status, and download the completed image.

### Start an Exposure
```
POST /camera/expose
Content-Type: application/json
{
  "exposure": 3.0,
  "gain": 50,
  "offset": 10
}
```

### Get Status
```
GET /camera/status
Content-Type: application/json
{
  "status": "exposing",
}
```

### Download Image
```
GET /camera/image
Content-Type: application/octet-stream
Content-Length: 1234
<binary data>
```

## Build

The container is cross-compiled for `arm64v8`.
You may need to `apt install qemu-user-static` to build the container on x64.

```shell
DOCKER_BUILDKIT=1 docker buildx build --platform linux/arm64v8 -t sdso/skycam:latest .
```


## Deploy

```shell
docker run -d -p 80:80 --device=/dev/bus/usb/001/003 --pull=always --restart unless-stopped --name=skycam <registry_url>/sdso/skycam:latest
```
