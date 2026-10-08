import tempfile
import unittest
from pathlib import Path
import numpy as np
from algorithms.support.scan_variability import local_rpm,describe
from algorithms.support.batch_analysis import aggregate
from algorithms.support.common import bag_path,result_path


class ScanTests(unittest.TestCase):
    def test_signed_rpm_with_irregular_sampling_and_rejected_observations(self):
        rng=np.random.RandomState(7);time=np.cumsum(rng.uniform(.08,.12,80));angles=45-time*60
        angles[20:24]=np.nan
        rpm=local_rpm(time,angles)
        np.testing.assert_allclose(rpm[np.isfinite(rpm)],-10,rtol=1e-12,atol=1e-12)
    def test_too_short_interval_has_no_rpm(self):
        self.assertTrue(np.isnan(local_rpm([0,.1,.2],[0,1,2])).all())
    def test_finite_statistics_do_not_invent_measurements(self):
        values=describe([1,np.nan,3,np.inf])
        self.assertEqual(values['n'],2);self.assertEqual(values['mean'],2)
        self.assertEqual(describe([np.nan])['std'],None)
    def test_path_traversal_rejected_for_nested_results_and_bags(self):
        for value in ('device_1/../rig.bag','/tmp/outside.bag','device_1/../../outside.bag'):
            with self.assertRaises(ValueError):bag_path(value)
        for value in ('batch/captures/../other','/tmp/outside','batch/other/child'):
            with self.assertRaises(ValueError):result_path(value)
    def test_all_failed_folder_has_a_report_and_unresolved_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);(output/'figures').mkdir();(output/'timing').mkdir()
            result=aggregate({'id':'verification','dataset':'device_2'},[],[{'bag_path':'device_2/bad.bag','status':'failed','error':'Unreadable ROS bag'}],output)
            self.assertEqual(result['totals']['failed_bags'],1)
            self.assertEqual(result['totals']['completed_bags'],0)
            self.assertEqual(result['overall_timing']['status'],'UNRESOLVED')
            self.assertIsNone(result['overall_timing']['candidate_tau_ms'])
            self.assertTrue((output/'REPORT.md').is_file())


if __name__=='__main__':unittest.main()
