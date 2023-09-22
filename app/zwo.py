import sys
from typing import Optional, Dict, Any, Tuple, List, Union
import ctypes
import platform
from pathlib import Path
import ctypes as c
from dataclasses import dataclass
from enum import IntEnum
import time
import asyncio


asi = None


class BayerPattern(IntEnum):
    RG = 0
    BG = 1
    GR = 2
    GB = 3


class ImageType(IntEnum):
    RAW8 = 0
    RGB24 = 1
    RAW16 = 2
    Y8 = 3


class GuideDirection(IntEnum):
    NORTH = 0
    SOUTH = 1
    EAST = 2
    WEST = 3


class FlipDirection(IntEnum):
    NONE = 0
    HORIZONTAL = 1
    VERTICAL = 2
    BOTH = 3


class TriggerMode(IntEnum):
    NORMAL = 0
    SOFT_EDGE = 1
    RISE_EDGE = 2
    FALL_EDGE = 3
    SOFT_LEVEL = 4
    HIGH_LEVEL = 5
    LOW_LEVEL = 6


class ErrorCode(IntEnum):
    SUCCESS = 0
    INVALID_INDEX = 1
    INVALID_ID = 2
    INVALID_CONTROL_TYPE = 3
    CAMERA_CLOSED = 4
    CAMERA_REMOVED = 5
    INVALID_PATH = 6
    INVALID_FILEFORMAT = 7
    INVALID_SIZE = 8
    INVALID_IMGTYPE = 9
    OUTOF_BOUNDARY = 10
    TIMEOUT = 11
    INVALID_SEQUENCE = 12
    BUFFER_TOO_SMALL = 13
    VIDEO_MODE_ACTIVE = 14
    EXPOSURE_IN_PROGRESS = 15
    GENERAL_ERROR = 16
    INVALID_MODE = 17


class TriggerOutput(IntEnum):
    NONE = -1
    PIN_A = 0
    PIN_B = 2


class ExposureStatus(IntEnum):
    IDLE = 0
    WORKING = 1
    SUCCESS = 2
    FAILED = 3


class ControlType(IntEnum):
    GAIN = 0
    EXPOSURE = 1
    GAMMA = 2
    WB_R = 3
    WB_B = 4
    OFFSET = 5
    BANDWIDTH_OVERLOAD = 6
    OVERCLOCK = 7
    TEMPERATURE = 8
    FLIP = 9
    AUTO_MAX_GAIN = 10
    AUTO_MAX_EXP = 11
    AUTO_TARGET_BRIGHTNESS = 12
    HARDWARE_BIN = 13
    HIGH_SPEED_MODE = 14
    COOLER_POWER_PERC = 15
    TARGET_TEMP = 16
    COOLER_ON = 17
    MONO_BIN = 18
    FAN_ON = 19
    PATTERN_ADJUST = 20
    ANTI_DEW_HEATER = 21
    UNKNOWN_22 = 22


@dataclass
class ROI:
    x: int
    y: int
    width: int
    height: int
    bins: int
    image_type: ImageType


def _get_camera_property(camera_id: int) -> Dict[str, Any]:
    prop = _ASI_CAMERA_INFO()
    r = asi.ASIGetCameraProperty(prop, camera_id)
    if r:
        raise _zwo_errors[r]
    return prop.get_dict()


def _open_camera(camera_id: int) -> None:
    r = asi.ASIOpenCamera(camera_id)
    if r:
        raise _zwo_errors[r]


def _init_camera(camera_id: int) -> None:
    r = asi.ASIInitCamera(camera_id)
    if r:
        raise _zwo_errors[r]



def _close_camera(camera_id: int) -> None:
    r = asi.ASICloseCamera(camera_id)
    if r:
        raise _zwo_errors[r]


def _get_num_controls(camera_id: int) -> int:
    num = c.c_int()
    r = asi.ASIGetNumOfControls(camera_id, num)
    if r:
        raise _zwo_errors[r]
    return num.value


def _get_control_caps(camera_id: int, control_index: int) -> Dict[str, Any]:
    caps = _ASI_CONTROL_CAPS()
    r = asi.ASIGetControlCaps(camera_id, control_index, caps)
    if r:
        raise _zwo_errors[r]
    return caps.get_dict()


def _get_control_value(camera_id: int, control_type: ControlType) -> Tuple[int, bool]:
    value = c.c_long()
    auto = c.c_int()
    r = asi.ASIGetControlValue(camera_id, control_type.value, value, auto)
    if r:
        raise _zwo_errors[r]
    return value.value, bool(auto.value)


