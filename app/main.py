from contextlib import asynccontextmanager
from dataclasses import dataclass
from fastapi import FastAPI, Request, Response, BackgroundTasks
from prometheus_fastapi_instrumentator import Instrumentator
from app.camera import Camera


@dataclass
class ExposureParameters:
    exposure: float
    gain: int
    offset: int
    is_dark: bool = False


async def take_image(camera: Camera, parameters: ExposureParameters):
    await camera.capture_image_async(parameters.exposure,
                                     parameters.gain,
                                     parameters.offset,
                                     is_dark=parameters.is_dark)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with Camera(0) as camera:
        app.state.camera = camera
        yield


app = FastAPI(lifespan=lifespan)
Instrumentator().instrument(app).expose(app)


@app.post('/camera/expose')
async def camera_expose(parameters: ExposureParameters,
                        background_tasks: BackgroundTasks,
                        request: Request,
                        response: Response):
    camera: Camera = request.app.state.camera
    if camera.is_exposing:
        response.status_code = 409
        return {}
    background_tasks.add_task(take_image, camera, parameters)
    return {}


@app.get('/camera/status')
async def camera_status(request: Request):
    camera: Camera = request.app.state.camera
    if camera.is_exposing:
        return {'status': 'exposing'}
    elif not camera.is_exposing and camera.most_recent_fits_data.getbuffer().nbytes > 0:
        return {'status': 'complete'}
    return {'status': 'error'}


@app.get('/camera/image')
async def camera_image(request: Request):
    camera: Camera = request.app.state.camera
    length = camera.most_recent_fits_data.getbuffer().nbytes
    camera.most_recent_fits_data.seek(0)
    return Response(camera.most_recent_fits_data.getvalue(),
                    media_type='application/octet-stream',
                    headers={'Content-Length': str(length)})
