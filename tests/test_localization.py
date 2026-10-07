import copy
import unittest
import numpy as np
from calibration import validate,project
from localization import maps,select,transform,target_mask
from timing import fit_multi


class LocalizationTests(unittest.TestCase):
    def calibration(self):
        return {'camera_model':'fisheye','translation_units':'metres','image_size_wh':[640,480],
                'K':[[300,0,320],[0,300,240],[0,0,1]],'D':[0,0,0,0],
                'T_lidar_to_camera':np.eye(4).tolist()}

    def test_fisheye_model_and_points_behind_camera(self):
        c=self.calibration();validate(c)
        uv,front=project([[0,0,2],[2,0,2],[0,0,-2]],c,[640,480])
        np.testing.assert_allclose(uv[0],[320,240]);self.assertAlmostEqual(uv[1,0],320+300*np.pi/4)
        self.assertFalse(front[2]);self.assertTrue(np.isnan(uv[2]).all())
        with self.assertRaisesRegex(ValueError,'Image size'):project([[0,0,2]],c,[320,240])

    def test_skew_is_applied_in_both_supported_camera_models(self):
        for model in ('fisheye','pinhole'):
            c=self.calibration();c['camera_model']=model
            baseline,_=project([[.3,.6,2]],c)
            c['K'][0][1]=21;validate(c)
            pixels,_=project([[.3,.6,2]],c)
            self.assertAlmostEqual(pixels[0,0],baseline[0,0]+21*(baseline[0,1]-240)/300)
            self.assertEqual(pixels[0,1],baseline[0,1])

    def test_matrix_direction_units_and_camera_model_are_validated(self):
        for field,value in [('K',[[0,0,0],[0,0,0],[0,0,1]]),('D',[0,0]),('translation_units','mm'),('camera_model','unknown')]:
            c=self.calibration();c[field]=value
            with self.assertRaises(ValueError):validate(c)
        c=self.calibration();c['T_lidar_to_camera'][0][0]=2
        with self.assertRaisesRegex(ValueError,'rigid'):validate(c)
        c=self.calibration();c['T_camera_to_lidar']=np.eye(4).tolist();c['T_camera_to_lidar'][0][3]=1
        with self.assertRaisesRegex(ValueError,'inverse'):validate(c)
        for reverse in ({'invalid':'matrix'}, None, [[1,0],[0,1]]):
            c=self.calibration();c['T_camera_to_lidar']=reverse
            with self.assertRaisesRegex(ValueError,'reverse transform'):validate(c)

    @staticmethod
    def scene(moving=True,centers=((.16,-.19),),rpm=-9):
        rng=np.random.RandomState(73);points=[];offsets=[0];time=np.linspace(0,32,64)
        for t in time:
            uv=rng.uniform(-.5,.5,(19000,2));depth=np.full(len(uv),6.)
            for center in centers:
                rel=uv-center;radius=np.linalg.norm(rel,axis=1);phi=np.arctan2(rel[:,1],rel[:,0])-t*rpm*2*np.pi/60
                opening=np.abs((phi+np.pi)%(2*np.pi)-np.pi)<np.pi/5
                disk=(radius<.095)&~((radius>.023)&opening)
                if moving:depth[disk]=3.4+rng.normal(0,.004,disk.sum())
                else:depth[radius<.095]=3.4
            xyz=np.column_stack([depth,uv*depth[:,None]])
            points.append(xyz);offsets.append(offsets[-1]+len(xyz))
        return np.concatenate(points),np.asarray(offsets),time

    def test_off_axis_wheel_and_different_distance_without_calibration(self):
        xyz,offsets,time=self.scene()
        evidence=maps(xyz,offsets)
        geometry,_=select(evidence,xyz,offsets,time)
        np.testing.assert_allclose(geometry['center_uv'],[.16,-.19],atol=.016)
        self.assertAlmostEqual(geometry['foreground_depth_m'],3.4,delta=.03)
        self.assertAlmostEqual(geometry['discovery_rpm'],-9,delta=.12)
        measured=transform(xyz,geometry)
        np.testing.assert_array_equal(measured[:,2],xyz[:,0].astype('f4'))
        self.assertGreater(target_mask(measured,geometry).sum(),1000)

    def test_static_scene_with_changing_scan_density_is_not_a_rotor(self):
        xyz,offsets,time=self.scene(moving=False)
        with self.assertRaisesRegex(ValueError,'No compact'):
            select(maps(xyz,offsets),xyz,offsets,time)

    def test_two_rotating_regions_are_ambiguous(self):
        xyz,offsets,time=self.scene(centers=((-0.2,-.15),(.2,.16)))
        with self.assertRaisesRegex(ValueError,'Multiple rotating'):
            select(maps(xyz,offsets),xyz,offsets,time)

    def test_new_and_reference_phase_conventions_cannot_mix(self):
        observations=[{'group':'same','omega_deg_s':w,'phase_delta_mod120_deg':20+w*.1} for w in [-90,-60,-30,30,60,90]]
        observations[-1].update(phase_period_deg=360,phase_convention='target_centred_h1_v1')
        with self.assertRaisesRegex(ValueError,'conventions'):fit_multi(observations)

    def test_full_circle_phase_timing_model(self):
        observations=[{'group':'same','omega_deg_s':w,'phase_delta_deg':170+w*.075,
                       'phase_period_deg':360,'phase_convention':'target_centred_h1_v1'} for w in [-90,-60,-30,30,60,90]]
        result,_=fit_multi(observations);self.assertAlmostEqual(result['candidate_tau_ms'],75,places=5)


if __name__=='__main__':unittest.main()
