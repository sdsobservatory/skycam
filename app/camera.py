from typing import Union, Optional
import asyncio
from io import BytesIO
from datetime import datetime
from astropy.io import fits
import numpy as np
import app.zwo as zwo


class Camera:

    def __init__(self, identifier: Union[int, str]):
        self._camera = zwo.Camera(identifier)
        self._buffer = bytearray()
        self._fits_data = BytesIO()
        self.is_exposing = False

    def __enter__(self) -> 'Camera':
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self):
        self._camera.open()
        self._camera.disable_dark_subtract()
        self._camera.stop_video_exposure()
        self._camera.stop_exposure()

    def close(self):
        self._camera.close()
        self._fits_data.close()

    async def capture_image_async(self,
                                  exposure: float,
                                  gain: int,
                                  offset: int,
                                  wb_b: Optional[int] = None,
                                  wb_r: Optional[int] = None,
                                  is_dark: bool = False) -> BytesIO:
        try:
            self.is_exposing = True

            self._camera.reset_roi()
            self._camera.set_control_value(zwo.ControlType.GAIN, gain)
            self._camera.set_control_value(zwo.ControlType.OFFSET, offset)
            self._camera.image_type = zwo.ImageType.RAW16

            if wb_b is not None:
                self._camera.set_control_value(zwo.ControlType.WB_B, wb_b)

            if wb_r is not None:
                self._camera.set_control_value(zwo.ControlType.WB_R, wb_r)

            if len(self._buffer) != self._camera.image_size_in_bytes:
                self._buffer = bytearray(self._camera.image_size_in_bytes)

            poll_interval_ms = max(0.01, exposure / 25.0)
            utc_now = datetime.utcnow()
            local_now = datetime.now()

            try:
                self._clear_buffer()
                await self._camera.capture_image_async(exposure_sec=exposure,
                                                       is_dark=is_dark,
                                                       poll_interval_ms=poll_interval_ms,
                                                       buffer=self._buffer)
            except asyncio.CancelledError:
                self._camera.stop_exposure()
                raise

            camera_info = self._camera.camera_info
            roi = self._camera.roi
            image_data = np.frombuffer(self._buffer, dtype='uint16').reshape((roi.height, roi.width))
            hdu = fits.PrimaryHDU(image_data)
            hdu.header['IMAGETYP'] = ('DARK' if is_dark else 'LIGHT', 'Type of exposure')
            hdu.header['INSTRUME'] = (camera_info['Name'], 'Imaging instrument name')
            hdu.header['EXPOSURE'] = (exposure, '[s] Exposure time')
            hdu.header['EXPTIME'] = (exposure, '[s] Exposure time')
            hdu.header['DATE-OBS'] = (utc_now.isoformat(), 'Time of observation (UTC)')
            hdu.header['DATE-LOC'] = (local_now.isoformat(), 'Time of observation (Local)')
            hdu.header['GAIN'] = (gain, 'Sensor gain')
            hdu.header['OFFSET'] = (offset, 'Sensor offset')
            if camera_info['IsColorCam']:
                bayer_lookup = {0: 'RGGB', 1: 'BGGR', 2: 'GRBG', 3: 'GBRG'}
                bayer = bayer_lookup[camera_info['BayerPattern']]
                hdu.header['BAYERPAT'] = (bayer, 'Bayer pattern')
                hdu.header['COLORTYP'] = (bayer, 'Bayer pattern')

            self._fits_data.close()
            self._fits_data = BytesIO()
            hdu.writeto(self._fits_data)
            return self._fits_data
        except:
            self._clear_buffer()
            self._fits_data.close()
            self._fits_data = BytesIO()
            raise
        finally:
            self.is_exposing = False

    def _clear_buffer(self):
        view = memoryview(self._buffer)
        for i in range(len(view)):
            view[i] = 0

    @property
    def most_recent_fits_data(self) -> BytesIO:
        return self._fits_data
