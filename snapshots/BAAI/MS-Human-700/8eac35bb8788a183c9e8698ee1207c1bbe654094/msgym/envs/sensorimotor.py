"""Common sensory observation contract for the two release environments.

Images: channel-first uint8 RGB. Sensors: MuJoCo sensor declaration order,
SI units in the sensor site frame (accelerometer includes specific force).
Reference contains task conditions, separately from measured proprioception.
Full-body sensors cover feet and head IMU; manipulation covers right hand and
head IMU. Sensor channels depend on the model variant.
"""
import mujoco
import numpy as np
from gymnasium import spaces


class SensorimotorObservations:
    def _init_senses(self, eye_camera_size=64, vision_render_interval=5, vision_enabled=True):
        if eye_camera_size < 16 or vision_render_interval < 1:
            raise ValueError("Invalid camera size or image update interval")
        self.eye_camera_size = int(eye_camera_size)
        self.vision_render_interval = int(vision_render_interval)
        self.vision_enabled = bool(vision_enabled)
        self._eye_renderer = None
        self._image_cache = None
        self._image_time = None
        self.sensor_slices = {}
        for i in range(self.model.nsensor):
            start = int(self.model.sensor_adr[i])
            self.sensor_slices[self.model.sensor(i).name] = slice(start, start + int(self.model.sensor_dim[i]))

    def _sensory_space(self, proprio_size, reference_size):
        size = self.eye_camera_size
        observations = {
            "proprio": spaces.Box(-np.inf, np.inf, (proprio_size,), dtype=np.float32),
            "sensors": spaces.Box(-np.inf, np.inf, (self.model.nsensordata,), dtype=np.float32),
            "reference": spaces.Box(-np.inf, np.inf, (reference_size,), dtype=np.float32),
        }
        if self.vision_enabled:
            observations.update({
                "left_eye": spaces.Box(0, 255, (3, size, size), dtype=np.uint8),
                "right_eye": spaces.Box(0, 255, (3, size, size), dtype=np.uint8),
            })
        return spaces.Dict(observations)

    def _sensory_obs(self, proprio, reference):
        observations = {
            "proprio": np.asarray(proprio, dtype=np.float32),
            "sensors": self.data.sensordata.astype(np.float32, copy=True),
            "reference": np.asarray(reference, dtype=np.float32),
        }
        if not self.vision_enabled:
            return observations
        refresh = self.vision_render_interval * self.dt
        if self._image_cache is None or self.data.time - self._image_time >= refresh - 1e-9:
            if self._eye_renderer is None:
                # Allocate the eye framebuffer at its output size, not the model's 4K video size.
                visual = self.model.vis.global_
                width, height = visual.offwidth, visual.offheight
                try:
                    visual.offwidth = visual.offheight = self.eye_camera_size
                    self._eye_renderer = mujoco.Renderer(self.model, height=self.eye_camera_size, width=self.eye_camera_size)
                finally:
                    visual.offwidth, visual.offheight = width, height
            option = mujoco.MjvOption()
            option.sitegroup[:] = 0
            option.geomgroup[3] = 0
            self._image_cache = {}
            for key, camera in (("left_eye", "eye_left"), ("right_eye", "eye_right")):
                self._eye_renderer.update_scene(self.data, camera=camera, scene_option=option)
                self._image_cache[key] = self._eye_renderer.render().transpose(2, 0, 1).copy()
            self._image_time = float(self.data.time)
        return {**observations, **{k: v.copy() for k, v in self._image_cache.items()}}

    def close(self):
        if getattr(self, "_eye_renderer", None) is not None:
            self._eye_renderer.close()
            self._eye_renderer = None
        super().close()
