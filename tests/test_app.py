import unittest
import tempfile
from pathlib import Path
from app import app
from algorithms.support.common import validate_options

class AppTests(unittest.TestCase):
    def setUp(self):self.client=app.test_client()
    def test_home_and_local_assets(self):
        self.assertEqual(self.client.get('/').status_code,200)
        response=self.client.get('/static/app.js');self.assertEqual(response.status_code,200);response.close()
    def test_all_copied_bags_visible(self):
        response=self.client.get('/api/bags');self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.get_json()),2)
    def test_path_traversal_rejected(self):
        self.assertEqual(self.client.get('/api/bag-info?name=../rig_20260828_192028_0.bag').status_code,400)
        self.assertEqual(self.client.get('/api/runs/..%2Foutside/result').status_code,400)
    def test_invalid_job_returns_actionable_error(self):
        response=self.client.post('/api/jobs',json={'bag':'missing.bag'})
        self.assertEqual(response.status_code,400);self.assertIn('error',response.get_json())
    def test_topic_types_and_crop_are_validated(self):
        meta={'topics':[{'name':'/camera','type':'sensor_msgs/Image'},{'name':'/lidar','type':'sensor_msgs/PointCloud2'}]}
        valid={'camera_topic':'/camera','livox_topic':'/lidar'}
        self.assertEqual(validate_options(meta,valid)['livox_topic'],'/lidar')
        with self.assertRaises(ValueError):validate_options(meta,{**valid,'camera_topic':'/lidar'})
        with self.assertRaises(ValueError):validate_options(meta,{**valid,'camera_roi':[0,0,10,10]})
    def test_duplicate_capture_not_independent(self):
        completed=[row for row in self.client.get('/api/runs').get_json() if row['status']=='complete' and row['kind']=='detection']
        if completed:
            response=self.client.post('/api/compare',json={'runs':[completed[0]['id']]*4})
            self.assertEqual(response.status_code,400)
    def test_device_folders_and_legacy_bag_lookup(self):
        devices=self.client.get('/api/datasets').get_json()
        self.assertEqual([d['id'] for d in devices],[f'device_{i}' for i in range(1,6)])
        self.assertEqual(devices[0]['bags'],2)
        from algorithms.support.common import bag_path
        self.assertEqual(bag_path('rig_20260828_192028_0.bag').parent.name,'device_1')
        self.assertEqual(len(self.client.get('/api/bags?dataset=device_1').get_json()),2)
        self.assertEqual(self.client.get('/api/bags?dataset=device_2').get_json(),[])
    def test_empty_and_invalid_device_not_queued(self):
        self.assertEqual(self.client.post('/api/batches',json={'dataset':'device_2'}).status_code,400)
        self.assertEqual(self.client.post('/api/batches',json={'dataset':'../device_1'}).status_code,400)
        self.assertEqual(self.client.get('/api/bags?dataset=../device_1').status_code,400)
    def test_invalid_folder_configuration_not_queued(self):
        self.assertEqual(self.client.post('/api/batches',json={'dataset':'device_1','auto_topics':'false'}).status_code,400)
        self.assertEqual(self.client.post('/api/batches',json={'dataset':'device_1','config':{'camera_roi':[0,0,2,2]}}).status_code,400)
    def test_valid_import_uses_selected_device_and_generic_filename(self):
        import rosbag
        import rospy
        from sensor_msgs.msg import Image,PointCloud2
        from algorithms.support.common import BAGS
        destination=BAGS/'device_5'/'verification.bag'
        if destination.exists():self.skipTest('Verification filename already exists in Device 5.')
        try:
            with tempfile.TemporaryDirectory() as tmp:
                source=Path(tmp)/'verification.bag'
                with rosbag.Bag(str(source),'w') as bag:
                    bag.write('/camera/image_raw',Image(height=3,width=3,encoding='mono8',step=3,data=bytes(range(9))),rospy.Time(1))
                    bag.write('/livox/lidar',PointCloud2(),rospy.Time(2))
                with source.open('rb') as stream:
                    response=self.client.post('/api/upload',data={'file':(stream,'verification.bag'),'dataset':'device_5'})
                self.assertEqual(response.status_code,200,response.get_json())
                self.assertEqual(response.get_json()['name'],'device_5/verification.bag')
                meta=self.client.get('/api/bag-info?name=device_5/verification.bag').get_json()
                self.assertEqual(meta['suggested_camera_topic'],'/camera/image_raw')
                self.assertEqual(meta['suggested_livox_topic'],'/livox/lidar')
                self.assertEqual(meta['suggested_phase_group'],'normal')
        finally:
            if destination.exists():destination.unlink()

if __name__=='__main__':unittest.main()