def _set_control_value(camera_id: int, control_type: ControlType, value: int, auto: bool) -> None:
    r = asi.ASISetControlValue(camera_id, control_type.value, value, auto)
    if r:
        raise _zwo_errors[r]


def _get_roi_format(camera_id: int) -> Tuple[int, int, int, int]:
    width = c.c_int()
    height = c.c_int()
    bins = c.c_int()
    image_type = c.c_int()
    r = asi.ASIGetROIFormat(camera_id, width, height, bins, image_type)
    if r:
        raise _zwo_errors[r]
    return width.value, height.value, bins.value, image_type.value


def _set_roi(camera_id: int, roi: ROI) -> None:
    cam_info = _get_camera_property(camera_id)

    if roi.bins < 1:
        raise ValueError('ROI bins too small')

    if roi.width < 8:
        raise ValueError('ROI width too small')
    elif roi.width > cam_info['MaxWidth'] // roi.bins:
        raise ValueError('ROI width larger than binned sensor width')
    elif roi.width % 8 != 0:
        raise ValueError('ROI width must be a multiple of 8')

    if roi.height < 2:
        raise ValueError('ROI height too small')
    elif roi.height > cam_info['MaxHeight'] // roi.bins:
        raise ValueError('ROI height larger than binned sensor height')
    elif roi.height % 2 != 0:
        raise ValueError('ROI height must be a multiple of 2')

    if cam_info['Name'] in ['ZWO ASI120MM', 'ZWO ASI120MC'] and (roi.width * roi.height) % 1024 != 0:
        raise ValueError(f'ROI width * height must be multiple of 1024 for {cam_info["Name"]}')

    r = asi.ASISetROIFormat(camera_id,
                            roi.width,
                            roi.height,
                            roi.bins,
                            roi.image_type.value)
    if r:
        raise _zwo_errors[r]


def _get_start_position(camera_id: int) -> Tuple[int, int]:
    start_x = c.c_int()
    start_y = c.c_int()
    r = asi.ASIGetStartPos(camera_id, start_x, start_y)
    if r:
        raise _zwo_errors[r]
    return start_x.value, start_y.value


def _set_start_position(camera_id: int, x: int, y: int) -> None:
    if x < 0:
        raise ValueError('X position too small')
    if y < 0:
        raise ValueError('Y position too small')
    r = asi.ASISetStartPos(camera_id, x, y)
    if r:
        raise _zwo_errors[r]


def _start_exposure(camera_id: int, is_dark: bool) -> None:
    r = asi.ASIStartExposure(camera_id, is_dark)
    if r:
        raise _zwo_errors[r]


def _stop_exposure(camera_id: int) -> None:
    r = asi.ASIStopExposure(camera_id)
    if r:
        raise _zwo_errors[r]


def _get_exposure_status(camera_id: int) -> ExposureStatus:
    status = c.c_int()
    r = asi.ASIGetExpStatus(camera_id, status)
    if r:
        raise _zwo_errors[r]
    return ExposureStatus(status.value)


def _download_image(camera_id: int, buffer: Optional[bytearray]) -> bytearray:
    width, height, bins, image_type = _get_roi_format(camera_id)
    size = width * height
    if image_type == ImageType.RAW16:
        size *= 2
    elif image_type == ImageType.RGB24:
        size *= 3

    if buffer is None:
        buffer = bytearray(size)
    else:
        if not isinstance(buffer, bytearray):
            raise TypeError('Supplied buffer must be a bytearray')
        if len(buffer) != size:
            raise ValueError(f'Buffer must be {size} bytes but it is {len(buffer)}')

    cbuf_type = c.c_char * size
    cbuf = cbuf_type.from_buffer(buffer)
    r = asi.ASIGetDataAfterExp(camera_id, cbuf, size)
    if r:
        raise _zwo_errors[r]
    return buffer


def _get_id(camera_id: int) -> str:
    asi_id = _ASI_ID()
    r = asi.ASIGetId(camera_id, asi_id)
    if r:
        raise _zwo_errors[r]
    return asi_id.get_id()


def _stop_video_capture(camera_id: int) -> None:
    r = asi.ASIStopVideoCapture(camera_id)
    if r:
        raise _zwo_errors[r]


