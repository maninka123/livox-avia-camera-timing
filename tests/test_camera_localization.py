import unittest
import tempfile
from pathlib import Path
import numpy as np
from camera_localization import detect
from common import validate_options


def scene(wheels, brightness=False):
    rng = np.random.RandomState(9)
    time = np.cumsum(rng.uniform(.15, .25, 128))
    yy, xx = np.indices((260, 420))
    frames = []
    for i, t in enumerate(time):
        image = np.full(xx.shape, 70., dtype=float)
        for cx, cy, a, b, rpm in wheels:
            u, v = (xx-cx)/a, (yy-cy)/b
            radius = np.hypot(u, v)
            phase = np.arctan2(v, u)-t*rpm*2*np.pi/60
            rotor = (radius < 1) & (radius > .22) & (np.cos(3*phase) > .3)
            image[rotor] = 210+10*np.cos(phase[rotor])
        if brightness:
            image += 15*np.sin(i*.7)
        frames.append(np.clip(image, 0, 255).astype('u1'))
    return np.asarray(frames), time


class CameraLocalizationTests(unittest.TestCase):
    def test_short_camera_topic_in_long_bag_is_sampled_over_its_own_sequence(self):
        try:
            import rosbag
            import rospy
            from sensor_msgs.msg import Image
            from std_msgs.msg import String
        except ImportError:
            self.skipTest('ROS is needed for indexed bag sampling')
        from camera_localization import sample_frames
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'short_camera.bag'
            with rosbag.Bag(str(path), 'w') as bag:
                for index in range(200):
                    image = Image(height=64, width=64, encoding='mono8', step=64, data=bytes([index % 256])*4096)
                    bag.write('/camera', image, rospy.Time.from_sec(index*.05))
                bag.write('/other', String(data='Longer sensor recording'), rospy.Time.from_sec(100))
            frames, stamps, size = sample_frames(path, '/camera')
            self.assertGreaterEqual(len(frames), 100)
            self.assertEqual(size, (64, 64))
            self.assertGreater(stamps[-1], 9)
            self.assertTrue(np.all(np.diff(stamps) > 0))

    def test_off_center_wheel_and_clipped_reflection_with_brightness_changes(self):
        frames, time = scene([(78, 167, 30, 25, -10), (255, 0, 45, 45, -10)], True)
        selected, _, _ = detect(frames, time)
        np.testing.assert_allclose(selected['center_px'], [78, 167], atol=2)
        self.assertAlmostEqual(abs(selected['discovery_rpm']), 10, places=1)
        self.assertGreaterEqual(len(selected['supported_harmonics']), 2)
        x, y, w, h = selected['roi']
        self.assertTrue(x < 48 and x+w > 108 and y < 142 and y+h > 192)

    def test_two_equally_plausible_wheels_require_target_selection(self):
        frames, time = scene([(100, 130, 30, 30, 10), (315, 130, 30, 30, -10)])
        with self.assertRaisesRegex(ValueError, 'Multiple camera wheels'):
            detect(frames, time)

    def test_static_target_with_global_brightness_changes_is_not_rotation(self):
        frames, time = scene([(210, 130, 30, 30, 0)], True)
        with self.assertRaisesRegex(ValueError, 'No clear moving camera target'):
            detect(frames, time)

    def test_automatic_default_and_explicit_manual_override(self):
        meta = {'topics': [{'name': '/camera', 'type': 'sensor_msgs/Image'},
                           {'name': '/lidar', 'type': 'sensor_msgs/PointCloud2'}]}
        options = {'camera_topic': '/camera', 'livox_topic': '/lidar'}
        self.assertIsNone(validate_options(meta, options)['camera_roi'])
        self.assertEqual(validate_options(meta, dict(options, camera_roi=[10, 20, 90, 90]))['camera_roi'], [10, 20, 90, 90])
        with self.assertRaises(ValueError):
            validate_options(meta, dict(options, camera_roi=[0, 0, 20, 20]))


if __name__ == '__main__':
    unittest.main()
