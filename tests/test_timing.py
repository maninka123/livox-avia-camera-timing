import unittest
import numpy as np
from timing import lag_profile,fit_multi,clock_metrics

class TimingTests(unittest.TestCase):
    def test_constant_rotation_cannot_identify_lag(self):
        camera_t=np.arange(0,20,.025);camera_a=30*camera_t+17
        lidar_t=np.arange(1,19,.1);lidar_a=30*(lidar_t+.080)+50
        result,_=lag_profile(camera_t,camera_a,lidar_t,lidar_a,.2,500)
        self.assertEqual(result['status'],'NOT_IDENTIFIABLE_FROM_THIS_BAG')
        self.assertFalse(result['physical_offset_calibrated'])

    def test_excited_motion_recovers_known_lag_and_sign(self):
        camera_t=np.arange(0,25,.01);camera_a=35*camera_t+8*np.sin(camera_t*1.8)
        lidar_t=np.arange(1,24,.1);lidar_a=np.interp(lidar_t+.120,camera_t,camera_a)+37
        result,_=lag_profile(camera_t,camera_a,lidar_t,lidar_a,.05,500)
        self.assertAlmostEqual(result['candidate_tau_ms'],120,delta=2)
        self.assertEqual(result['status'],'NON_CONSTANT_MOTION_CANDIDATE')

    def test_cross_speed_separates_phase_and_known_delay(self):
        observations=[]
        for group,beta in (('normal',20),('red',-12)):
            for omega in (-90,-60,-30,30,60,90):
                phase=beta+omega*.075
                observations.append({'group':group,'omega_deg_s':omega,'phase_delta_mod120_deg':(phase+60)%120-60})
        result,_=fit_multi(observations)
        self.assertAlmostEqual(result['candidate_tau_ms'],75,places=5)
        self.assertEqual(result['bags'],12)

    def test_same_speed_rejected(self):
        with self.assertRaisesRegex(ValueError,'not identifiable'):
            fit_multi([{'group':'same','omega_deg_s':60,'phase_delta_mod120_deg':10} for _ in range(5)])

    def test_two_speeds_with_multiple_phase_wrap_solutions_are_unresolved(self):
        observations=[{'group':'rig','omega_deg_s':omega,'phase_delta_mod120_deg':20+omega*.12} for omega in (-90,90,-90,90)]
        with self.assertRaisesRegex(ValueError,'Multiple phase-wrap branches'):fit_multi(observations)

    def test_offset_beyond_supported_cross_speed_search_is_unresolved(self):
        observations=[{'group':'rig','omega_deg_s':omega,'phase_delta_mod120_deg':(20+omega*1.3+60)%120-60} for omega in (-90,-60,-30,30,60,90)]
        with self.assertRaisesRegex(ValueError,'search'):fit_multi(observations)

    def test_device_uptime_is_not_subtracted_from_unix(self):
        record=1787909000+np.arange(100)*.1;header=1000+np.arange(100)*.1
        result=clock_metrics(record,header,'Livox')
        self.assertEqual(result['domain'],'device_or_other_epoch')
        self.assertIsNone(result['record_minus_header_mean_ms'])

if __name__=='__main__':unittest.main()