def _disable_dark_subtract(camera_id: int) -> None:
    r = asi.ASIDisableDarkSubtract(camera_id)
    if r:
        raise _zwo_errors[r]


def get_num_cameras() -> int:
    return asi.ASIGetNumOfConnectedCameras()


def list_cameras() -> List[str]:
    r = []
    for camera_id in range(get_num_cameras()):
        r.append(_get_camera_property(camera_id)['Name'])
    return r


def print_controls(camera: 'Camera') -> None:
    controls = camera.controls
    for cn in sorted(controls.keys()):
        print(f'    {cn}:')
        for k in sorted(controls[cn].keys()):
            print(f'        {k}: {repr(controls[cn][k])}')


def print_control_values(camera: 'Camera') -> None:
    values = camera.control_values
    for name, value in values.items():
        print(f'{name}: {value}')


class ZwoError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class ZwoIoError(ZwoError):
    def __init__(self, error_code: ErrorCode):
        super().__init__(error_code.name)
        self.error_code = error_code


class Camera:
    def __init__(self, identifier: Union[int, str]):
        self.id = -1
        self.connected = False

        if isinstance(identifier, int):
            # ASI sdk requires calling ASIGetNumOfConnectedCameras or the ID won't work
            num_cameras = get_num_cameras()
            if 0 <= identifier < num_cameras:
                self.id = identifier
            else:
                raise ValueError(f'Invalid camera id {identifier}, {num_cameras} cameras found')
        else:
            for i in range(get_num_cameras()):
                model = _get_camera_property(i)['Name']
                if model in (identifier, f'ZWO {identifier}'):
                    self.id = i
                    break
            if self.id < 0:
                raise ValueError(f'Could not find camera model {identifier}')

    def __del__(self):
        try:
            self.close()
        except:
            pass

    def __enter__(self) -> 'Camera':
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self):
        try:
            _open_camera(self.id)
            _init_camera(self.id)
            self.connected = True
        except Exception as e:
            self.close()
            raise e

    def close(self):
        try:
            _close_camera(self.id)
        finally:
            self.connected = False

    def set_roi(self,
                x: Optional[int] = None,
                y: Optional[int] = None,
                width: Optional[int] = None,
                height: Optional[int] = None,
                bins: Optional[int] = None,
                image_type: Optional[ImageType] = None):
        cam_info = self.camera_info
        roi = self.roi

        if bins is None:
            bins = roi.bins
        elif 'SupportedBins' in cam_info and bins not in cam_info['SupportedBins']:
            raise ValueError(f'Unsupported bins, camera only supports {cam_info["SupportedBins"]}')

        image_type = image_type or roi.image_type

        if width is None:
            width = cam_info['MaxWidth'] // bins
            width -= width % 8  # must multiple of 8

        if height is None:
            height = cam_info['MaxHeight'] // bins
            height -= height % 2  # must multiple of 2

        if x is None:
            x = ((cam_info['MaxWidth'] // bins) - width) // 2

        if x + width > cam_info['MaxWidth'] // bins:
            raise ValueError('ROI and start position larger than binned sensor width')

        if y is None:
            y = ((cam_info['MaxHeight'] // bins) - height) // 2

        if y + height > cam_info['MaxHeight'] // bins:
            raise ValueError('ROI and start position larger than binned sensor height')

        new_roi = ROI(x, y, width, height, bins, image_type)
        _set_roi(self.id, new_roi)
        _set_start_position(self.id, x, y)

    def reset_roi(self) -> None:
        cam_info = self.camera_info
        self.set_roi(x=0,
                     y=0,
                     width=cam_info['MaxWidth'],
                     height=cam_info['MaxHeight'],
                     bins=1)

    def get_control_value(self, control_type: ControlType) -> Tuple[int, bool]:
        return _get_control_value(self.id, control_type)

    def set_control_value(self, control_type: ControlType, value: int, auto: bool = False) -> None:
        _set_control_value(self.id, control_type, value, auto)

    def stop_exposure(self) -> None:
        try:
            _stop_exposure(self.id)
        except (KeyboardInterrupt, SystemExit):
            raise
        except ZwoError:
            pass

    def stop_video_exposure(self) -> None:
        try:
            _stop_video_capture(self.id)
        except (KeyboardInterrupt, SystemExit):
            raise
        except ZwoError:
            pass

    def disable_dark_subtract(self) -> None:
        _disable_dark_subtract(self.id)

    def capture_image(self,
                      exposure_sec: float,
                      is_dark: bool = False,
                      poll_interval_ms: float = 0.01,
                      buffer: Optional[bytearray] = None) -> bytearray:
        self.set_control_value(ControlType.EXPOSURE, int(exposure_sec * 1_000_000))
        _start_exposure(self.id, is_dark)

        while (status := _get_exposure_status(self.id)) == ExposureStatus.WORKING:
            if poll_interval_ms != 0:
                time.sleep(poll_interval_ms)

        if status != ExposureStatus.SUCCESS:
            raise ZwoError(f'Image capture failed as {status.name}')

        return _download_image(self.id, buffer)

    async def capture_image_async(self,
                                  exposure_sec: float,
                                  is_dark: bool = False,
                                  poll_interval_ms: float = 0.01,
                                  buffer: Optional[bytearray] = None
                                  ) -> bytearray:
        self.set_control_value(ControlType.EXPOSURE, int(exposure_sec * 1_000_000))
        _start_exposure(self.id, is_dark)

        while (status := _get_exposure_status(self.id)) == ExposureStatus.WORKING:
            if poll_interval_ms != 0:
                await asyncio.sleep(poll_interval_ms)

        if status != ExposureStatus.SUCCESS:
            raise ZwoError(f'Image capture failed as {status.name}')

        return _download_image(self.id, buffer)

    @property
    def camera_info(self) -> Dict[str, Any]:
        return _get_camera_property(self.id)

    @property
    def num_controls(self) -> int:
        return _get_num_controls(self.id)

    @property
    def controls(self) -> Dict[str, Any]:
        r = dict()
        for i in range(self.num_controls):
            d = _get_control_caps(self.id, i)
            r[d['Name']] = d
        return r

    @property
    def control_values(self) -> Dict[str, Any]:
        controls = self.controls
        r = dict()
        for k in controls:
            r[k] = self.get_control_value(ControlType(controls[k]['ControlType']))[0]
        return r

    @property
    def roi(self) -> ROI:
        x, y = _get_start_position(self.id)
        width, height, bins, image_type = _get_roi_format(self.id)
        return ROI(x, y, width, height, bins, ImageType(image_type))

    @property
    def image_type(self) -> ImageType:
        return self.roi.image_type

    @image_type.setter
    def image_type(self, value: ImageType) -> None:
        self.set_roi(image_type=value)

    @property
    def image_size_in_bytes(self) -> int:
        roi = self.roi
        size = roi.width * roi.height
        if roi.image_type == ImageType.RAW16:
            size *= 2
        elif roi.image_type == ImageType.RGB24:
            size *= 3
        return size


_zwo_errors = [ZwoIoError(error_code) for error_code in ErrorCode]


class _ASI_CAMERA_INFO(c.Structure):
    _fields_ = [
        ('Name', c.c_char * 64),
        ('CameraID', c.c_int),
        ('MaxHeight', c.c_long),
        ('MaxWidth', c.c_long),
        ('IsColorCam', c.c_int),
        ('BayerPattern', c.c_int),
        ('SupportedBins', c.c_int * 16),
        ('SupportedVideoFormat', c.c_int * 8),
        ('PixelSize', c.c_double),  # in um
        ('MechanicalShutter', c.c_int),
        ('ST4Port', c.c_int),
        ('IsCoolerCam', c.c_int),
        ('IsUSB3Host', c.c_int),
        ('IsUSB3Camera', c.c_int),
        ('ElecPerADU', c.c_float),
        ('BitDepth', c.c_int),
        ('IsTriggerCam', c.c_int),

        ('Unused', c.c_char * 16)
    ]

    def get_dict(self) -> Dict[str, Any]:
        r = {}
        for k, _ in self._fields_:
            v = getattr(self, k)
            if sys.version_info[0] >= 3 and isinstance(v, bytes):
                v = v.decode()
            r[k] = v
        del r['Unused']

        r['SupportedBins'] = []
        for i in range(len(self.SupportedBins)):
            if self.SupportedBins[i]:
                r['SupportedBins'].append(self.SupportedBins[i])
            else:
                break

        r['SupportedVideoFormat'] = []
        for i in range(len(self.SupportedVideoFormat)):
            if self.SupportedVideoFormat[i] == -1:
                break
            r['SupportedVideoFormat'].append(self.SupportedVideoFormat[i])

        for k in ('IsColorCam', 'MechanicalShutter', 'IsCoolerCam',
                  'IsUSB3Host', 'IsUSB3Camera'):
            r[k] = bool(getattr(self, k))

        return r


class _ASI_CONTROL_CAPS(c.Structure):
    _fields_ = [
        ('Name', c.c_char * 64),
        ('Description', c.c_char * 128),
        ('MaxValue', c.c_long),
        ('MinValue', c.c_long),
        ('DefaultValue', c.c_long),
        ('IsAutoSupported', c.c_int),
        ('IsWritable', c.c_int),
        ('ControlType', c.c_int),
        ('Unused', c.c_char * 32),
    ]

    def get_dict(self) -> Dict[str, Any]:
        r = {}
        for k, _ in self._fields_:
            v = getattr(self, k)
            if sys.version_info[0] >= 3 and isinstance(v, bytes):
                v = v.decode()
            r[k] = v
        del r['Unused']
        for k in ('IsAutoSupported', 'IsWritable'):
            r[k] = bool(getattr(self, k))
        return r


class _ASI_ID(c.Structure):
    _fields_ = [('id', c.c_char * 8)]

    def get_id(self) -> str:
        # return self.id
        v = self.id
        if sys.version_info[0] >= 3 and isinstance(v, bytes):
            v = v.decode()
        return v


class _ASI_SUPPORTED_MODE(c.Structure):
    _fields_ = [('SupportedCameraMode', c.c_int * 16)]

    def get_dict(self) -> Dict[str, Any]:
        base_dict = {k: getattr(self, k) for k, _ in self._fields_}
        base_dict['SupportedCameraMode'] = [int(x) for x in base_dict['SupportedCameraMode']]
        return base_dict


def _init():
    global asi

    if asi is not None:
        return

    system = platform.system()
    arch = platform.machine()
    library = Path(__file__).parent / 'native'
    if system == 'Linux':
        filename = 'libASICamera2.so'
        if arch in ['x86_64', 'AMD64']:
            library = library / 'linux' / 'x64' / filename
        elif arch == 'aarch64':
            library = library / 'linux' / 'armv8' / filename
        else:
            raise RuntimeError(f'Unsupported arch {arch}')
    elif system == 'Windows':
        filename = 'ASICamera2.dll'
        if arch in ['x86_64', 'AMD64']:
            library = library / 'windows' / 'x64' / filename
        else:
            raise RuntimeError(f'Unsupported arch {arch}')
    else:
        raise RuntimeError(f'Unsupported system {system}')

    if not library.exists():
        raise RuntimeError('ASI SDK dynamic library not found')

    if system == 'Linux':
        asi = c.CDLL(str(library), mode=ctypes.RTLD_GLOBAL)
    else:
        asi = c.WinDLL(str(library))

    if asi is None:
        raise RuntimeError('ASI SDK dynamic library not found')

    asi.ASIGetNumOfConnectedCameras.argtypes = []
    asi.ASIGetNumOfConnectedCameras.restype = c.c_int

    asi.ASIGetCameraProperty.argtypes = [c.POINTER(_ASI_CAMERA_INFO), c.c_int]
    asi.ASIGetCameraProperty.restype = c.c_int

    asi.ASIOpenCamera.argtypes = [c.c_int]
    asi.ASIOpenCamera.restype = c.c_int

    asi.ASIInitCamera.argtypes = [c.c_int]
    asi.ASIInitCamera.restype = c.c_int

    asi.ASICloseCamera.argtypes = [c.c_int]
    asi.ASICloseCamera.restype = c.c_int

    asi.ASIGetNumOfControls.argtypes = [c.c_int, c.POINTER(c.c_int)]
    asi.ASIGetNumOfControls.restype = c.c_int

    asi.ASIGetControlCaps.argtypes = [c.c_int, c.c_int,
                                      c.POINTER(_ASI_CONTROL_CAPS)]
    asi.ASIGetControlCaps.restype = c.c_int

    asi.ASIGetControlValue.argtypes = [c.c_int,
                                       c.c_int,
                                       c.POINTER(c.c_long),
                                       c.POINTER(c.c_int)]
    asi.ASIGetControlValue.restype = c.c_int

    asi.ASISetControlValue.argtypes = [c.c_int, c.c_int, c.c_long, c.c_int]
    asi.ASISetControlValue.restype = c.c_int

    asi.ASIGetROIFormat.argtypes = [c.c_int,
                                    c.POINTER(c.c_int),
                                    c.POINTER(c.c_int),
                                    c.POINTER(c.c_int),
                                    c.POINTER(c.c_int)]
    asi.ASIGetROIFormat.restype = c.c_int

    asi.ASISetROIFormat.argtypes = [c.c_int, c.c_int, c.c_int, c.c_int, c.c_int]
    asi.ASISetROIFormat.restype = c.c_int

    asi.ASIGetStartPos.argtypes = [c.c_int,
                                   c.POINTER(c.c_int),
                                   c.POINTER(c.c_int)]
    asi.ASIGetStartPos.restype = c.c_int

    asi.ASISetStartPos.argtypes = [c.c_int, c.c_int, c.c_int]
    asi.ASISetStartPos.restype = c.c_int

    asi.ASIGetDroppedFrames.argtypes = [c.c_int, c.POINTER(c.c_int)]
    asi.ASIGetDroppedFrames.restype = c.c_int

    asi.ASIEnableDarkSubtract.argtypes = [c.c_int, c.POINTER(c.c_char)]
    asi.ASIEnableDarkSubtract.restype = c.c_int

    asi.ASIDisableDarkSubtract.argtypes = [c.c_int]
    asi.ASIDisableDarkSubtract.restype = c.c_int

    asi.ASIStartVideoCapture.argtypes = [c.c_int]
    asi.ASIStartVideoCapture.restype = c.c_int

    asi.ASIStopVideoCapture.argtypes = [c.c_int]
    asi.ASIStopVideoCapture.restype = c.c_int

    asi.ASIGetVideoData.argtypes = [c.c_int,
                                    c.POINTER(c.c_char),
                                    c.c_long,
                                    c.c_int]
    asi.ASIGetVideoData.restype = c.c_int

    asi.ASIPulseGuideOn.argtypes = [c.c_int, c.c_int]
    asi.ASIPulseGuideOn.restype = c.c_int

    asi.ASIPulseGuideOff.argtypes = [c.c_int, c.c_int]
    asi.ASIPulseGuideOff.restype = c.c_int

    asi.ASIStartExposure.argtypes = [c.c_int, c.c_int]
    asi.ASIStartExposure.restype = c.c_int

    asi.ASIStopExposure.argtypes = [c.c_int]
    asi.ASIStopExposure.restype = c.c_int

    asi.ASIGetExpStatus.argtypes = [c.c_int, c.POINTER(c.c_int)]
    asi.ASIGetExpStatus.restype = c.c_int

    asi.ASIGetDataAfterExp.argtypes = [c.c_int, c.POINTER(c.c_char), c.c_long]
    asi.ASIGetDataAfterExp.restype = c.c_int

    asi.ASIGetID.argtypes = [c.c_int, c.POINTER(_ASI_ID)]
    asi.ASIGetID.restype = c.c_int

    asi.ASISetID.argtypes = [c.c_int, _ASI_ID]
    asi.ASISetID.restype = c.c_int

    asi.ASIGetGainOffset.argtypes = [c.c_int,
                                     c.POINTER(c.c_int),
                                     c.POINTER(c.c_int),
                                     c.POINTER(c.c_int),
                                     c.POINTER(c.c_int)]
    asi.ASIGetGainOffset.restype = c.c_int

    asi.ASISetCameraMode.argtypes = [c.c_int, c.c_int]
    asi.ASISetCameraMode.restype = c.c_int

    asi.ASIGetCameraMode.argtypes = [c.c_int, c.POINTER(c.c_int)]
    asi.ASIGetCameraMode.restype = c.c_int

    asi.ASIGetCameraSupportMode.argtypes = [c.c_int, c.POINTER(_ASI_SUPPORTED_MODE)]
    asi.ASIGetCameraSupportMode.restype = c.c_int

    asi.ASISendSoftTrigger.argtypes = [c.c_int, c.c_int]
    asi.ASISendSoftTrigger.restype = c.c_int

    asi.ASISetTriggerOutputIOConf.argtypes = [c.c_int,
                                              c.c_int,
                                              c.c_int,
                                              c.c_long,
                                              c.c_long]
    asi.ASISetTriggerOutputIOConf.restype = c.c_int

    asi.ASIGetTriggerOutputIOConf.argtypes = [c.c_int,
                                              c.c_int,
                                              c.POINTER(c.c_int),
                                              c.POINTER(c.c_long),
                                              c.POINTER(c.c_long)]
    asi.ASIGetTriggerOutputIOConf.restype = c.c_int


_init()
