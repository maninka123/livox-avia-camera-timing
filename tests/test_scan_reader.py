import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import scan_reader


class ScanReaderTests(unittest.TestCase):
    def test_each_scan_is_exact_for_both_storage_orders_and_float_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'clouds.npz'
            offsets = np.array([0, 0, 3, 9, 11])
            for dtype in (np.float32, np.float64):
                for order in ('C', 'F'):
                    points = np.array(np.arange(44).reshape(11, 4), dtype=dtype, order=order)
                    np.savez_compressed(path, points=points, stamps=np.arange(4), offsets=offsets,
                                        depth_bounds_m=[3, 5], coordinate_system='target_centred')
                    with patch.object(scan_reader, 'CHUNK_BYTES', 32):
                        for index in range(4):
                            actual, bounds, localized = scan_reader.read_scan(path, index)
                            np.testing.assert_array_equal(actual, points[offsets[index]:offsets[index + 1]])
                            self.assertEqual(bounds, (3., 5.)); self.assertTrue(localized)

    def test_legacy_metadata_and_invalid_indices(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'clouds.npz'
            np.savez_compressed(path, points=np.ones((8, 4), dtype='f4'), stamps=[0, 1], offsets=[0, 4, 8])
            _, bounds, localized = scan_reader.read_scan(path, 1)
            self.assertEqual(bounds, (1.2, 2.7)); self.assertFalse(localized)
            for index in (-1, 2):
                with self.assertRaisesRegex(ValueError, 'outside'):scan_reader.read_scan(path, index)
            np.savez_compressed(path, points=np.ones((8, 4), dtype='f4'), stamps=[0, 1], offsets=[0, 4, 9])
            with self.assertRaisesRegex(ValueError, 'exceed'):scan_reader.read_scan(path, 1)


if __name__ == '__main__':
    unittest.main()
